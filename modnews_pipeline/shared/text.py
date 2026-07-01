from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    normalized = text.lower().strip()
    tokens = TOKEN_RE.findall(normalized)
    cjk_chars = CJK_RE.findall(normalized)
    tokens.extend(cjk_chars)
    tokens.extend(
        f"{cjk_chars[index]}{cjk_chars[index + 1]}"
        for index in range(len(cjk_chars) - 1)
    )
    return tokens
