from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem, StepResult
from modnews.repository.source_config import source_config_store

from modnews.service.ingest.base import IngestStep

CN_TZ = timezone(timedelta(hours=8))


class NewsNowStep(IngestStep):
    step_name = "newsnow"

    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        store = source_config_store(ctx.config.project_root)
        source_config = store.load()
        step_config = source_config["steps"]["newsnow"]
        sources = store.enabled_newsnow_sources()
        retries = int(self.options.get("retries", step_config.get("retries", 2)))
        retry_delay = float(self.options.get("retry_delay", step_config.get("retry_delay", 1.0)))
        limit_per_source = int(self.options.get("limit_per_source", step_config.get("limit_per_source", 50)))
        items: list[NewsItem] = []
        errors: list[str] = []

        for source in sources:
            api_url = f"{ctx.config.newsnow_api_url}?id={source['id']}&latest"
            try:
                payload = _fetch_payload(ctx, api_url, retries=retries, retry_delay=retry_delay)
                for row in payload.get("items", [])[:limit_per_source]:
                    items.append(
                        NewsItem(
                            platform=source["id"],
                            title=(row.get("title") or "").strip(),
                            url=row.get("url", ""),
                            pubtime=_extract_pubtime(row),
                            scrape_date=ctx.scrape_date,
                        )
                    )
            except Exception as exc:
                cache_rows = _load_cached_rows(ctx.config.newsnow_cache_dir, source["id"])
                if cache_rows is None:
                    errors.append(f"{source['id']}: {exc}")
                    continue
                for row in cache_rows[:limit_per_source]:
                    items.append(
                        NewsItem(
                            platform=source["id"],
                            title=(row.get("title") or "").strip(),
                            url=row.get("url", ""),
                            pubtime=_extract_pubtime(row),
                            scrape_date=ctx.scrape_date,
                        )
                    )
                errors.append(f"{source['id']}: live failed, used cache ({exc})")

        return items, StepResult(
            step=self.step_name,
            item_count=len(items),
            errors=errors,
        )


def _fetch_payload(
    ctx: PipelineContext, api_url: str, retries: int, retry_delay: float
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = ctx.session.get(api_url, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(retry_delay * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _load_cached_rows(cache_dir: Path | None, source_id: str) -> list[dict[str, Any]] | None:
    if not cache_dir:
        return None
    path = cache_dir / f"{source_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else None


def _extract_pubtime(row: dict[str, Any]) -> str | None:
    candidates = [
        row.get("pubDate"),
        row.get("date"),
        row.get("time"),
        row.get("publishTime"),
        row.get("publishedAt"),
        row.get("timestamp"),
    ]
    nested = row.get("extra")
    if isinstance(nested, dict):
        candidates.extend(
            [
                nested.get("pubDate"),
                nested.get("date"),
                nested.get("time"),
                nested.get("publishTime"),
                nested.get("publishedAt"),
                nested.get("timestamp"),
            ]
        )

    for value in candidates:
        normalized = _normalize_datetime(value)
        if normalized:
            return normalized
    return None


def _normalize_datetime(value: Any) -> str | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return _normalize_datetime(int(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CN_TZ)
            return parsed.isoformat()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S",):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=CN_TZ).isoformat()
            except ValueError:
                pass
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CN_TZ)
            return parsed.isoformat()
        except (TypeError, ValueError, IndexError):
            return None
    return None
