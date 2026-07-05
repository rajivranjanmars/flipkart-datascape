# Plan: residential-proxy rollout & review coverage

Status: setup/infra is done, a real live bug got found and fixed, and Meesho's
review API has been partially reverse-engineered (two candidate endpoints
identified, blocked mid-investigation by rate-limiting — see step 3).

## Important correction: "residential proxy" vs. "home WiFi"

Earlier framing conflated these. A residential *proxy* is only needed when the
machine actually running the scraper has a **datacenter IP** (a cloud VM, CI
box, dev sandbox, etc.) — the proxy's whole job is to make that traffic look
like it's coming from a normal home connection. If the scraper runs directly
on a machine connected to actual home WiFi (e.g. mani's Mac Mini), its
outbound IP **is already residential** — no proxy needed for Myntra's IP-based
block specifically. Confirmed hard evidence for this from this session's dev
sandbox (Oracle Cloud ASN, i.e. a real datacenter IP): Myntra returned a "Site
Maintenance" block page immediately, no proxy in place.

So: step 1 below should be tested by literally running the scraper from
wherever it will really run (home WiFi = no proxy needed to test this). The
`.env` proxy config still exists and works for the case where you *do* end up
running from non-residential infra — it's just not automatically required
just because "there's no proxy set up yet."

## Where things stand

| Site | Categories | Products (top 100/category) | Reviews |
|------|:---:|:---:|:---:|
| Flipkart | 18 | works | works — full pipeline, uncapped (`--max-reviews 0`) |
| Amazon | 10 | works | works, but only with a logged-in session — drop cookies in `secrets/amazon_cookies.json` |
| Myntra | 10 | blocked from datacenter IPs; untested from a real residential connection | **not implemented** — adapter is products-only |
| Meesho | 10 | works (verified live) | **not implemented yet** — two candidate API endpoints identified, see step 3 |

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
- **Fixed a live regression affecting every site** (`scraper/core/browser.py`,
  `_stealth_headers`): the hardcoded `sec-fetch-dest`/`sec-fetch-mode`/
  `sec-fetch-site`/`sec-fetch-user` headers were being applied to *every*
  request on the context via `set_extra_http_headers`. Those headers must
  vary per request type (a script fetch needs `sec-fetch-dest: script`, not
  `document`) — on current Chromium (v149, whatever `playwright install`
  pulls today), setting fixed document-nav values on every request now gets
  rejected outright with `net::ERR_INVALID_ARGUMENT`, which was silently
  killing almost every request past the initial page load (all JS chunks,
  XHR, everything). This explains why a from-scratch Meesho listing fetch was
  returning zero products in this session before the fix — the page's own
  client-side product-fetching JS never ran. Verified fixed: Meesho search
  now returns real products, Flipkart search still works, all 40 unit tests
  still pass. This was a real bug independent of any specific site and was
  probably silently degrading reliability on Flipkart/Amazon too — worth
  keeping an eye on error rates in your next real run to confirm the
  improvement.

## Next steps

### 1. Verify Myntra actually clears the block on the real (home WiFi) machine
No proxy setup needed for this — just run it from wherever the scraper will
really run day to day, from inside the project folder:
```bash
.venv/bin/python -m scraper products --site myntra --output-dir data/runs/myntra_test --max-products 10
```
**Paste the full terminal output back to Claude** (new conversation is fine —
point it at this PLAN.md) so it can tell from the output whether it's real
product data or a block page, and take the next step from there.

- If it works: good, move to full-scale runs (100/category × 10 categories).
  You likely never needed the proxy at all for Myntra specifically.
- If it's **still** blocked even from genuine home WiFi: Myntra's edge
  (Akamai) may be fingerprinting on TLS/JA3, not just source IP — a proxy
  wouldn't fix that either, since a proxy only changes the IP, not the TLS
  handshake. Check `scraper/sites/myntra.py` and `scraper/core/browser.py`'s
  `_STEALTH_JS` / `_stealth_headers` first; may need a TLS-impersonating
  client (e.g. `curl_cffi`) for Myntra specifically instead of Playwright.
- Only reach for `PROXY_SERVER` in `.env` if you end up needing to run/test
  Myntra from non-residential infra (a cloud VM, CI, this kind of dev
  sandbox) — confirmed in this session that a datacenter IP (Oracle Cloud)
  gets an immediate "Site Maintenance" block page, no proxy in place.

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

### 3. Implement Meesho review scraping — partially investigated, needs a residential connection to finish

Findings from live investigation this session (from the dev sandbox's
datacenter IP, after the header-bug fix above):

- Meesho's **search/listing** pages load fine and return real products —
  confirmed extracting real product URLs/titles from
  `https://www.meesho.com/search?q=<query>&searchType=manual`.
- Meesho's **product detail pages** (where reviews live) are protected much
  more tightly. Two things happened, in order, as I probed further:
  1. Navigating directly to a product URL in a fresh session (no prior
     browse history) got an outright Akamai `Access Denied` block page.
  2. Browsing there naturally (search → click a real product link, same
     session/cookies) got further before failing: it triggered
     `POST https://www.meesho.com/api/v1/product/<product_id>` — almost
     certainly **the** product-detail API (this is very likely where
     rating/review data lives) — but it came back `429` with body
     `{"cpr_chlge":"true","t":"..."}`, i.e. a bot-challenge trigger, after a
     few requests in quick succession. Backing off didn't clear it within
     this session.
  3. Also observed (once, before the challenge kicked in):
     `GET https://www.meesho.com/_next/data/<buildId>/<slug>/p/<id>.json`
     returning `200`. This is Next.js's own client-navigation data endpoint —
     it should carry the same props that populate the page (very likely
     including rating/review summary, maybe not full review text/pagination).

**Two concrete candidate endpoints to check next, in priority order:**
1. `_next/data/<buildId>/<product-path>.json` — got a real 200 once; body
   wasn't captured before the session got flagged. Check this first.
2. `POST /api/v1/product/<product_id>` — the more direct product API; got
   challenged before returning real data.

**Do this from an actual residential connection**, not this kind of dev
sandbox — a datacenter IP making several product-page requests in a short
window visibly escalates Meesho's bot mitigation (search pages tolerate it,
product pages don't).

**Copy-paste this whole block** into a terminal, from inside the project
folder (after `./setup.sh` has run at least once so `.venv` exists). It
searches Meesho, clicks into a real product like a normal user would, and
prints the two candidate endpoints' JSON bodies:

```bash
.venv/bin/python - <<'EOF'
import sys
sys.path.insert(0, ".")
from scraper.core.browser import create_browser_context

browser, context = create_browser_context(prime_url=None)
page = context.new_page()

bodies = {}
def on_response(response):
    url = response.url
    if ("_next/data" in url and url.endswith(".json")) or "/api/v1/product/" in url:
        try:
            bodies[url] = (response.status, response.text())
        except Exception as e:
            bodies[url] = (response.status, f"<error: {e}>")
page.on("response", on_response)

page.goto("https://www.meesho.com/search?q=kurti&searchType=manual", timeout=25000, wait_until="domcontentloaded")
page.wait_for_timeout(3000)
link = page.query_selector("a[href*='/p/']")
print("Product link found:", link.get_attribute("href") if link else "NONE")
if link:
    with page.expect_navigation(timeout=20000):
        link.click()
    page.wait_for_timeout(4000)

context.close(); browser.close()

print(f"\n=== Captured {len(bodies)} response(s) ===\n")
for url, (status, body) in bodies.items():
    print(f"--- {status} {url}")
    print(body[:4000])
    print()
EOF
```

**Paste the full printed output back to Claude** (new conversation is fine —
point it at this PLAN.md) — that's enough to confirm the review data's shape
and go implement it directly, no further back-and-forth needed.

- Once the shape of the review data is confirmed, implement it as
  `MeeshoAdapter` review methods (`get_reviews_url` / `build_review_page_url` /
  `parse_reviews`, or a `scrape_reviews_via_session` override if it's cleaner
  to hit the JSON API directly rather than go through HTML page scraping —
  see how `engine.scrape_product_reviews` calls
  `adapter.scrape_reviews_via_session` first if present). Set
  `supports_reviews = True` and add fixture-based tests in
  `tests/test_adapters.py` once the real JSON shape is known.

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

Message me with something like "Myntra worked/didn't work from home WiFi" or
"here's the Meesho product JSON" and I'll pick up directly at the relevant
numbered step above — the groundwork (proxy plumbing, setup scripts, adapter
structure, the header-bug fix) is already in place, so from here it's scoped
implementation, not another round of infra work.
