"""Crawl orchestration: discover listing pages, then scrape product pages."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin

from .fetcher import FetchError
from .models import Book
from .parser import parse_categories, parse_listing, parse_product, slugify

logger = logging.getLogger(__name__)


class PageFetcher(Protocol):
    """Anything with a ``get(url) -> html`` method (real fetcher or test fake)."""

    def get(self, url: str) -> str: ...


@dataclass(slots=True)
class ScrapeResult:
    """Outcome of a crawl."""

    books: list[Book] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)
    skipped: int = 0


class BookScraper:
    """High-level crawler for a books.toscrape.com style catalogue.

    Args:
        fetcher: Object used to download pages.
        base_url: Root URL of the site.
        workers: Thread count for product-page downloads.
    """

    def __init__(self, fetcher: PageFetcher, base_url: str, workers: int = 4) -> None:
        self.fetcher = fetcher
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.workers = max(1, workers)

    # ------------------------------------------------------------- discovery
    def list_categories(self) -> dict[str, str]:
        """Return all categories available on the site."""
        home = urljoin(self.base_url, "index.html")
        return parse_categories(self.fetcher.get(home), home)

    def resolve_start_url(self, category: str | None) -> str:
        """Return the first listing page for ``category`` (or the full catalogue).

        Raises:
            ValueError: if the category does not exist.
        """
        if not category:
            return urljoin(self.base_url, "catalogue/page-1.html")
        wanted = slugify(category)
        categories = self.list_categories()
        for name, url in categories.items():
            if wanted in (slugify(name), slugify(url.rstrip("/").split("/")[-2])):
                return url
        available = ", ".join(sorted(categories))
        raise ValueError(f"Unknown category {category!r}. Available: {available}")

    def collect_product_urls(self, start_url: str, max_pages: int | None = None) -> list[str]:
        """Walk paginated listing pages and return product URLs in order."""
        urls: list[str] = []
        page_url: str | None = start_url
        pages = 0
        while page_url and (max_pages is None or pages < max_pages):
            try:
                listing = parse_listing(self.fetcher.get(page_url), page_url)
            except FetchError as exc:
                logger.error("Listing page failed, stopping pagination: %s", exc)
                break
            pages += 1
            urls.extend(item.product_url for item in listing.items)
            logger.info("Listing page %d: %d products (%s)", pages, len(listing.items), page_url)
            page_url = listing.next_url
        return list(dict.fromkeys(urls))  # de-duplicate, keep order

    # -------------------------------------------------------------- scraping
    def scrape_products(self, urls: list[str]) -> ScrapeResult:
        """Download and parse product pages concurrently; log & continue on errors."""
        result = ScrapeResult()
        by_url: dict[str, Book] = {}
        total = len(urls)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._scrape_one, url): url for url in urls}
            for done, future in enumerate(as_completed(futures), start=1):
                url = futures[future]
                try:
                    by_url[url] = future.result()
                except (FetchError, ValueError) as exc:
                    logger.error("Failed %s: %s", url, exc)
                    result.failed_urls.append(url)
                _log_progress(done, total)
        result.books = [by_url[u] for u in urls if u in by_url]
        return result

    def _scrape_one(self, url: str) -> Book:
        book = parse_product(self.fetcher.get(url), url)
        logger.debug("Scraped %s", book.title)
        return book

    # ----------------------------------------------------------------- facade
    def run(
        self,
        category: str | None = None,
        max_pages: int | None = None,
        skip_urls: Iterable[str] = (),
    ) -> ScrapeResult:
        """Full pipeline: resolve start page, collect URLs, scrape products."""
        start = self.resolve_start_url(category)
        urls = self.collect_product_urls(start, max_pages)
        skip = set(skip_urls)
        todo = [u for u in urls if u not in skip]
        if skipped := len(urls) - len(todo):
            logger.info("Resume: skipping %d already-scraped products", skipped)
        logger.info("Scraping %d product pages with %d worker(s)", len(todo), self.workers)
        result = self.scrape_products(todo)
        result.skipped = skipped
        return result


def _log_progress(done: int, total: int) -> None:
    step = max(1, total // 10)
    if done == total or done % step == 0:
        logger.info("Progress: %d/%d (%.0f%%)", done, total, 100 * done / max(total, 1))
