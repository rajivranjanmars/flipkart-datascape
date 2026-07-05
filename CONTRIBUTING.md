# Contributing

Thanks for taking the time to contribute.

## Before you start

- Read the [README](README.md) for the project overview.
- Read [Batch Workflows](docs/BATCH_WORKFLOWS.md) if your change touches the batch scrapers.
- Keep changes focused. This repository is small, so narrow pull requests are easier to review and maintain.

## Development setup

Install dependencies:

```bash
pip install -r requirements.txt
python -m playwright install
```

## Running tests

```bash
python -m unittest tests.test_engine tests.test_adapters tests.test_batch tests.test_browser tests.test_cookies
python -m py_compile scraper/*.py scraper/core/*.py scraper/sites/*.py
```

Tests run fully offline (HTML/JSON fixtures + a fake browser session).

## Adding a marketplace

Implement a `SiteAdapter` subclass in `scraper/sites/`, register it in
`scraper/sites/registry.py`, and add fixture-based tests in `tests/`. The shared
engine (`scraper/core/`) provides browsing, concurrency, resume, and reporting.

## Guidelines

- Match the existing code style.
- Prefer small, reviewable changes.
- Add or update tests when behavior changes.
- Keep generated data, logs, and local run artifacts out of git.
- Document user-facing CLI behavior when adding or changing scraper options.

## Pull requests

A good pull request should include:
- a short explanation of the problem being solved
- the behavior change or new capability
- any new commands, flags, or output files
- relevant test coverage
