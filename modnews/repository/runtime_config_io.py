from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    next_text = json.dumps(data, ensure_ascii=False, indent=2)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current != next_text:
            backup_config(path)
            path.write_text(next_text, encoding="utf-8")
            return
    path.write_text(next_text, encoding="utf-8")


def backup_config(path: Path) -> None:
    backup_dir = path.parent / "config.backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d%H%M%S%f")
    shutil.copy2(path, backup_dir / f"{path.stem}-{stamp}{path.suffix}")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
