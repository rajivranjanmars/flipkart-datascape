"""Load auth cookies for logged-in scraping.

Accepts the common browser-extension export format (Cookie-Editor / EditThisCookie:
keys like ``expirationDate``, ``sameSite: "no_restriction"``) and the native
Playwright format, and normalizes both to what ``context.add_cookies`` expects.

Cookie files hold live credentials — keep them out of git (see ``secrets/``).
"""

from __future__ import annotations

import json
from pathlib import Path

# Browser-export sameSite values -> Playwright's accepted set.
_SAME_SITE = {
    "strict": "Strict",
    "lax": "Lax",
    "no_restriction": "None",
    "none": "None",
}


def _normalize(cookie: dict) -> dict | None:
    """Convert one raw cookie dict to Playwright's shape, or None if unusable."""

    name = cookie.get("name")
    value = cookie.get("value")
    if not name or value is None:
        return None

    out: dict[str, object] = {"name": name, "value": value}

    domain = cookie.get("domain")
    if domain:
        out["domain"] = domain
        out["path"] = cookie.get("path", "/")
    elif cookie.get("url"):
        out["url"] = cookie["url"]
    else:
        return None

    expires = cookie.get("expires", cookie.get("expirationDate"))
    if expires is not None:
        try:
            out["expires"] = float(expires)
        except (TypeError, ValueError):
            pass

    if "httpOnly" in cookie:
        out["httpOnly"] = bool(cookie["httpOnly"])
    if "secure" in cookie:
        out["secure"] = bool(cookie["secure"])

    same_site = _SAME_SITE.get(str(cookie.get("sameSite") or "").lower())
    if same_site:
        out["sameSite"] = same_site

    return out


def load_cookies(path: str | Path) -> list[dict]:
    """Read a cookie JSON file and return Playwright-format cookies.

    Supports a bare list of cookies or an object with a ``cookies`` key.
    """

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ValueError(f"Cookie file {path} is not a list of cookies.")

    normalized = [_normalize(c) for c in data if isinstance(c, dict)]
    return [c for c in normalized if c]


def default_cookies_path(site: str) -> Path:
    """Return the conventional cookie file path for a site (may not exist)."""

    return Path("secrets") / f"{site}_cookies.json"


def discover_cookies(site: str) -> list[dict] | None:
    """Load cookies from the conventional path if it exists, else None."""

    path = default_cookies_path(site)
    if path.exists():
        try:
            cookies = load_cookies(path)
            return cookies or None
        except (ValueError, json.JSONDecodeError):
            return None
    return None
