# Plan: 100 categories × top 100 products × full reviews (Flipkart + Myntra)

## Current goal

Get **all top 100 categories**, **top 100 products** per category, and **all
reviews** for every one of those products — across the sites where this is
actually achievable without extra infra.

## Where things stand

| Site | Categories | Products (top 100/category) | Reviews |
|------|:---:|:---:|:---:|
| Flipkart | **100** | works | works — full pipeline, uncapped (`--max-reviews 0`) |
| Myntra | **100** | works, no proxy needed | **now implemented** — see below |
| Amazon | 10 | works | works, but only with a logged-in session — drop cookies in `secrets/amazon_cookies.json` |
| Meesho | 10 | works | **not implemented** — reviews sit behind a bot-challenge-protected internal API (see Deferred) |

### This session's changes

1. **`FlipkartAdapter.default_targets`** (`scraper/sites/flipkart.py`) expanded
   from 18 → **100** category/subcategory pairs spanning Mobiles &
   Accessories, Electronics, Computers, Large Appliances, Furniture, Home &
   Kitchen, Kids & Baby, Toys & Games, Sports & Fitness, Books, Automotive,
   Bags & Luggage, Jewellery & Watches, Eyewear, Grocery & Gourmet, Health &
   Personal Care, Stationery & Office, Pet Supplies, Musical Instruments, and
   Tools & Home Improvement. No duplicates.

2. **Resolved the Myntra proxy question**: this machine's outbound IP is a
   real residential/mobile connection (Reliance Jio ASN), not a datacenter —
   confirmed via `curl ipinfo.io/org`. Ran
   `scraper products --site myntra --max-products 5` live: **10/10 categories
   succeeded**, returning real product data (titles, prices, ratings, URLs) —
   no proxy needed here. `PROXY_SERVER`/etc. in `.env` remain available for
   whoever ends up running this from a cloud VM/CI box instead.

3. **Implemented Myntra review scraping** (`scraper/sites/myntra.py`).
   Reverse-engineered live: Myntra serves reviews from its own JSON API,
   `GET https://www.myntra.com/web/v1/reviews/batch/{styleId}?size=20&page=N`
   (same-origin, cookie-free — confirmed working with a cold session, no
   prior page visit or login required). The style/product id is the numeric
   segment before `/buy` in the product URL.
   - `get_reviews_url` extracts the style id and builds the batch URL.
   - `build_review_page_url` swaps the `page=` param — the existing generic
     pager in `scraper/core/engine.py` drives pagination and dedup, no
     custom session-scraping override needed.
   - `parse_reviews` unwraps the `<pre>...</pre>`-wrapped JSON Chromium
     renders for a raw API navigation and maps `userRating`/`review`/
     `userName`/`upvotes`/`updatedAt`/`styleAttribute` onto the standard
     review row shape.
   - The `sort`/`rating` query params the frontend UI offers turned out to
     have **no effect** on this endpoint in testing (same unique review set
     regardless) — the API plateaus around **~100-300 reviews per product**
     before returning empty pages, which the generic pager's "stop on empty
     page" logic already handles correctly. This is the same class of
     limitation as Amazon's public review page topping out around 100.
   - `MyntraAdapter.default_targets` also expanded 10 → **100** categories
     (Men/Women/Kids clothing, Footwear, Sports, Accessories, Bags,
     Jewellery, Beauty, Personal Care, Home, Kitchen, Electronics, Toys,
     Books & Stationery, Pet Supplies).
   - Verified end-to-end: `scraper pipeline --site myntra --max-products 3
     --max-reviews 0` across all (now 10, pre-expansion) categories → 30
     products, reviews ranging from 11 to 589 per product, real dates/
     reviewers/body text in the combined CSV. A few products correctly came
     back `empty` (genuinely 0 reviews on that listing).
   - Added fixture-based tests in `tests/test_adapters.py`
     (`MyntraReviewTest`) following the existing Flipkart/Amazon pattern —
     offline, no live network needed. Full suite: **44/44 passing**.

## Next steps

### 1. Full-scale runs
```bash
.venv/bin/python -m scraper pipeline --site flipkart \
  --output-dir data/runs/flipkart_all_100 \
  --max-products 100 --max-reviews 0

.venv/bin/python -m scraper pipeline --site myntra \
  --output-dir data/runs/myntra_all_100 \
  --max-products 100 --max-reviews 0
```
- `--max-reviews 0` = uncapped (scrape every review the site's pagination
  actually exposes — for Myntra that ceiling is site-imposed, ~100-300/product).
- 100 categories × up to 100 products × full review threads is a long job —
  expect **hours, not minutes** per site. Both pipelines are resumable
  (`product_review_status.csv` ledger); safe to interrupt and rerun the same
  command to pick up where it left off.
- Watch `run_report.json` / `run_report.txt` in each output dir for
  per-category failures as it runs.

### 2. QA the output
- Run `tools/quality_check.py` against each output dir.
- Spot-check a sample of category CSVs and review CSVs for completeness.
- Flag any categories that produced 0 products (bad search term / dead
  category) so their `SubcategoryTarget` can be adjusted.

### 3. Tune concurrency if throttled
If either site starts rate-limiting mid-run (visible in `run_report.json` as
repeated failures), drop to the `polite` profile:
```bash
.venv/bin/python -m scraper pipeline --site <site> --profile polite \
  --output-dir <dir> --max-products 100 --max-reviews 0
```

## Deferred

- **Meesho reviews**: product-detail pages (where reviews live) are
  protected by Akamai bot-mitigation that escalates quickly on repeated
  requests — `POST /api/v1/product/<id>` returned a `429` bot-challenge
  after a few requests even from this session's residential IP. Two
  candidate endpoints were identified in prior investigation
  (`_next/data/<buildId>/<slug>/p/<id>.json` and the `/api/v1/product/<id>`
  API) but need slower, more human-like pacing (longer delays between
  product visits) to get past the challenge — worth another pass with much
  lower concurrency/rate before writing `MeeshoAdapter` review methods.
- **Amazon**: works, but only with a logged-in session (cookies in
  `secrets/amazon_cookies.json`). Its 10-category list could also be scaled
  to 100 the same way Flipkart/Myntra were, if wanted.
- **Meesho categories**: still at 10; scaling to 100 is low-value until
  reviews work, but is the same mechanical exercise as Flipkart/Myntra if
  someone wants product-only data at scale sooner.

## How to resume this conversation

Message me with "run the full 100-category Flipkart/Myntra scrape" and I'll
kick off step 1 above, or "here's more on Meesho's bot challenge" if you want
to pick that thread back up — the groundwork (100-category lists, working
Myntra reviews, proxy plumbing) is already in place.
