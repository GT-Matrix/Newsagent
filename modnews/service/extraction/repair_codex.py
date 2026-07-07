from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any

from modnews.service.extraction.repair_store import RepairTask, write_json


def build_codex_command(task: RepairTask) -> list[str]:
    command = ["codex", "exec"]
    if env_bool("MODNEWS_CODEX_IGNORE_USER_CONFIG", False):
        command.append("--ignore-user-config")
    profile = os.environ.get("MODNEWS_CODEX_PROFILE")
    if profile:
        command.extend(["--profile", profile])
    model = os.environ.get("MODNEWS_CODEX_MODEL")
    if model:
        command.extend(["--model", model])
    provider = os.environ.get("MODNEWS_CODEX_PROVIDER")
    if provider:
        command.extend(["--config", f"model_provider={json.dumps(provider)}"])
    for item in shlex.split(os.environ.get("MODNEWS_CODEX_CONFIG", "")):
        command.extend(["--config", item])
    bypass_sandbox = env_bool("MODNEWS_CODEX_BYPASS_SANDBOX", False)
    if bypass_sandbox:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    command.extend(
        [
            "--cd",
            str(task.work_dir),
            "--skip-git-repo-check",
            "--json",
            "--output-last-message",
            str(task.result_path),
            (
                "Read TASK.md. Fix current/extractor.py until it satisfies the contract and tests. "
                "Your final answer must be exactly one JSON object with keys: "
                "status, summary, files_changed, next_steps. "
                "Allowed status values: fixed, failed, needs_review, skipped_unrepairable. "
                "Use status=skipped_unrepairable when the target is blocked by Cloudflare, CAPTCHA, "
                "login wall, rate limit, network policy, or another access issue that code changes cannot fix. "
                "In that case, do not promote a fake parser fix; summarize the blocker clearly."
            ),
        ]
    )
    if not bypass_sandbox:
        command[command.index("--json") : command.index("--json")] = [
            "--sandbox",
            os.environ.get("MODNEWS_CODEX_SANDBOX", "danger-full-access"),
        ]
    return command


def validate_final_result(path: Path) -> str | None:
    if not path.exists():
        return "codex did not write result.json"
    try:
        raw = path.read_text(encoding="utf-8")
        payload = extract_json_object(raw)
    except Exception as exc:
        return f"invalid final result JSON: {exc}"
    status = payload.get("status")
    if status not in {"fixed", "failed", "needs_review", "skipped_unrepairable"}:
        return "final result status is missing or invalid"
    if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
        return "final result summary is missing"
    if not isinstance(payload.get("files_changed"), list):
        return "final result files_changed must be a list"
    write_json(path, payload)
    return None


def extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
