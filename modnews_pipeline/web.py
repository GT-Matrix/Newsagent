from __future__ import annotations

import argparse
import os

from modnews.app.server import create_app

app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the modnews API server.")
    parser.add_argument("--host", default=os.environ.get("MODNEWS_PROGRESS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MODNEWS_PROGRESS_PORT", "5055")))
    args = parser.parse_args()
    print(f"modnews api listening on http://{args.host}:{args.port}", flush=True)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
