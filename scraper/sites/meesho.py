"""Meesho adapter (listing only, best-effort).

Meesho is a Next.js SPA. Where the search/category HTML embeds a
``__NEXT_DATA__`` JSON island we read products from it; otherwise we fall back to
server-rendered product anchors (``/p/`` links) and nearby price text.

Reviews are unsupported: Meesho serves ratings/reviews from internal JSON APIs
that need site-specific request work. Of the four adapters this is the most
likely to need live tuning, since Meesho leans hardest on client-side fetching.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

from scraper.core.models import ProductRecord, SubcategoryTarget
from scraper.core.textutils import normalize_text
from scraper.sites.base import SiteAdapter

_BASE_URL = "https://www.meesho.com"
_PRICE_PATTERN = re.compile(r"₹\s*[\d,]+")


def _looks_like_product(item: dict) -> bool:
    keys = item.keys()
    has_name = "name" in keys or "title" in keys
    has_id = any(k in keys for k in ("id", "product_id", "catalog_id", "slug"))
    has_price = any(k in keys for k in ("price", "original_price", "min_product_price"))
    return has_name and has_id and has_price


def _find_product_list(obj: object) -> list[dict] | None:
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and _looks_like_product(obj[0]):
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


class MeeshoAdapter(SiteAdapter):
    name = "meesho"
    label = "Meesho"
    base_url = _BASE_URL
    home_url = _BASE_URL
    locale = "en-IN"
    listing_ready_selector = "a[href*='/p/']"
    supports_reviews = False
    max_listing_pages = 8
    notes = (
        "Listing only, best-effort. Tries the __NEXT_DATA__ JSON then falls back to "
        "/p/ product anchors. Meesho is heavily client-rendered, so expect to tune "
        "selectors/queries against live pages. Reviews are not scraped."
    )

    default_targets = [
        SubcategoryTarget("Women", "Kurtis", "kurti"),
        SubcategoryTarget("Women", "Sarees", "saree"),
        SubcategoryTarget("Women", "Dress Material", "dress material"),
        SubcategoryTarget("Men", "T-Shirts", "men tshirt"),
        SubcategoryTarget("Kids", "Kids Wear", "kids wear"),
        SubcategoryTarget("Footwear", "Shoes", "shoes"),
        SubcategoryTarget("Accessories", "Watches", "watch"),
        SubcategoryTarget("Jewellery", "Jewellery Set", "jewellery set"),
        SubcategoryTarget("Home", "Bedsheets", "bedsheet"),
        SubcategoryTarget("Home", "Kitchen", "kitchen organizer"),
    ]

    def build_search_url(self, query: str) -> str:
        return f"{_BASE_URL}/search?q={quote_plus(query)}&searchType=manual"

    def build_listing_page_url(self, search_url: str, page_number: int) -> str:
        separator = "&" if "?" in search_url else "?"
        return f"{search_url}{separator}page={page_number}"

    def _records_from_json(
        self,
        products: list[dict],
        category: str,
        subcategory: str,
        source_url: str,
        max_records: int,
    ) -> list[ProductRecord]:
        records: list[ProductRecord] = []
        seen: set[str] = set()
        for item in products:
            slug = str(item.get("slug") or "").strip().lstrip("/")
            product_id = str(item.get("id") or item.get("product_id") or item.get("catalog_id") or "")
            if not slug and not product_id:
                continue
            if "/p/" in slug:
                product_url = f"{_BASE_URL}/{slug}"
            elif slug and product_id:
                product_url = f"{_BASE_URL}/{slug}/p/{product_id}"
            else:
                product_url = f"{_BASE_URL}/product/{product_id}"
            if product_url in seen:
                continue
            seen.add(product_url)

            price_value = item.get("price") or item.get("min_product_price") or item.get("original_price")
            records.append(
                ProductRecord(
                    site=self.name,
                    category=category,
                    subcategory=subcategory,
                    title=normalize_text(str(item.get("name") or item.get("title") or "")) or "Unknown product",
                    price=f"₹{price_value}" if price_value not in (None, "") else "",
                    rating=str(item.get("rating") or item.get("avg_rating") or ""),
                    ratings_count=str(item.get("rating_count") or item.get("ratingCount") or ""),
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
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            href = str(anchor["href"]).strip()
            if "/p/" not in href:
                continue
            product_url = urljoin(_BASE_URL, href.split("?", 1)[0])
            if product_url in seen:
                continue
            seen.add(product_url)

            card_text = normalize_text(anchor.get_text(" ", strip=True))
            price_match = _PRICE_PATTERN.search(card_text)
            title = ""
            img = anchor.find("img")
            if isinstance(img, Tag):
                title = normalize_text(str(img.get("alt") or ""))
            if not title:
                title = normalize_text(_PRICE_PATTERN.sub(" ", card_text))[:140]

            records.append(
                ProductRecord(
                    site=self.name,
                    category=category,
                    subcategory=subcategory,
                    title=title or "Unknown product",
                    price=price_match.group(0) if price_match else "",
                    rating="",
                    ratings_count="",
                    reviews_count="",
                    product_url=product_url,
                    product_id=product_url.rstrip("/").split("/")[-1],
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
        soup = BeautifulSoup(html, "lxml")

        next_data = soup.find("script", id="__NEXT_DATA__")
        if isinstance(next_data, Tag) and next_data.string:
            try:
                data = json.loads(next_data.string)
            except json.JSONDecodeError:
                data = None
            if data is not None:
                products = _find_product_list(data)
                if products:
                    records = self._records_from_json(
                        products, category, subcategory, source_url, max_records
                    )
                    if records:
                        return records

        return self._records_from_dom(soup, category, subcategory, source_url, max_records)
