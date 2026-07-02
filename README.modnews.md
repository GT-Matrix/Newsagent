# modnews-pipeline

Modular `uv` project for a two-stage pipeline:

1. `ingest`: aggregate RSS, NewsNow, and site list items into one normalized news list
2. `classify`: classify AI-related news into event records with an LLM

## Layout

```text
src/modnews_pipeline/
├── pipeline.py
├── runner.py
├── cli.py
├── config.py
├── context.py
├── models.py
├── shared/
├── ingest/
│   ├── stage.py
│   ├── base.py
│   ├── rss/
│   ├── newsnow/
│   └── site_lists/
└── classify/
    ├── article.py
    ├── llm_client.py
    └── stage.py
```

Root files expose the pipeline skeleton. Shared helpers stay outside the two big stages. Each ingest source has its own directory under `ingest/`.

## Run

```bash
cd /Users/zyf/Code/Projects/modnews/modnews
uv run modnews-pipeline
```

Use a custom config file:

```bash
uv run modnews-pipeline --config config.example.json
```

Quick test runs:

```bash
uv run modnews-pipeline --only-ingest-step rss --disable-classify
uv run modnews-pipeline --only-ingest-step rss --only-ingest-step newsnow
```

## Mock Server

Use the local cached outputs as a mock API server for frontend or integration work.

The server now prefers internal snapshot files under `mock_data/` so it does not depend on `output/`.
That keeps the mock API stable even if test runs overwrite pipeline output files.
`newsnow` source caches are also served from `mock_data/newsnow/`.

Runtime env file:

- [`.env.runtime`](/Users/zyf/Code/Projects/modnews/modnews/.env.runtime)

Current env variables:

- `NEWS_MODE=mock|real`
- `LLM_MODEL=...`
- `LLM_BASE_URL=...`
- `LLM_API_KEY=...`
- `EMBEDDING_MODEL=...`
- `EMBEDDING_BASE_URL=...`
- `EMBEDDING_API_KEY=...`
- `CLASSIFICATION_BATCH_CONCURRENCY=20`
- `SOURCE_LAB_PROXY=...`

When `NEWS_MODE=mock`, the helper script auto-starts the mock server if needed and routes all news-source ingestion to local mock endpoints.
When `NEWS_MODE=real`, ingestion goes back to the built-in external source URLs.
LLM classification always uses `LLM_BASE_URL` and `LLM_API_KEY`.

Start it from the `modnews/` directory:

```bash
cd /Users/zyf/Code/Projects/modnews/modnews
./scripts/run_with_mode.sh uv run modnews-pipeline
```

Load the same env file for any command:

```bash
./scripts/run_with_mode.sh uv run modnews-pipeline --only-ingest-step rss --disable-classify
./scripts/with-env.sh env | grep NEWS_MODE
```

Available endpoints:

- `GET /health` or `GET /api/health`: local cache status
- `GET /api/latest`: lightweight version payload
- `GET /api/sources`: available cached `newsnow` source ids
- `GET /api/s?id=github-trending-today`: one cached `newsnow` source
- `POST /api/s/entire`: batch read cached `newsnow` sources, body `{"sources":["github-trending-today","aihot"]}`
- `GET /api/news`: `combined_news.json`
- `GET /api/news-with-events`: `news_with_events.json`
- `GET /api/events`: `events.json`
- `GET /api/rss`: `rss_items` snapshot
- `GET /api/site-lists`: `site_lists_items` snapshot

Bundled snapshot files:

- `mock_data/combined_news.snapshot.json`
- `mock_data/news_with_events.snapshot.json`
- `mock_data/events.snapshot.json`
- `mock_data/rss_items.snapshot.json`
- `mock_data/site_lists_items.snapshot.json`
- `mock_data/newsnow/*.json`

Common query params:

- `limit`
- `offset`
- `platform` for news item filtering
- `event_id` for clustered item filtering
- `q` for keyword filtering

Programmatic use:

```python
from modnews_pipeline import build_config, run_pipeline

config = build_config(
    {
        "output_path": "output/combined_news.json",
        "proxy_url": "http://127.0.0.1:7897",
        "newsnow_cache_dir": "mock_data/newsnow",
        "ingest_steps": [
            {"type": "rss", "enabled": True},
            {"type": "newsnow", "enabled": True, "columns": ["tech", "finance"]},
            {
                "type": "site_lists",
                "enabled": True,
                "sites": [],
                "limit_per_site": 10,
            },
        ],
        "classification": {
          "enabled": True,
          "batch_size": 40,
          "event_candidate_count": 5,
          "merge_candidate_count": 5,
          "llm": {
            "model": "qwen-plus",
            "cache_path": "output/llm_classification_cache.sqlite3",
            "temperature": 0
          },
        },
    },
    base_dir="/Users/zyf/Code/Projects/modnews/modnews",
)
result = run_pipeline(config)
print(result.output_path)
```

