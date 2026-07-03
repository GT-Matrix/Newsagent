from __future__ import annotations

import os
from pathlib import Path

_LOADED_ENV_FILES: set[Path] = set()


def ensure_runtime_env(project_root: str | Path | None = None) -> Path | None:
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    env_path = _resolve_env_file(root)
    if env_path is None:
        return None
    if env_path in _LOADED_ENV_FILES:
        return env_path
    _load_env_file(env_path)
    _LOADED_ENV_FILES.add(env_path)
    return env_path


def _resolve_env_file(project_root: Path) -> Path | None:
    explicit = os.environ.get("MODNEWS_ENV_FILE")
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        return candidate.resolve()

    for candidate in (project_root / ".env.runtime", project_root / "modnews" / ".env.runtime"):
        if candidate.exists():
            return candidate.resolve()
    return None


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip())
