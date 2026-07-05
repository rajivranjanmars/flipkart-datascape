const fs = require("fs");
const path = require("path");
const PptxGenJS = require("pptxgenjs");

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "OpenAI Codex";
pptx.company = "Rajiv Personal Agent";
pptx.subject = "Flipkart batch scraper academic project report";
pptx.title = "Flipkart data scraps";
pptx.lang = "en-US";
pptx.theme = {
  headFontFace: "Aptos Display",
  bodyFontFace: "Aptos",
  lang: "en-US",
};

const OUT_DIR = path.join(process.cwd(), "artifacts");
const OUT_FILE = path.join(OUT_DIR, "flipkart-data-scraps-report.pptx");

const COLORS = {
  ink: "10233F",
  inkSoft: "4B607C",
  accent: "0F9D8A",
  accentSoft: "DDF6F2",
  gold: "FFB64D",
  goldSoft: "FFF1DA",
  redSoft: "FCE2E2",
  red: "C85B5B",
  bg: "F6F4EF",
  card: "FFFDFC",
  border: "D7D2C8",
  white: "FFFFFF",
  slate: "6D7685",
};

const SLIDE_W = 13.333;
const SLIDE_H = 7.5;

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function addBg(slide, accent = false) {
  slide.background = { color: COLORS.bg };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: SLIDE_W,
    h: 0.28,
    line: { color: accent ? COLORS.gold : COLORS.accent, transparency: 100 },
    fill: { color: accent ? COLORS.gold : COLORS.accent, transparency: 0 },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: SLIDE_H - 0.18,
    w: SLIDE_W,
    h: 0.18,
    line: { color: COLORS.ink, transparency: 100 },
    fill: { color: COLORS.ink, transparency: 0 },
  });
}

function addHeader(slide, title, kicker) {
  addBg(slide);
  slide.addText(kicker.toUpperCase(), {
    x: 0.6,
    y: 0.42,
    w: 2.2,
    h: 0.22,
    fontFace: "Aptos",
    fontSize: 10,
    color: COLORS.accent,
    bold: true,
    charSpace: 0.8,
    margin: 0,
  });
  slide.addText(title, {
    x: 0.6,
    y: 0.66,
    w: 8.8,
    h: 0.48,
    fontFace: "Aptos Display",
    fontSize: 24,
    color: COLORS.ink,
    bold: true,
    margin: 0,
  });
}

function addFooter(slide, index, total) {
  slide.addText(`Flipkart Batch Scraper Report`, {
    x: 0.6,
    y: 7.08,
    w: 3.2,
    h: 0.16,
    fontSize: 8,
    color: COLORS.white,
    margin: 0,
  });
  slide.addText(`${index}/${total}`, {
    x: 12.1,
    y: 7.05,
    w: 0.6,
    h: 0.18,
    fontSize: 8,
    color: COLORS.white,
    align: "right",
    margin: 0,
  });
}

function addBulletList(slide, items, opts = {}) {
  const runs = [];
  items.forEach((item, idx) => {
    runs.push({
      text: item,
      options: { bullet: { indent: 12 } },
    });
    if (idx !== items.length - 1) {
      runs.push({ text: "\n" });
    }
  });
  slide.addText(runs, {
    x: opts.x ?? 0.8,
    y: opts.y ?? 1.55,
    w: opts.w ?? 5.2,
    h: opts.h ?? 4.7,
    fontFace: "Aptos",
    fontSize: opts.fontSize ?? 17,
    color: COLORS.ink,
    breakLine: false,
    paraSpaceAfterPt: 10,
    valign: "top",
    margin: 0.06,
  });
}

function addCard(slide, x, y, w, h, title, body, tone = "accent", opts = {}) {
  const fillColor = tone === "gold" ? COLORS.goldSoft : tone === "red" ? COLORS.redSoft : COLORS.card;
  const edge = tone === "gold" ? COLORS.gold : tone === "red" ? COLORS.red : COLORS.accent;
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.08,
    line: { color: edge, pt: 1.3 },
    fill: { color: fillColor },
  });
  slide.addText(title, {
    x: x + 0.18,
    y: y + 0.14,
    w: w - 0.36,
    h: 0.22,
    fontSize: opts.titleFontSize ?? 13,
    bold: true,
    color: COLORS.ink,
    margin: 0,
  });
  slide.addText(body, {
    x: x + 0.18,
    y: y + 0.42,
    w: w - 0.36,
    h: h - 0.54,
    fontSize: opts.bodyFontSize ?? 11.5,
    color: COLORS.inkSoft,
    valign: "top",
    margin: 0,
  });
}

