#!/usr/bin/env bash
# Durable Amazon reviews pass — meant to run in its OWN tmux session so it
# survives Claude Code restarts. Resumable: rerun this exact script to continue
# from product_review_status.csv. Uncapped reviews, gentle pacing (polite, c=1).

set -u
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD"

RUN_DIR="$(cat data/runs/bg_latest.txt)"
LOG="$RUN_DIR/amazon_reviews.log"

echo "[$(date -u +'%F %T UTC')] launching Amazon reviews (uncapped, polite, c=1) for $RUN_DIR" | tee -a "$LOG"
python3 -u -m scraper reviews --site amazon \
  --product-dir "$RUN_DIR/amazon" \
  --output-dir "$RUN_DIR/amazon_reviews" \
  --max-reviews 0 --concurrency 1 --profile polite >>"$LOG" 2>&1
echo "[$(date -u +'%F %T UTC')] Amazon reviews finished (exit $?)" | tee -a "$LOG"
