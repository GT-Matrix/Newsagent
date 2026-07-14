#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_ROOT="${NEWSAGENT_ARCHIVE_ROOT:-data/archive}"
FULL_ARCHIVE_DAYS="${NEWSAGENT_FULL_ARCHIVE_DAYS:-14}"
PIPELINE_ARCHIVE_DAYS="${NEWSAGENT_PIPELINE_ARCHIVE_DAYS:-90}"
REPORT_ARCHIVE_DAYS="${NEWSAGENT_REPORT_ARCHIVE_DAYS:-365}"

for value in "$FULL_ARCHIVE_DAYS" "$PIPELINE_ARCHIVE_DAYS" "$REPORT_ARCHIVE_DAYS"; do
  [[ "$value" =~ ^[0-9]+$ ]] || { echo "Archive retention values must be non-negative integers." >&2; exit 1; }
done

mkdir -p "$ARCHIVE_ROOT"
ARCHIVE_ROOT="$(cd "$ARCHIVE_ROOT" && pwd)"
now_epoch="$(date +%s)"

safe_remove() {
  local path="$1"
  case "$path" in
    "$ARCHIVE_ROOT"/*) rm -rf -- "$path" ;;
    *) echo "Refusing to remove path outside archive root: $path" >&2; exit 1 ;;
  esac
}

for archive_dir in "$ARCHIVE_ROOT"/*; do
  [ -d "$archive_dir" ] || continue
  archive_date="$(basename "$archive_dir")"
  [[ "$archive_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || continue
  archive_epoch="$(date -d "$archive_date" +%s 2>/dev/null || true)"
  [ -n "$archive_epoch" ] || continue
  age_days=$(( (now_epoch - archive_epoch) / 86400 ))

  if [ "$age_days" -gt "$REPORT_ARCHIVE_DAYS" ]; then
    safe_remove "$archive_dir"
    echo "archive_cleanup removed_full_archive=$archive_date age_days=$age_days"
    continue
  fi

  if [ "$age_days" -gt "$PIPELINE_ARCHIVE_DAYS" ]; then
    safe_remove "$archive_dir/pipeline_output"
    rm -f -- "$archive_dir/report_output/daily_report_debug.md" \
      "$archive_dir/report_output/enriched_events.json" \
      "$archive_dir/report_output/evidence_events.json" \
      "$archive_dir/report_output/report_candidates.json" \
      "$archive_dir/report_output/review_candidates.json"
    echo "archive_cleanup compacted_to_report=$archive_date age_days=$age_days"
  fi

  if [ "$age_days" -gt "$FULL_ARCHIVE_DAYS" ]; then
    safe_remove "$archive_dir/report_output/news_cards"
    safe_remove "$archive_dir/report_output/test_image_flow"
    echo "archive_cleanup removed_rendered_cards=$archive_date age_days=$age_days"
  fi
done
