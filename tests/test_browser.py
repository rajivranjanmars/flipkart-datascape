"""Tests for the anti-bot / stealth helpers (no real browser needed)."""

from __future__ import annotations

import unittest

from scraper.core.batch import build_session_kwargs
from scraper.core.browser import looks_blocked
from scraper.sites.amazon import AmazonAdapter
from scraper.sites.flipkart import FlipkartAdapter


class LooksBlockedTest(unittest.TestCase):
    def test_none_is_not_blocked(self) -> None:
        self.assertFalse(looks_blocked(None))

    def test_short_block_page_detected(self) -> None:
        self.assertTrue(looks_blocked("<html><title>Access Denied</title></html>"))
        self.assertTrue(looks_blocked("<html>503 - Service Unavailable rush hour</html>"))

    def test_large_page_with_marker_is_not_blocked(self) -> None:
        # A genuine page that merely mentions "captcha" shouldn't be flagged.
        big = "<html>" + ("x" * 9000) + " captcha </html>"
        self.assertFalse(looks_blocked(big))

    def test_normal_small_page_not_blocked(self) -> None:
        self.assertFalse(looks_blocked("<html><body>A product page</body></html>"))


class SessionKwargsTest(unittest.TestCase):
    def test_profile_blocking_used_by_default(self) -> None:
        kwargs = build_session_kwargs(FlipkartAdapter(), block_resources=True)
        self.assertTrue(kwargs["block_resources"])

    def test_adapter_override_wins(self) -> None:
        # Amazon forces blocking off even when the profile wants it on.
        kwargs = build_session_kwargs(AmazonAdapter(), block_resources=True)
        self.assertFalse(kwargs["block_resources"])

    def test_empty_user_agent_becomes_none_for_auto(self) -> None:
        kwargs = build_session_kwargs(FlipkartAdapter(), block_resources=False)
        self.assertIsNone(kwargs["user_agent"])


class AuthWallTest(unittest.TestCase):
    def test_amazon_detects_login_wall(self) -> None:
        self.assertTrue(AmazonAdapter().is_auth_wall("<input id='ap_email'> sign in"))

    def test_amazon_review_html_is_not_auth_wall(self) -> None:
        self.assertFalse(AmazonAdapter().is_auth_wall("<div data-hook='review'>ok</div>"))

    def test_default_no_markers(self) -> None:
        self.assertFalse(FlipkartAdapter().is_auth_wall("<input id='ap_email'>"))


if __name__ == "__main__":
    unittest.main()
