# Amazon Reviews — Full Extraction Playbook

Everything we can try to pull **all** the reviews Amazon will give us, ranked, with
honest trade-offs. Written for the "next term" push. (The `PHD Project.rar` had no
bypass — review *counts* only, no review text, proxy rotation never wired.)

## Hard truths first (so we don't chase impossible things)
- The product page shows ~3–8 reviews; `/product-reviews/<ASIN>/` shows ~10 per page.
- The `?pageNumber=N` **URL doesn't paginate** — it re-serves page 1. Deep pages load
  via a background **AJAX** call.
- **Per-star filters each expose a *different* ~10** → proven **5×** (10 → 50) in our tests.
- **Amazon caps total accessible reviews.** Even a logged-in human can only page ~100
  pages per filter. So "ALL reviews" for a 50k-review product realistically means a few
  **thousand** max — not literally every review. Nobody gets literally-all without
  Amazon's official firehose / Brand access.
- The practical wall is **per-IP throttling**. A trusted (residential) IP + gentle pace
  is the enabler for everything below.

---

## Tier 1 — Free, high-yield, buildable now

**T1. Star × sort × media filter expansion** *(proven 5×)*
- Build several review-source URLs per product: 5 star filters (`filterByStar=five_star…
  one_star`) × sorts (`sortBy=recent|helpful`) × (`mediaType=media_reviews_only`). Dedupe.
- Yield: **~50–150 unique/product** where they exist. Reuses our engine + cooldown loop.
- Effort: **low** (~1h). Ceiling: one page of each filter.

**T2. AJAX `reviews-render` deep pagination** *(the deep route)*
- `POST /hz/reviews-render/ajax/reviews/get/…` with the page's **CSRF token** + cookies +
  form params (`asin`, `pageNumber`, `sortBy`, `filterByStar`, `reviewerType`, `scope`).
- For **each** star filter, paginate 1..N until dry → up to ~**5 × 100 × 10 = ~5,000/product**
  (Amazon's ceiling). This is the deepest programmatic route.
- Returns an `&&&`-delimited JS-command stream → parse the embedded review HTML chunks.
- Effort: **medium–high**; **fragile** (token expiry), throttles hard → needs Tier 2 IP.

---

## Tier 2 — The enabler (unblocks + speeds up Tier 1)

**T3a. Tailscale exit node (home/mobile)** — *free, best free unblock*
- Route the scraper out through a device on your **home broadband** (or phone) → requests
  come from a **residential IP**. Network-layer, so **zero code change**.
- One IP (no rotation) → still per-IP throttle, so pace gently. Also unblocks **Meesho PDPs
  + Myntra**.

**T3b. Residential proxy pool** — *paid, the scale solution*
- Bright Data / Oxylabs / Smartproxy / IPRoyal. Rotating residential IPs defeat throttle at
  scale. Wire into Playwright `proxy={server,username,password}` per context. ~$3–15/GB.

**T3c. Mobile proxies** — highest trust, pricier, lower volume.

---

## Tier 3 — Real-browser / extension (most human, lowest detection) ← your idea

**T4. Playwright persistent real Chrome profile**
- `launch_persistent_context(user_data_dir=<your real Chrome profile>)` → runs as **your
  actual logged-in browser** (real cookies, real fingerprint). Run it on your **home
  machine** = real residential IP for free.
- Navigate review pages, apply star filters, click **"Next page"** (fires Amazon's own
  AJAX), scrape the DOM, dedupe. Looks fully human → hardest to throttle.

**T5. Browser extension / userscript** *(your "extension inside a browser" idea — good one)*
- A **Manifest V3 content script** (or a **Tampermonkey userscript** — faster to build) that
  you install in **your own Chrome**. On `/product-reviews/` pages it auto-clicks through
  star filters + "Next", harvests reviews from the DOM, and POSTs them to a tiny local
  server (or downloads JSON).
- It **is** a real user on a real residential IP → the single most robust **free** way to
  get deep reviews. Semi-automatic: feed it a product-URL list, let it grind.

**T6. Selenium + undetected-chromedriver / nodriver** — alternative stealth stack, same idea
as T4.

---

## Tier 4 — Outsource / datasets (you said not up for these; listed for completeness)
- **T7. Managed scraping APIs** — Apify *Amazon Reviews* actor, Bright Data Web Unlocker,
  ScraperAPI, ZenRows. Paid, reliable, deep.
- **T8. Public datasets** — McAuley **"Amazon Reviews 2023"** (~571M reviews), free historical
  bulk; won't match your exact product set.

---

## Recommended path for next term (free + robust)
1. **Run on a residential IP** — Tailscale exit node from home, or run directly on your home
   machine (T3a / T4).
2. **Deep-extract** via either the **AJAX endpoint** (T2) wired into our engine, **or** a
   **browser extension/userscript** in your real logged-in Chrome (T5).
3. **Iterate star filters** to multiply coverage (T1); dedupe (engine already does).
4. **Pace gently + cooldown loop** (already built).

**Expected yield:** up to ~1,000–5,000 reviews for the most-reviewed products, and *all*
reviews for smaller ones — i.e., essentially everything Amazon exposes to a human, for free.

## What I can build when you say go
- **(A)** Star-filter expansion in adapter/engine — ~1h, works today.
- **(B)** AJAX `reviews-render` client (curl_cffi or Playwright request) with CSRF handling —
  ~½ day, test on a residential IP.
- **(C)** Manifest V3 Chrome extension / Tampermonkey userscript → harvests review pages in
  your real browser to local JSON — ~½ day.
- **(D)** Proxy / Tailscale wiring into `create_browser_context` — ~15 min.
