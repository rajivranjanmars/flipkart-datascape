"""Convenience launcher.

``python main.py`` with no arguments opens the interactive terminal app.
``python main.py <command> ...`` forwards to the flag-based CLI.
Equivalent to ``python -m scraper``.
"""

from __future__ import annotations

import sys

from scraper.cli import main

if __name__ == "__main__":
    sys.exit(main())
