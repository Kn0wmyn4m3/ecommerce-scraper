"""Pure HTML -> dataclass parsing functions (no network, easy to test).

All selectors for the target site live here, so adapting the scraper to a
new store usually means editing only this module.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import Book, ListingItem, ListingPage

RATING_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_PRICE_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
_STOCK_RE = re.compile(r"\((\d+)\s+available\)", re.IGNORECASE)


# --------------------------------------------------------------- primitives
def parse_price(text: str) -> float:
    """``'£51.77'`` -> ``51.77``. Returns ``0.0`` if no number is found."""
    match = _PRICE_RE.search(text.replace(",", ""))
    return float(match.group(1)) if match else 0.0


def parse_rating(tag: Tag | None) -> int:
    """Read a ``<p class="star-rating Three">`` tag -> ``3`` (``0`` if unknown)."""
    if tag is None:
        return 0
    for css_class in tag.get("class", []):
        if (value := RATING_WORDS.get(css_class.lower())) is not None:
            return value
    return 0


def parse_stock_count(text: str) -> int | None:
    """``'In stock (22 available)'`` -> ``22``; out of stock -> ``0``; else ``None``."""
    if match := _STOCK_RE.search(text):
        return int(match.group(1))
    if "out of stock" in text.lower():
        return 0
    return None


def slugify(text: str) -> str:
    """Normalise a category name or slug for comparison (``'Sequential Art'`` -> ``'sequential-art'``)."""
    text = re.sub(r"_\d+$", "", text.strip().lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ------------------------------------------------------------------- pages
def parse_categories(html: str, page_url: str) -> dict[str, str]:
    """Return ``{category name: absolute URL}`` from the sidebar navigation."""
    soup = _soup(html)
    links = soup.select("div.side_categories ul.nav-list li ul li a")
    return {_clean(a.get_text()): urljoin(page_url, a["href"]) for a in links if a.get("href")}


def parse_listing(html: str, page_url: str) -> ListingPage:
    """Parse a listing/category page into product teasers + next-page URL."""
    soup = _soup(html)
    items = [_parse_listing_item(pod, page_url) for pod in soup.select("article.product_pod")]
    next_link = soup.select_one("ul.pager li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return ListingPage(items=[i for i in items if i is not None], next_url=next_url)


def _parse_listing_item(pod: Tag, page_url: str) -> ListingItem | None:
    link = pod.select_one("h3 a")
    if link is None or not link.get("href"):
        return None
    price_tag = pod.select_one("p.price_color")
    stock_tag = pod.select_one("p.availability")
    return ListingItem(
        title=link.get("title") or _clean(link.get_text()),
        product_url=urljoin(page_url, link["href"]),
        price=parse_price(price_tag.get_text()) if price_tag else 0.0,
        rating=parse_rating(pod.select_one("p.star-rating")),
        in_stock="in stock" in _clean(stock_tag.get_text() if stock_tag else "").lower(),
    )


def parse_product(html: str, page_url: str) -> Book:
    """Parse a product detail page into a :class:`Book`.

    Raises:
        ValueError: if the page does not look like a product page.
    """
    soup = _soup(html)
    main = soup.select_one("div.product_main")
    if main is None or main.h1 is None:
        raise ValueError(f"Not a product page: {page_url}")

    info = _product_info_table(soup)
    availability = _clean(info.get("Availability")) or _clean(
        _text_of(main.select_one("p.availability"))
    )
    price_text = info.get("Price (incl. tax)") or _text_of(main.select_one("p.price_color"))
    return Book(
        title=_clean(main.h1.get_text()),
        price=parse_price(price_text),
        rating=parse_rating(main.select_one("p.star-rating")),
        availability=availability,
        stock_count=parse_stock_count(availability),
        category=_parse_category(soup),
        upc=_clean(info.get("UPC")),
        product_url=page_url,
        image_url=_parse_image(soup, page_url),
        description=_parse_description(soup),
    )


def _text_of(tag: Tag | None) -> str:
    return tag.get_text() if tag else ""


def _product_info_table(soup: BeautifulSoup) -> dict[str, str]:
    rows = soup.select("table.table-striped tr")
    return {
        _clean(row.th.get_text()): _clean(row.td.get_text())
        for row in rows
        if row.th is not None and row.td is not None
    }


def _parse_category(soup: BeautifulSoup) -> str:
    crumbs = soup.select("ul.breadcrumb li a")
    # Home > Books > <Category> > (active title)
    return _clean(crumbs[-1].get_text()) if len(crumbs) >= 3 else ""


def _parse_image(soup: BeautifulSoup, page_url: str) -> str:
    img = soup.select_one("#product_gallery img") or soup.select_one("div.item.active img")
    return urljoin(page_url, img["src"]) if img and img.get("src") else ""


def _parse_description(soup: BeautifulSoup) -> str:
    header = soup.select_one("#product_description")
    paragraph = header.find_next_sibling("p") if header else None
    text = _clean(paragraph.get_text()) if paragraph else ""
    return text.removesuffix("...more").strip()
