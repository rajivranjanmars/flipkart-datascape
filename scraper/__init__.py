"""Datascape — a multi-marketplace product & review scraper.

Public surface:
- ``scraper.runner`` — high-level operations (products / search / reviews / pipeline)
- ``scraper.sites.registry`` — site adapter lookup
- ``scraper.app`` — the interactive terminal app
- ``scraper.cli`` — the flag-based CLI
"""

from __future__ import annotations

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
