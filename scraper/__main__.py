"""``python -m scraper`` entrypoint."""

from __future__ import annotations

import sys

from scraper.cli import main

if __name__ == "__main__":
    sys.exit(main())
