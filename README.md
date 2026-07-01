# NewsAgent

This project now contains the full v1.0 pipeline:

```text
raw sources
  -> modnews_pipeline ingest/classify
  -> output/combined_news.json
  -> report pipeline scoring/verification/summarization
  -> data/output/daily_report.md
```

## Project Layout

```text
modnews_pipeline/        upstream data ingest, cleaning, filtering, clustering, classification
src/                     report-layer code: layering, scoring, verification, summary, report generation
config.example.json      local config example for modnews_pipeline
config.bailian.example.json
output/                  default upstream processed output directory
data/output/             default report-layer output directory
```

## 1. Run Data Processing

The integrated upstream package writes the canonical processed file:

```text
output/combined_news.json
```

Run with a config file:

```bash
python -m modnews_pipeline.cli --config config.example.json
```

For Bailian-compatible LLM settings, start from:

```bash
python -m modnews_pipeline.cli --config config.bailian.example.json
```

The processed file must contain both:

```text
events: clustered event records
items: source news records with URLs and metadata
```

## 2. Generate Daily Report

```bash
python -m src.main --input output/combined_news.json --date 2026-06-30
```

Outputs:

```text
data/output/enriched_events.json
data/output/report_candidates.json
data/output/daily_report.md
```

## Report Layer

The report layer performs:

```text
processed events
  -> PRD v1.0 layer classification
  -> rule-based scoring
  -> source-based verification
  -> template summary
  -> daily report section selection
```

The report layer only targets the canonical processed file from `modnews_pipeline`; it no longer maintains separate compatibility paths for ad hoc event-only JSON files.
