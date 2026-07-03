from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class ApiClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def available(self) -> bool:
        try:
            self.get("/")
            return True
        except Exception:
            return False

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request("PATCH", path, payload)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.api_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                text = response.read().decode("utf-8")
        except URLError as exc:
            raise RuntimeError(f"API request failed: {exc}") from exc
        return json.loads(text) if text else None
