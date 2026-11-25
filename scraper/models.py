"""Plain data containers produced by the parser and consumed by exporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass(slots=True)
class Book:
    """A fully scraped product (book) record."""

    title: str
    price: float
    rating: int
    availability: str
    stock_count: int | None
    category: str
    upc: str
    product_url: str
    image_url: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Return the record as a plain ``dict`` (column order preserved)."""
        return asdict(self)

    @classmethod
    def field_names(cls) -> list[str]:
        """Column names in export order."""
        return [f.name for f in fields(cls)]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Book:
        """Build a ``Book`` from loosely typed data (e.g. a CSV row).

        Missing or empty values are coerced to sensible defaults so that
        previously exported files can be re-loaded for resuming.
        """

        def text(key: str) -> str:
            value = data.get(key)
            return "" if value is None else str(value)

        stock_raw = data.get("stock_count")
        stock = int(float(stock_raw)) if stock_raw not in (None, "") else None
        return cls(
            title=text("title"),
            price=float(data.get("price") or 0.0),
            rating=int(float(data.get("rating") or 0)),
            availability=text("availability"),
            stock_count=stock,
            category=text("category"),
            upc=text("upc"),
            product_url=text("product_url"),
            image_url=text("image_url"),
            description=text("description"),
        )


@dataclass(frozen=True, slots=True)
class ListingItem:
    """A product teaser as shown on a category / listing page."""

    title: str
    product_url: str
    price: float
    rating: int
    in_stock: bool


@dataclass(frozen=True, slots=True)
class ListingPage:
    """One parsed listing page: its products and the link to the next page."""

    items: list[ListingItem] = field(default_factory=list)
    next_url: str | None = None
