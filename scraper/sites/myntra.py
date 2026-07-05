"""Myntra adapter (listing only).

Myntra is a client-rendered SPA, but its search HTML still ships the result set
inline in a ``window.__myx`` JSON blob. Parsing that JSON is far more reliable
than scraping the hydrated DOM, so this adapter reads it directly and falls back
to DOM cards only if the blob is missing.

Reviews are intentionally unsupported: Myntra serves individual reviews from an
internal gateway API (not the product HTML), which needs site-specific request
work to access responsibly.
"""

from __future__ import annotations

import json
from urllib.parse import quote, quote_plus

from bs4 import BeautifulSoup, Tag

from scraper.core.models import ProductRecord, SubcategoryTarget
from scraper.core.textutils import normalize_text
from scraper.sites.base import SiteAdapter

_BASE_URL = "https://www.myntra.com"


def _extract_js_object(text: str, marker: str) -> dict | None:
    """Extract the first balanced ``{...}`` JSON object following ``marker``."""

    start = text.find(marker)
    if start == -1:
        return None
    brace_start = text.find("{", start)
    if brace_start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(brace_start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                blob = text[brace_start : index + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def _find_product_list(obj: object) -> list[dict] | None:
    """Recursively find the first list of product-like dicts in a JSON tree."""

    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            sample = obj[0]
            if "landingPageUrl" in sample or ("productId" in sample and "price" in sample):
                return obj  # type: ignore[return-value]
        for item in obj:
            found = _find_product_list(item)
            if found:
                return found
    elif isinstance(obj, dict):
        for value in obj.values():
            found = _find_product_list(value)
            if found:
                return found
    return None


class MyntraAdapter(SiteAdapter):
    name = "myntra"
    label = "Myntra"
    base_url = _BASE_URL
    home_url = _BASE_URL
    locale = "en-IN"
    listing_ready_selector = "li.product-base, script"
    supports_reviews = False
    max_listing_pages = 10
    notes = (
        "Listing only. Reads the inline window.__myx JSON. Reviews are served from "
        "Myntra's internal API and are not scraped here. Best-effort; may need tuning."
    )

    default_targets = [
        SubcategoryTarget("Men", "T-Shirts", "men tshirts"),
        SubcategoryTarget("Men", "Shirts", "men shirts"),
        SubcategoryTarget("Men", "Jeans", "men jeans"),
        SubcategoryTarget("Women", "Dresses", "women dresses"),
        SubcategoryTarget("Women", "Kurtas", "women kurtas"),
        SubcategoryTarget("Women", "Tops", "women tops"),
        SubcategoryTarget("Footwear", "Mens Shoes", "men casual shoes"),
        SubcategoryTarget("Footwear", "Womens Heels", "women heels"),
        SubcategoryTarget("Accessories", "Watches", "watches"),
        SubcategoryTarget("Accessories", "Sunglasses", "sunglasses"),
    ]

    def build_search_url(self, query: str) -> str:
        slug = quote(query.strip().lower().replace(" ", "-"))
        return f"{_BASE_URL}/{slug}?rawQuery={quote_plus(query)}"

    def build_listing_page_url(self, search_url: str, page_number: int) -> str:
        separator = "&" if "?" in search_url else "?"
        return f"{search_url}{separator}p={page_number}"

    def _records_from_json(
        self,
        products: list[dict],
        category: str,
        subcategory: str,
        source_url: str,
        max_records: int,
    ) -> list[ProductRecord]:
        records: list[ProductRecord] = []
        for item in products:
            landing = str(item.get("landingPageUrl") or "").lstrip("/")
            product_id = str(item.get("productId") or "")
            if not landing and not product_id:
                continue
            product_url = (
                f"{_BASE_URL}/{landing}"
                if landing
                else f"{_BASE_URL}/{product_id}/buy"
            )
            brand = str(item.get("brand") or "").strip()
            name = str(item.get("product") or item.get("productName") or "").strip()
            title = normalize_text(f"{brand} {name}") or "Unknown product"
            price_value = item.get("price")
            rating_value = item.get("rating")
            records.append(
                ProductRecord(
                    site=self.name,
                    category=category,
                    subcategory=subcategory,
                    title=title,
                    price=f"₹{price_value}" if price_value not in (None, "") else "",
                    rating=f"{float(rating_value):.1f}" if rating_value else "",
                    ratings_count=str(item.get("ratingCount") or ""),
                    reviews_count="",
                    product_url=product_url,
                    product_id=product_id,
                    source_url=source_url,
                )
            )
            if len(records) >= max_records:
                break
        return records

    def _records_from_dom(
        self,
        soup: BeautifulSoup,
        category: str,
        subcategory: str,
        source_url: str,
        max_records: int,
    ) -> list[ProductRecord]:
        records: list[ProductRecord] = []
        seen: set[str] = set()
        for card in soup.select("li.product-base"):
            if not isinstance(card, Tag):
                continue
            link = card.find("a", href=True)
            if not isinstance(link, Tag):
                continue
            href = str(link["href"]).strip().lstrip("/")
            product_url = f"{_BASE_URL}/{href}"
            if product_url in seen:
                continue
            seen.add(product_url)
            brand = normalize_text(card.select_one("h3.product-brand").get_text()) if card.select_one("h3.product-brand") else ""
            name = normalize_text(card.select_one("h4.product-product").get_text()) if card.select_one("h4.product-product") else ""
            price_node = card.select_one("span.product-discountedPrice") or card.select_one("div.product-price")
            price = normalize_text(price_node.get_text()) if isinstance(price_node, Tag) else ""
            records.append(
                ProductRecord(
                    site=self.name,
                    category=category,
                    subcategory=subcategory,
                    title=normalize_text(f"{brand} {name}") or "Unknown product",
                    price=price,
                    rating="",
                    ratings_count="",
                    reviews_count="",
                    product_url=product_url,
                    product_id=href.rstrip("/").split("/")[-2] if "/buy" in href else "",
                    source_url=source_url,
                )
            )
            if len(records) >= max_records:
                break
        return records

    def parse_products(
        self,
        html: str,
        category: str,
        subcategory: str,
        source_url: str,
        max_records: int,
    ) -> list[ProductRecord]:
        data = _extract_js_object(html, "window.__myx")
        if data is not None:
            products = _find_product_list(data)
            if products:
                records = self._records_from_json(
                    products, category, subcategory, source_url, max_records
                )
                if records:
                    return records

        soup = BeautifulSoup(html, "lxml")
        return self._records_from_dom(soup, category, subcategory, source_url, max_records)
