# Plan: residential-proxy rollout & review coverage

Status as of this commit: **setup/infra is done**. What's left is testing and a
couple of scoped implementation tasks that need a real residential IP to do
properly — pick this doc back up once that's available.

## Where things stand

| Site | Categories | Products (top 100/category) | Reviews |
|------|:---:|:---:|:---:|
| Flipkart | 18 | works | works — full pipeline, uncapped (`--max-reviews 0`) |
| Amazon | 10 | works | works, but only with a logged-in session — drop cookies in `secrets/amazon_cookies.json` |
| Myntra | 10 | blocked without a proxy (CDN hard-blocks datacenter IPs) | **not implemented** — adapter is products-only |
| Meesho | 10 | works | **not implemented** — reviews sit behind an internal API this scraper doesn't call |

Infra that's already built and tested:
- Residential proxy support (`scraper/core/proxy.py`, wired through
  `scraper/core/browser.py` and `scraper/core/batch.py`'s `build_session_kwargs`)
  — set `PROXY_SERVER` / `PROXY_USERNAME` / `PROXY_PASSWORD` in `.env` and every
  site/command picks it up automatically. Verified: resolves correctly from env,
  `None` when unset, `.env` auto-loads via `python-dotenv`.
- `setup.sh` — creates a private `.venv`, installs deps + Chromium, prompts once
  for proxy credentials and writes `.env`. Verified end-to-end (fresh venv, pip
  install, real Chromium download all succeeded in a clean copy).
- `Start Scraper.command` — Mac double-click launcher for a non-technical user;
  no Terminal typing required. Same setup.sh underneath.
- Git hygiene: `node_modules/` and the stray 132MB `PHD Project.rar` are
  untracked and gitignored; MIT `LICENSE` added.

## Next steps (do these once you have a residential IP to test from)

### 1. Verify Myntra actually clears the block through the proxy
Set `PROXY_SERVER` (+ user/pass) in `.env` and run:
```bash
.venv/bin/python -m scraper products --site myntra --output-dir data/runs/myntra_test --max-products 10
```
- If it works: good, move to full-scale runs (100/category × 10 categories).
- If it's **still** blocked: Myntra's edge (Akamai) may be fingerprinting on
  TLS/JA3, not just source IP — an IP change alone won't fix that. Check
  `scraper/sites/myntra.py` and `scraper/core/browser.py`'s `_STEALTH_JS` /
  `_stealth_headers` first; may need a TLS-impersonating client (e.g.
  `curl_cffi` or a non-Playwright HTTP path for Myntra specifically) rather than
  just routing Playwright through a proxy.

### 2. Implement Myntra review scraping
Currently `MyntraAdapter.supports_reviews = False` (`scraper/sites/myntra.py:92`).
Myntra's product pages embed a `__myx` JSON blob (already used for listing
data per the README) — check whether that same blob or a paired API also
carries review data for a product page. If so:
- Add review parsing methods to `MyntraAdapter` (mirror `FlipkartAdapter` /
  `AmazonAdapter`'s review methods in `scraper/sites/flipkart.py` /
  `scraper/sites/amazon.py`).
- Set `supports_reviews = True`.
- Add fixture-based tests in `tests/test_adapters.py` (follow the existing
  Flipkart/Amazon review fixture pattern — everything runs offline against
  saved HTML/JSON, no live network needed for the test suite itself).

### 3. Implement Meesho review scraping
Per the README, Meesho reviews are "behind an internal API (not scraped)".
Needs reverse-engineering:
- Open a product page in a real browser with devtools' Network tab open,
  filter for XHR/fetch calls when scrolling to the reviews section.
- Identify the endpoint, required headers/auth (if any), and the product-id
  parameter it expects (likely derivable from the listing data already
  scraped).
- If it's a plain JSON API, this can bypass Playwright's DOM scraping
  entirely for reviews — probably faster than Flipkart/Amazon's approach.
  Add it as `MeeshoAdapter` review methods, same pattern as above.

### 4. Tune concurrency/profile for proxied traffic
Residential proxies are usually slower and sometimes rate-limited per
session. Before running full 100-products × N-categories jobs through a
proxy:
- Test `fast` vs `balanced` profile through the actual proxy and watch for
  timeouts / throttling in the run report.
- If the provider does per-request IP rotation vs. sticky sessions, check
  whether that changes block rates — may be worth adding a
  `PROXY_SESSION_HEADER`-style env var if the provider needs a custom
  header/query param to pin or rotate sessions (not built yet; add to
  `scraper/core/proxy.py` if needed).
- Consider a dedicated `residential` speed profile in `scraper/runner.py`
  (lower concurrency, longer timeouts) if the existing three don't fit.

### 5. Full-scale run + QA
Once 1–4 are solid:
```bash
.venv/bin/python -m scraper pipeline --site flipkart --output-dir data/runs/flipkart_all --max-products 100 --max-reviews 0
.venv/bin/python -m scraper pipeline --site amazon   --output-dir data/runs/amazon_all   --max-products 100 --max-reviews 0
.venv/bin/python -m scraper pipeline --site myntra   --output-dir data/runs/myntra_all   --max-products 100 --max-reviews 0   # after step 2
.venv/bin/python -m scraper pipeline --site meesho   --output-dir data/runs/meesho_all   --max-products 100 --max-reviews 0   # after step 3
```
Then run `tools/quality_check.py` against the outputs and spot-check a sample
of CSVs for completeness before calling it done. Expect this to take hours,
not minutes — it's resumable, so it's fine to run unattended and rerun the
same command to pick up where it left off.

## How to resume this conversation

Message me once you're set up on the residential IP with something like "ready
to test Myntra through the proxy" or "got the Meesho reviews endpoint" and
I'll pick up directly at the relevant numbered step above — the groundwork
(proxy plumbing, setup scripts, adapter structure) is already in place, so
from here it's scoped implementation, not another round of infra work.
