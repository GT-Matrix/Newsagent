# MODNEWS_EXTRACTOR {"created_at": "2026-07-02T16:56:48+08:00", "entrypoint": "extractor.py:run", "id": "huggingface_papers_trending", "kind": "paper", "name": "Hugging Face Trending Papers", "notes": "Bootstrap extractor generated for Codex repair task.", "schedule": null, "status": "enabled", "tags": ["company", "ai"], "target_url": "https://huggingface.co/papers/trending", "updated_at": "2026-07-02T17:21:02+08:00", "version": "0.0.0"}
from __future__ import annotations

import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape


DEFAULT_URL = "https://huggingface.co/papers/trending"
PLATFORM = "huggingface_papers_trending"
VERSION = "0.1.0"
USER_AGENT = "Mozilla/5.0 (compatible; modnews-extractor/0.1; +https://huggingface.co/papers/trending)"


class AccessBlockedError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch_html(url: str, timeout: int = 25) -> tuple[str, dict]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return content.decode(charset, errors="replace"), {
                "http_status": response.status,
                "content_type": response.headers.get("content-type"),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        if exc.code in {401, 403, 407, 408, 409, 423, 429, 451, 503} or _looks_blocked(body):
            raise AccessBlockedError(f"HTTP {exc.code}: access blocked or challenged") from exc
        raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
        raise AccessBlockedError(f"network access failed: {exc}") from exc


def _looks_blocked(html: str) -> bool:
    lowered = html.lower()
    block_markers = (
        "captcha",
        "cloudflare",
        "cf-challenge",
        "awswaf.com",
        "challenge.js",
        "rate limit",
        "too many requests",
        "access denied",
        "login required",
    )
    return any(marker in lowered for marker in block_markers)


def _extract_data_props(html: str) -> dict | None:
    match = re.search(
        r'<div\b[^>]*data-target=["\']DailyPapers["\'][^>]*data-props=(["\'])(.*?)\1',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    raw = unescape(match.group(2))
    return json.loads(raw)


def _paper_url(paper_id: str, base_url: str) -> str:
    return urllib.parse.urljoin(base_url, f"/papers/{paper_id}")


def _item_from_daily_paper(entry: dict, base_url: str, scrape_date: str) -> dict | None:
    paper = entry.get("paper") if isinstance(entry, dict) else None
    if not isinstance(paper, dict):
        return None
    paper_id = str(paper.get("id") or "").strip()
    title = str(paper.get("title") or entry.get("title") or "").strip()
    if not paper_id or not title:
        return None

    item = {
        "platform": PLATFORM,
        "title": title,
        "url": _paper_url(paper_id, base_url),
        "scrape_date": scrape_date,
        "external_id": paper_id,
    }
    summary = str(paper.get("summary") or entry.get("summary") or "").strip()
    if summary:
        item["summary"] = summary
    published_at = paper.get("publishedAt") or entry.get("publishedAt")
    if published_at:
        item["published_at"] = published_at
    if paper.get("upvotes") is not None:
        item["score"] = paper.get("upvotes")
    return item


def _parse_structured_items(html: str, base_url: str, scrape_date: str, limit: int) -> list[dict]:
    props = _extract_data_props(html)
    if not props:
        return []
    daily_papers = props.get("dailyPapers") or []
    items = []
    seen_urls = set()
    for entry in daily_papers:
        item = _item_from_daily_paper(entry, base_url, scrape_date)
        if not item or item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _parse_link_fallback(html: str, base_url: str, scrape_date: str, limit: int) -> list[dict]:
    items = []
    seen_urls = set()
    for match in re.finditer(r'<a\b[^>]*href=["\'](/papers/[^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        href, body = match.groups()
        paper_id = href.rstrip("/").split("/")[-1]
        text = re.sub(r"<[^>]+>", " ", body)
        title = " ".join(unescape(text).split())
        if not title or not paper_id or paper_id == "trending":
            continue
        url = urllib.parse.urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(
            {
                "platform": PLATFORM,
                "title": title,
                "url": url,
                "scrape_date": scrape_date,
                "external_id": paper_id,
            }
        )
        if len(items) >= limit:
            break
    return items


def _limit_from_payload(payload: dict) -> int:
    try:
        limit = int(payload.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    return max(1, min(limit, 100))


def run(payload: dict) -> dict:
    payload = payload or {}
    url = payload.get("url") or DEFAULT_URL
    scrape_date = payload.get("scrape_date") or _now_iso()
    limit = _limit_from_payload(payload)

    try:
        html, fetch_diagnostics = _fetch_html(url)
    except AccessBlockedError as exc:
        return {
            "ok": False,
            "status": "blocked",
            "items": [],
            "diagnostics": {
                "message": str(exc),
                "target_url": url,
            },
            "extractor_version": VERSION,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "fetch_error",
            "items": [],
            "diagnostics": {
                "message": str(exc),
                "target_url": url,
            },
            "extractor_version": VERSION,
        }

    try:
        items = _parse_structured_items(html, url, scrape_date, limit)
        parser = "DailyPapers data-props"
        if not items:
            items = _parse_link_fallback(html, url, scrape_date, limit)
            parser = "paper link fallback"
    except Exception as exc:
        return {
            "ok": False,
            "status": "parse_error",
            "items": [],
            "diagnostics": {
                "message": str(exc),
                "target_url": url,
                **fetch_diagnostics,
            },
            "extractor_version": VERSION,
        }

    if not items:
        if _looks_blocked(html):
            return {
                "ok": False,
                "status": "blocked",
                "items": [],
                "diagnostics": {
                    "message": "Fetched page contains access challenge or blocking markers and no parseable paper items.",
                    "target_url": url,
                    "html_length": len(html),
                    **fetch_diagnostics,
                },
                "extractor_version": VERSION,
            }
        return {
            "ok": False,
            "status": "parse_error",
            "items": [],
            "diagnostics": {
                "message": "No paper items found in Hugging Face trending papers page.",
                "target_url": url,
                "html_length": len(html),
                **fetch_diagnostics,
            },
            "extractor_version": VERSION,
        }

    return {
        "ok": True,
        "status": "ok",
        "items": items,
        "diagnostics": {
            "target_url": url,
            "items_found": len(items),
            "parser": parser,
            **fetch_diagnostics,
        },
        "extractor_version": VERSION,
    }


if __name__ == "__main__":
    import json
    from datetime import datetime

    sample = {
        "source_id": "huggingface_papers_trending",
        "url": "https://huggingface.co/papers/trending",
        "scrape_date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "limit": 10,
        "options": {},
    }
    print(json.dumps(run(sample), ensure_ascii=False, indent=2))
