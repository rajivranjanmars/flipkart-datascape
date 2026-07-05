# Datascape — multi-marketplace scraper

An interactive terminal toolkit for collecting **product listings** and
**reviews** from Indian marketplaces into structured CSV + JSON + ZIP outputs.

Supported sites (status from live runs on 2026-06-21):

| Site | Products | Reviews | Live status |
|------|:--------:|:-------:|-------|
| **Flipkart** | ✅ | ✅ | Verified working end-to-end. |
| **Amazon** | ✅ | ✅ with cookies | Listings work logged-out. Reviews need a logged-in session — drop your cookies in `secrets/amazon_cookies.json` (see below). Verified: 40 reviews pulled with cookies. |
| **Myntra** | ⚠️ blocked | — | Parser verified on fixtures, but Myntra's edge **hard-blocks this server's IP** for every URL. Needs a residential proxy / TLS-impersonation to reach live. |
| **Meesho** | ✅ | — | Listings verified (reads `__NEXT_DATA__`). Reviews are behind an internal API (not scraped). |

> **What "live status" means:** Flipkart, Amazon (products), and Meesho (products)
> were run against the real sites and returned correct data. Amazon reviews are
> gated behind login. Myntra blocks datacenter IPs at its CDN edge — the adapter
> code is correct (unit-tested against its `__myx` JSON) but can't be reached from
> a blocked network without a proxy.

### Getting past anti-bot edges

Amazon, Myntra, and Meesho all sit behind bot managers that reject a default
headless browser. The engine ships a stealth fingerprint that clears Amazon and
Meesho from a datacenter IP:

- `navigator.webdriver` and other headless tells are patched out
- the user-agent + client-hint headers are derived from the **real** browser
  version (so they never drift out of sync)
