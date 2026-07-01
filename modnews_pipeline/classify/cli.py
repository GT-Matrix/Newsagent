from __future__ import annotations

import argparse
import json
from pathlib import Path

from modnews_pipeline.config import load_config
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem

from .stage import run_classification


def main() -> None:
    parser = argparse.ArgumentParser(description="Run classify stage from an existing news snapshot.")
    parser.add_argument("--config", help="Path to a JSON config file.", default=None)
    parser.add_argument("--input", required=True, help="Path to a news snapshot JSON file.")
    parser.add_argument("--output", required=True, help="Path to write classified news JSON.")
    parser.add_argument("--events-output", required=True, help="Path to write events JSON.")
    parser.add_argument("--resume-from-checkpoint", help="Path to classification_progress.json.", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    config.classification.output_path = Path(args.output).resolve()
    config.classification.events_output_path = Path(args.events_output).resolve()
    if args.resume_from_checkpoint:
        config.classification.checkpoint_path = Path(args.resume_from_checkpoint).resolve()

    items = _load_items(Path(args.input).resolve())
    ctx = PipelineContext.create(config)
    classified_items, events, result = run_classification(ctx, items, config.classification)

    print(result.output_path)
    print(config.classification.events_output_path)
    print(f"items={len(classified_items)}")
    print(f"events={len(events)}")


def _load_items(path: Path) -> list[NewsItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
    return [
        NewsItem(
            platform=row["platform"],
            title=row["title"],
            url=row["url"],
            pubtime=row.get("pubtime"),
            scrape_date=row["scrape_date"],
        )
        for row in rows
    ]
