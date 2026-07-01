from __future__ import annotations

import argparse
import json
from pathlib import Path

from .client import CATEGORY_JSON_URL, fetch_category_topics


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch linux.do News category topic list.")
    parser.add_argument(
        "--output-dir",
        default="output/linux_do",
        help="Directory to store linux.do output JSON files.",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Optional curl proxy URL, e.g. http://127.0.0.1:7897",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    topics = fetch_category_topics(proxy_url=args.proxy)
    (output_dir / "category_news.json").write_text(
        json.dumps([topic.to_dict() for topic in topics], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "category_url": "https://linux.do/c/news/34",
                "category_json_url": CATEGORY_JSON_URL,
                "topic_count": len(topics),
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(output_dir)
    print(f"topics={len(topics)}")
