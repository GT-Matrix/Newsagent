# NewsAgent

NewsAgent is an AI news pipeline with three layers:

1. Ingest RSS, NewsNow, and managed web extractors into normalized news items.
2. Cluster and classify AI-related items into event records.
3. Run the report layer under `src/` to score, verify, section, summarize, and generate the daily report.

## Pipeline

```text
runtime/config.json
  -> RSS / NewsNow / managed web extractors
  -> output/combined_news.json
  -> src report layer
  -> data/output/daily_report.md
```

Papers are modeled as normal sources with `content_type=paper`. There is no separate arXiv attach stage.

## Configuration

Runtime source and step settings live in `runtime/config.json` and are editable from the WebUI. Secrets and model endpoints stay in environment variables:

```bash
LLM_MODEL=...
LLM_BASE_URL=...
LLM_API_KEY=...
EMBEDDING_MODEL=...
EMBEDDING_BASE_URL=...
EMBEDDING_API_KEY=...
NEWS_MODE=real
```

The backend loads env from `MODNEWS_ENV_FILE`, `.env.runtime`, or the legacy `modnews/.env.runtime` path.

## Run

```bash
python -m modnews.cli.main run start
python -m modnews.cli.main report generate --input output/combined_news.json --date 2026-07-02
```

## Outputs

```text
output/combined_news.json
output/news_with_events.json
output/events.json
output/discarded_news.json

data/output/daily_report.md
data/output/daily_report_debug.md
data/output/enriched_events.json
data/output/evidence_events.json
data/output/report_candidates.json
data/output/review_candidates.json
```

## Web Extraction

Managed extractors live under `extractors/<source_id>/current/`. Agent work directories and logs live under `.agent_work/` and are not committed.

Current committed extractors:

- `anthropic`
- `huggingface_papers_trending`
