# MODNEWS_EXTRACTOR {"created_at": "2026-07-02T00:00:00+08:00", "entrypoint": "extractor.py:run", "id": "huggingface", "kind": "paper", "name": "Hugging Face Trending Papers", "notes": "Managed extractor for https://huggingface.co/papers/trending.", "schedule": null, "status": "enabled", "tags": ["papers", "huggingface", "trending"], "target_url": "https://huggingface.co/papers/trending", "updated_at": "2026-07-02T00:00:00+08:00", "version": "2026.07.02"}
from __future__ import annotations

import html
import json
import re
from typing import Any

import requests

TARGET_URL = "https://huggingface.co/papers/trending"
EXTRACTOR_VERSION = "2026.07.02"


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scrape_date = str(payload.get("scrape_date") or "")
    limit = int(payload.get("limit") or 40)
    url = str(payload.get("url") or TARGET_URL)
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    response.raise_for_status()
    rows = _parse_daily_papers(response.text)
    items = [_paper_from_row(row, scrape_date) for row in rows[:limit]]
    return {
        "ok": bool(items),
        "items": items,
        "diagnostics": {
            "url": url,
            "status_code": response.status_code,
            "row_count": len(rows),
        },
        "extractor_version": EXTRACTOR_VERSION,
    }


def _parse_daily_papers(document: str) -> list[dict[str, Any]]:
    match = re.search(r'data-target="DailyPapers" data-props="([\s\S]*?)"><section', document)
    if not match:
        raise ValueError("DailyPapers payload not found")
    payload = json.loads(html.unescape(match.group(1)))
    rows = payload.get("dailyPapers")
    if not isinstance(rows, list):
        raise ValueError("dailyPapers payload is not a list")
    return rows


def _paper_from_row(row: dict[str, Any], scrape_date: str) -> dict[str, Any]:
    paper = row.get("paper") if isinstance(row.get("paper"), dict) else {}
    categories = _str_list(paper.get("ai_keywords"))
    paper_id = _clean(paper.get("id"))
    return {
        "platform": "huggingface",
        "title": _clean(row.get("title")) or _clean(paper.get("title")) or "",
        "url": f"https://huggingface.co/papers/{paper_id}" if paper_id else TARGET_URL,
        "pubtime": _clean(row.get("publishedAt")) or _clean(paper.get("publishedAt")),
        "scrape_date": scrape_date,
        "summary": _clean(paper.get("ai_summary")) or _clean(row.get("summary")) or _clean(paper.get("summary")),
        "authors": _author_names(paper.get("authors")),
        "categories": categories,
        "primary_category": categories[0] if categories else None,
        "paper_id": paper_id,
    }


def _author_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict) and _clean(item.get("name")):
            names.append(str(_clean(item.get("name"))))
    return names


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


if __name__ == "__main__":
    print(json.dumps(run({"source_id": "huggingface", "url": TARGET_URL, "scrape_date": "manual", "limit": 3}), indent=2))
