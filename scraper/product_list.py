"""Helpers for collecting product URLs from Flipkart listing pages."""

from __future__ import annotations

from playwright.sync_api import BrowserContext
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from tqdm import tqdm

from scraper.utils import get_page_html

_BASE_URL = "https://www.flipkart.com"
_MAX_CONSECUTIVE_EMPTY_RESPONSES = 3


def get_product_urls(
    base_url: str,
    context: BrowserContext,
    max_products: int = 100,
) -> list[str]:
    """Scrape up to ``max_products`` unique product URLs from a Flipkart listing."""

    if max_products <= 0:
        return []

    product_urls: list[str] = []
    seen_urls: set[str] = set()
    page_number = 1
    consecutive_empty_responses = 0

    with tqdm(desc="Pages scraped", unit="page") as progress:
        while len(product_urls) < max_products:
            parsed_url = urlparse(base_url)
            query_params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
            query_params["page"] = str(page_number)
            page_url = urlunparse(parsed_url._replace(query=urlencode(query_params)))

            html = get_page_html(context, page_url)
            progress.update(1)

            if html is None:
                tqdm.write(
                    f"Warning: no response received for page {page_number}: {page_url}",
                )
                consecutive_empty_responses += 1

                # Repeated empty responses usually indicate the listing has ended or
                # Flipkart is throttling requests, so stop before looping forever.
                if consecutive_empty_responses >= _MAX_CONSECUTIVE_EMPTY_RESPONSES:
                    tqdm.write(
                        "Warning: stopping after repeated empty responses from Flipkart.",
                    )
                    break

                page_number += 1
                continue

            consecutive_empty_responses = 0
            soup = BeautifulSoup(html, "lxml")
            page_links_found = 0

            for anchor in soup.find_all("a", href=True):
                href = str(anchor["href"]).strip()

                if not href.startswith("/") or "/p/" not in href:
                    continue

                absolute_url = f"{_BASE_URL}{href.split('#', maxsplit=1)[0]}"

                if absolute_url in seen_urls:
                    continue

                seen_urls.add(absolute_url)
                product_urls.append(absolute_url)
                page_links_found += 1

                if len(product_urls) >= max_products:
                    break

            if page_links_found == 0:
                break

            page_number += 1

    if len(product_urls) < max_products:
        print(
            f"Warning: only found {len(product_urls)} unique product URLs for {base_url}.",
        )

    return product_urls[:max_products]
