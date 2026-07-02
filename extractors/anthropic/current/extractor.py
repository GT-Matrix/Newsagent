# MODNEWS_EXTRACTOR {"created_at": "2026-07-02T16:54:32+08:00", "entrypoint": "extractor.py:run", "id": "anthropic", "kind": "news", "name": "Anthropic News", "notes": "Bootstrap extractor generated for Codex repair task.", "schedule": null, "status": "enabled", "tags": ["company", "ai"], "target_url": "https://www.anthropic.com/news", "updated_at": "2026-07-02T17:22:15+08:00", "version": "0.0.0"}
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


EXTRACTOR_VERSION = "1.0.0"
DEFAULT_URL = "https://www.anthropic.com/news"
PLATFORM = "anthropic"
USER_AGENT = (
    "Mozilla/5.0 (compatible; modnews-anthropic-extractor/1.0; "
    "+https://www.anthropic.com/news)"
)

BLOCKED_STATUS_CODES = {401, 403, 407, 408, 409, 425, 429, 451, 503}
BLOCKED_MARKERS = (
    "cloudflare",
    "cf-chl",
    "cf-ray",
    "captcha",
    "hcaptcha",
    "recaptcha",
    "access denied",
    "request blocked",
    "rate limit",
    "too many requests",
    "verify you are human",
    "please enable cookies",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _failure(status: str, message: str, target_url: str, **extra: object) -> dict:
    diagnostics = {"message": message, "target_url": target_url}
    diagnostics.update({key: value for key, value in extra.items() if value is not None})
    return {
        "ok": False,
        "status": status,
        "items": [],
        "diagnostics": diagnostics,
        "extractor_version": EXTRACTOR_VERSION,
    }


def _text(node) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _looks_blocked(body: str) -> bool:
    lowered = body[:20000].lower()
    return any(marker in lowered for marker in BLOCKED_MARKERS)


def _fetch(url: str) -> tuple[str | None, dict | None]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8", "replace")
            status_code = getattr(response, "status", None)
            if status_code in BLOCKED_STATUS_CODES or _looks_blocked(body):
                return None, _failure(
                    "blocked",
                    "Anthropic news page appears to be blocked by an access-control or anti-bot response.",
                    url,
                    http_status=status_code,
                )
            return body, None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        blocked = exc.code in BLOCKED_STATUS_CODES or _looks_blocked(body)
        return None, _failure(
            "blocked" if blocked else "fetch_error",
            (
                "Anthropic news page request was blocked by an access-control response."
                if blocked
                else "Anthropic news page request failed."
            ),
            url,
            http_status=exc.code,
            reason=str(exc.reason),
        )
    except (TimeoutError, URLError, OSError) as exc:
        return None, _failure("fetch_error", "Anthropic news page request failed.", url, error=str(exc))


def _title_for_anchor(anchor) -> str:
    selectors = [
        "h1",
        "h2",
        "h3",
        "h4",
        '[class*="title" i]',
    ]
    for selector in selectors:
        node = anchor.select_one(selector)
        title = _text(node)
        if title:
            return title
    return ""


def _category_for_anchor(anchor) -> str:
    for selector in ('[class*="subject" i]', '[class*="meta" i] span', "span"):
        node = anchor.select_one(selector)
        value = _text(node)
        if value and not any(char.isdigit() for char in value):
            return value
    return ""


def _summary_for_anchor(anchor) -> str:
    paragraph = anchor.find("p")
    return _text(paragraph)


def _is_article_path(href: str) -> bool:
    parsed = urlparse(href)
    path = parsed.path.rstrip("/")
    return path.startswith("/news/") or path.startswith("/policy-")


def _extract_items(html: str, base_url: str, scrape_date: str, limit: int) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    items: list[dict] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not _is_article_path(href):
            continue

        published = _text(anchor.find("time"))
        title = _title_for_anchor(anchor)
        if not title or not published:
            continue

        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)

        item = {
            "platform": PLATFORM,
            "title": unescape(title),
            "url": url,
            "scrape_date": scrape_date,
            "published_date": published,
        }

        category = _category_for_anchor(anchor)
        if category:
            item["category"] = category

        summary = _summary_for_anchor(anchor)
        if summary:
            item["summary"] = unescape(summary)

        items.append(item)
        if len(items) >= limit:
            break

    return items


def _coerce_limit(value: object) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return 20
    return max(1, min(limit, 100))


def run(payload: dict) -> dict:
    target_url = payload.get("url") or DEFAULT_URL
    scrape_date = payload.get("scrape_date") or _now_iso()
    limit = _coerce_limit(payload.get("limit", 20))

    html, error = _fetch(target_url)
    if error is not None:
        return error

    try:
        items = _extract_items(html or "", target_url, scrape_date, limit)
    except Exception as exc:
        return _failure(
            "parse_error",
            "Anthropic news page could not be parsed.",
            target_url,
            error=f"{type(exc).__name__}: {exc}",
        )

    if not items:
        return _failure(
            "parse_error",
            "No Anthropic news items were found in the page markup.",
            target_url,
            html_length=len(html or ""),
        )

    return {
        "ok": True,
        "status": "ok",
        "items": items,
        "diagnostics": {
            "message": f"Extracted {len(items)} Anthropic news items.",
            "target_url": target_url,
        },
        "extractor_version": EXTRACTOR_VERSION,
    }


if __name__ == "__main__":
    import json
    from datetime import datetime

    sample = {
        "source_id": "anthropic",
        "url": "https://www.anthropic.com/news",
        "scrape_date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "limit": 10,
        "options": {},
    }
    print(json.dumps(run(sample), ensure_ascii=False, indent=2))
