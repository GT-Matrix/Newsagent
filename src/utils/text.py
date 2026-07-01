from __future__ import annotations

import re


MOJIBAKE_MARKERS = ("�", "鐨", "鍙", "鏄", "涓", "绋", "鎺", "彂", "竴", "鈥", "锟")


def compact_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def contains_mojibake(value: str) -> bool:
    if not value:
        return False
    marker_hits = sum(1 for marker in MOJIBAKE_MARKERS if marker in value)
    return marker_hits >= 2 or "?" in value and any(marker in value for marker in MOJIBAKE_MARKERS)


def mostly_english(value: str) -> bool:
    text = compact_spaces(value)
    if not text:
        return False
    ascii_letters = sum(1 for char in text if "a" <= char.lower() <= "z")
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return ascii_letters >= 12 and ascii_letters > cjk * 2


def text_quality(*values: str) -> str:
    joined = " ".join(value or "" for value in values)
    if not joined.strip():
        return "missing"
    if contains_mojibake(joined):
        return "bad"
    return "ok"


def choose_best_title(event_label: str, representative_titles: list[str]) -> str:
    candidates = [event_label, *representative_titles]
    clean = [compact_spaces(item) for item in candidates if compact_spaces(item)]
    if not clean:
        return "Untitled event"
    non_bad = [item for item in clean if not contains_mojibake(item)]
    pool = non_bad or clean
    chinese_pool = [item for item in pool if not mostly_english(item)]
    if chinese_pool:
        pool = chinese_pool
    return min(pool, key=lambda item: (len(item) > 110, len(item)))


def short_sentence(value: str, fallback: str, max_len: int = 120) -> str:
    text = compact_spaces(value) or compact_spaces(fallback)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def has_any_word(text: str, words: set[str]) -> bool:
    lowered = (text or "").lower()
    return any(word.lower() in lowered for word in words)