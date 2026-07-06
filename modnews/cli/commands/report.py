from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from modnews.cli.api_client import ApiClient
from modnews.service.report.config import DEFAULT_INPUT, DEFAULT_OUTPUT_DIR


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("report", help="Generate report artifacts from PipelineResult or classification_progress inputs.")
    nested = parser.add_subparsers(dest="report_command", required=True)
    generate_cmd = nested.add_parser("generate")
    generate_cmd.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input path. Supports data file, output directory, or checkpoint.json.")
    generate_cmd.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    generate_cmd.add_argument("--date", default=None)
    generate_cmd.add_argument("--config", type=Path, default=None)
    generate_cmd.set_defaults(handler=generate_report_command)


def generate_report_command(_ctx: Any, _client: Any, args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "input": str(args.input),
        "output_dir": str(args.output_dir),
        "date": args.date,
        "config": str(args.config) if args.config else None,
    }
    if isinstance(_client, ApiClient):
        return _client.post("/api/report/generate", payload)
    return _client.report_generate(payload)
