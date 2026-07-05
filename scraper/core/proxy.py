"""Residential/HTTP proxy configuration, sourced from environment variables.

Drop a proxy provider's credentials into ``.env`` (see ``.env.example``) and
every browser session picks them up automatically — no code changes needed.
This is what lets sites that block datacenter IPs (Myntra in particular) be
reached from behind a residential proxy.
"""

from __future__ import annotations

import os


def resolve_proxy_from_env() -> dict[str, str] | None:
    """Build a Playwright ``proxy`` dict from ``PROXY_*`` env vars.

    Returns ``None`` when ``PROXY_SERVER`` is unset/blank, so scraping without a
    proxy keeps working exactly as before.
    """

    server = os.environ.get("PROXY_SERVER", "").strip()
    if not server:
        return None

    proxy: dict[str, str] = {"server": server}

    username = os.environ.get("PROXY_USERNAME", "").strip()
    if username:
        proxy["username"] = username

    password = os.environ.get("PROXY_PASSWORD", "").strip()
    if password:
        proxy["password"] = password

    bypass = os.environ.get("PROXY_BYPASS", "").strip()
    if bypass:
        proxy["bypass"] = bypass

    return proxy
