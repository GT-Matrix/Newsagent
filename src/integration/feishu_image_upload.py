from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests


TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
UPLOAD_URL = "https://open.feishu.cn/open-apis/im/v1/images"


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload rendered news card PNG files to Feishu and write image_key values.")
    parser.add_argument("--manifest", default="data/output/news_cards/manifest.json")
    args = parser.parse_args()

    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise SystemExit("FEISHU_APP_ID and FEISHU_APP_SECRET are required for image upload.")

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = get_tenant_access_token(app_id, app_secret)

    uploaded = 0
    for item in manifest.get("items", []):
        if item.get("image_key"):
            continue
        png_path = Path(item["png_path"])
        item["image_key"] = upload_image(token, png_path)
        uploaded += 1

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Uploaded {uploaded} Feishu image(s)")


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    response = requests.post(TOKEN_URL, json={"app_id": app_id, "app_secret": app_secret}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Failed to get tenant_access_token: {payload}")
    return str(payload["tenant_access_token"])


def upload_image(token: str, path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("rb") as file:
        response = requests.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": (path.name, file, "image/png")},
            timeout=60,
        )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Failed to upload image {path}: {payload}")
    return str(payload["data"]["image_key"])


if __name__ == "__main__":
    main()
