# Web Extraction Agent Design

## Current State

The current web extraction path is centered on managed extractor jobs:

- `site_lists` is the pipeline step name for managed web extraction jobs.
- Managed extractors live under `extractors/<id>/current/`.
- Only the Hugging Face trending papers source is active by default because it already has an agent-format extractor.
- Repair tasks are manually created from the WebUI via `POST /api/repair-tasks`.
- Task state is stored as files under `.agent_work/extractors/<source_id>/<task_id>/`.
- Task logs are written to `codex.jsonl`; task metadata is written to `task.json`; the final Codex response is written to `result.json`.
- The frontend fetches `/api/repair-tasks` and `/api/repair-tasks/<task_id>`. It does not currently stream task events live.

Automatic "scrape failed, create repair task" behavior exists in the orchestrator policy, but should stay conservative until validation is stronger.

## Immediate Backup

The current runtime web sources were backed up to:

`runtime/backups/site_lists_sources_20260702.json`

The removed non-HuggingFace web-source code/config snapshot was also backed up to:

`runtime/backups/non_huggingface_web_sources_20260702.tar.gz`

These are only reference snapshots. They should not become compatibility layers.

## Recommended Direction

Keep `site_lists` as a web extraction orchestration step rather than a hard-coded scraper collection.

The pipeline-level step should only:

- Load enabled web sources from `runtime/source_config.json`.
- Create one extraction job per source.
- Run jobs with bounded concurrency.
- Collect successful extracted items.
- Persist per-source job states and events.
- Emit pipeline-visible summaries.

The orchestrator should not know how Hugging Face or any future site is parsed. That belongs inside each source's extractor task.

## Runtime Config Shape

Recommended `sources.site_lists` entry:

```json
{
  "huggingface-papers": {
    "enabled": true,
    "name": "Hugging Face Trending Papers",
    "url": "https://huggingface.co/papers/trending",
    "content_type": "paper",
    "extractor_id": "huggingface",
    "tags": ["papers", "trending"],
    "repair_policy": {
      "enabled": true,
      "max_attempts_before_repair": 3,
      "auto_start": true
    }
  }
}
```

Required fields:

- `enabled`: source-level switch.
- `name`: UI label.
- `url`: target page or API endpoint.
- `content_type`: `news` or `paper`.
- `extractor_id`: managed extractor ID under `extractors/<id>/current/extractor.py`.

Optional fields:

- `tags`: free-form classification and filtering labels.
- `options`: extractor-specific runtime options.
- `repair_policy`: per-source auto-repair behavior.

Secrets must stay in environment variables. Runtime config should only contain public source configuration and non-sensitive options.

## Extractor Contract

Each extractor module should expose:

```python
def run(payload: dict) -> dict:
    ...
```

Input payload:

```json
{
  "source_id": "anthropic",
  "url": "https://www.anthropic.com/news",
  "scrape_date": "2026-07-02",
  "limit": 20,
  "content_type": "news",
  "options": {}
}
```

Output payload:

```json
{
  "ok": true,
  "status": "ok",
  "items": [],
  "diagnostics": {},
  "extractor_version": "0.1.0"
}
```

Recommended `status` enum:

- `ok`: extraction succeeded.
- `empty`: request succeeded but no items were found.
- `blocked`: Cloudflare, CAPTCHA, login wall, rate limit, or network policy prevents useful extraction.
- `network_error`: transient DNS, timeout, TLS, or connection issue.
- `parse_error`: page fetched but structure/parser failed.
- `invalid_output`: extractor returned invalid contract data.

The current contract has `ok/items/diagnostics/extractor_version`; it should be expanded to include `status`, `error_type`, and `retryable`.

## Extractor Metadata Comment

Generated files should keep metadata in the first comment block:

```python
# MODNEWS_EXTRACTOR {"id":"huggingface","name":"Hugging Face Trending Papers","kind":"paper","version":"0.1.0","status":"enabled","entrypoint":"extractor.py:run","target_url":"https://huggingface.co/papers/trending","tags":["papers","trending"],"created_at":"2026-07-02T00:00:00+08:00","updated_at":"2026-07-02T00:00:00+08:00"}
```

This supports registry refresh, enable/disable, retry, regenerate, delete, and UI display without executing the extractor.

## Per-Source State Machine

Each web extraction job should have a clear state machine:

```text
queued
  -> scraping
  -> succeeded
  -> failed_retryable
  -> scraping
  -> failed_exhausted
  -> repair_queued
  -> repairing
  -> testing
  -> repaired
  -> skipped_unrepairable
  -> failed
```

Important terminal states:

- `succeeded`: extraction returned valid items.
- `repaired`: Codex produced a candidate, tests passed, and the extractor was promoted or is ready for review.
- `skipped_unrepairable`: failure is likely Cloudflare/CAPTCHA/login/network policy and code repair has no value.
- `failed`: exhausted retries or repair failed.

The pipeline should treat `skipped_unrepairable` as a known non-code failure, not as a reason to repeatedly spawn repair tasks.

## Failure Classification

Before starting Codex, classify the failure:

- `blocked`: HTTP 403/429, Cloudflare challenge HTML, CAPTCHA text, "enable JavaScript", login-required walls.
- `network_error`: timeout, DNS, TLS, connection reset.
- `parse_error`: HTTP success with changed DOM/API shape or missing expected fields.
- `contract_error`: extractor returns invalid schema.
- `empty`: valid page but zero items.

Only `parse_error`, `contract_error`, and repeated suspicious `empty` results should usually start a repair task.

