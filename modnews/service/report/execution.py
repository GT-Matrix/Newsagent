from __future__ import annotations

from datetime import date
from pathlib import Path

from modnews.service.report.models import EnrichedEvent
from modnews.service.report.pipeline import run_pipeline
from modnews.service.report.utils.time import parse_report_date


def generate_report(
    input_path: Path,
    output_dir: Path,
    *,
    report_date: date | str | None = None,
    config_path: Path | None = None,
) -> list[EnrichedEvent]:
    parsed_date = parse_report_date(report_date) if isinstance(report_date, str) or report_date is None else report_date
    return run_pipeline(input_path, output_dir, parsed_date, config_path)
