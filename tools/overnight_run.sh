#!/usr/bin/env bash
# Background scrape orchestrator: Amazon + Meesho (Flipkart already done; Myntra
# IP-blocked here). Smoke first for a fast quality gate, then the full run.
# Amazon reviews are uncapped and paced gently (polite, concurrency 1).
# Each step's failure is logged but does NOT abort the rest of the run.

set -u
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD"

TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="data/runs/bg_${TS}"
mkdir -p "$RUN_DIR"
# Stable pointer so polling can find the active run without guessing the timestamp.
echo "$RUN_DIR" > data/runs/bg_latest.txt
LOG="$RUN_DIR/run.log"

log()  { echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] $*" | tee -a "$LOG"; }
step() {
  local name="$1"; shift
  log "START: $name"
  if "$@" >>"$LOG" 2>&1; then
    log "DONE:  $name"
  else
    log "FAILED($?): $name"
  fi
}

PY="python3 -u -m scraper"

log "Background run starting. RUN_DIR=$RUN_DIR"
log "Plan: smoke gate -> Amazon products(150/cat, balanced) -> Amazon reviews(all, polite, c=1) + Meesho products(150/cat)."

# ---- Phase 0: smoke (fast end-to-end quality proof of both sites) ----
step "smoke-amazon-products"  $PY search "wireless earbuds" --site amazon --output-dir "$RUN_DIR/smoke/amazon" --max-products 3 --profile balanced
step "smoke-amazon-reviews"   $PY reviews --site amazon --product-dir "$RUN_DIR/smoke/amazon" --output-dir "$RUN_DIR/smoke/amazon_reviews" --max-reviews 5 --concurrency 1 --profile polite
step "smoke-meesho-products"  $PY search "kurti" --site meesho --output-dir "$RUN_DIR/smoke/meesho" --max-products 3 --profile balanced
log "SMOKE COMPLETE — early quality sample ready under $RUN_DIR/smoke"

# ---- Phase 1: main run ----
# Amazon products first (fast, logged-out browsing).
step "amazon-products" $PY products --site amazon --output-dir "$RUN_DIR/amazon" --max-products 150 --profile balanced

# Then Meesho products (bg, no account risk) in parallel with the long, gentle
# Amazon review pass (concurrency 1 -> only ~5 browsers total, safe).
( step "meesho-products" $PY products --site meesho --output-dir "$RUN_DIR/meesho" --max-products 150 --profile balanced ) &
MEESHO_PID=$!

step "amazon-reviews" $PY reviews --site amazon --product-dir "$RUN_DIR/amazon" --output-dir "$RUN_DIR/amazon_reviews" --max-reviews 0 --concurrency 1 --profile polite

wait "$MEESHO_PID" 2>/dev/null || true
log "ALL STEPS COMPLETE. RUN_DIR=$RUN_DIR"
