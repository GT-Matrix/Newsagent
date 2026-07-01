from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from .config import PipelineConfig


@dataclass(slots=True)
class PipelineContext:
    config: PipelineConfig
    scrape_date: str
    session: requests.Session
    work_dir: Path
    artifacts: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def create(cls, config: PipelineConfig) -> "PipelineContext":
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )
        if config.proxy_url:
            session.proxies.update({"http": config.proxy_url, "https": config.proxy_url})
        return cls(
            config=config,
            scrape_date=datetime.now().astimezone().isoformat(timespec="seconds"),
            session=session,
            work_dir=config.output_path.parent,
        )