- a realistic timezone/locale and no injected global `Referer` (a global Referer
  deterministically tripped Amazon's 503)
- block pages are detected and retried with backoff
- Amazon keeps resource-loading on (skipping sub-resources trips its edge)

## Highlights

- **One interactive app.** Pick a site, pick a mode, set options, go.
- **Four sites, one fast engine.** All sites share the same browser, concurrency,
  resume, and reporting machinery via a thin per-site adapter.
- **Fast by default.** Blocks images/CSS/fonts, waits for real content instead of
  fixed sleeps, and reuses one browser per worker instead of relaunching per item.
- **Resumable reviews.** Long review jobs write to disk per product and resume
  from where they stopped.
- **Scriptable too.** The same operations are available as flag-based CLI commands.

## Requirements

- Python 3.11+
- Playwright Chromium

## Quick start (Mac, no Terminal needed)

Handing this to someone non-technical? This is the whole flow:

1. Get the project onto their Mac (clone it, or send them a zip/folder) and open the folder in Finder.
2. Double-click **`Start Scraper.command`**.
   - First time only, macOS may show *"cannot be opened because it is from an
     unidentified developer."* Right-click the file → **Open** → **Open** again.
     You only need to do this once.
3. The first run asks for residential proxy details (paste them in, or press
   Enter to skip if you don't have one yet — everything except Myntra works
   with no proxy). Then it installs everything automatically (~1-3 minutes on
   home WiFi) and opens the scraper's menu.
4. Every run after that: just double-click the same file again — no waiting,
   no setup.

## Quick start (Terminal)

```bash
git clone https://github.com/rajivranjanmars/flipkart-datascape.git
cd flipkart-datascape
./setup.sh                     # creates .venv, installs deps + Chromium, sets up .env
.venv/bin/python -m scraper    # or: source .venv/bin/activate && python -m scraper
```

`setup.sh` creates a private `.venv`, installs dependencies into it, runs
`playwright install chromium`, and creates `.env` — prompting once for
residential proxy credentials (needed for Myntra; see
[Residential proxy](#residential-proxy) below) if you don't already have them
set. It's safe to re-run any time; later runs are fast no-ops.

## The interactive app

```bash
python -m scraper        # or:  python main.py
```

You'll get menus:

1. **Choose a marketplace** — Flipkart / Amazon / Myntra / Meesho
2. **Choose what to do**
   - Scrape product listings (all preset categories)
   - Scrape product listings (custom search query or listing URL)
   - Scrape reviews (from a product folder) — *review-capable sites only*
   - Full pipeline (products → reviews)
3. **Set options** — max products/reviews, speed profile, concurrency, output dir
4. **Confirm and run** — live progress, everything written under `data/runs/...`

### Logged-in scraping (cookies)

Some pages (e.g. Amazon's review pages) require a logged-in session. Export your
cookies and the scraper will use them:

1. Log into the site in your own browser.
2. Export cookies with a browser extension (Cookie-Editor / EditThisCookie) — the
   JSON export format is supported as-is, as is the native Playwright format.
3. Save them to `secrets/<site>_cookies.json` (e.g. `secrets/amazon_cookies.json`).
   The `secrets/` folder is **gitignored** — cookies are credentials, never commit them.

The scraper auto-discovers `secrets/<site>_cookies.json`, or pass `--cookies PATH`
explicitly. When cookies load you'll see `Using N auth cookie(s) ... (logged-in session)`.

> Cookies grant access to your account. Treat the file like a password, and sign
> out / rotate the session when you're done.

### Residential proxy

Myntra's CDN hard-blocks datacenter IPs for every URL, so it only becomes reachable
through a residential (or other IP-rotating) proxy. Flipkart, Amazon, and Meesho
all work fine with no proxy.

`./setup.sh` (and `Start Scraper.command` on Mac) already prompts for these
credentials interactively on first run and writes `.env` for you — you don't
need to do anything below unless you want to add or change them later. To do
it by hand instead, copy `.env.example` to `.env` and fill in your provider's
credentials:

```bash
cp .env.example .env
```

```dotenv
PROXY_SERVER=http://gate.your-proxy-provider.com:8000
PROXY_USERNAME=your-username
PROXY_PASSWORD=your-password
```

`.env` is loaded automatically — no flags needed. Every browser session (all
sites, all commands) picks up the proxy once `PROXY_SERVER` is set; leave it
blank or delete `.env` to scrape without a proxy, same as before. `.env` is
gitignored — never commit real credentials.

### Speed profiles

| Profile | Resource blocking | Waits | Concurrency | When to use |
|---------|:-----------------:|:-----:|:-----------:|-------------|
| `fast` | on | minimal | 8 | Quick bulk collection (default for big runs). |
| `balanced` | on | moderate | 4 | Sensible default. |
| `polite` | off | longer | 2 | Gentlest on the site; loads everything. |

## Scriptable CLI

The interactive app launches when you pass no arguments. With arguments it runs
one operation and exits — good for cron/CI.

```bash
# List supported sites
python -m scraper --list-sites

# Product listings for all preset categories
python -m scraper products --site flipkart --output-dir data/runs/fk_products --max-products 100 --profile fast

# A single custom search (or a full listing URL)
python -m scraper search "wireless earbuds" --site amazon --output-dir data/runs/az_search --max-products 50

# Reviews from a product folder (resumable; rerun the same command to resume)
python -m scraper reviews --site flipkart --product-dir data/runs/fk_products --output-dir data/runs/fk_reviews --max-reviews 0 --concurrency 8

# End-to-end: products then reviews
python -m scraper pipeline --site flipkart --output-dir data/runs/fk_all --max-products 50 --max-reviews 50
```

`--max-reviews 0` means uncapped. `--concurrency 0` uses the profile default.

## Architecture

```text
scraper/
├── app.py            # interactive terminal app (rich menus)
├── cli.py            # flag-based CLI (argparse)
├── runner.py         # high-level ops + speed profiles (shared by app & cli)
├── core/             # site-agnostic engine
│   ├── browser.py    #   fast Playwright fetch: resource blocking, selector waits, reusable sessions
│   ├── engine.py     #   generic listing + review pagination
│   ├── batch.py      #   concurrency, resume ledger, reports, zip
│   ├── models.py     #   dataclasses + CSV schemas
│   └── textutils.py  #   slugify / normalize helpers
└── sites/            # per-marketplace adapters (pure site knowledge)
    ├── base.py       #   SiteAdapter contract
    ├── flipkart.py   ├── amazon.py
    └── myntra.py     └── meesho.py
```

To add a marketplace: implement a `SiteAdapter` subclass in `scraper/sites/`,
register it in `scraper/sites/registry.py`, and it inherits all the speed,
concurrency, resume, and reporting machinery for free.

## Why it's faster than a naive scraper

Three concrete levers, all in `core/browser.py` and `core/engine.py`:

1. **Resource blocking** — images, media, fonts, and stylesheets are aborted.
   Only the HTML/JSON we parse is downloaded.
2. **Content-aware waits** — pages wait for a real content selector and a short
   settle, instead of a flat multi-second sleep on every page.
3. **Browser reuse** — each batch worker keeps one browser alive across all its
   items rather than launching (and priming) Chromium per product.

## Output files

**Products** (`<site>` is `flipkart`, `amazon`, ...):

```text
<category>-<subcategory>.csv     # one per preset category
run_report.json / run_report.txt
<site>_product_csvs.zip
```

**Reviews:**

```text
combined_reviews.csv
<category>-<subcategory>-reviews.csv
product_review_status.csv        # the resume ledger
empty_products.csv / failed_products.csv
review_run_report.json / .txt
<site>_review_csvs.zip
```

## Testing

```bash
python -m unittest tests.test_engine tests.test_adapters tests.test_batch tests.test_browser tests.test_cookies
python -m py_compile scraper/*.py scraper/core/*.py scraper/sites/*.py
```

Tests run fully offline using HTML/JSON fixtures and a fake browser session — no
network required.

## Responsible use

Review each site's terms, robots guidance, and applicable rules before scraping
at scale. Prefer the `polite` profile, modest concurrency, and reasonable caps.
The new Amazon/Myntra/Meesho adapters are best-effort and may need tuning.

## License

[MIT](LICENSE)