function addCodePanel(slide, x, y, w, h, title, code, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.05,
    line: { color: "C6D1DB", pt: 1 },
    fill: { color: "F3F6FA" },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x,
    y,
    w,
    h: 0.33,
    line: { color: COLORS.ink, transparency: 100 },
    fill: { color: COLORS.ink },
  });
  slide.addText(title, {
    x: x + 0.12,
    y: y + 0.08,
    w: w - 0.24,
    h: 0.14,
    fontSize: 10,
    color: COLORS.white,
    bold: true,
    margin: 0,
  });
  slide.addText(code, {
    x: x + 0.14,
    y: y + 0.42,
    w: w - 0.28,
    h: h - 0.52,
    fontFace: "Courier New",
    fontSize: opts.fontSize ?? 9.5,
    color: COLORS.ink,
    margin: 0,
    breakLine: false,
    valign: "top",
  });
}

function addStageBox(slide, x, y, w, h, title, lines, tone = "accent", opts = {}) {
  addCard(slide, x, y, w, h, title, lines.join("\n"), tone, opts);
}

function addArrow(slide, x, y, w) {
  slide.addShape(pptx.ShapeType.chevron, {
    x,
    y,
    w,
    h: 0.26,
    line: { color: COLORS.accent, transparency: 100 },
    fill: { color: COLORS.accent },
  });
}

function addSectionBand(slide, label, x, y, w) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.28,
    rectRadius: 0.05,
    line: { color: COLORS.accent, transparency: 100 },
    fill: { color: COLORS.accentSoft },
  });
  slide.addText(label, {
    x: x + 0.12,
    y: y + 0.05,
    w: w - 0.24,
    h: 0.14,
    fontSize: 10,
    color: COLORS.accent,
    bold: true,
    margin: 0,
  });
}

