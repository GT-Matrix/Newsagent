from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.service.extraction.metadata import ExtractorMetadata, metadata_comment
from modnews.service.extraction.repair_store import write_json


def write_bootstrap_extractor(current_dir: Path, source_id: str, source_metadata: dict[str, Any]) -> None:
    current_dir.mkdir(parents=True, exist_ok=True)
    current_now = now()
    url = optional_str(source_metadata.get("url"))
    content_type = str(source_metadata.get("content_type") or "news")
    meta = ExtractorMetadata(
        id=source_id,
        name=str(source_metadata.get("name") or source_id),
        kind=content_type,
        version="0.0.0",
        status="enabled",
        target_url=url,
        tags=[str(item) for item in source_metadata.get("tags", []) if item not in (None, "")],
        created_at=current_now,
        updated_at=current_now,
        notes="Bootstrap extractor generated for Codex repair task.",
    )
    (current_dir / "extractor.py").write_text(
        f"""{metadata_comment(meta)}
from __future__ import annotations


def run(payload: dict) -> dict:
    return {{
        "ok": False,
        "status": "parse_error",
        "items": [],
        "diagnostics": {{
            "message": "Bootstrap extractor. Implement site-specific extraction.",
            "target_url": payload.get("url"),
        }},
        "extractor_version": "0.0.0",
    }}


if __name__ == "__main__":
    import json
    from datetime import datetime

    sample = {{
        "source_id": "{source_id}",
        "url": "{url or ''}",
        "scrape_date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "limit": 10,
        "options": {{}},
    }}
    print(json.dumps(run(sample), ensure_ascii=False, indent=2))
""",
        encoding="utf-8",
    )
    write_json(
        current_dir / "manifest.json",
        {
            "id": source_id,
            "status": "enabled",
            "created_at": current_now,
            "updated_at": current_now,
            "bootstrap": True,
        },
    )


def write_task_md(
    path: Path,
    source_id: str,
    reason: str,
    source_metadata: dict[str, Any],
    *,
    bootstrap: bool,
) -> None:
    metadata_block = json.dumps(source_metadata, ensure_ascii=False, indent=2) if source_metadata else "{}"
    path.write_text(
        f"""# Extractor Repair Task

Source: `{source_id}`
Reason: {reason}
Bootstrap task: {str(bootstrap).lower()}

Source metadata:
```json
{metadata_block}
```

Work only inside this task directory. The active extractor candidate is `current/extractor.py`.

Required contract:
- The module must expose `run(payload: dict) -> dict`.
- The returned dict must match `schema/extractor_result.schema.json`.
- `ok: true` requires at least one item.
- Each item needs `platform`, `title`, `url`, and `scrape_date`.
- Use `status: "blocked"` and final status `skipped_unrepairable` when the failure is Cloudflare, CAPTCHA, login, rate limiting, or network blocking rather than parser breakage.
- If live requests are blocked by access policy, stop after documenting the blocker. Do not keep changing selectors just to satisfy live validation.

Useful commands:
```bash
python current/extractor.py
python -m py_compile current/extractor.py
```

Do not write secrets. Do not edit files outside this work directory.
""",
        encoding="utf-8",
    )


def write_contract_schema(path: Path) -> None:
    write_json(
        path,
        {
            "type": "object",
            "required": ["ok", "items", "diagnostics", "extractor_version"],
            "properties": {
                "ok": {"type": "boolean"},
                "extractor_version": {"type": "string"},
                "diagnostics": {"type": "object"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["platform", "title", "url", "scrape_date"],
                    },
                },
            },
        },
    )


def write_final_schema(path: Path) -> None:
    write_json(
        path,
        {
            "type": "object",
            "required": ["status", "summary", "files_changed"],
            "properties": {
                "status": {"type": "string", "enum": ["fixed", "failed", "needs_review", "skipped_unrepairable"]},
                "summary": {"type": "string"},
                "files_changed": {"type": "array", "items": {"type": "string"}},
                "next_steps": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    )


def infer_url_from_task(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "Create extractor for "
    if marker in text:
        tail = text.split(marker, 1)[1]
        if ": http" in tail:
            return "http" + tail.split(": http", 1)[1].split()[0].strip()
    for token in text.replace("`", " ").split():
        if token.startswith("http://") or token.startswith("https://"):
            return token.strip(".,)")
    return None


def infer_name_from_task(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "Create extractor for "
    if marker not in text:
        return None
    value = text.split(marker, 1)[1].splitlines()[0]
    if ": http" in value:
        value = value.split(": http", 1)[0]
    return value.strip() or None


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
