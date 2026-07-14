from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


SECTION_ORDER = {"top_news": 0, "insight": 1, "deep_asset": 2, "watchlist": 3}
SECTION_META = {
    "top_news": {
        "layer": "浅层",
        "label": "今日重点新闻",
        "tone": "red",
        "accent": "#e5484d",
        "accent_dark": "#8f1d28",
        "bg": "#fff7f6",
    },
    "insight": {
        "layer": "中层",
        "label": "研究、评测与论文",
        "tone": "blue",
        "accent": "#2563eb",
        "accent_dark": "#173b8f",
        "bg": "#f4f8ff",
    },
    "deep_asset": {
        "layer": "深层",
        "label": "长期方法与资源沉淀",
        "tone": "green",
        "accent": "#0f8f5f",
        "accent_dark": "#07523d",
        "bg": "#f3fbf7",
    },
    "watchlist": {
        "layer": "观察",
        "label": "待观察线索",
        "tone": "gray",
        "accent": "#64748b",
        "accent_dark": "#334155",
        "bg": "#f8fafc",
    },
}


@dataclass(slots=True)
class CardItem:
    index: int
    event_id: str
    section: str
    title: str
    brief: str
    why: str
    source_name: str
    source_url: str
    image_path: str | None
    image_url: str | None
    fallback_theme: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML newspaper-style image cards for selected report events.")
    parser.add_argument("--events", default="data/output/enriched_events.json", help="Path to enriched_events.json.")
    parser.add_argument("--out-dir", default="data/output/news_cards", help="Output directory for HTML/assets/manifest.")
    parser.add_argument("--limit", type=int, default=12, help="Maximum number of report items to render.")
    parser.add_argument("--timeout", type=int, default=12, help="HTTP timeout in seconds for original pages/images.")
    args = parser.parse_args()

    events_path = Path(args.events)
    out_dir = Path(args.out_dir)
    assets_dir = out_dir / "assets"
    html_dir = out_dir / "html"
    assets_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    events = json.loads(events_path.read_text(encoding="utf-8"))
    selected = sorted(
        [event for event in events if event.get("should_include_report")],
        key=lambda event: (
            SECTION_ORDER.get(str(event.get("report_section") or ""), 99),
            -float(event.get("final_score") or 0),
        ),
    )[: args.limit]

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            )
        }
    )

    manifest_items: list[dict[str, Any]] = []
    for index, event in enumerate(selected, start=1):
        item = _build_item(index, event)
        image_url = _find_original_image(session, item.source_url, args.timeout) if item.source_url else None
        image_path = _download_image(session, image_url, assets_dir, args.timeout) if image_url else None
        item.image_url = image_url
        item.image_path = _relative(image_path, html_dir) if image_path else None

        html_path = html_dir / f"{index:02d}_{_slug(item.event_id or item.title)}.html"
        html_path.write_text(_render_html(item), encoding="utf-8")
        manifest_items.append(
            {
                "index": item.index,
                "event_id": item.event_id,
                "section": item.section,
                "layer": SECTION_META.get(item.section, SECTION_META["watchlist"])["layer"],
                "title": item.title,
                "brief": item.brief,
                "why": item.why,
                "source_name": item.source_name,
                "source_url": item.source_url,
                "image_url": item.image_url,
                "html_path": str(html_path.as_posix()),
                "png_path": str((out_dir / "png" / f"{index:02d}_{_slug(item.event_id or item.title)}.png").as_posix()),
                "image_key": None,
            }
        )

    manifest = {
        "version": 1,
        "source_events": str(events_path.as_posix()),
        "items": manifest_items,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(manifest_items)} HTML card(s) under {out_dir}")


def _build_item(index: int, event: dict[str, Any]) -> CardItem:
    source = _first_source(event)
    section = str(event.get("report_section") or "watchlist")
    title = str(event.get("title") or event.get("event_label") or "Untitled")
    brief = str(event.get("one_sentence") or "")
    why = str(event.get("why_important") or "")
    return CardItem(
        index=index,
        event_id=str(event.get("event_id") or f"event_{index}"),
        section=section,
        title=title,
        brief=brief,
        why=why,
        source_name=str(source.get("platform") or "unknown"),
        source_url=str(source.get("url") or ""),
        image_path=None,
        image_url=None,
        fallback_theme=_fallback_theme(title, brief, why, event),
    )


def _first_source(event: dict[str, Any]) -> dict[str, Any]:
    for source in event.get("source_items") or []:
        if source.get("url"):
            return source
    sources = event.get("source_items") or []
    return sources[0] if sources else {}