## Output

Default output files:

- `output/combined_news.json`
- `output/news_with_events.json`
- `output/events.json`
- `output/discarded_news.json`

`newsnow` will fetch live API data first and can fall back to `mock_data/newsnow/` when configured.

`site_lists` runs managed extractors configured in `runtime/config.json`. Extractor source code lives under `extractors/<source_id>/current/`.

Each news item uses the normalized shape:

```json
{
  "platform": "github-trending-today",
  "title": "Example title",
  "url": "https://example.com/post/1",
  "pubtime": "2026-06-26T10:00:00+00:00",
  "scrape_date": "2026-06-26T11:20:00+08:00",
  "event_id": "evt_20260626_0001",
  "event_label": "OpenAI 发布新模型",
  "event_confidence": 0.91,
  "is_ai_relevant": true,
  "relevance_score": 92,
  "canonical_summary": "OpenAI发布新模型",
  "entities": ["OpenAI"],
  "event_type": "model",
  "classification_decision": "assign",
  "classification_reason": "同一模型发布事件"
}
```

Each event record looks like:

```json
{
  "event_id": "evt_20260626_0001",
  "event_label": "OpenAI 发布新模型",
  "member_count": 4,
  "platforms": ["openai", "techcrunch-ai"],
  "latest_pubtime": "2026-06-26T12:20:00+08:00",
  "representative_titles": [
    "OpenAI 发布新模型",
    "OpenAI unveils new model for developers"
  ],
  "confidence": 0.91,
  "event_summary": "OpenAI发布新一代模型并开放使用",
  "event_type": "model",
  "key_entities": ["OpenAI"],
  "source_news_ids": [0, 12, 18],
  "last_llm_updated_at": "2026-06-26T11:20:00+08:00"
}
```

## Classification

Current classification step is an LLM-driven clustered stage.

- Every title is embedded, clustered locally, and sent to the LLM in clustered batches of 40
- Each title-cluster LLM call directly outputs AI event records plus suspected AI items; unrelated items are omitted
- `discarded_news.json` contains suspected items for separate review, not every unrelated title
- Event labels and summaries are embedded, clustered locally, and sent to the LLM in clustered batches of 40 for one merge pass
- Title extraction and event merge LLM calls both use `batch_concurrency`, defaulting to 20

`event_type` is fixed to:
`model`, `product`, `research`, `infrastructure`, `hardware`, `funding`, `partnership`, `policy`, `safety`, `security`, `open_source`, `company`, `acquisition`, `litigation`, `application`, `benchmark`, `other`.

`confidence` uses decimal probability values from `0.0` to `1.0`, not percentages or 0-100 scores.

Minimal config for an OpenAI-compatible chat endpoint:

```json
{
  "classification": {
    "batch_size": 40,
    "batch_concurrency": 20,
    "event_candidate_count": 5,
    "merge_candidate_count": 5,
    "llm": {
      "model": "qwen-plus",
      "base_url": "https://api.openai.com/v1",
      "api_key": "YOUR_KEY",
      "cache_path": "output/llm_classification_cache.sqlite3",
      "temperature": 0
    },
    "embedding": {
      "model": "text-embedding-3-small",
      "base_url": "https://api.openai.com/v1",
      "api_key": "YOUR_KEY",
      "cache_path": "output/event_vector_cache.sqlite3"
    }
  }
}
```

## Extend

- Add a new ingestion step under `src/modnews_pipeline/ingest/` and register it in [ingest/stage.py](/Users/zyf/Code/Projects/modnews/modnews/src/modnews_pipeline/ingest/stage.py)
- Extend [classify/stage.py](/Users/zyf/Code/Projects/modnews/modnews/src/modnews_pipeline/classify/stage.py) for pipeline orchestration, [classify/llm_client.py](/Users/zyf/Code/Projects/modnews/modnews/src/modnews_pipeline/classify/llm_client.py) for LLM transport/cache, and [classify/article.py](/Users/zyf/Code/Projects/modnews/modnews/src/modnews_pipeline/classify/article.py) for suspect article excerpts
