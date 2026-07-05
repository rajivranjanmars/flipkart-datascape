"""Myntra adapter (listing + reviews).

Myntra is a client-rendered SPA, but its search HTML still ships the result set
inline in a ``window.__myx`` JSON blob. Parsing that JSON is far more reliable
than scraping the hydrated DOM, so this adapter reads it directly and falls back
to DOM cards only if the blob is missing.

Reviews are served by Myntra's own JSON API rather than the product page HTML:
``GET /web/v1/reviews/batch/{styleId}?size=N&page=P`` (same-origin, no auth
needed — confirmed working cold, no prior page visit required). The endpoint
plateaus around ~100 reviews per product regardless of the ``sort``/``rating``
query params it otherwise accepts (mirrors Amazon's public review page, which
tops out similarly); pages beyond that come back empty and the generic pager
stops there.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, quote_plus

from bs4 import BeautifulSoup, Tag

from scraper.core.models import ProductRecord, SubcategoryTarget
from scraper.core.textutils import normalize_text
from scraper.sites.base import ReviewsNotSupported, SiteAdapter

_BASE_URL = "https://www.myntra.com"
_STYLE_ID_PATTERN = re.compile(r"/(\d+)/buy")
_REVIEWS_PAGE_SIZE = 20
_PRE_TAG_PATTERN = re.compile(r"<pre[^>]*>(.*)</pre>", re.IGNORECASE | re.DOTALL)


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
    review_ready_selector = None
    supports_reviews = True
    max_listing_pages = 10
    reviews_per_page_guess = 15
    notes = (
        "Reads the inline window.__myx JSON for listings and Myntra's own "
        "/web/v1/reviews/batch/{styleId} JSON API for reviews. That API caps out "
        "around ~100 reviews per product regardless of page depth (same class of "
        "limit as Amazon's public review page)."
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
        SubcategoryTarget("Men", "Trousers", "men trousers"),
        SubcategoryTarget("Men", "Track Pants", "men track pants"),
        SubcategoryTarget("Men", "Shorts", "men shorts"),
        SubcategoryTarget("Men", "Sweatshirts", "men sweatshirts"),
        SubcategoryTarget("Men", "Jackets", "men jackets"),
        SubcategoryTarget("Men", "Blazers", "men blazers"),
        SubcategoryTarget("Men", "Kurtas", "men kurtas"),
        SubcategoryTarget("Men", "Innerwear", "men innerwear"),
        SubcategoryTarget("Men", "Nightwear", "men nightwear"),
        SubcategoryTarget("Men", "Ethnic Sets", "men ethnic sets"),
        SubcategoryTarget("Women", "Leggings", "women leggings"),
        SubcategoryTarget("Women", "Jeans", "women jeans"),
        SubcategoryTarget("Women", "Sarees", "sarees"),
        SubcategoryTarget("Women", "Sweaters", "women sweaters"),
        SubcategoryTarget("Women", "Jackets", "women jackets"),
        SubcategoryTarget("Women", "Skirts", "women skirts"),
        SubcategoryTarget("Women", "Jumpsuits", "women jumpsuits"),
        SubcategoryTarget("Women", "Nightwear", "women nightwear"),
        SubcategoryTarget("Women", "Lingerie", "women lingerie"),
        SubcategoryTarget("Women", "Ethnic Sets", "women ethnic sets"),
        SubcategoryTarget("Women", "Palazzos", "women palazzos"),
        SubcategoryTarget("Women", "Shrugs", "women shrugs"),
        SubcategoryTarget("Kids", "Boys T-Shirts", "boys tshirts"),
        SubcategoryTarget("Kids", "Girls Dresses", "girls dresses"),
        SubcategoryTarget("Kids", "Boys Jeans", "boys jeans"),
        SubcategoryTarget("Kids", "Girls Tops", "girls tops"),
        SubcategoryTarget("Kids", "Infant Clothing", "infant clothing"),
        SubcategoryTarget("Kids", "Kids Footwear", "kids footwear"),
        SubcategoryTarget("Kids", "Kids Nightwear", "kids nightwear"),
        SubcategoryTarget("Footwear", "Mens Sneakers", "men sneakers"),
        SubcategoryTarget("Footwear", "Mens Formal Shoes", "men formal shoes"),
        SubcategoryTarget("Footwear", "Mens Sandals", "men sandals"),
        SubcategoryTarget("Footwear", "Mens Flip Flops", "men flip flops"),
        SubcategoryTarget("Footwear", "Womens Flats", "women flats"),
        SubcategoryTarget("Footwear", "Womens Sports Shoes", "women sports shoes"),
        SubcategoryTarget("Footwear", "Womens Sandals", "women sandals"),
        SubcategoryTarget("Footwear", "Womens Boots", "women boots"),
        SubcategoryTarget("Sports", "Sports Shoes", "sports shoes"),
        SubcategoryTarget("Sports", "Track Suits", "track suits"),
        SubcategoryTarget("Sports", "Sports Jackets", "sports jackets"),
        SubcategoryTarget("Sports", "Yoga Wear", "yoga wear"),
        SubcategoryTarget("Accessories", "Belts", "belts"),
        SubcategoryTarget("Accessories", "Wallets", "wallets"),
        SubcategoryTarget("Accessories", "Caps & Hats", "caps hats"),
        SubcategoryTarget("Accessories", "Ties", "ties"),
        SubcategoryTarget("Accessories", "Scarves", "scarves"),
        SubcategoryTarget("Accessories", "Mufflers", "mufflers"),
        SubcategoryTarget("Accessories", "Gloves", "gloves"),
        SubcategoryTarget("Bags", "Backpacks", "backpacks"),
        SubcategoryTarget("Bags", "Handbags", "handbags"),
        SubcategoryTarget("Bags", "Clutches", "clutches"),
        SubcategoryTarget("Bags", "Trolley Bags", "trolley bags"),
        SubcategoryTarget("Bags", "Laptop Bags", "laptop bags"),
        SubcategoryTarget("Jewellery", "Earrings", "earrings"),
        SubcategoryTarget("Jewellery", "Necklaces", "necklaces"),
        SubcategoryTarget("Jewellery", "Rings", "rings"),
        SubcategoryTarget("Jewellery", "Bangles & Bracelets", "bangles bracelets"),
        SubcategoryTarget("Beauty", "Lipstick", "lipstick"),
        SubcategoryTarget("Beauty", "Foundation", "foundation"),
        SubcategoryTarget("Beauty", "Kajal & Eyeliner", "kajal eyeliner"),
        SubcategoryTarget("Beauty", "Moisturizer", "moisturizer"),
        SubcategoryTarget("Beauty", "Sunscreen", "sunscreen"),
        SubcategoryTarget("Beauty", "Shampoo", "shampoo"),
        SubcategoryTarget("Beauty", "Perfume", "perfume"),
        SubcategoryTarget("Beauty", "Hair Oil", "hair oil"),
        SubcategoryTarget("Beauty", "Face Wash", "face wash"),
        SubcategoryTarget("Beauty", "Nail Polish", "nail polish"),
        SubcategoryTarget("Personal Care", "Trimmers", "trimmers"),
        SubcategoryTarget("Personal Care", "Hair Dryers", "hair dryers"),
        SubcategoryTarget("Personal Care", "Electric Shavers", "electric shavers"),
        SubcategoryTarget("Home", "Bedsheets", "bedsheets"),
        SubcategoryTarget("Home", "Cushion Covers", "cushion covers"),
        SubcategoryTarget("Home", "Curtains", "curtains"),
        SubcategoryTarget("Home", "Wall Decor", "wall decor"),
        SubcategoryTarget("Home", "Table Decor", "table decor"),
        SubcategoryTarget("Home", "Storage Boxes", "storage boxes"),
        SubcategoryTarget("Kitchen", "Cookware", "cookware"),
        SubcategoryTarget("Kitchen", "Dinnerware", "dinnerware"),
        SubcategoryTarget("Kitchen", "Water Bottles", "water bottles"),
        SubcategoryTarget("Electronics", "Headphones", "headphones"),
        SubcategoryTarget("Electronics", "Smartwatches", "smart watches"),
        SubcategoryTarget("Electronics", "Power Banks", "power banks"),
        SubcategoryTarget("Electronics", "Mobile Covers", "mobile covers"),
        SubcategoryTarget("Toys", "Soft Toys", "soft toys"),
        SubcategoryTarget("Toys", "Board Games", "board games"),
        SubcategoryTarget("Toys", "Action Figures", "action figures"),
        SubcategoryTarget("Books & Stationery", "Notebooks", "notebooks"),
        SubcategoryTarget("Pet Supplies", "Pet Accessories", "pet accessories"),
        SubcategoryTarget("Men", "Suits", "men suits"),
        SubcategoryTarget("Women", "Gowns", "women gowns"),
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

    # -- Reviews -------------------------------------------------------------- #
    def get_reviews_url(self, product_url: str) -> str:
        match = _STYLE_ID_PATTERN.search(product_url)
        if not match:
            raise ReviewsNotSupported(
                f"Could not extract Myntra style id from URL: {product_url}"
            )
        style_id = match.group(1)
        return f"{_BASE_URL}/web/v1/reviews/batch/{style_id}?size={_REVIEWS_PAGE_SIZE}&page=1"

    def build_review_page_url(self, reviews_url: str, page_number: int) -> str:
        return re.sub(r"page=\d+", f"page={page_number}", reviews_url)

    def parse_reviews(
        self,
        html: str,
        product_url: str,
        product_name: str,
    ) -> list[dict[str, object]]:
        pre_match = _PRE_TAG_PATTERN.search(html)
        text = pre_match.group(1) if pre_match else html
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return []

        reviews: list[dict[str, object]] = []
        for item in data.get("reviews") or []:
            if not isinstance(item, dict):
                continue
            date = ""
            updated_at = item.get("updatedAt")
            if updated_at:
                try:
                    date = datetime.fromtimestamp(
                        int(updated_at) / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                except (TypeError, ValueError, OverflowError):
                    date = ""
            variant = ", ".join(
                f"{attr.get('name')}: {attr.get('value')}"
                for attr in (item.get("styleAttribute") or [])
                if isinstance(attr, dict) and attr.get("name") and attr.get("value")
            )
            try:
                helpful_count = int(item.get("upvotes") or 0)
            except (TypeError, ValueError):
                helpful_count = 0
            reviews.append(
                {
                    "rating": item.get("userRating"),
                    "title": "",
                    "body": normalize_text(str(item.get("review") or "")),
                    "reviewer": normalize_text(str(item.get("userName") or "")),
                    "date": date,
                    "helpful_count": helpful_count,
                    "variant": variant,
                    "city": "",
                    "reviewer_badge": "",
                }
            )
        return reviews
