from __future__ import annotations

import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.service.extraction.repair_promote import promote_repair_task
from modnews.service.extraction.repair_runtime import run_repair_task
from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_store import RepairTask, RepairTaskStore, read_json, write_json
from modnews.service.extraction.repair_support import (
    now,
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
        task = promote_repair_task(self.project_root, self.registry, task)
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
        task = run_repair_task(task)
        self._save_task(task)
        try:
            if task.status == "succeeded":
                result = read_json(task.result_path, {})
                if result.get("status") in {"fixed", "needs_review"}:
                    try:
                        self.promote_task(task.id)
                    except Exception:
                        pass
        finally:
            self._save_task(task)

    def _load_task(self, task_id: str) -> RepairTask:
        return self.store.get_task(task_id)

    def _save_task(self, task: RepairTask) -> None:
        self.store.save_task(task)
