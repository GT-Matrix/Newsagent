from __future__ import annotations

import re
from html import unescape

from modnews_pipeline.context import PipelineContext


def fetch_article_excerpt(ctx: PipelineContext, url: str, segment_chars: int = 200) -> str:
    if not url:
        return ""
    response = ctx.session.get(url, timeout=25)
    response.raise_for_status()
    text = _html_to_text(response.text)
    if not text:
        return ""
    if len(text) <= segment_chars * 3:
        return text[: segment_chars * 3]
    middle = max(segment_chars, len(text) // 2)
    return "\n\n".join(
        [
            text[:segment_chars],
            text[middle : middle + segment_chars],
            text[-segment_chars:],
        ]
    )


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
