#!/usr/bin/env bash
set -euo pipefail

cd /opt/newsagent

source .venv/bin/activate
ENV_FILE="${NEWSAGENT_ENV_FILE:-.env.prod}"
if [ ! -f "$ENV_FILE" ]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi
source "$ENV_FILE"

TODAY="$(date +%F)"
ARCHIVE_DIR="data/archive/$TODAY"

echo "[$(date '+%F %T')] start modnews pipeline"
python -m modnews_pipeline.cli --config config.prod.json

echo "[$(date '+%F %T')] start daily report"
python -m src.main --input output/combined_news.json --date "$TODAY" --config config.prod.json

echo "[$(date '+%F %T')] generate news image cards"
python -m src.integration.news_image_cards --events data/output/enriched_events.json --out-dir data/output/news_cards --limit 30

echo "[$(date '+%F %T')] render news image cards"
node scripts/render-news-images.mjs data/output/news_cards/manifest.json

echo "[$(date '+%F %T')] upload news image cards"
python -m src.integration.feishu_image_upload --manifest data/output/news_cards/manifest.json

echo "[$(date '+%F %T')] send feishu image card"
python -m src.integration.feishu_webhook --manifest data/output/news_cards/manifest.json --report data/output/daily_report.md --title "AI 新闻早报 - $TODAY" --max-items 30

echo "[$(date '+%F %T')] archive daily outputs"
mkdir -p "$ARCHIVE_DIR"
rm -rf "$ARCHIVE_DIR/report_output"
cp -a data/output "$ARCHIVE_DIR/report_output"
mkdir -p "$ARCHIVE_DIR/pipeline_output"
for path in \
  output/combined_news.json \
  output/news_with_events.json \
  output/events.json \
  output/discarded_news.json \
  output/paper_attach_decisions.json \
  output/arxiv_papers.json \
  output/event_history.json \
  output/rss_items.json \
  output/newsnow_items.json \
  output/newsnow_fetch_status.json \
  output/site_lists_items.json \
  output/site_lists_raw.json \
  output/site_lists_fetch_status.json
do
  if [ -f "$path" ]; then
    cp -f "$path" "$ARCHIVE_DIR/pipeline_output/"
  fi
done
cp -f config.prod.json "$ARCHIVE_DIR/config.prod.json"

echo "[$(date '+%F %T')] clean expired archives"
scripts/cleanup_archives.sh

echo "[$(date '+%F %T')] done"
