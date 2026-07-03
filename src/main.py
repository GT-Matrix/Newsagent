from __future__ import annotations

import argparse
from pathlib import Path

from modnews.service.report import run_pipeline
from src.config import DEFAULT_INPUT, DEFAULT_OUTPUT_DIR
from src.utils.time import parse_report_date


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate v1.0 AI news report candidates.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to processed modnews PipelineResult JSON, usually output/combined_news.json.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for generated outputs.")
    parser.add_argument("--date", type=str, default=None, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--config", type=Path, default=None, help="Optional modnews config for LLM final report polishing.")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    report_date = parse_report_date(args.date)
    enriched = run_pipeline(args.input, args.output_dir, report_date, args.config)
    selected = [event for event in enriched if event.should_include_report]
    with_sources = [event for event in enriched if event.source_items]
    print(f"Loaded {len(enriched)} events")
    print(f"Events with source items: {len(with_sources)}")
    print(f"Selected {len(selected)} report items")
    print(f"Wrote outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
