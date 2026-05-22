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
python -m unittest tests.test_batch_product_scraper tests.test_batch_review_scraper
python -m py_compile scraper/batch_product_scraper.py scraper/batch_review_scraper.py
```

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