def _find_original_image(session: requests.Session, page_url: str, timeout: int) -> str | None:
    try:
        response = session.get(page_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return None
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "<html" not in response.text[:1000].lower():
        return None
    text = response.text[:700_000]
    patterns = [
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        image_url = html.unescape(match.group(1)).strip()
        if image_url:
            return urljoin(page_url, image_url)
    return None


def _download_image(session: requests.Session, image_url: str | None, assets_dir: Path, timeout: int) -> Path | None:
    if not image_url:
        return None
    parsed = urlparse(image_url)
    if parsed.scheme not in {"http", "https"}:
        return None
    try:
        response = session.get(image_url, timeout=timeout, stream=True)
        response.raise_for_status()
    except requests.RequestException:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if not content_type.startswith("image/"):
        return None
    suffix = _image_suffix(content_type, parsed.path)
    digest = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:18]
    path = assets_dir / f"original_{digest}{suffix}"
    size = 0
    with path.open("wb") as file:
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            size += len(chunk)
            if size > 8_000_000:
                path.unlink(missing_ok=True)
                return None
            file.write(chunk)
    if size < 8_000:
        path.unlink(missing_ok=True)
        return None
    return path


def _image_suffix(content_type: str, path: str) -> str:
    lower_path = path.lower()
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        if lower_path.endswith(suffix):
            return suffix
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def _render_html(item: CardItem) -> str:
    meta = SECTION_META.get(item.section, SECTION_META["watchlist"])
    visual = (
        f'<img class="hero-img" src="{html.escape(item.image_path)}" alt=""><div class="photo-scrim"></div>'
        if item.image_path
        else _fallback_visual(item.fallback_theme)
    )
    source = item.source_name or "NewsAgent"
    report_subtitle = _u("\u0041\u0049 \u60c5\u62a5\u65e9\u62a5")
    generated_label = _u("\u81ea\u52a8\u751f\u6210")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1200,initial-scale=1">
<title>{html.escape(item.title)}</title>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;width:1200px;height:675px;background:#eef1f5;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","Microsoft YaHei",Arial,sans-serif;color:#111827;overflow:hidden}}
.page{{width:1200px;height:675px;padding:34px 42px 32px;background:#eef1f5;position:relative;overflow:hidden}}
.paper{{width:100%;height:100%;background:linear-gradient(90deg,rgba(17,24,39,.045) 1px,transparent 1px) 0 0/34px 34px,linear-gradient(180deg,#fffef9 0%,{meta["bg"]} 100%);border:4px solid #111827;box-shadow:12px 12px 0 rgba(17,24,39,.16);padding:28px 34px 26px;position:relative;overflow:hidden}}
.topline{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:5px solid #111827;padding-bottom:15px}}
.brand{{font-size:35px;line-height:1;font-weight:950;letter-spacing:0}}
.brand small{{display:block;margin-top:8px;color:#4b5563;font-size:16px;font-weight:850}}
.edition{{color:{meta["accent_dark"]};font-size:25px;font-weight:950;text-align:right}}
.content{{display:grid;grid-template-columns:575px 1fr;gap:34px;padding-top:28px}}
.visual{{height:405px;border:4px solid #111827;background:radial-gradient(circle at 25% 20%,rgba(255,255,255,.34),transparent 24%),linear-gradient(135deg,{meta["accent_dark"]} 0%,#111827 58%,{meta["accent"]} 100%);position:relative;overflow:hidden;color:#fff}}
.hero-img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;filter:saturate(1.05) contrast(1.03);transform:scale(1.01)}}
.photo-scrim{{position:absolute;inset:0;background:linear-gradient(90deg,rgba(17,24,39,.78) 0%,rgba(17,24,39,.32) 48%,rgba(17,24,39,.08) 100%),linear-gradient(0deg,rgba(17,24,39,.48) 0%,transparent 46%)}}
.visual::before{{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(255,255,255,.11) 1px,transparent 1px) 0 0/26px 26px,linear-gradient(180deg,rgba(255,255,255,.10) 1px,transparent 1px) 0 0/26px 26px;opacity:.55;z-index:2}}
.fallback{{height:100%;position:relative;background:linear-gradient(135deg,{meta["accent_dark"]},#111827 68%);overflow:hidden}}
.fallback-grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.12) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.12) 1px,transparent 1px);background-size:42px 42px;opacity:.32}}
.fallback-shape{{position:absolute;border:2px solid rgba(255,255,255,.42);box-shadow:0 0 50px rgba(255,255,255,.18)}}
.shape-a{{left:70px;top:70px;width:250px;height:250px;border-radius:28px;transform:rotate(10deg)}}
.shape-b{{right:55px;bottom:92px;width:220px;height:220px;border-radius:50%}}
.shape-c{{left:135px;bottom:88px;width:280px;height:90px;border-radius:999px}}
.fallback-word{{position:absolute;left:34px;bottom:26px;right:34px;font-size:74px;line-height:.92;font-weight:950;color:rgba(255,255,255,.94);letter-spacing:0;z-index:3;text-shadow:0 3px 14px rgba(0,0,0,.35)}}
.panel{{height:405px;border-left:4px solid #111827;padding-left:28px;display:flex;flex-direction:column;justify-content:center;min-width:0}}
.kicker{{display:inline-block;width:max-content;color:#fff;background:{meta["accent"]};font-size:22px;line-height:1;font-weight:950;padding:11px 16px;margin-bottom:20px}}
.headline{{margin:0;max-width:430px;font-size:{_headline_size(item.title)}px;line-height:1.03;font-weight:950;letter-spacing:0;color:#111827;display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden}}
.meta-row{{margin-top:28px;border-top:3px solid rgba(17,24,39,.55);padding-top:16px;display:grid;grid-template-columns:96px 1fr;gap:16px;align-items:center}}
.number{{color:{meta["accent_dark"]};font-size:54px;line-height:.85;font-weight:950;margin:0}}
.meta-text{{font-size:18px;line-height:1.22;font-weight:850;color:#374151}}
.source-row{{position:absolute;left:76px;bottom:66px;display:flex;gap:10px;z-index:4}}
.source-pill{{border:2px solid #111827;background:rgba(255,255,255,.96);color:#111827;padding:7px 12px;font-size:18px;line-height:1;font-weight:900;box-shadow:2px 2px 0 rgba(17,24,39,.16)}}
.footer{{position:absolute;left:76px;right:76px;bottom:24px;display:flex;justify-content:space-between;align-items:center;border-top:2px solid rgba(17,24,39,.55);padding-top:12px;color:#374151;font-size:19px;font-weight:850}}
</style>
</head>
<body>
<main class="page">
  <section class="paper">
    <section class="topline">
      <div class="brand">AI NEWS DAILY<small>{report_subtitle}</small></div>
      <div class="edition">{html.escape(meta["layer"])} &middot; {html.escape(meta["label"])}</div>
    </section>
    <section class="content">
      <section class="visual">{visual}</section>
      <section class="panel">
        <article>
          <div class="kicker">{html.escape(_signal_label(item.title + ' ' + item.brief))}</div>
          <h1 class="headline">{html.escape(item.title)}</h1>
          <div class="meta-row">
            <div class="number">{item.index:02d}</div>
            <div class="meta-text">{html.escape(meta["layer"])} &middot; NewsAgent</div>
          </div>
        </article>
      </section>
    </section>
    <section class="source-row"><span class="source-pill">{html.escape(source)}</span></section>
    <section class="footer"><span>NewsAgent {generated_label}</span><span>{html.escape(meta["layer"])}</span></section>
  </section>
</main>
</body>
</html>
"""


def _fallback_visual(theme: str) -> str:
    return f"""<div class="fallback">
  <div class="fallback-grid"></div>
  <div class="fallback-shape shape-a"></div>
  <div class="fallback-shape shape-b"></div>
  <div class="fallback-shape shape-c"></div>
  <div class="fallback-word">{html.escape(theme.upper())}</div>
</div>"""



def _headline_size(title: str) -> int:
    length = len(title)
    if length > 92:
        return 34
    if length > 72:
        return 38
    if length > 54:
        return 42
    return 48


def _signal_label(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("chip", "gpu", "nvidia", "inference", "compute", "??", "??", "??", "???")):
        return _u("\u7b97\u529b\u4e0e\u57fa\u7840\u8bbe\u65bd")
    if any(word in lowered for word in ("science", "chemistry", "biology", "research", "??", "??", "??", "??")):
        return _u("\u0041\u0049 \u79d1\u5b66")
    if any(word in lowered for word in ("agent", "benchmark", "tool", "???", "??", "??")):
        return _u("\u667a\u80fd\u4f53\u4e0e\u8bc4\u6d4b")
    if any(word in lowered for word in ("open source", "github", "repo", "framework", "??", "??", "??")):
        return _u("\u5f00\u6e90\u751f\u6001")
    if any(word in lowered for word in ("safety", "security", "??")):
        return _u("\u5b89\u5168\u4e0e\u6cbb\u7406")
    return _u("\u4eca\u65e5\u91cd\u70b9")

def _u(value: str) -> str:
    return value

def _fallback_theme(title: str, brief: str, why: str, event: dict[str, Any]) -> str:
    text = f"{title} {brief} {why} {event.get('normalized_event_type', '')} {' '.join(event.get('entities') or [])}".lower()
    groups = [
        ("compute", {"chip", "gpu", "nvidia", "inference", "compute", "hbm", "芯片", "算力", "推理", "英伟达"}),
        ("agents", {"agent", "benchmark", "tool", "workflow", "智能体", "评测", "工具", "工作流"}),
        ("science", {"science", "chemistry", "biology", "protein", "research", "科研", "化学", "生物", "蛋白", "研究"}),
        ("opensource", {"open source", "github", "repo", "framework", "开源", "仓库", "框架"}),
    ]
    for label, words in groups:
        if any(word in text for word in words):
            return label
    return "ai news"


def _slug(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return f"{cleaned[:36] or 'card'}_{digest}"


def _relative(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    return path.resolve().relative_to(base.resolve()).as_posix() if path.resolve().is_relative_to(base.resolve()) else path.resolve().as_uri()


if __name__ == "__main__":
    main()
