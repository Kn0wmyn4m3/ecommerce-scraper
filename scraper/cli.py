"""Command-line interface: ``python -m scraper --help``."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .config import DEFAULT_BASE_URL, DEFAULT_USER_AGENT, ScraperConfig
from .crawler import BookScraper
from .exporter import SUPPORTED_FORMATS, export, infer_format, load_existing
from .fetcher import Fetcher, FetchError

logger = logging.getLogger("scraper")


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    p = argparse.ArgumentParser(
        prog="python -m scraper",
        description="Polite, robust product scraper for books.toscrape.com.",
    )
    p.add_argument("--category", help="Category name or slug, e.g. 'travel' or 'Sequential Art'")
    p.add_argument("--max-pages", type=_positive_int, help="Max listing pages to crawl")
    p.add_argument("--workers", type=_positive_int, default=4, help="Concurrent threads (default 4)")
    p.add_argument("--format", choices=SUPPORTED_FORMATS, help="Output format (default: from --output extension, else csv)")
    p.add_argument("--output", type=Path, help="Output file path (default: books.<format>)")
    p.add_argument("--delay", type=float, default=0.5, help="Min seconds between requests (default 0.5)")
    p.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds (default 15)")
    p.add_argument("--retries", type=int, default=3, help="Retries per request (default 3)")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Custom User-Agent header")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    p.add_argument("--resume", action="store_true", help="Skip products already present in --output")
    p.add_argument("--list-categories", action="store_true", help="Print available categories and exit")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return p


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return number


def resolve_output(output: Path | None, fmt: str | None) -> tuple[Path, str]:
    """Work out the final (path, format) pair from the CLI flags."""
    fmt = fmt or (infer_format(output) if output else None) or "csv"
    return (output or Path(f"books.{fmt}")), fmt


def configure_logging(verbose: bool) -> None:
    """Set up concise timestamped console logging."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    output, fmt = resolve_output(args.output, args.format)
    config = ScraperConfig(
        base_url=args.base_url,
        user_agent=args.user_agent,
        timeout=args.timeout,
        max_retries=args.retries,
        delay=args.delay,
        workers=args.workers,
    )
    with Fetcher(config) as fetcher:
        scraper = BookScraper(fetcher, config.base_url, workers=config.workers)
        try:
            if args.list_categories:
                print("\n".join(sorted(scraper.list_categories())))
                return 0
            return _run(scraper, args, output, fmt)
        except (ValueError, FetchError) as exc:
            logger.error("%s", exc)
            return 2


def _run(scraper: BookScraper, args: argparse.Namespace, output: Path, fmt: str) -> int:
    started = time.perf_counter()
    existing = load_existing(output, fmt) if args.resume else []
    result = scraper.run(
        category=args.category,
        max_pages=args.max_pages,
        skip_urls=(b.product_url for b in existing),
    )
    books = existing + result.books
    export(books, output, fmt)
    logger.info(
        "Done in %.1fs: %d new, %d resumed, %d failed -> %s",
        time.perf_counter() - started, len(result.books), len(existing),
        len(result.failed_urls), output,
    )
    return 1 if result.failed_urls and not books else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
