"""Interactive terminal app — the comfortable, menu-driven front door.

Run ``python -m scraper`` (or ``python main.py``) with no arguments to land here.
Pick a site, pick what to do, tweak the options, confirm, and go. Everything is
driven by :mod:`scraper.runner`, so the flag-based CLI behaves identically.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from scraper.runner import (
    DEFAULT_PROFILE,
    SPEED_PROFILES,
    get_profile,
    run_pipeline,
    run_products,
    run_reviews,
    run_search,
)
from scraper.sites.base import SiteAdapter
from scraper.sites.registry import all_adapters, get_adapter

console = Console()


# --------------------------------------------------------------------------- #
# Prompt helpers (rich, with numbered selection)
# --------------------------------------------------------------------------- #
def _select(title: str, options: list[tuple[str, str, str]], default_index: int = 0) -> str:
    """Show a numbered menu and return the chosen value.

    ``options`` is a list of ``(value, label, description)`` tuples.
    """

    table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    table.add_column("#", style="bold yellow", width=3)
    table.add_column("Option", style="bold")
    table.add_column("Details", style="dim")
    for index, (_value, label, description) in enumerate(options, start=1):
        table.add_row(str(index), label, description)
    console.print(table)

    choices = [str(i) for i in range(1, len(options) + 1)]
    answer = IntPrompt.ask(
        f"[bold green]{title}[/bold green]",
        choices=choices,
        default=default_index + 1,
        show_choices=False,
    )
    return options[answer - 1][0]


def _ask_int(label: str, default: int, *, allow_zero_hint: str = "") -> int:
    suffix = f" [dim]({allow_zero_hint})[/dim]" if allow_zero_hint else ""
    return IntPrompt.ask(f"[green]{label}[/green]{suffix}", default=default)


def _ask_path(label: str, default: str) -> Path:
    return Path(Prompt.ask(f"[green]{label}[/green]", default=default)).expanduser()


def _timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


# --------------------------------------------------------------------------- #
# Screens
# --------------------------------------------------------------------------- #
def _banner() -> None:
    console.print(
        Panel.fit(
            "[bold magenta]Datascape[/bold magenta] — multi-marketplace scraper\n"
            "[dim]Flipkart · Amazon · Myntra · Meesho[/dim]",
            border_style="magenta",
        )
    )


def _choose_site() -> SiteAdapter | None:
    options: list[tuple[str, str, str]] = []
    for adapter in all_adapters():
        caps = "products + reviews" if adapter.supports_reviews else "products only"
        options.append((adapter.name, adapter.label, caps))
    options.append(("__quit__", "Quit", "Exit the app"))

    choice = _select("Choose a marketplace", options)
    if choice == "__quit__":
        return None
    adapter = get_adapter(choice)
    if adapter.notes:
        console.print(Panel(adapter.notes, title=f"{adapter.label} notes", border_style="yellow"))
    return adapter


def _choose_mode(adapter: SiteAdapter) -> str:
    options = [
        ("products", "Scrape product listings (all categories)", f"{len(adapter.default_targets)} preset categories"),
        ("search", "Scrape product listings (custom search)", "One free-text query or a listing URL"),
    ]
    if adapter.supports_reviews:
        options.append(("reviews", "Scrape reviews (from a product folder)", "Resumable; reads product CSVs"))
        options.append(("pipeline", "Full pipeline (products then reviews)", "End-to-end in one run"))
    options.append(("__back__", "Back", "Choose a different site"))
    return _select(f"What do you want to do on {adapter.label}?", options)


def _choose_profile() -> str:
    options = [
        (name, name.capitalize(), profile.description)
        for name, profile in SPEED_PROFILES.items()
    ]
    default_index = list(SPEED_PROFILES).index(DEFAULT_PROFILE)
    return _select("Speed profile", options, default_index=default_index)


def _confirm_and_run(summary: dict[str, str], run) -> None:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    for key, value in summary.items():
        table.add_row(key, str(value))
    console.print(Panel(table, title="Review settings", border_style="green"))

    if not Confirm.ask("[bold]Start now?[/bold]", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return
    console.rule("[bold green]Running[/bold green]")
    try:
        run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Any completed work is saved on disk.[/yellow]")
    console.rule("[bold green]Done[/bold green]")


# --------------------------------------------------------------------------- #
# Mode handlers
# --------------------------------------------------------------------------- #
def _run_products(adapter: SiteAdapter) -> None:
    max_products = _ask_int("Max products per category", 100)
    profile = get_profile(_choose_profile())
    concurrency = _ask_int("Concurrency (parallel browsers)", profile.default_concurrency)
    out = _ask_path("Output directory", f"data/runs/{adapter.name}_products_{_timestamp()}")

    _confirm_and_run(
        {
            "Site": adapter.label,
            "Mode": "Product listings (all categories)",
            "Categories": str(len(adapter.default_targets)),
            "Max products / category": str(max_products),
            "Speed profile": profile.name,
            "Concurrency": str(concurrency),
            "Output": str(out),
        },
        lambda: run_products(
            adapter,
            output_dir=out,
            max_products=max_products,
            concurrency=concurrency,
            profile=profile,
            logger=console.print,
        ),
    )


def _run_search(adapter: SiteAdapter) -> None:
    raw = Prompt.ask("[green]Search query or full listing URL[/green]")
    listing_url = raw if raw.startswith("http") else None
    query = "" if listing_url else raw
    max_products = _ask_int("Max products", 100)
    profile = get_profile(_choose_profile())
    out = _ask_path("Output directory", f"data/runs/{adapter.name}_search_{_timestamp()}")

    _confirm_and_run(
        {
            "Site": adapter.label,
            "Mode": "Custom search",
            "Query/URL": raw,
            "Max products": str(max_products),
            "Speed profile": profile.name,
            "Output": str(out),
        },
        lambda: run_search(
            adapter,
            query=query,
            listing_url=listing_url,
            output_dir=out,
            max_products=max_products,
            profile=profile,
            logger=console.print,
        ),
    )


def _run_reviews(adapter: SiteAdapter) -> None:
    product_dir = _ask_path("Product CSV folder (from a products run)", f"data/runs/{adapter.name}_products_latest")
    if not product_dir.exists():
        console.print(f"[red]Folder not found:[/red] {product_dir}")
        return
    max_reviews = _ask_int("Max reviews per product", 100, allow_zero_hint="0 = uncapped")
    profile = get_profile(_choose_profile())
    concurrency = _ask_int("Concurrency (parallel browsers)", profile.default_concurrency)
    out = _ask_path("Output directory", f"data/runs/{adapter.name}_reviews_{_timestamp()}")
    resume = Confirm.ask("Resume if output already has progress?", default=True)

    _confirm_and_run(
        {
            "Site": adapter.label,
            "Mode": "Reviews",
            "Product folder": str(product_dir),
            "Max reviews / product": "uncapped" if max_reviews <= 0 else str(max_reviews),
            "Speed profile": profile.name,
            "Concurrency": str(concurrency),
            "Resume": "on" if resume else "off",
            "Output": str(out),
        },
        lambda: run_reviews(
            adapter,
            product_dir=product_dir,
            output_dir=out,
            max_reviews=max_reviews,
            concurrency=concurrency,
            resume=resume,
            profile=profile,
            logger=console.print,
        ),
    )


def _run_pipeline(adapter: SiteAdapter) -> None:
    max_products = _ask_int("Max products per category", 50)
    max_reviews = _ask_int("Max reviews per product", 50, allow_zero_hint="0 = uncapped")
    profile = get_profile(_choose_profile())
    out = _ask_path("Output directory", f"data/runs/{adapter.name}_pipeline_{_timestamp()}")

    _confirm_and_run(
        {
            "Site": adapter.label,
            "Mode": "Full pipeline (products then reviews)",
            "Max products / category": str(max_products),
            "Max reviews / product": "uncapped" if max_reviews <= 0 else str(max_reviews),
            "Speed profile": profile.name,
            "Output": str(out),
        },
        lambda: run_pipeline(
            adapter,
            output_dir=out,
            max_products=max_products,
            max_reviews=max_reviews,
            profile=profile,
            logger=console.print,
        ),
    )


_HANDLERS = {
    "products": _run_products,
    "search": _run_search,
    "reviews": _run_reviews,
    "pipeline": _run_pipeline,
}


# --------------------------------------------------------------------------- #
# Entry
# --------------------------------------------------------------------------- #
def run_app() -> int:
    if not sys.stdin.isatty():
        console.print(
            "[red]The interactive app needs a terminal.[/red] "
            "Run it in your shell, or use the flag-based CLI: "
            "[cyan]python -m scraper --help[/cyan]"
        )
        return 2

    _banner()
    while True:
        adapter = _choose_site()
        if adapter is None:
            console.print("[magenta]Bye![/magenta]")
            return 0

        mode = _choose_mode(adapter)
        if mode == "__back__":
            continue

        _HANDLERS[mode](adapter)

        if not Confirm.ask("\n[bold]Run another task?[/bold]", default=True):
            console.print("[magenta]Bye![/magenta]")
            return 0


if __name__ == "__main__":
    raise SystemExit(run_app())
