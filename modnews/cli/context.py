from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CliContext:
    project_root: Path
    mode: str = "auto"
    api_url: str = "http://127.0.0.1:5055"
    output_format: str = "table"
    dry_run: bool = False
