"""Registry mapping site slugs to adapter instances."""

from __future__ import annotations

from scraper.sites.amazon import AmazonAdapter
from scraper.sites.base import SiteAdapter
from scraper.sites.flipkart import FlipkartAdapter
from scraper.sites.meesho import MeeshoAdapter
from scraper.sites.myntra import MyntraAdapter

# Order here is the order shown in the terminal app.
_ADAPTER_CLASSES = [FlipkartAdapter, AmazonAdapter, MyntraAdapter, MeeshoAdapter]

_ADAPTERS: dict[str, SiteAdapter] = {cls.name: cls() for cls in _ADAPTER_CLASSES}


def available_sites() -> list[str]:
    """Return the registered site slugs in display order."""

    return list(_ADAPTERS.keys())


def get_adapter(name: str) -> SiteAdapter:
    """Return the adapter instance for a site slug (case-insensitive)."""

    key = name.strip().lower()
    if key not in _ADAPTERS:
        raise KeyError(
            f"Unknown site '{name}'. Available: {', '.join(_ADAPTERS)}",
        )
    return _ADAPTERS[key]


def all_adapters() -> list[SiteAdapter]:
    """Return all adapter instances in display order."""

    return list(_ADAPTERS.values())
