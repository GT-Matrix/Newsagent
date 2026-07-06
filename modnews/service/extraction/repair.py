from __future__ import annotations

import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.service.extraction.metadata import replace_metadata_comment
from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_store import RepairTask, RepairTaskStore, read_json, write_json
from modnews.service.extraction.repair_support import (
    build_codex_command,
    infer_name_from_task,
    infer_url_from_task,
    now,
    validate_final_result,
    write_bootstrap_extractor,
    write_contract_schema,
    write_final_schema,
    write_task_md,
)


class RepairManager:
    def __init__(self, project_root: Path, registry: ExtractorRegistry) -> None:
        self.project_root = project_root
        self.registry = registry
        self.tasks_root = runtime_paths(project_root).agent_work_dir / "extractors"
        self._lock = threading.Lock()
        self.store = RepairTaskStore(self.tasks_root)

    def list_tasks(self) -> list[dict[str, Any]]:
        return self.store.list_tasks()

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self._load_task(task_id).to_dict()
        task["log_tail"] = self.read_log(task_id)
        return task

    def delete_task(self, task_id: str) -> None:
        self.store.delete_task(task_id)

    def promote_task(self, task_id: str) -> RepairTask:
        task = self._load_task(task_id)
        result = read_json(task.result_path, {})
        if task.status != "succeeded" or result.get("status") not in {"fixed", "needs_review"}:
            raise RuntimeError("only succeeded fixed/needs_review tasks can be promoted")

        current_dir = task.work_dir / "current"
        extractor_path = current_dir / "extractor.py"
        manifest_path = current_dir / "manifest.json"
        if not extractor_path.exists():
            raise RuntimeError("task has no current/extractor.py")

        target_dir = self.registry.root / task.source_id / "current"
        if target_dir.exists():
            version_dir = self.registry.root / task.source_id / "versions" / datetime.now().strftime("%Y%m%d%H%M%S")
            version_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target_dir, version_dir)
            shutil.rmtree(target_dir)
        shutil.copytree(current_dir, target_dir)

        try:
            record = self.registry.get(task.source_id)
            record.metadata.version = result.get("version") or record.metadata.version
            record.metadata.status = "enabled"
            record.metadata.updated_at = now()
            if not record.metadata.target_url:
                inferred_url = _infer_target_url(extractor_path) or infer_url_from_task(task.work_dir / "TASK.md")
                record.metadata.target_url = inferred_url
            if record.metadata.name == task.source_id:
                record.metadata.name = infer_name_from_task(task.work_dir / "TASK.md") or record.metadata.name
            replace_metadata_comment(record.extractor_path, record.metadata)
            manifest = read_json(manifest_path, {})
            manifest.update(
                {
                    "id": task.source_id,
                    "status": "enabled",
                    "updated_at": record.metadata.updated_at,
                    "promoted_from_task": task.id,
                }
            )
            write_json(record.manifest_path, manifest)

            from modnews.repository.source_config import source_config_store

            source_config_store(self.project_root).update_site_list_item(
                task.source_id,
                {
                    "enabled": True,
                    "name": record.metadata.name or task.source_id,
                    "url": record.metadata.target_url,
                    "content_type": record.metadata.kind or "news",
                    "extractor_id": task.source_id,
                    "tags": record.metadata.tags,
                },
            )
        except Exception:
            pass

        task.updated_at = now()
        self._save_task(task)
        return task

    def retry_task(self, task_id: str) -> RepairTask:
        task = self._load_task(task_id)
        task.status = "queued"
        task.error = None
        task.updated_at = now()
        self._save_task(task)
        return task

    def read_log(self, task_id: str, max_chars: int = 40000) -> str:
        task = self._load_task(task_id)
        if task.log_path.exists():
            text = task.log_path.read_text(encoding="utf-8", errors="replace")
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
            current_dir = None
            bootstrap = True

        task_id = f"{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        work_dir = self.tasks_root / source_id / task_id
        work_dir.mkdir(parents=True, exist_ok=True)
        if current_dir:
            shutil.copytree(current_dir, work_dir / "current", dirs_exist_ok=True)
        else:
            write_bootstrap_extractor(work_dir / "current", source_id, source_metadata or {})

        (work_dir / "fixtures").mkdir(exist_ok=True)
        (work_dir / "schema").mkdir(exist_ok=True)
        result_path = work_dir / "result.json"
        log_path = work_dir / "codex.jsonl"
        write_contract_schema(work_dir / "schema" / "extractor_result.schema.json")
        write_final_schema(work_dir / "schema" / "final_message.schema.json")
        write_task_md(work_dir / "TASK.md", source_id, reason, source_metadata or {}, bootstrap=bootstrap)

        current_now = now()
        task = RepairTask(
            id=task_id,
            source_id=source_id,
            status="queued",
            work_dir=work_dir,
            created_at=current_now,
            updated_at=current_now,
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
        command = build_codex_command(task)
        task.status = "running"
        task.updated_at = now()
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
                result_error = validate_final_result(task.result_path)
                if result_error:
                    task.status = "failed"
                    task.error = result_error
                else:
                    self._apply_final_status(task, read_json(task.result_path, {}))
            else:
                task.status = "failed"
                task.error = f"codex exited with code {process.returncode}"
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
        finally:
            task.updated_at = now()
            self._save_task(task)
            if task.status == "succeeded":
                result = read_json(task.result_path, {})
                if result.get("status") in {"fixed", "needs_review"}:
                    try:
                        self.promote_task(task.id)
                    except Exception:
                        pass

    def _apply_final_status(self, task: RepairTask, result: dict[str, Any]) -> None:
        final_status = result.get("status")
        if final_status == "skipped_unrepairable":
            task.status = "blocked"
            task.error = str(result.get("summary") or "blocked or unrepairable")
            write_json(
                task.work_dir / "blocked.json",
                {
                    "status": "blocked",
                    "source_id": task.source_id,
                    "summary": task.error,
                    "next_steps": result.get("next_steps") if isinstance(result.get("next_steps"), list) else [],
                    "updated_at": now(),
                },
            )
        elif final_status in {"fixed", "needs_review"}:
            task.status = "succeeded"
            task.error = None
        else:
            task.status = "failed"
            task.error = str(result.get("summary") or f"codex returned status {final_status}")

    def _load_task(self, task_id: str) -> RepairTask:
        return self.store.get_task(task_id)

    def _save_task(self, task: RepairTask) -> None:
        self.store.save_task(task)


def _infer_target_url(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("DEFAULT_URL"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip("\"'")
    return None
