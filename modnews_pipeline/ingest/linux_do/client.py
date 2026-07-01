from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any


CATEGORY_JSON_URL = "https://linux.do/c/news/34.json"
TOPIC_JSON_URL = "https://linux.do/t/topic/{topic_id}.json"


class _HtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self.parts)


@dataclass(slots=True)
class TopicSummary:
    topic_id: int
    title: str
    slug: str
    url: str
    created_at: str | None
    last_posted_at: str | None
    excerpt: str | None
    posts_count: int | None
    views: int | None
    reply_count: int | None
    scrape_date: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "title": self.title,
            "slug": self.slug,
            "url": self.url,
            "created_at": self.created_at,
            "last_posted_at": self.last_posted_at,
            "excerpt": self.excerpt,
            "posts_count": self.posts_count,
            "views": self.views,
            "reply_count": self.reply_count,
            "scrape_date": self.scrape_date,
        }


def _run_curl(url: str, proxy_url: str | None = None, cookie: str | None = None) -> str:
    cmd = [
        "curl",
        "-sS",
        "-L",
        "--max-time",
        "30",
        "-H",
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "-H",
        "Accept: application/json,text/plain,*/*",
        "-H",
        "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        url,
    ]
    if proxy_url:
        cmd[1:1] = ["--proxy", proxy_url]
    if cookie:
        cmd[1:1] = ["-H", f"Cookie: {cookie}"]
    return subprocess.check_output(cmd, text=True)


def _fetch_json(url: str, proxy_url: str | None = None, cookie: str | None = None) -> dict[str, Any]:
    raw = _run_curl(url, proxy_url=proxy_url, cookie=cookie)
    text = raw.lstrip()
    if not text.startswith("{"):
        lowered = raw.lower()
        if "cf-chl" in lowered or "just a moment" in lowered or "enable javascript and cookies" in lowered:
            raise RuntimeError("linux.do blocked by Cloudflare challenge; use a browser-verified cookie or disable linux_do")
        raise RuntimeError(f"linux.do returned non-JSON response: {raw[:160]}")
    return json.loads(raw)

def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    parser = _HtmlTextParser()
    parser.feed(html)
    return parser.get_text()


def _build_topic_url(topic_id: int, slug: str) -> str:
    return f"https://linux.do/t/{slug}/{topic_id}"


def fetch_category_topics(proxy_url: str | None = None) -> list[TopicSummary]:
    payload = _fetch_json(CATEGORY_JSON_URL, proxy_url=proxy_url)
    scrape_date = datetime.now().astimezone().isoformat(timespec="seconds")
    topics: list[TopicSummary] = []
    for row in payload.get("topic_list", {}).get("topics", []):
        topic_id = int(row["id"])
        slug = row.get("slug") or "topic"
        topics.append(
            TopicSummary(
                topic_id=topic_id,
                title=(row.get("title") or "").strip(),
                slug=slug,
                url=_build_topic_url(topic_id, slug),
                created_at=row.get("created_at"),
                last_posted_at=row.get("last_posted_at"),
                excerpt=row.get("excerpt"),
                posts_count=row.get("posts_count"),
                views=row.get("views"),
                reply_count=row.get("reply_count"),
                scrape_date=scrape_date,
            )
        )
    return topics


def fetch_topic_detail(topic_id: int, proxy_url: str | None = None) -> dict[str, Any]:
    payload = _fetch_json(TOPIC_JSON_URL.format(topic_id=topic_id), proxy_url=proxy_url)
    posts = []
    for post in payload.get("post_stream", {}).get("posts", []):
        posts.append(
            {
                "post_id": post.get("id"),
                "post_number": post.get("post_number"),
                "username": post.get("username"),
                "name": post.get("name"),
                "created_at": post.get("created_at"),
                "updated_at": post.get("updated_at"),
                "reply_count": post.get("reply_count"),
                "reads": post.get("reads"),
                "score": post.get("score"),
                "cooked_html": post.get("cooked"),
                "text": _strip_html(post.get("cooked")),
            }
        )

    return {
        "topic_id": payload.get("id"),
        "title": payload.get("title"),
        "created_at": payload.get("created_at"),
        "last_posted_at": payload.get("last_posted_at"),
        "views": payload.get("views"),
        "reply_count": payload.get("reply_count"),
        "posts_count": payload.get("posts_count"),
        "tags": payload.get("tags") or [],
        "url": _build_topic_url(int(payload["id"]), "topic"),
        "posts": posts,
    }
