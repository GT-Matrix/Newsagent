from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .metadata import ExtractorMetadata, metadata_comment
from .registry import ExtractorRegistry
from modnews_pipeline.paths import runtime_paths


@dataclass(slots=True)
class RepairTask:
    id: str
    source_id: str
    status: str
    work_dir: Path
    created_at: str
    updated_at: str
    log_path: Path
    result_path: Path
    command: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "status": self.status,
            "work_dir": str(self.work_dir),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "log_path": str(self.log_path),
            "result_path": str(self.result_path),
            "command": self.command,
            "error": self.error,
        }


class RepairManager:
    def __init__(self, project_root: Path, registry: ExtractorRegistry) -> None:
        self.project_root = project_root
        self.registry = registry
        self.tasks_root = runtime_paths(project_root).agent_work_dir / "extractors"
        self._lock = threading.Lock()

    def list_tasks(self) -> list[dict[str, Any]]:
        if not self.tasks_root.exists():
            return []
        rows = []
        for meta_path in sorted(self.tasks_root.glob("*/*/task.json"), reverse=True):
            rows.append(_read_json(meta_path, {}))
        return rows

    def get_task(self, task_id: str) -> dict[str, Any]:
        for task in self.list_tasks():
            if task.get("id") == task_id:
                task["log_tail"] = self.read_log(task_id)
                return task
        raise KeyError(task_id)

    def delete_task(self, task_id: str) -> None:
        task = self._load_task(task_id)
        if task.work_dir.exists():
            shutil.rmtree(task.work_dir)

    def retry_task(self, task_id: str) -> RepairTask:
        task = self._load_task(task_id)
        task.status = "queued"
        task.error = None
        task.updated_at = _now()
        self._save_task(task)
        thread = threading.Thread(target=self.run_task, args=(task_id,), daemon=True)
        thread.start()
        return task

    def read_log(self, task_id: str, max_chars: int = 40000) -> str:
        for task in self.list_tasks():
            if task.get("id") == task_id:
                log_path = Path(str(task.get("log_path") or ""))
                if log_path.exists():
                    text = log_path.read_text(encoding="utf-8", errors="replace")
                    return text[-max_chars:]
        return ""

    def create_task(
        self,
        source_id: str,
        reason: str,
        auto_start: bool = True,
        source_metadata: dict[str, Any] | None = None,
    ) -> RepairTask:
        try:
            record = self.registry.get(source_id)
            current_dir = record.current_dir
            bootstrap = False
        except Exception:
            record = None
            current_dir = None
            bootstrap = True
        task_id = f"{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        work_dir = self.tasks_root / source_id / task_id
        work_dir.mkdir(parents=True, exist_ok=True)
        if current_dir:
            shutil.copytree(current_dir, work_dir / "current", dirs_exist_ok=True)
        else:
            self._write_bootstrap_extractor(work_dir / "current", source_id, source_metadata or {})
        (work_dir / "fixtures").mkdir(exist_ok=True)
        (work_dir / "schema").mkdir(exist_ok=True)
        result_path = work_dir / "result.json"
        log_path = work_dir / "codex.jsonl"
        self._write_contract_schema(work_dir / "schema" / "extractor_result.schema.json")
        self._write_final_schema(work_dir / "schema" / "final_message.schema.json")
        self._write_task_md(work_dir / "TASK.md", source_id, reason, source_metadata or {}, bootstrap=bootstrap)
        now = _now()
        task = RepairTask(
            id=task_id,
            source_id=source_id,
            status="queued",
            work_dir=work_dir,
            created_at=now,
            updated_at=now,
            log_path=log_path,
            result_path=result_path,
        )
        self._save_task(task)
        if auto_start:
            thread = threading.Thread(target=self.run_task, args=(task_id,), daemon=True)
            thread.start()
        return task

    def run_task(self, task_id: str) -> None:
        task = self._load_task(task_id)
        command = self._build_codex_command(task)
        task.status = "running"
        task.updated_at = _now()
        task.command = command
        self._save_task(task)
        try:
            with task.log_path.open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    command,
                    cwd=task.work_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    timeout=1800,
                    check=False,
            )
            if process.returncode == 0:
                result_error = self._validate_final_result(task.result_path)
                task.status = "failed" if result_error else "succeeded"
                task.error = result_error
            else:
                task.status = "failed"
                task.error = f"codex exited with code {process.returncode}"
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
        finally:
            task.updated_at = _now()
            self._save_task(task)

    def _build_codex_command(self, task: RepairTask) -> list[str]:
        command = ["codex", "exec"]
        if _env_bool("MODNEWS_CODEX_IGNORE_USER_CONFIG", False):
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
        bypass_sandbox = _env_bool("MODNEWS_CODEX_BYPASS_SANDBOX", False)
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
                    "Allowed status values: fixed, failed, needs_review, skipped_unrepairable."
                ),
            ]
        )
        if not bypass_sandbox:
            command[command.index("--json") : command.index("--json")] = [
                "--sandbox",
                os.environ.get("MODNEWS_CODEX_SANDBOX", "danger-full-access"),
            ]
        return command

    def _validate_final_result(self, path: Path) -> str | None:
        if not path.exists():
            return "codex did not write result.json"
        try:
            raw = path.read_text(encoding="utf-8")
            payload = _extract_json_object(raw)
        except Exception as exc:
            return f"invalid final result JSON: {exc}"
        status = payload.get("status")
        if status not in {"fixed", "failed", "needs_review", "skipped_unrepairable"}:
            return "final result status is missing or invalid"
        if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
            return "final result summary is missing"
        if not isinstance(payload.get("files_changed"), list):
            return "final result files_changed must be a list"
        _write_json(path, payload)
        return None

    def _load_task(self, task_id: str) -> RepairTask:
        for raw in self.list_tasks():
            if raw.get("id") == task_id:
                return RepairTask(
                    id=str(raw["id"]),
                    source_id=str(raw["source_id"]),
                    status=str(raw["status"]),
                    work_dir=Path(raw["work_dir"]),
                    created_at=str(raw["created_at"]),
                    updated_at=str(raw["updated_at"]),
                    log_path=Path(raw["log_path"]),
                    result_path=Path(raw["result_path"]),
                    command=[str(item) for item in raw.get("command", [])],
                    error=raw.get("error"),
                )
        raise KeyError(task_id)

    def _save_task(self, task: RepairTask) -> None:
        with self._lock:
            _write_json(task.work_dir / "task.json", task.to_dict())

    def _write_bootstrap_extractor(self, current_dir: Path, source_id: str, source_metadata: dict[str, Any]) -> None:
        current_dir.mkdir(parents=True, exist_ok=True)
        now = _now()
        url = _optional_str(source_metadata.get("url"))
        content_type = str(source_metadata.get("content_type") or "news")
        meta = ExtractorMetadata(
            id=source_id,
            name=str(source_metadata.get("name") or source_id),
            kind=content_type,
            version="0.0.0",
            status="enabled",
            target_url=url,
            tags=[str(item) for item in source_metadata.get("tags", []) if item not in (None, "")],
            created_at=now,
            updated_at=now,
            notes="Bootstrap extractor generated for Codex repair task.",
        )
        (current_dir / "extractor.py").write_text(
            f"""{metadata_comment(meta)}
from __future__ import annotations


def run(payload: dict) -> dict:
    return {{
        "ok": False,
        "status": "parse_error",
        "items": [],
        "diagnostics": {{
            "message": "Bootstrap extractor. Implement site-specific extraction.",
            "target_url": payload.get("url"),
        }},
        "extractor_version": "0.0.0",
    }}


if __name__ == "__main__":
    import json
    from datetime import datetime

    sample = {{
        "source_id": "{source_id}",
        "url": "{url or ''}",
        "scrape_date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "limit": 10,
        "options": {{}},
    }}
    print(json.dumps(run(sample), ensure_ascii=False, indent=2))
""",
            encoding="utf-8",
        )
        _write_json(
            current_dir / "manifest.json",
            {
                "id": source_id,
                "status": "enabled",
                "created_at": now,
                "updated_at": now,
                "bootstrap": True,
            },
        )

    def _write_task_md(
        self,
        path: Path,
        source_id: str,
        reason: str,
        source_metadata: dict[str, Any],
        *,
        bootstrap: bool,
    ) -> None:
        metadata_block = json.dumps(source_metadata, ensure_ascii=False, indent=2) if source_metadata else "{}"
        path.write_text(
            f"""# Extractor Repair Task

Source: `{source_id}`
Reason: {reason}
Bootstrap task: {str(bootstrap).lower()}

Source metadata:
```json
{metadata_block}
```

Work only inside this task directory. The active extractor candidate is `current/extractor.py`.

Required contract:
- The module must expose `run(payload: dict) -> dict`.
- The returned dict must match `schema/extractor_result.schema.json`.
- `ok: true` requires at least one item.
- Each item needs `platform`, `title`, `url`, and `scrape_date`.
- Use `status: "blocked"` and final status `skipped_unrepairable` when the failure is Cloudflare, CAPTCHA, login, rate limiting, or network blocking rather than parser breakage.
- If live requests are blocked by access policy, stop after documenting the blocker. Do not keep changing selectors just to satisfy live validation.

Useful commands:
```bash
python current/extractor.py
python -m py_compile current/extractor.py
```

Do not write secrets. Do not edit files outside this work directory.
""",
            encoding="utf-8",
        )

    def _write_contract_schema(self, path: Path) -> None:
        _write_json(
            path,
            {
                "type": "object",
                "required": ["ok", "items", "diagnostics", "extractor_version"],
                "properties": {
                    "ok": {"type": "boolean"},
                    "extractor_version": {"type": "string"},
                    "diagnostics": {"type": "object"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["platform", "title", "url", "scrape_date"],
                        },
                    },
                },
            },
        )

    def _write_final_schema(self, path: Path) -> None:
        _write_json(
            path,
            {
                "type": "object",
                "required": ["status", "summary", "files_changed"],
                "properties": {
                    "status": {"type": "string", "enum": ["fixed", "failed", "needs_review", "skipped_unrepairable"]},
                    "summary": {"type": "string"},
                    "files_changed": {"type": "array", "items": {"type": "string"}},
                    "next_steps": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        )


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_json_object(raw: str) -> dict[str, Any]:
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


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
