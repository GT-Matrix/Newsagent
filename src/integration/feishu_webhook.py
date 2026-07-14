from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


INTRO_TEXT = ""
SOURCE_LABEL = "\u6765\u6e90"
BRIEF_LABEL = "\u7b80\u62a5"
WHY_LABEL = "\u4e3a\u4ec0\u4e48\u91cd\u8981"
TREND_TITLE = "\u56db\u3001\u4eca\u65e5\u8d8b\u52bf\u89c2\u5bdf"
FOOTER_TEXT = "\u5b8c\u6574\u65e5\u62a5\u4e0e\u56fe\u7247\u6587\u4ef6\u4fdd\u5b58\u5728\u670d\u52a1\u5668 data/output/news_cards/\u3002"
DEFAULT_TITLE_PREFIX = "AI \u65b0\u95fb\u65e9\u62a5"
SECTION_TITLES = {
    "top_news": "\u4e00\u3001\u4eca\u65e5\u91cd\u70b9\u65b0\u95fb",
    "insight": "\u4e8c\u3001\u7814\u7a76\u8bba\u6587\u4e0e\u8bc4\u6d4b",
    "deep_asset": "\u4e09\u3001\u957f\u671f\u65b9\u6cd5\u4e0e\u8d44\u6e90\u6c89\u6dc0",
    "watchlist": "\u5f85\u89c2\u5bdf\u7ebf\u7d22",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send NewsAgent report to Feishu webhook with uploaded news-card images.")
    parser.add_argument("--manifest", default="data/output/news_cards/manifest.json")
    parser.add_argument("--report", default="data/output/daily_report.md")
    parser.add_argument("--title", default=None)
    parser.add_argument("--max-items", type=int, default=30)
    args = parser.parse_args()

    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
    secret = os.environ.get("FEISHU_SECRET", "")
    if not webhook_url:
        raise SystemExit("FEISHU_WEBHOOK_URL is required.")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    title = args.title or f"{DEFAULT_TITLE_PREFIX} - {time.strftime('%Y-%m-%d')}"
    report_path = Path(args.report) if args.report else None
    send_card(webhook_url, secret, build_card(title, manifest, args.max_items, report_path))
    print("Sent Feishu image card message")


def build_card(title: str, manifest: dict[str, Any], max_items: int, report_path: Path | None = None) -> dict[str, Any]:
    elements: list[dict[str, Any]] = []
    last_section = None
    rendered = 0

    for item in manifest.get("items") or []:
        if max_items > 0 and rendered >= max_items:
            break
        image_key = item.get("image_key")
        if not image_key:
            continue

        section = str(item.get("section") or "watchlist")
        if section != last_section:
            elements.append({"tag": "hr"})
            elements.append(_markdown(f"**{_md_escape(_section_title(item))}**"))
            last_section = section

        title_text = str(item.get("title") or "news card")
        elements.append(
            {
                "tag": "img",
                "img_key": image_key,
                "alt": {"tag": "plain_text", "content": title_text},
                "mode": "fit_horizontal",
            }
        )
        elements.append(_markdown(_item_text(item)))
        rendered += 1

    trend = _extract_trend(report_path) if report_path else ""
    if trend:
        elements.append({"tag": "hr"})
        elements.append(_markdown(f"**{TREND_TITLE}**\n\n{_md_escape(_clean(trend, 1800))}"))

    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": FOOTER_TEXT}]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }


def _section_title(item: dict[str, Any]) -> str:
    section = str(item.get("section") or "")
    return SECTION_TITLES.get(section) or str(item.get("section_title") or item.get("layer") or "") or "\u65b0\u95fb"


def _item_text(item: dict[str, Any]) -> str:
    lines: list[str] = []

    brief = _clean(str(item.get("brief") or item.get("one_sentence") or ""), 520)
    why = _clean(str(item.get("why") or item.get("why_important") or ""), 420)
    if brief:
        lines.append(f"**{BRIEF_LABEL}\uff1a** {_md_escape(brief)}")
    if why:
        lines.append(f"**{WHY_LABEL}\uff1a** {_md_escape(why)}")

    source_url = str(item.get("source_url") or "").strip()
    source_name = _clean(str(item.get("source_name") or ""), 80)
    if source_url and source_name:
        source = f"[{_md_escape(source_name)}]({source_url})"
    elif source_name:
        source = _md_escape(source_name)
    else:
        source = "NewsAgent"
    lines.append(f"**{SOURCE_LABEL}\uff1a** {source}")
    return "\n\n".join(lines)


def _extract_trend(report_path: Path | None) -> str:
    if not report_path or not report_path.exists():
        return ""
    text = report_path.read_text(encoding="utf-8", errors="ignore")
    pattern = r"(?ms)^##\s*(?:\u56db\u3001)?\s*\u4eca\u65e5\u8d8b\u52bf\u89c2\u5bdf\s*\n(?P<body>.*?)(?=\n##\s|\n>\s*\u8bf4\u660e|\Z)"
    match = re.search(pattern, text)
    if not match:
        return ""
    body = match.group("body")
    body = re.sub(r"\n>\s*\u8bf4\u660e.*", "", body, flags=re.S)
    body = re.sub(r"\s+", " ", body).strip()
    return body


def _markdown(content: str) -> dict[str, Any]:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _md_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")


def send_card(webhook_url: str, secret: str, card: dict[str, Any]) -> None:
    timestamp = str(int(time.time()))
    payload: dict[str, Any] = {"msg_type": "interactive", "card": card}
    if secret:
        payload["timestamp"] = timestamp
        payload["sign"] = make_sign(secret, timestamp)
    response = requests.post(webhook_url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("code") not in (0, None):
        raise RuntimeError(f"Feishu webhook failed: {data}")


def make_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


if __name__ == "__main__":
    main()
