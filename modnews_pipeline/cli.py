from __future__ import annotations

import argparse
from pathlib import Path

from .config import apply_runtime_overrides, load_config
from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the modnews pipeline.")
    parser.add_argument("--config", help="Path to a JSON config file.", default=None)
    parser.add_argument(
        "--only-ingest-step",
        action="append",
        default=[],
        help="Run only the selected ingest step. Repeatable, e.g. --only-ingest-step rss",
    )
    parser.add_argument(
        "--disable-classify",
        action="store_true",
        help="Disable the classify stage for quick ingestion tests.",
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        help="Resume classify stage from a classification_progress.json checkpoint.",
        default=None,
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if args.resume_from_checkpoint:
        config.classification.checkpoint_path = Path(args.resume_from_checkpoint).resolve()
    apply_runtime_overrides(
        config,
        only_ingest_steps=args.only_ingest_step or None,
        disable_classification=args.disable_classify,
    )
    result = run_pipeline(config)
    print(result.output_path)
    print(f"total={len(result.items)}")

if __name__ == "__main__":
    main()