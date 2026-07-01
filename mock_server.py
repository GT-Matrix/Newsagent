from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
OUTPUT_DIR = ROOT_DIR / "output"
MOCK_DATA_DIR = ROOT_DIR / "mock_data"
NEWSNOW_CACHE_DIR = MOCK_DATA_DIR / "newsnow"
EMBEDDING_DB_PATH = MOCK_DATA_DIR / "embedding_cache.snapshot.sqlite3"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _parse_int(value: str | None, default: int, *, min_value: int = 0) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(min_value, parsed)


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _utc_ms_from_file(path: Path) -> int:
    return int(path.stat().st_mtime * 1000)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slice(items: list[Any], offset: int, limit: int | None) -> list[Any]:
    if offset:
        items = items[offset:]
    if limit is not None:
        items = items[:limit]
    return items


def _filter_items(items: list[dict[str, Any]], query: dict[str, list[str]]) -> list[dict[str, Any]]:
    platform = _first(query, "platform")
    event_id = _first(query, "event_id")
    keyword = _first(query, "q")

    filtered = items
    if platform:
        filtered = [item for item in filtered if item.get("platform") == platform]
    if event_id:
        filtered = [item for item in filtered if item.get("event_id") == event_id]
    if keyword:
        needle = keyword.casefold()
        filtered = [
            item for item in filtered
            if needle in json.dumps(item, ensure_ascii=False).casefold()
        ]
    return filtered


