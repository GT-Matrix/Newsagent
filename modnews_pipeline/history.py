from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import EventRecord

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff]{2,}")
STOP_TOKENS = {
    "the", "and", "for", "with", "from", "this", "that", "news", "ai", "????",
    "??", "??", "??", "??", "??", "??", "??", "??", "??",
}


@dataclass(slots=True)
class HistoryDedupeConfig:
    enabled: bool = True
    history_path: Path = field(default_factory=lambda: Path("output/event_history.json"))
    lookback_days: int = 14
    similarity_threshold: float = 0.72


def apply_history_dedupe(events: list[EventRecord], config: HistoryDedupeConfig, scrape_date: str) -> None:
    if not config.enabled:
        return
    config.history_path.parent.mkdir(parents=True, exist_ok=True)
    history = _load_history(config.history_path)
    recent = _recent_history(history, scrape_date, config.lookback_days)

    for event in events:
        best = _best_match(event, recent, config.similarity_threshold)
        if best is None:
            event.is_duplicate = False
            event.duplicate_of_event_id = None
            event.first_seen_date = scrape_date[:10]
            continue
        event.is_duplicate = True
        event.duplicate_of_event_id = str(best.get("event_id") or "")
        event.first_seen_date = str(best.get("first_seen_date") or best.get("scrape_date") or scrape_date[:10])

    _write_history(config.history_path, history, events, scrape_date)


def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("events") if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _write_history(path: Path, previous: list[dict[str, Any]], events: list[EventRecord], scrape_date: str) -> None:
    by_key: dict[str, dict[str, Any]] = {}
    for row in previous:
        key = str(row.get("history_key") or row.get("event_id") or "")
        if key:
            by_key[key] = row
    for event in events:
        if event.is_duplicate:
            continue
        tokens = _event_tokens(event)
        history_key = _history_key(event, tokens)
        by_key[history_key] = {
            "history_key": history_key,
            "event_id": event.event_id,
            "event_label": event.event_label,
            "event_summary": event.event_summary,
            "event_type": event.event_type,
            "key_entities": event.key_entities,
            "tokens": sorted(tokens),
            "first_pubtime": event.first_pubtime,
            "latest_pubtime": event.latest_pubtime,
            "first_seen_date": event.first_seen_date or scrape_date[:10],
            "scrape_date": scrape_date[:10],
        }
    rows = sorted(by_key.values(), key=lambda row: str(row.get("scrape_date") or ""), reverse=True)
    path.write_text(json.dumps({"updated_at": scrape_date, "events": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def _recent_history(rows: list[dict[str, Any]], scrape_date: str, lookback_days: int) -> list[dict[str, Any]]:
    cutoff = _parse_date(scrape_date) - timedelta(days=max(1, lookback_days))
    result = []
    for row in rows:
        row_date = _parse_date(str(row.get("scrape_date") or row.get("first_seen_date") or ""))
        if row_date >= cutoff:
            result.append(row)
    return result


def _best_match(event: EventRecord, rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    event_tokens = _event_tokens(event)
    if not event_tokens:
        return None
    best_score = 0.0
    best_row: dict[str, Any] | None = None
    event_type = (event.event_type or "").lower()
    event_entities = {entity.lower() for entity in event.key_entities if entity}
    for row in rows:
        if str(row.get("event_id") or "") == event.event_id:
            continue
        row_tokens = set(str(token).lower() for token in row.get("tokens") or [])
        if not row_tokens:
            row_tokens = _tokens(" ".join(str(row.get(key) or "") for key in ["event_label", "event_summary", "event_type"]))
        score = _jaccard(event_tokens, row_tokens)
        row_type = str(row.get("event_type") or "").lower()
        row_entities = {str(entity).lower() for entity in row.get("key_entities") or []}
        entity_overlap = bool(event_entities & row_entities)
        if event_type and row_type and event_type == row_type:
            score += 0.08
        if entity_overlap:
            score += 0.12
        if score > best_score:
            best_score = score
            best_row = row
    return best_row if best_score >= threshold else None


def _event_tokens(event: EventRecord) -> set[str]:
    return _tokens(" ".join([
        event.event_label or "",
        event.event_summary or "",
        event.event_type or "",
        " ".join(event.key_entities or []),
        " ".join(event.representative_titles or []),
    ]))


def _tokens(text: str) -> set[str]:
    tokens = {match.group(0).lower() for match in TOKEN_RE.finditer(text or "")}
    return {token for token in tokens if token not in STOP_TOKENS and len(token) >= 2}


def _history_key(event: EventRecord, tokens: set[str]) -> str:
    prefix = (event.event_type or "unknown").lower()
    entity_part = ":".join(sorted(entity.lower() for entity in event.key_entities[:4] if entity))
    token_part = ":".join(sorted(tokens)[:10])
    return f"{prefix}|{entity_part}|{token_part}"


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _parse_date(value: str) -> datetime:
    text = (value or "").strip()[:10]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.min
