from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths


class CheckpointRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.root = runtime_paths(project_root).process_dir / "runs"

    def list(self, run_id: str | None = None) -> list[dict[str, Any]]:
        base = self.root / run_id if run_id else self.root
        if not base.exists():
            return []
        rows = []
        for path in base.glob("**/checkpoint.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            rows.append({"path": str(path), **payload})
        return sorted(rows, key=lambda row: str(row.get("finished_at") or row.get("started_at") or row.get("path")))

    def read(self, checkpoint_path: str | Path) -> dict[str, Any]:
        path = Path(checkpoint_path).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"invalid checkpoint payload: {path}")
        payload.setdefault("path", str(path))
        return payload

    def write(self, run_id: str, step_id: str, task_id: str, payload: dict[str, Any]) -> Path:
        now = _now()
        path = self._checkpoint_dir(run_id, step_id, task_id) / "checkpoint.json"
        payload = {
            "run_id": run_id,
            "step_id": step_id,
            "task_id": task_id,
            "started_at": payload.get("started_at") or now,
            "finished_at": payload.get("finished_at") or now,
            **payload,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_artifact(self, run_id: str, step_id: str, task_id: str, name: str, payload: Any) -> Path:
        path = self._checkpoint_dir(run_id, step_id, task_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _checkpoint_dir(self, run_id: str, step_id: str, task_id: str) -> Path:
        step_dir = self.root / run_id / "checkpoints" / step_id
        if step_dir.exists():
            suffix = f"-{task_id}"
            matches = sorted(path for path in step_dir.iterdir() if path.is_dir() and path.name.endswith(suffix))
            if matches:
                return matches[-1]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return step_dir / f"{stamp}-{task_id}"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