`blocked` and pure network failures should create a visible job event and optionally notify the UI, but should not ask Codex to "fix" parser code by default.

## Codex Repair Task Prompt

The generated `TASK.md` should include:

- Source metadata: ID, name, URL, content type, tags.
- Last failing payload.
- Last exception and traceback.
- HTTP status, selected headers, and a short sanitized response sample when available.
- Extractor contract schema.
- Required test commands.
- Explicit skip rule for non-code failures.

Required prompt clause:

```text
If the failure appears to be caused by Cloudflare, CAPTCHA, login requirements, rate limiting, network blocking, or another access problem rather than a page structure or parser issue, do not rewrite the extractor. Return status "skipped_unrepairable" with evidence in diagnostics.
```

Recommended final response schema:

```json
{
  "status": "fixed",
  "summary": "string",
  "files_changed": ["current/extractor.py"],
  "diagnostics": {},
  "validation": {
    "commands": [],
    "passed": true
  }
}
```

Recommended `status` enum:

- `fixed`
- `skipped_unrepairable`
- `failed`
- `needs_review`

The current schema only allows `fixed`, `failed`, and `needs_review`; it should add `skipped_unrepairable`.

## Save/Promotion Flow

Do not immediately replace production extractors just because Codex exits successfully.

Recommended flow:

1. Create task workdir and copy current extractor.
2. Run Codex in task workdir only.
3. Run static validation: `python -m py_compile current/extractor.py`.
4. Run contract validation with captured fixtures or a live request when safe.
5. Compare result against schema and require at least one item for `ok`.
6. Store validation report in task workdir.
7. Mark task `ready_for_review` or `repaired`.
8. Promote manually from UI, or auto-promote only if source policy explicitly allows it.

Promotion should version old extractors:

```text
extractors/huggingface/
  current/
  versions/20260702-153000/
  versions/20260702-160200/
```

## Events and Frontend Sync

The current frontend polling model is enough for a first version, but the backend should write structured task events separately from raw Codex logs.

Recommended files:

```text
.agent_work/extractors/<source>/<task>/
  task.json
  events.jsonl
  codex.jsonl
  result.json
  validation.json
  current/extractor.py
  schema/
  fixtures/
```

Event examples:

```json
{"ts":"2026-07-02T15:30:00+08:00","type":"job_started","source_id":"huggingface-papers","state":"scraping"}
{"ts":"2026-07-02T15:30:03+08:00","type":"scrape_failed","error_type":"parse_error","message":"missing title selector"}
{"ts":"2026-07-02T15:30:04+08:00","type":"repair_started","task_id":"huggingface-20260702153004"}
{"ts":"2026-07-02T15:32:10+08:00","type":"validation_passed","items":8}
```

Recommended APIs:

- `GET /api/web-sources`: list configured web sources plus extractor and last job state.
- `PUT /api/web-sources/<source_id>`: create/update one source.
- `DELETE /api/web-sources/<source_id>`: delete source.
- `POST /api/web-sources/<source_id>/run`: start one extraction job.
- `GET /api/web-jobs`: list extraction/repair jobs.
- `GET /api/web-jobs/<job_id>`: job detail.
- `GET /api/web-jobs/<job_id>/events`: structured timeline.
- `GET /api/web-jobs/<job_id>/logs`: raw logs.
- `POST /api/repair-tasks`: manual repair task creation.
- `POST /api/repair-tasks/<task_id>/promote`: promote validated extractor candidate.

The existing `/api/repair-tasks` can remain, but it should become a specialized view over web jobs or link repair tasks to their parent web job.

## UI Layout

The WebUI "网页抓取" page should be split into:

- Source table card: source config, enable switch, paper source switch, extractor binding, last status, manual run.
- Extractor capability card: extractor metadata, enable switch, version, target URL, repair button.
- Jobs card: recent per-source jobs with status and latest event.
- Task drawer: structured timeline from `events.jsonl`, raw Codex log tab, validation report tab, final result tab.

The top-right global button should remain "任务列表", but the web extraction page should also show source-scoped jobs so users do not need to hunt in the global task drawer.

## Backend Module Layout

Recommended backend modules:

```text
modnews_pipeline/web_extraction/
  config.py
  contract.py
  events.py
  job_store.py
  orchestrator.py
  runner.py
  repair_policy.py
  validation.py
```

Responsibilities:

- `config.py`: read normalized web source config from `SourceConfigStore`.
- `contract.py`: input/output schema and validation.
- `events.py`: append/read structured JSONL events.
- `job_store.py`: persist job state, attempts, timestamps, result paths.
- `orchestrator.py`: create one job per enabled source and aggregate results.
- `runner.py`: execute extractor in the current process or isolated subprocess.
- `repair_policy.py`: classify failures and decide whether repair should be created.
- `validation.py`: test candidate extractor before promotion.

`modnews_pipeline/extractors/repair.py` should focus only on Codex task execution, not scrape orchestration.

## Suggested Migration Plan

1. Keep only sources with managed extractor contracts in active runtime config.
2. Create new source support through repair/generation tasks instead of adding hard-coded fetchers.
3. Add failure classification and automatic repair policy hardening.
4. Add validation reports and richer frontend timeline tabs.
5. Promote generated extractors only after contract and live/fixture validation pass.

## Open Design Choices

- Auto-promotion should default to off until enough validation exists.
- Live HTTP validation should be optional, because some failures are access-policy related and repeated live tests can make blocking worse.
- For Cloudflare/CAPTCHA cases, the system should surface a clear skipped state rather than burning Codex cycles.
- Paper handling should be a content capability of any source, not a separate paper-only step.
