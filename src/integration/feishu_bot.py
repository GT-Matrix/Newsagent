from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


MAX_ITEMS = 12
MAX_FIELD_CHARS = 700


def make_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^\s*#+\s*", "", text)
    text = re.sub(r"^\s*[-*]\s*", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def truncate(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def parse_report(markdown: str) -> tuple[str | None, list[dict[str, str]]]:
    trend: str | None = None
    items: list[dict[str, str]] = []
    current_section = ""
    current: dict[str, str] | None = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("## "):
            current_section = clean_text(line)
            continue

        title_match = re.match(r"^(\d+)\.\s+\*\*(.*?)\*\*", line)
        if title_match:
            if current:
                items.append(current)
            current = {
                "section": current_section,
                "index": title_match.group(1),
                "title": clean_text(title_match.group(2)),
                "brief": "",
                "why": "",
                "source": "",
                "status": "",
            }
            continue

        if line.startswith("- 简报：") and current:
            current["brief"] = line.removeprefix("- 简报：").strip()
        elif line.startswith("- 为什么重要：") and current:
            current["why"] = line.removeprefix("- 为什么重要：").strip()
        elif line.startswith("- 来源：") and current:
            current["source"] = line.removeprefix("- 来源：").strip()
        elif line.startswith("- 状态：") and current:
            current["status"] = line.removeprefix("- 状态：").strip()
        elif ("趋势" in line or "总览" in line) and trend is None:
            trend = clean_text(line)

    if current:
        items.append(current)

    return trend, items[:MAX_ITEMS]


def build_card(title: str, markdown: str) -> dict[str, Any]:
    trend, items = parse_report(markdown)
    today = time.strftime("%Y-%m-%d")

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**生成日期：** {today}\n**入选条数：** {len(items)}",
            },
        }
    ]

    if trend:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**趋势摘要：** {truncate(trend, 500)}",
                },
            }
        )

    last_section = None
    for item in items:
        section = item.get("section") or "重点新闻"
        if section != last_section:
            elements.append({"tag": "hr"})
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{section}**",
                    },
                }
            )
            last_section = section

        body = [
            f"**{item['index']}. {item['title']}**",
            f"**简报：** {truncate(item.get('brief', ''))}",
            f"**为什么重要：** {truncate(item.get('why', ''))}",
        ]

        if item.get("source"):
            body.append(f"**来源：** {item['source']}")
        if item.get("status"):
            body.append(f"**状态：** {clean_text(item['status'])}")

        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n\n".join(body),
                },
            }
        )

    elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "完整日报已保存在服务器：/opt/newsagent/data/output/daily_report.md",
                }
            ],
        }
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": title,
            },
        },
        "elements": elements,
    }


def send_card(webhook_url: str, secret: str, card: dict[str, Any]) -> None:
    timestamp = str(int(time.time()))
    payload: dict[str, Any] = {
        "msg_type": "interactive",
        "card": card,
    }

    if secret:
        payload["timestamp"] = timestamp
        payload["sign"] = make_sign(secret, timestamp)

    response = requests.post(webhook_url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("code") not in (0, None):
        raise RuntimeError(f"Feishu webhook failed: {data}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send NewsAgent daily report to Feishu bot.")
    parser.add_argument("--input", default="data/output/daily_report.md")
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
    secret = os.environ.get("FEISHU_SECRET", "")

    if not webhook_url:
        raise SystemExit("FEISHU_WEBHOOK_URL is required")

    report = Path(args.input).read_text(encoding="utf-8").strip()
    title = args.title or f"AI 新闻早报 - {time.strftime('%Y-%m-%d')}"

    send_card(webhook_url, secret, build_card(title, report))
    print("Sent 1 Feishu card message")


if __name__ == "__main__":
    main()
