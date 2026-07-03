from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from modnews.service.report import generate_report
from modnews.service.report.config import DEFAULT_INPUT, DEFAULT_OUTPUT_DIR


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("report", help="Generate report artifacts from published outputs.")
    nested = parser.add_subparsers(dest="report_command", required=True)
    generate_cmd = nested.add_parser("generate")
    generate_cmd.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    generate_cmd.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    generate_cmd.add_argument("--date", default=None)
    generate_cmd.add_argument("--config", type=Path, default=None)
    generate_cmd.set_defaults(handler=generate_report_command)


def generate_report_command(_ctx: Any, _client: Any, args: argparse.Namespace) -> dict[str, Any]:
    events = generate_report(args.input, args.output_dir, report_date=args.date, config_path=args.config)
    selected = [event for event in events if event.should_include_report]
    with_sources = [event for event in events if event.source_items]
    return {
        "event_count": len(events),
        "events_with_sources": len(with_sources),
        "selected_count": len(selected),
        "output_dir": str(args.output_dir),
    }
