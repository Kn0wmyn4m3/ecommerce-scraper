"""Tests for the pure HTML parsing functions."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from scraper.parser import (
    parse_categories,
    parse_listing,
    parse_price,
    parse_product,
    parse_rating,
    parse_stock_count,
    slugify,
)

from .conftest import BASE, TRAVEL, load

PRODUCT_URL = BASE + "catalogue/its-only-the-himalayas_981/index.html"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("£51.77", 51.77), ("Â£12.00", 12.0), ("$1,299.99", 1299.99), ("free", 0.0)],
)
def test_parse_price(text: str, expected: float) -> None:
    assert parse_price(text) == expected


@pytest.mark.parametrize(
    ("css", "expected"),
    [("star-rating One", 1), ("star-rating Three", 3), ("star-rating Five", 5), ("star-rating", 0)],
)
def test_parse_rating(css: str, expected: int) -> None:
    tag = BeautifulSoup(f'<p class="{css}"></p>', "html.parser").p
    assert parse_rating(tag) == expected


def test_parse_rating_none() -> None:
    assert parse_rating(None) == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [("In stock (22 available)", 22), ("Out of stock", 0), ("In stock", None)],
)
def test_parse_stock_count(text: str, expected: int | None) -> None:
    assert parse_stock_count(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Sequential Art", "sequential-art"), ("travel_2", "travel"), ("  Travel ", "travel")],
)
def test_slugify(text: str, expected: str) -> None:
    assert slugify(text) == expected


def test_parse_categories() -> None:
    categories = parse_categories(load("home.html"), BASE + "index.html")
    assert list(categories)[:2] == ["Travel", "Mystery"]
    assert "Books" not in categories
    assert categories["Travel"] == TRAVEL + "index.html"
    assert categories["Sequential Art"].endswith("sequential-art_5/index.html")


def test_parse_listing_first_page() -> None:
    page = parse_listing(load("category_page1.html"), TRAVEL + "index.html")
    assert len(page.items) == 2
    first = page.items[0]
    assert first.title == "It's Only the Himalayas"
    assert first.product_url == PRODUCT_URL
    assert first.price == 45.17
    assert first.rating == 2
    assert first.in_stock is True
    # full title comes from the title attribute, not the truncated link text
    assert page.items[1].title.startswith("Full Moon over Noah’s Ark: An Odyssey")
    assert page.next_url == TRAVEL + "page-2.html"


def test_parse_listing_last_page() -> None:
    page = parse_listing(load("category_page2.html"), TRAVEL + "page-2.html")
    assert page.next_url is None
    assert page.items[0].in_stock is False
    assert "&" in page.items[0].title


def test_parse_product() -> None:
    book = parse_product(load("product.html"), PRODUCT_URL)
    assert book.title == "It's Only the Himalayas"
    assert book.price == 45.17
    assert book.rating == 2
    assert book.availability == "In stock (19 available)"
    assert book.stock_count == 19
    assert book.category == "Travel"
    assert book.upc == "a22124811bfa8350"
    assert book.product_url == PRODUCT_URL
    assert book.image_url == BASE + "media/cache/6d/41/6d418a73cc7d4ecfd75ca11d854041db.jpg"
    assert book.description.startswith("“Wherever you go")
    assert not book.description.endswith("...more")


def test_parse_product_rejects_non_product_page() -> None:
    with pytest.raises(ValueError, match="Not a product page"):
        parse_product(load("home.html"), BASE)


def test_parse_product_tolerates_missing_optional_parts() -> None:
    html = '<div class="product_main"><h1>Bare</h1><p class="price_color">£1.50</p></div>'
    book = parse_product(html, BASE + "x")
    assert (book.title, book.price, book.rating, book.upc, book.description) == (
        "Bare", 1.5, 0, "", "",
    )
    assert book.stock_count is None
