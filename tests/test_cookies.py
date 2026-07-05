"""Tests for the cookie loader (browser-export + Playwright formats)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scraper.core.cookies import load_cookies


class LoadCookiesTest(unittest.TestCase):
    def _write(self, data: object) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_browser_export_format_is_normalized(self) -> None:
        path = self._write(
            [
                {
                    "domain": ".amazon.in",
                    "name": "session-token",
                    "value": "abc",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "expirationDate": 1813655174.92,
                    "sameSite": "no_restriction",
                    "hostOnly": False,
                    "storeId": None,
                },
            ]
        )
        cookies = load_cookies(path)
        self.assertEqual(len(cookies), 1)
        cookie = cookies[0]
        self.assertEqual(cookie["name"], "session-token")
        self.assertEqual(cookie["domain"], ".amazon.in")
        self.assertEqual(cookie["expires"], 1813655174.92)  # renamed from expirationDate
        self.assertEqual(cookie["sameSite"], "None")  # mapped from no_restriction
        self.assertNotIn("hostOnly", cookie)
        self.assertNotIn("storeId", cookie)

    def test_samesite_variants(self) -> None:
        path = self._write(
            [
                {"domain": "x.com", "name": "a", "value": "1", "sameSite": "lax"},
                {"domain": "x.com", "name": "b", "value": "2", "sameSite": "strict"},
                {"domain": "x.com", "name": "c", "value": "3", "sameSite": None},
            ]
        )
        by_name = {c["name"]: c for c in load_cookies(path)}
        self.assertEqual(by_name["a"]["sameSite"], "Lax")
        self.assertEqual(by_name["b"]["sameSite"], "Strict")
        self.assertNotIn("sameSite", by_name["c"])  # null dropped, not invalid

    def test_skips_entries_without_name_or_domain(self) -> None:
        path = self._write(
            [
                {"name": "", "value": "x", "domain": "x.com"},
                {"name": "ok", "value": "y"},  # no domain or url
                {"name": "good", "value": "z", "domain": "x.com"},
            ]
        )
        cookies = load_cookies(path)
        self.assertEqual([c["name"] for c in cookies], ["good"])

    def test_object_with_cookies_key(self) -> None:
        path = self._write({"cookies": [{"name": "a", "value": "1", "domain": "x.com"}]})
        self.assertEqual(len(load_cookies(path)), 1)


if __name__ == "__main__":
    unittest.main()