@dataclass(slots=True)
class DataStore:
    output_dir: Path
    mock_data_dir: Path
    newsnow_cache_dir: Path
    embedding_db_path: Path

    def latest_payload(self) -> dict[str, str]:
        return {"v": "mock-local"}

    def combined_news(self) -> dict[str, Any]:
        return _load_json(self.mock_data_dir / "combined_news.snapshot.json", _load_json(self.output_dir / "combined_news.json", {
            "scrape_date": _iso_now(),
            "total": 0,
            "items": [],
            "events": [],
            "steps": [],
            "output_path": str(self.output_dir / "combined_news.json"),
        }))

    def news_with_events(self) -> list[dict[str, Any]]:
        return _load_json(
            self.mock_data_dir / "news_with_events.snapshot.json",
            _load_json(self.output_dir / "news_with_events.json", []),
        )

    def events(self) -> list[dict[str, Any]]:
        return _load_json(
            self.mock_data_dir / "events.snapshot.json",
            _load_json(self.output_dir / "events.json", []),
        )

    def rss_items(self) -> list[dict[str, Any]]:
        return _load_json(
            self.mock_data_dir / "rss_items.snapshot.json",
            _load_json(self.output_dir / "rss_items.json", []),
        )

    def site_lists_items(self) -> list[dict[str, Any]]:
        return _load_json(
            self.mock_data_dir / "site_lists_items.snapshot.json",
            _load_json(self.output_dir / "site_lists_items.json", []),
        )

    def linux_do_items(self) -> list[dict[str, Any]]:
        return _load_json(
            self.mock_data_dir / "linux_do_items.snapshot.json",
            _load_json(self.output_dir / "linux_do_items.json", []),
        )

    def newsnow_source_ids(self) -> list[str]:
        if not self.newsnow_cache_dir.exists():
            return []
        return sorted(
            path.stem
            for path in self.newsnow_cache_dir.glob("*.json")
            if path.is_file()
        )

    def newsnow_source(self, source_id: str) -> dict[str, Any]:
        path = self.newsnow_cache_dir / f"{source_id}.json"
        if not path.exists():
            raise FileNotFoundError(source_id)
        items = _load_json(path, [])
        if not isinstance(items, list):
            raise ValueError(f"Invalid cache payload for {source_id}")
        return {
            "status": "success",
            "id": source_id,
            "updatedTime": _utc_ms_from_file(path),
            "items": items,
        }

    def embeddings(self, *, key: str | None, offset: int, limit: int) -> dict[str, Any]:
        if not self.embedding_db_path.exists():
            return {
                "total": 0,
                "offset": offset,
                "limit": limit,
                "items": [],
            }

        with sqlite3.connect(self.embedding_db_path) as conn:
            conn.row_factory = sqlite3.Row
            if key:
                rows = conn.execute(
                    """
                    SELECT cache_key, vector_json, created_at
                    FROM embedding_cache
                    WHERE cache_key = ?
                    ORDER BY created_at DESC
                    """,
                    (key,),
                ).fetchall()
                total = len(rows)
            else:
                total_row = conn.execute("SELECT COUNT(*) AS count FROM embedding_cache").fetchone()
                total = int(total_row["count"])
                rows = conn.execute(
                    """
                    SELECT cache_key, vector_json, created_at
                    FROM embedding_cache
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()

        items = []
        for row in rows:
            vector = json.loads(row["vector_json"])
            items.append({
                "cache_key": row["cache_key"],
                "created_at": row["created_at"],
                "vector_size": len(vector) if isinstance(vector, list) else None,
                "vector": vector,
            })

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": items,
        }

    def status(self) -> dict[str, Any]:
        combined = self.combined_news()
        news_with_events = self.news_with_events()
        events = self.events()
        return {
            "status": "ok",
            "generated_at": _iso_now(),
            "paths": {
                "combined_news": str(self.output_dir / "combined_news.json"),
                "combined_news_snapshot": str(self.mock_data_dir / "combined_news.snapshot.json"),
                "news_with_events": str(self.output_dir / "news_with_events.json"),
                "news_with_events_snapshot": str(self.mock_data_dir / "news_with_events.snapshot.json"),
                "events": str(self.output_dir / "events.json"),
                "events_snapshot": str(self.mock_data_dir / "events.snapshot.json"),
                "rss_items_snapshot": str(self.mock_data_dir / "rss_items.snapshot.json"),
                "site_lists_items_snapshot": str(self.mock_data_dir / "site_lists_items.snapshot.json"),
                "linux_do_items_snapshot": str(self.mock_data_dir / "linux_do_items.snapshot.json"),
                "embedding_cache": str(self.embedding_db_path),
                "newsnow_cache_dir": str(self.newsnow_cache_dir),
            },
            "counts": {
                "combined_news_items": len(combined.get("items", [])),
                "news_with_events_items": len(news_with_events),
                "events": len(events),
                "rss_items": len(self.rss_items()),
                "site_lists_items": len(self.site_lists_items()),
                "linux_do_items": len(self.linux_do_items()),
                "newsnow_sources": len(self.newsnow_source_ids()),
            },
        }


STORE = DataStore(
    output_dir=OUTPUT_DIR,
    mock_data_dir=MOCK_DATA_DIR,
    newsnow_cache_dir=NEWSNOW_CACHE_DIR,
    embedding_db_path=EMBEDDING_DB_PATH,
)


class MockHandler(BaseHTTPRequestHandler):
    server_version = "ModNewsMockServer/0.1"

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        try:
            if method == "GET" and parsed.path in {"/health", "/api/health"}:
                return self._send_json(STORE.status())

            if method == "GET" and parsed.path == "/api/latest":
                return self._send_json(STORE.latest_payload())

            if method == "GET" and parsed.path == "/api/s":
                source_id = _first(query, "id")
                if not source_id:
                    return self._send_error(HTTPStatus.BAD_REQUEST, "Missing query param: id")
                return self._send_json(STORE.newsnow_source(source_id))

            if method == "POST" and parsed.path == "/api/s/entire":
                body = self._read_json_body()
                source_ids = body.get("sources", [])
                if not isinstance(source_ids, list):
                    return self._send_error(HTTPStatus.BAD_REQUEST, "sources must be an array")
                responses = []
                for source_id in source_ids:
                    if not isinstance(source_id, str):
                        continue
                    try:
                        responses.append(STORE.newsnow_source(source_id))
                    except FileNotFoundError:
                        continue
                return self._send_json(responses)

            if method == "GET" and parsed.path == "/api/sources":
                return self._send_json({
                    "sources": STORE.newsnow_source_ids(),
                })

            if method == "GET" and parsed.path in {"/api/news", "/api/mock/news"}:
                payload = STORE.combined_news()
                items = payload.get("items", [])
                filtered = _filter_items(items, query)
                offset = _parse_int(_first(query, "offset"), 0)
                limit = _first(query, "limit")
                limit_value = _parse_int(limit, len(filtered)) if limit is not None else None
                payload["items"] = _slice(filtered, offset, limit_value)
                payload["total"] = len(filtered)
                return self._send_json(payload)

            if method == "GET" and parsed.path in {"/api/rss", "/api/mock/rss"}:
                items = STORE.rss_items()
                filtered = _filter_items(items, query)
                offset = _parse_int(_first(query, "offset"), 0)
                limit = _first(query, "limit")
                limit_value = _parse_int(limit, len(filtered)) if limit is not None else None
                return self._send_json({
                    "items": _slice(filtered, offset, limit_value),
                    "total": len(filtered),
                    "offset": offset,
                    "limit": limit_value,
                })

            if method == "GET" and parsed.path in {"/api/site-lists", "/api/mock/site-lists"}:
                items = STORE.site_lists_items()
                filtered = _filter_items(items, query)
                offset = _parse_int(_first(query, "offset"), 0)
                limit = _first(query, "limit")
                limit_value = _parse_int(limit, len(filtered)) if limit is not None else None
                return self._send_json({
                    "items": _slice(filtered, offset, limit_value),
                    "total": len(filtered),
                    "offset": offset,
                    "limit": limit_value,
                })

            if method == "GET" and parsed.path in {"/api/linux-do", "/api/mock/linux-do"}:
                items = STORE.linux_do_items()
                filtered = _filter_items(items, query)
                offset = _parse_int(_first(query, "offset"), 0)
                limit = _first(query, "limit")
                limit_value = _parse_int(limit, len(filtered)) if limit is not None else None
                return self._send_json({
                    "items": _slice(filtered, offset, limit_value),
                    "total": len(filtered),
                    "offset": offset,
                    "limit": limit_value,
                })

            if method == "GET" and parsed.path in {"/api/news-with-events", "/api/mock/news-with-events"}:
                items = STORE.news_with_events()
                filtered = _filter_items(items, query)
                offset = _parse_int(_first(query, "offset"), 0)
                limit = _first(query, "limit")
                limit_value = _parse_int(limit, len(filtered)) if limit is not None else None
                return self._send_json({
                    "items": _slice(filtered, offset, limit_value),
                    "total": len(filtered),
                    "offset": offset,
                    "limit": limit_value,
                })

            if method == "GET" and parsed.path in {"/api/events", "/api/mock/events"}:
                items = STORE.events()
                event_id = _first(query, "event_id")
                keyword = _first(query, "q")
                if event_id:
                    items = [item for item in items if item.get("event_id") == event_id]
                if keyword:
                    needle = keyword.casefold()
                    items = [
                        item for item in items
                        if needle in json.dumps(item, ensure_ascii=False).casefold()
                    ]
                offset = _parse_int(_first(query, "offset"), 0)
                limit = _first(query, "limit")
                limit_value = _parse_int(limit, len(items)) if limit is not None else None
                return self._send_json({
                    "items": _slice(items, offset, limit_value),
                    "total": len(items),
                    "offset": offset,
                    "limit": limit_value,
                })

            if method == "GET" and parsed.path in {"/api/embeddings", "/api/mock/embeddings"}:
                offset = _parse_int(_first(query, "offset"), 0)
                limit = _parse_int(_first(query, "limit"), 20, min_value=1)
                key = _first(query, "key")
                return self._send_json(STORE.embeddings(key=key, offset=offset, limit=limit))

            return self._send_error(HTTPStatus.NOT_FOUND, f"Unknown route: {parsed.path}")
        except FileNotFoundError as exc:
            return self._send_error(HTTPStatus.NOT_FOUND, f"Not found: {exc}")
        except json.JSONDecodeError as exc:
            return self._send_error(HTTPStatus.BAD_REQUEST, f"Invalid JSON: {exc}")
        except Exception as exc:
            return self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message, "status": status.value}, status=status)

    def _send_json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(encoded)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve local modnews data as a mock HTTP API.")
    parser.add_argument(
        "--host",
        default=os.environ.get("MODNEWS_MOCK_HOST", "127.0.0.1"),
        help="Host to bind.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MODNEWS_MOCK_PORT", "8000")),
        help="Port to bind.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), MockHandler)
    print(f"Mock server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