function buildSlides() {
  const totalSlides = 14;

  {
    const slide = pptx.addSlide();
    addBg(slide, true);
    slide.addShape(pptx.ShapeType.rect, {
      x: 0.62,
      y: 0.7,
      w: 5.55,
      h: 5.95,
      line: { color: COLORS.accent, transparency: 100 },
      fill: { color: COLORS.card },
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 6.45,
      y: 0.9,
      w: 6.15,
      h: 5.55,
      rectRadius: 0.06,
      line: { color: COLORS.gold, pt: 1.4 },
      fill: { color: COLORS.goldSoft },
    });
    slide.addText("Flipkart data scraps", {
      x: 0.92,
      y: 1.12,
      w: 4.7,
      h: 0.82,
      fontFace: "Aptos Display",
      fontSize: 28,
      bold: true,
      color: COLORS.ink,
      margin: 0,
    });
    slide.addText("Batch product scrapper and batch review scrapper project report", {
      x: 0.92,
      y: 2.1,
      w: 4.7,
      h: 0.82,
      fontSize: 18,
      color: COLORS.inkSoft,
      margin: 0,
    });
    slide.addText("Academic viva / demo presentation\nRepository focus: batch flow only, not main.py", {
      x: 0.92,
      y: 3.08,
      w: 4.6,
      h: 0.72,
      fontSize: 15,
      color: COLORS.accent,
      margin: 0,
    });
    addCard(slide, 0.92, 4.3, 2.1, 1.06, "Name", "<Your Name>");
    addCard(slide, 3.18, 4.3, 2.1, 1.06, "College / Dept", "<Your College>");
    addCard(slide, 0.92, 5.52, 2.1, 0.84, "Guide", "<Mentor Name>");
    addCard(slide, 3.18, 5.52, 2.1, 0.84, "Date", "<Presentation Date>");
    slide.addText("Report Highlights", {
      x: 6.82,
      y: 1.18,
      w: 2.8,
      h: 0.3,
      fontSize: 14,
      bold: true,
      color: COLORS.ink,
      margin: 0,
    });
    addBulletList(slide, [
      "Two-stage pipeline: product discovery -> review enrichment",
      "Actual function names and supporting modules from the batch flow",
      "Technology stack, data flow, error handling, testing, and limits",
      "Outputs: CSV, JSON, TXT reports, ZIP artifacts, and resume ledger",
    ], { x: 6.82, y: 1.6, w: 5.0, h: 3.2, fontSize: 16 });
    addCard(slide, 6.82, 5.08, 5.0, 1.0, "Scope note", "Slides are based on scraper/batch_product_scraper.py, scraper/batch_review_scraper.py, and the direct helper modules used in that workflow.", "accent", { bodyFontSize: 10.2 });
    addFooter(slide, 1, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Project Context And Objective", "Project Overview");
    addBulletList(slide, [
      "The project automates large-scale Flipkart scraping in two batch stages instead of one ad hoc single-URL run.",
      "Stage 1 discovers products across 18 configured subcategories through SUBCATEGORY_TARGETS in scraper/batch_product_scraper.py.",
      "Stage 2 reads those product CSVs and enriches them with structured customer reviews using scraper/batch_review_scraper.py.",
      "The academic value is the complete data pipeline: collection, normalization, persistence, recovery, and validation.",
    ], { x: 0.82, y: 1.55, w: 6.0, h: 4.6, fontSize: 16.2 });
    addCard(slide, 7.1, 1.5, 2.35, 1.05, "Pipeline Goal", "Convert raw Flipkart pages into reusable CSV and report artifacts.", "accent", { bodyFontSize: 10.5 });
    addCard(slide, 9.65, 1.5, 2.35, 1.22, "Primary Users", "Student researcher, evaluator, or analyst who needs category-wise product and review datasets.", "accent", { bodyFontSize: 9.9 });
    addCard(slide, 7.1, 2.8, 4.9, 1.05, "Why Batch Instead Of main.py?", "main.py is a single-run entrypoint. The batch design adds multiple categories, concurrency, resumable review scraping, and packaged run artifacts.", "gold");
    addCard(slide, 7.1, 4.15, 4.9, 1.05, "Key Outputs", "Product CSVs, review CSVs, JSON/TXT run reports, ZIP archives, and a review-status ledger for resume mode.");
    addFooter(slide, 2, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Technology Stack Used In The Batch Flow", "Stack");
    addCard(slide, 0.8, 1.52, 2.7, 1.18, "Python", "Main language for scraping logic, CLI handling, data classes, and artifact writing.", "accent", { bodyFontSize: 10.2 });
    addCard(slide, 3.68, 1.52, 2.7, 1.18, "Playwright", "Browser automation used by create_browser_context() and get_page_html().", "accent", { bodyFontSize: 10.2 });
    addCard(slide, 6.56, 1.52, 2.7, 1.18, "BeautifulSoup + lxml", "DOM parsing stack used in product and review extraction.", "accent", { bodyFontSize: 10.2 });
    addCard(slide, 9.44, 1.52, 2.7, 1.18, "Parallel + artifacts", "ProcessPoolExecutor, csv, json, and zipfile support concurrent jobs and stored outputs.", "accent", { bodyFontSize: 10.2 });
    addSectionBand(slide, "Important runtime defaults from code", 0.8, 3.05, 3.3);
    addBulletList(slide, [
      "Product batch: DEFAULT_MAX_PRODUCTS = 100, DEFAULT_CONCURRENCY = 4",
      "Review batch: DEFAULT_MAX_REVIEWS_PER_PRODUCT = 100, DEFAULT_CONCURRENCY = 16",
      "Product page stopping controls: MAX_EMPTY_PAGES = 3, MAX_PAGES_PER_SUBCATEGORY = 12",
      "Review retry controls: DEFAULT_RETRIES = 2, empty-page retry wait = 8.0 seconds",
    ], { x: 0.82, y: 3.42, w: 6.0, h: 2.8, fontSize: 15.5 });
    addCodePanel(slide, 7.2, 3.1, 5.25, 2.65, "requirements.txt + concurrency signals", [
      "requests",
      "cloudscraper",
      "playwright",
      "beautifulsoup4",
      "pandas",
      "tqdm",
      "lxml",
      "",
      "from concurrent.futures import",
      "    ProcessPoolExecutor, as_completed",
    ].join("\n"));
    addFooter(slide, 3, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Repository Architecture For Batch Scraping", "Architecture");
    addStageBox(slide, 0.8, 1.75, 2.1, 1.2, "batch_product_scraper.py", [
      "Search URL creation",
      "Product extraction",
      "Category CSV writing",
    ], "accent", { titleFontSize: 10.8, bodyFontSize: 9.8 });
    addStageBox(slide, 3.25, 1.75, 2.1, 1.2, "utils.py", [
      "create_browser_context()",
      "get_page_html()",
      "Shared Playwright runtime",
    ], "gold", { titleFontSize: 10.8, bodyFontSize: 9.6 });
    addStageBox(slide, 5.7, 1.75, 2.1, 1.2, "batch_review_scraper.py", [
      "Reads product CSVs",
      "Scrapes reviews",
      "Resumable outputs",
    ], "accent", { titleFontSize: 10.8, bodyFontSize: 9.8 });
    addStageBox(slide, 8.15, 1.75, 2.1, 1.2, "review_scraper.py", [
      "Review page URL logic",
      "Review block parser",
      "Metadata extraction",
    ], "gold", { titleFontSize: 10.8, bodyFontSize: 9.6 });
    addStageBox(slide, 10.6, 1.75, 1.95, 1.2, "Artifacts", [
      "CSV",
      "JSON/TXT reports",
      "ZIP packages",
    ], "accent", { titleFontSize: 10.8, bodyFontSize: 9.6 });
    addArrow(slide, 2.93, 2.18, 0.22);
    addArrow(slide, 5.38, 2.18, 0.22);
    addArrow(slide, 7.83, 2.18, 0.22);
    addArrow(slide, 10.28, 2.18, 0.22);
    addCard(slide, 0.82, 3.5, 3.8, 2.08, "Product Stage Inputs", "SUBCATEGORY_TARGETS defines 18 category-subcategory pairs. Each pair is converted into a Flipkart search URL through build_search_url(), then paginated by build_page_url().");
    addCard(slide, 4.78, 3.5, 3.8, 2.08, "Review Stage Inputs", "load_product_inputs() reads every generated product CSV, validates required columns, and creates ProductInput objects used by review workers.");
    addCard(slide, 8.74, 3.5, 3.8, 2.08, "Core Design Pattern", "Dataclasses capture stable row schemas, helper functions isolate scraping logic, and artifact writers separate data collection from persistence.");
    addFooter(slide, 4, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "End-To-End Workflow: Batch Product Scrapper", "Workflow 1");
    addStageBox(slide, 0.78, 2.1, 1.95, 1.08, "1. Target List", [
      "SUBCATEGORY_TARGETS",
      "18 fixed subcategories",
    ], "accent", { titleFontSize: 11.4, bodyFontSize: 9.6 });
    addStageBox(slide, 3.0, 2.1, 2.1, 1.08, "2. Query Build", [
      "build_search_url()",
      "build_page_url()",
    ], "gold", { titleFontSize: 11.4, bodyFontSize: 9.6 });
    addStageBox(slide, 5.38, 2.1, 2.18, 1.08, "3. Page Fetch", [
      "create_browser_context()",
      "get_page_html()",
    ], "accent", { titleFontSize: 11.4, bodyFontSize: 9.6 });
    addStageBox(slide, 7.84, 2.1, 2.18, 1.08, "4. Record Parse", [
      "parse_product_records()",
      "extract_title(), extract_counts()",
    ], "gold", { titleFontSize: 11.4, bodyFontSize: 9.4 });
    addStageBox(slide, 10.3, 2.1, 2.18, 1.08, "5. Artifact Write", [
      "write_category_csv()",
      "write_run_artifacts()",
    ], "accent", { titleFontSize: 11.2, bodyFontSize: 9.4 });
    addArrow(slide, 2.78, 2.49, 0.18);
    addArrow(slide, 5.16, 2.49, 0.18);
    addArrow(slide, 7.62, 2.49, 0.18);
    addArrow(slide, 10.08, 2.49, 0.18);
    addBulletList(slide, [
      "collect_products_for_target() loops across up to 12 listing pages per subcategory.",
      "The scraper retries missing HTML responses, increments empty_pages, and stops after MAX_EMPTY_PAGES consecutive misses or empty results.",
      "Duplicate product URLs are filtered through seen_urls so each listing row stays unique.",
      "scrape_and_write_target() wraps one target, while run_batch() distributes all targets through ProcessPoolExecutor.",
    ], { x: 0.86, y: 4.0, w: 6.0, h: 2.55, fontSize: 14.2 });
    addCodePanel(slide, 7.1, 3.82, 5.2, 2.3, "CLI example from docs/BATCH_WORKFLOWS.md", [
      "python -m scraper.batch_product_scraper \\",
      "  --output-dir data/runs/20260522_products \\",
      "  --max-products 100 \\",
      "  --concurrency 4 \\",
      "  --retries 2",
    ].join("\n"));
    addFooter(slide, 5, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Important Functions In Product Discovery", "Function Detail");
    addSectionBand(slide, "High-impact functions from scraper/batch_product_scraper.py", 0.8, 1.42, 4.25);
    addCard(slide, 0.82, 1.85, 3.35, 0.92, "slugify(value)", "Creates safe file names like beauty-care-women-skincare.csv.", "accent", { bodyFontSize: 10.5 });
    addCard(slide, 4.4, 1.85, 3.35, 0.92, "parse_product_records(...)", "Converts one listing page HTML into normalized ProductRecord rows.", "accent", { bodyFontSize: 10.5 });
    addCard(slide, 7.98, 1.85, 2.9, 0.92, "collect_products_for_target(...)", "Handles retry, pagination, and de-duplication.", "accent", { titleFontSize: 11.3, bodyFontSize: 9.9 });
    addCard(slide, 11.08, 1.85, 1.45, 0.92, "run_batch(...)", "Runs subcategory jobs in parallel.", "accent", { titleFontSize: 10.8, bodyFontSize: 9.4 });
    addCard(slide, 0.82, 3.05, 3.35, 0.92, "extract_title(...)", "Chooses the cleanest title from anchor, card text, or URL slug fallback.", "accent", { bodyFontSize: 10.0 });
    addCard(slide, 4.4, 3.05, 3.35, 0.92, "extract_product_id(...)", "Parses product ID from query pid or /p/<id> path.", "accent", { bodyFontSize: 10.0 });
    addCard(slide, 7.98, 3.05, 2.9, 0.92, "write_category_csv(...)", "Writes one CSV per category-subcategory pair.", "accent", { titleFontSize: 11.3, bodyFontSize: 9.9 });
    addCard(slide, 11.08, 3.05, 1.45, 0.92, "write_run_artifacts(...)", "Writes JSON, TXT, and ZIP outputs.", "accent", { titleFontSize: 10.4, bodyFontSize: 9.0 });
    addCodePanel(slide, 0.82, 4.3, 5.6, 2.2, "Snippet: parse_product_records()", [
      "for anchor in soup.find_all('a', href=True):",
      "    if '/p/' not in href:",
      "        continue",
      "    product_url = absolute_product_url(href)",
      "    card = find_card_container(anchor)",
      "    records.append(ProductRecord(",
      "        title=extract_title(anchor, card, product_url),",
      "        product_id=extract_product_id(product_url),",
      "    ))",
    ].join("\n"));
    addCard(slide, 6.7, 4.3, 5.7, 2.2, "Why this stage matters", "This stage is responsible for dataset breadth. If product discovery is weak or duplicate-prone, the downstream review stage inherits incomplete coverage.");
    addFooter(slide, 6, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Product Batch Outputs And Stored Artifacts", "Output Design");
    addBulletList(slide, [
      "One CSV per subcategory with 10 normalized columns: category, subcategory, title, price, rating, ratings_count, reviews_count, product_url, product_id, and source_url.",
      "run_report.json contains structured run metadata and per-subcategory status.",
      "run_report.txt produces a simple readable audit log.",
      "flipkart_product_csvs.zip packages all CSVs and reports for transfer or archival.",
    ], { x: 0.82, y: 1.55, w: 6.1, h: 3.0, fontSize: 16.2 });
    addCodePanel(slide, 7.2, 1.52, 5.0, 2.15, "Snippet: write_run_artifacts()", [
      "report = {",
      "  'summary': {",
      "    'total_subcategories': len(results),",
      "    'successful_subcategories': len(successful_results),",
      "    'total_rows': sum(result.row_count for result in results),",
      "  },",
      "}",
      "zip_path = output_dir / 'flipkart_product_csvs.zip'",
    ].join("\n"));
    addCard(slide, 7.2, 3.95, 2.3, 1.16, "Status values", "success\nempty\nfailed", "gold");
    addCard(slide, 9.72, 3.95, 2.48, 1.16, "Evidence for viva", "Outputs show the scraper is not only collecting data but also documenting run quality.");
    addCard(slide, 0.82, 4.85, 3.65, 1.34, "Sample file naming", "beauty-care-women-skincare.csv\nelectronics-smartphones.csv\nwearable-devices-smartwatches.csv");
    addCard(slide, 4.68, 4.85, 3.65, 1.34, "Normalization benefit", "Downstream stages receive predictable, machine-readable records instead of raw HTML fragments.");
    addCard(slide, 8.54, 4.85, 3.65, 1.34, "Testing evidence", "tests/test_batch_product_scraper.py validates URL building, slugification, parsing, and artifact generation.");
    addFooter(slide, 7, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "End-To-End Workflow: Batch Review Scrapper", "Workflow 2");
    addStageBox(slide, 0.76, 2.05, 2.12, 1.08, "1. Product CSV Input", [
      "load_product_inputs()",
      "validates required fields",
    ], "accent", { titleFontSize: 11.2, bodyFontSize: 9.6 });
    addStageBox(slide, 3.1, 2.05, 2.2, 1.08, "2. Resume Filter", [
      "load_completed_product_keys()",
      "skips terminal states",
    ], "gold", { titleFontSize: 11.2, bodyFontSize: 9.6 });
    addStageBox(slide, 5.56, 2.05, 2.3, 1.08, "3. Review Fetch", [
      "scrape_product_reviews()",
      "page retry logic",
    ], "accent", { titleFontSize: 11.1, bodyFontSize: 9.6 });
    addStageBox(slide, 8.1, 2.05, 2.34, 1.08, "4. Row Normalize", [
      "normalize_review_rows()",
      "caps or uncaps reviews",
    ], "gold", { titleFontSize: 11.0, bodyFontSize: 9.4 });
    addStageBox(slide, 10.68, 2.05, 1.84, 1.08, "5. Incremental Write", [
      "append_product_artifacts()",
      "status ledger update",
    ], "accent", { titleFontSize: 10.6, bodyFontSize: 9.0 });
    addArrow(slide, 2.9, 2.43, 0.18);
    addArrow(slide, 5.32, 2.43, 0.18);
    addArrow(slide, 7.74, 2.43, 0.18);
    addArrow(slide, 10.16, 2.43, 0.18);
    addBulletList(slide, [
      "run_review_batch() can continue interrupted runs because completed product IDs are persisted in product_review_status.csv.",
      "Review pages are discovered by get_reviews_url() and _build_review_page_url() from scraper/review_scraper.py.",
      "For first-page empty results, the code performs an additional delayed retry using empty_retry_wait_seconds.",
      "The stage writes combined review CSVs, per-subcategory review CSVs, failed and empty ledgers, plus JSON/TXT reports and ZIP output.",
    ], { x: 0.86, y: 3.9, w: 6.25, h: 2.45, fontSize: 15.2 });
    addCodePanel(slide, 7.3, 3.82, 5.05, 2.3, "CLI example from docs/BATCH_WORKFLOWS.md", [
      "python -m scraper.batch_review_scraper \\",
      "  --product-dir data/runs/20260522_products \\",
      "  --output-dir data/runs/20260522_reviews \\",
      "  --max-reviews 0 \\",
      "  --concurrency 1 \\",
      "  --retries 3",
    ].join("\n"));
    addFooter(slide, 8, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Important Functions In Review Scraping And Parsing", "Function Detail");
    addCard(slide, 0.82, 1.62, 3.1, 0.92, "load_product_inputs(...)", "Reads product CSVs and builds ProductInput records.", "accent", { bodyFontSize: 10.2 });
    addCard(slide, 4.12, 1.62, 3.1, 0.92, "scrape_product_reviews(...)", "Drives retry logic, pagination, waits, and result status creation.", "accent", { bodyFontSize: 9.9 });
    addCard(slide, 7.42, 1.62, 3.1, 0.92, "normalize_review_rows(...)", "Copies product metadata onto raw review dictionaries.", "accent", { bodyFontSize: 10.0 });
    addCard(slide, 10.72, 1.62, 1.8, 0.92, "append_product_artifacts(...)", "Persists each finished product immediately.", "accent", { titleFontSize: 10.6, bodyFontSize: 8.9 });
    addCard(slide, 0.82, 2.82, 3.1, 0.92, "get_reviews_url(...)", "Converts /p/ product path into /product-reviews/ path.", "accent", { bodyFontSize: 10.0 });
    addCard(slide, 4.12, 2.82, 3.1, 0.92, "_get_rating_nodes(...)", "Finds true review rating nodes with one-decimal validation.", "accent", { bodyFontSize: 9.9 });
    addCard(slide, 7.42, 2.82, 3.1, 0.92, "_parse_review_block(...)", "Extracts title, body, reviewer, date, helpful count, city, and badge.", "accent", { bodyFontSize: 9.6 });
    addCard(slide, 10.72, 2.82, 1.8, 0.92, "_extract_reviews_from_page(...)", "Deduplicates parsed review blocks per page.", "accent", { titleFontSize: 10.4, bodyFontSize: 8.8 });
    addCodePanel(slide, 0.82, 4.1, 5.55, 2.28, "Snippet: scrape_product_reviews()", [
      "while max_pages is None or page_number <= max_pages:",
      "    review_page_url = _build_review_page_url(...)",
      "    html = get_page_html(context, review_page_url)",
      "    page_reviews = _extract_reviews_from_page(...)",
      "    if page_number == 1 and not page_reviews:",
      "        retry_html = get_page_html(..., wait_seconds=empty_retry_wait_seconds)",
      "    raw_reviews.extend(page_reviews)",
    ].join("\n"));
    addCodePanel(slide, 6.74, 4.1, 5.55, 2.28, "Snippet: _parse_review_block()", [
      "rating_text = texts[0]",
      "title = texts[2] if len(texts) > 2 else ''",
      "variant_match = _VARIANT_PATTERN.fullmatch(texts[3])",
      "body = texts[body_index] if len(texts) > body_index else ''",
      "reviewer = texts[reviewer_index] if len(texts) > reviewer_index else ''",
      "return {'rating': float(rating_text), 'title': title, ...}",
    ].join("\n"));
    addFooter(slide, 9, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Data Flow And Persistence Model", "Data Flow");
    addStageBox(slide, 0.8, 2.0, 2.2, 1.05, "Search Pages", [
      "Flipkart listing HTML",
      "product anchors",
    ]);
    addStageBox(slide, 3.25, 2.0, 2.2, 1.05, "ProductRecord", [
      "normalized listing row",
      "written per subcategory",
    ], "gold");
    addStageBox(slide, 5.7, 2.0, 2.2, 1.05, "ProductInput", [
      "CSV -> dataclass",
      "review work item",
    ]);
    addStageBox(slide, 8.15, 2.0, 2.2, 1.05, "ReviewRow", [
      "product + review metadata",
      "combined output row",
    ], "gold");
    addStageBox(slide, 10.6, 2.0, 2.0, 1.05, "Reports", [
      "status ledgers",
      "JSON/TXT/ZIP",
    ]);
    addArrow(slide, 3.0, 2.38, 0.18);
    addArrow(slide, 5.45, 2.38, 0.18);
    addArrow(slide, 7.9, 2.38, 0.18);
    addArrow(slide, 10.35, 2.38, 0.18);
    addBulletList(slide, [
      "The product stage transforms raw page HTML into ProductRecord rows with a stable schema.",
      "The review stage rehydrates those rows into ProductInput objects so metadata is preserved during review scraping.",
      "normalize_review_rows() enriches every raw review dictionary with product-level fields before writing ReviewRow entries.",
      "This design keeps the dataset relational: one product listing can produce many review rows without losing category, price, or source context.",
    ], { x: 0.86, y: 3.78, w: 6.15, h: 2.5, fontSize: 15.4 });
    addCard(slide, 7.28, 3.76, 5.0, 2.5, "Resume-aware persistence", "append_product_artifacts() writes combined_reviews.csv, a subcategory review CSV, and product_review_status.csv immediately after each product completes. load_completed_product_keys() later uses that ledger to skip already completed product IDs or URLs.");
    addFooter(slide, 10, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Error Handling, Retry Logic, And Reliability Controls", "Resilience");
    addCard(slide, 0.82, 1.55, 3.75, 1.12, "Product stage controls", "collect_products_for_target() retries empty HTML responses, tracks consecutive empty pages, and stops after MAX_EMPTY_PAGES to avoid infinite loops.", "gold");
    addCard(slide, 4.8, 1.55, 3.75, 1.12, "Review stage controls", "scrape_product_reviews() retries page loads, performs a first-page delayed retry for empty review results, and marks hard failures with explicit status and error text.");
    addCard(slide, 8.78, 1.55, 3.75, 1.12, "Graceful status model", "Both batch stages record success, empty, and failed outcomes instead of silently dropping bad cases.");
    addBulletList(slide, [
      "Exception handling wraps both scrape_and_write_target() and scrape_product_reviews() so errors are persisted as structured run results.",
      "Failed or empty review products are copied into failed_products.csv or empty_products.csv for later inspection.",
      "log_progress(), utc_now(), and format_elapsed_seconds() produce stable UTC runtime logs for long-running jobs.",
      "STATUS_TERMINAL_STATES = {'success', 'empty', 'failed'} defines what counts as fully processed during resume mode.",
    ], { x: 0.86, y: 3.1, w: 6.1, h: 2.8, fontSize: 15.2 });
    addCodePanel(slide, 7.25, 3.05, 5.05, 2.75, "Snippet: terminal-state resume logic", [
      "status = row.get('status', '').strip().lower()",
      "if status not in STATUS_TERMINAL_STATES:",
      "    continue",
      "product_id = row.get('product_id', '').strip()",
      "product_url = row.get('product_url', '').strip()",
      "key = product_id or product_url",
      "completed_keys.add(key)",
    ].join("\n"));
    addFooter(slide, 11, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Testing Strategy And Verification Evidence", "Testing");
    addBulletList(slide, [
      "The repository contains dedicated unit tests for both batch stages: tests/test_batch_product_scraper.py and tests/test_batch_review_scraper.py.",
      "Product tests verify target-list integrity, query encoding, slug generation, URL-title fallback, HTML parsing, and artifact creation.",
      "Review tests verify product-input loading, review normalization, uncapped review mode, incremental artifact persistence, resume behavior, and CLI wait options.",
      "Current verification run in this session: python3 -m unittest tests.test_batch_product_scraper tests.test_batch_review_scraper -> 13 tests, all passed.",
    ], { x: 0.82, y: 1.55, w: 6.35, h: 3.35, fontSize: 15.0 });
    addCard(slide, 7.4, 1.52, 4.85, 1.15, "Representative product tests", "build_search_url query encoding\nparse_product_records listing-card extraction\nwrite_csv_and_run_artifacts()", "accent", { bodyFontSize: 10.8 });
    addCard(slide, 7.4, 2.92, 4.85, 1.48, "Representative review tests", "normalize_review_rows caps and metadata copy\nappend_product_artifacts incremental progress\nrun_review_batch resume skip behavior", "accent", { bodyFontSize: 10.4 });
    addCodePanel(slide, 7.4, 4.62, 4.85, 1.6, "Observed command result", [
      "Ran 13 tests in 0.010s",
      "",
      "OK",
    ].join("\n"));
    addFooter(slide, 12, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Current Limitations In The Batch Scraper", "Limitations");
    addCard(slide, 0.82, 1.62, 3.75, 1.26, "Flipkart DOM dependency", "The review parser depends on the current React Native Web structure, selectors like div.css-146c3p1, and relative-date text patterns. Major frontend changes could break parsing.", "red");
    addCard(slide, 4.8, 1.62, 3.75, 1.26, "No anti-blocking escalation", "The current code uses Playwright and browser-like headers, but it does not implement rotating proxies, adaptive backoff, or captcha handling.", "red");
    addCard(slide, 8.78, 1.62, 3.75, 1.26, "Limited semantic validation", "The parser checks structure and simple text patterns, but it does not verify whether a review belongs to a variant beyond the visible page text.", "red");
    addBulletList(slide, [
      "Product scraping stops after configured page and empty-response thresholds, so very large categories may be sampled rather than fully exhausted.",
      "Review count pagination uses REVIEWS_PER_PAGE_GUESS = 10, which assumes the current site page size remains stable.",
      "Tests are unit-style and deterministic; they do not run live end-to-end browser scraping against Flipkart in CI.",
      "The tool writes CSV-based artifacts only; there is no database layer or analytics dashboard in this repository.",
    ], { x: 0.86, y: 3.28, w: 11.45, h: 2.7, fontSize: 15.3 });
    addFooter(slide, 13, totalSlides);
  }

  {
    const slide = pptx.addSlide();
    addHeader(slide, "Future Improvements And Viva Conclusion", "Conclusion");
    addCard(slide, 0.82, 1.65, 3.7, 1.14, "Recommended future work", "Add proxy rotation, configurable category lists, richer logging, and schema export to databases or parquet.");
    addCard(slide, 4.82, 1.65, 3.7, 1.14, "Parser hardening", "Version selectors, add DOM snapshot fixtures, and create more tests for malformed or partial review blocks.", "gold");
    addCard(slide, 8.82, 1.65, 3.7, 1.14, "Usability upgrades", "Expose summary dashboards or notebooks on top of the generated CSV and JSON run artifacts.");
    addBulletList(slide, [
      "The project demonstrates a complete batch scraping pipeline, not only page scraping scripts.",
      "Its strongest academic points are modular design, function-level normalization, resumable execution, and measurable artifact generation.",
      "The two-stage design makes the system easier to reason about: first discover products, then enrich them with reviews.",
      "Because the report is tied to exact file names and function names, it is defensible in a viva or code walkthrough.",
    ], { x: 0.86, y: 3.22, w: 7.0, h: 2.6, fontSize: 16 });
    addCard(slide, 8.2, 3.24, 4.1, 2.55, "Final takeaway", "batch_product_scraper.py and batch_review_scraper.py together form a resilient data-collection workflow with structured outputs, retry logic, and test-backed helper modules.\n\nThank you");
    addFooter(slide, 14, totalSlides);
  }
}

async function main() {
  ensureDir(OUT_DIR);
  buildSlides();
  await pptx.writeFile({ fileName: OUT_FILE });
  console.log(OUT_FILE);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
