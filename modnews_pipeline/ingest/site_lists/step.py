from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem, StepResult

from ..base import IngestStep

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)


class SiteListsStep(IngestStep):
    step_name = "site_lists"

    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        mock_url = ctx.config.site_lists_api_url
        if mock_url:
            return _run_via_mock(ctx, mock_url)

        site_ids = self.options.get("sites", ["anthropic", "aibase", "stanford_hai"])
        limit = int(self.options.get("limit_per_site", 10))
        errors: list[str] = []
        items: list[NewsItem] = []
        raw_output: dict[str, list[dict[str, str | None]]] = {}

        fetchers = {
            "anthropic": _fetch_anthropic,
            "aibase": _fetch_aibase,
            "stanford_hai": _fetch_stanford_hai,
        }

        for site_id in site_ids:
            fetcher = fetchers.get(site_id)
            if not fetcher:
                errors.append(f"{site_id}: unsupported site")
                continue
            try:
                rows = fetcher(ctx, limit=limit)
                raw_output[site_id] = rows
                for row in rows:
                    items.append(
                        NewsItem(
                            platform=site_id,
                            title=row["title"] or "",
                            url=row["url"] or "",
                            pubtime=row["pubtime"],
                            scrape_date=ctx.scrape_date,
                        )
                    )
            except Exception as exc:
                errors.append(f"{site_id}: {exc}")

        output_path = ctx.work_dir / "site_lists_items.json"
        output_path.write_text(
            json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raw_path = ctx.work_dir / "site_lists_raw.json"
        raw_path.write_text(json.dumps(raw_output, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.artifacts[self.step_name] = output_path
        ctx.artifacts[f"{self.step_name}_raw"] = raw_path
        return items, StepResult(
            step=self.step_name,
            item_count=len(items),
            output_path=str(output_path),
            errors=errors,
        )


def _fetch_html(ctx: PipelineContext, url: str) -> str:
    resp = ctx.session.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.text


def _run_via_mock(ctx: PipelineContext, api_url: str) -> tuple[list[NewsItem], StepResult]:
    resp = ctx.session.get(api_url, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    items = [
        NewsItem(
            platform=(row.get("platform") or "").strip(),
            title=(row.get("title") or "").strip(),
            url=row.get("url", ""),
            pubtime=row.get("pubtime"),
            scrape_date=row.get("scrape_date") or ctx.scrape_date,
        )
        for row in payload.get("items", [])
    ]
    output_path = ctx.work_dir / "site_lists_items.json"
    output_path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    raw_path = ctx.work_dir / "site_lists_raw.json"
    raw_path.write_text(json.dumps({"mock_api_url": api_url}, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.artifacts["site_lists"] = output_path
    ctx.artifacts["site_lists_raw"] = raw_path
    return items, StepResult(
        step="site_lists",
        item_count=len(items),
        output_path=str(output_path),
        meta={"mode": "mock", "api_url": api_url},
    )


def _normalize_date(text: str | None) -> str | None:
    if not text:
        return None
    text = unescape(text).strip()
    for fmt, tz in (
        ("%b %d, %Y", timezone.utc),
        ("%B %d, %Y", timezone.utc),
        ("%b %d", timezone.utc),
        ("%B %d", timezone.utc),
        ("%Y-%m-%d", timezone.utc),
        ("%Y/%m/%d", timezone.utc),
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                parsed = parsed.replace(year=datetime.now().year)
            return parsed.replace(tzinfo=tz).isoformat()
        except ValueError:
            continue
    return None


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(text).split())


def _dedupe(rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    seen: set[str] = set()
    result = []
    for row in rows:
        url = row["url"] or ""
        if url in seen:
            continue
        seen.add(url)
        result.append(row)
    return result


def _fetch_anthropic(ctx: PipelineContext, limit: int) -> list[dict[str, str | None]]:
    html = _fetch_html(ctx, "https://www.anthropic.com/news")
    pattern = re.compile(r'<a href="(?P<href>/[^"]+)"[^>]*>(?P<body>.*?)</a>', re.S)
    rows = []
    for match in pattern.finditer(html):
        href = match.group("href")
        if not (href.startswith("/news/") or href.startswith("/policy")):
            continue
        body = match.group("body")
        date_match = re.search(r"<time[^>]*>(?P<date>[^<]+)</time>", body)
        title_match = re.search(r"<h[1-6][^>]*>(?P<title>.*?)</h[1-6]>", body, re.S)
        if not date_match or not title_match:
            continue
        rows.append(
            {
                "title": _clean_text(title_match.group("title")),
                "url": urljoin("https://www.anthropic.com", href),
                "pubtime": _normalize_date(date_match.group("date")),
            }
        )
        if len(rows) >= limit:
            break
    return _dedupe(rows)


def _fetch_aibase(ctx: PipelineContext, limit: int) -> list[dict[str, str | None]]:
    html = _fetch_html(ctx, "https://news.aibase.com/zh/news")
    pattern = re.compile(
        r'<a href="(?P<url>https://news\.aibase\.com/zh/news/\d+)"[^>]*>.*?title="(?P<title>[^"]+)"',
        re.S,
    )
    rows = []
    page_date_match = re.search(r"(\d{4}-\d{2}-\d{2})", html)
    page_pubtime = _normalize_date(page_date_match.group(1)) if page_date_match else None
    for match in pattern.finditer(html):
        rows.append(
            {
                "title": re.sub(r"^#\d+\s*", "", _clean_text(match.group("title"))),
                "url": match.group("url"),
                "pubtime": page_pubtime,
            }
        )
        if len(rows) >= limit:
            break
    return _dedupe(rows)


def _fetch_stanford_hai(ctx: PipelineContext, limit: int) -> list[dict[str, str | None]]:
    html = _fetch_html(ctx, "https://hai.stanford.edu/news")
    rows = []
    anchor_pattern = re.compile(r'<a[^>]+href="(?P<href>/news/[^"]+)"[^>]*>(?P<body>.*?)</a>', re.S | re.I)
    date_pattern = re.compile(r"(?P<date>[A-Z][a-z]+ \d{1,2})")
    for match in anchor_pattern.finditer(html):
        title = _clean_text(match.group("body"))
        if not title or title == "Read More" or len(title) < 12:
            continue
        window = html[max(0, match.start() - 300) : match.end() + 1200]
        date_match = date_pattern.search(window)
        rows.append(
            {
                "title": _clean_text(title),
                "url": urljoin("https://hai.stanford.edu", match.group("href")),
                "pubtime": _normalize_date(date_match.group("date")) if date_match else None,
            }
        )
        if len(rows) >= limit:
            break
    if rows:
        return _dedupe(rows)

    fallback = re.compile(r'<a href="(?P<href>/news/[^"]+)".*?>(?P<title>[^<]{12,})</a>', re.S)
    for match in fallback.finditer(html):
        title = _clean_text(match.group("title"))
        if title == "Read More":
            continue
        rows.append(
            {
                "title": title,
                "url": urljoin("https://hai.stanford.edu", match.group("href")),
                "pubtime": None,
            }
        )
        if len(rows) >= limit:
            break
    return _dedupe(rows)
