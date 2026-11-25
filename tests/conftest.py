"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from scraper.fetcher import FetchError
from scraper.models import Book

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/"
TRAVEL = BASE + "catalogue/category/books/travel_2/"


def load(name: str) -> str:
    """Read a fixture HTML file."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    """Serves fixture HTML by URL; unknown URLs raise ``FetchError``."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        if url not in self.pages:
            raise FetchError(f"HTTP 404 for {url}")
        return self.pages[url]


@pytest.fixture
def site() -> FakeFetcher:
    """A miniature offline copy of the site: home, 2 travel pages, products."""
    product = load("product.html")
    return FakeFetcher(
        {
            BASE + "index.html": load("home.html"),
            TRAVEL + "index.html": load("category_page1.html"),
            TRAVEL + "page-2.html": load("category_page2.html"),
            BASE + "catalogue/its-only-the-himalayas_981/index.html": product,
            BASE + "catalogue/full-moon-over-noahs-ark-an-odyssey-to-mount-ararat-and-beyond_811/index.html": product,
            # the 3rd product (see-america_732) is intentionally missing -> failure path
        }
    )


@pytest.fixture
def sample_books() -> list[Book]:
    """Two representative records, including non-ASCII text and a missing stock count."""
    return [
        Book(
            title="It's Only the Himalayas",
            price=45.17,
            rating=2,
            availability="In stock (19 available)",
            stock_count=19,
            category="Travel",
            upc="a22124811bfa8350",
            product_url=BASE + "catalogue/its-only-the-himalayas_981/index.html",
            image_url=BASE + "media/cache/6d/41/6d418a73cc7d4ecfd75ca11d854041db.jpg",
            description="“Wherever you go, whatever you do…” — café, naïve.",
        ),
        Book(
            title="Unknown Stock",
            price=10.0,
            rating=5,
            availability="In stock",
            stock_count=None,
            category="Poetry",
            upc="0000",
            product_url=BASE + "catalogue/unknown_1/index.html",
            image_url="",
            description="",
        ),
    ]
