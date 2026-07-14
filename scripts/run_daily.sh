#!/usr/bin/env bash
set -euo pipefail

cd /opt/newsagent

source .venv/bin/activate
source .env.prod

TODAY="$(date +%F)"

echo "[$(date '+%F %T')] start modnews pipeline"
python -m modnews_pipeline.cli --config config.prod.json

echo "[$(date '+%F %T')] start daily report"
python -m src.main --input output/combined_news.json --date "$TODAY" --config config.prod.json

echo "[$(date '+%F %T')] send feishu"
python -m src.integration.feishu_bot --input data/output/daily_report.md --title "AI 新闻早报 - $TODAY"

echo "[$(date '+%F %T')] done"
