"""Export scraped records to CSV, JSON or a formatted Excel workbook."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import Book

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("csv", "json", "xlsx")
HEADER_FILL = PatternFill("solid", start_color="1F4E78", end_color="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
MAX_COLUMN_WIDTH = 60


def infer_format(path: Path) -> str | None:
    """Return the export format implied by a file extension, if supported."""
    suffix = path.suffix.lower().lstrip(".")
    return suffix if suffix in SUPPORTED_FORMATS else None


def export(books: Iterable[Book], path: Path, fmt: str) -> Path:
    """Write ``books`` to ``path`` in format ``fmt`` and return the path."""
    writers: dict[str, Callable[[list[Book], Path], None]] = {
        "csv": to_csv,
        "json": to_json,
        "xlsx": to_xlsx,
    }
    if fmt not in writers:
        raise ValueError(f"Unsupported format {fmt!r}; choose from {SUPPORTED_FORMATS}")
    path.parent.mkdir(parents=True, exist_ok=True)
    records = list(books)
    writers[fmt](records, path)
    logger.info("Wrote %d records to %s", len(records), path)
    return path


def to_csv(books: list[Book], path: Path) -> None:
    """Write UTF-8 CSV (with BOM so Excel opens accents/£ correctly)."""
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=Book.field_names())
        writer.writeheader()
        writer.writerows(book.to_dict() for book in books)


def to_json(books: list[Book], path: Path) -> None:
    """Write a pretty-printed JSON array."""
    payload = [book.to_dict() for book in books]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def to_xlsx(books: list[Book], path: Path) -> None:
    """Write an Excel workbook with styled header, filters and auto column widths."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Products"
    headers = Book.field_names()
    sheet.append([h.replace("_", " ").title() for h in headers])
    for book in books:
        sheet.append([getattr(book, h) for h in headers])
    _style_sheet(sheet, headers)
    workbook.save(path)


def _style_sheet(sheet: Worksheet, headers: list[str]) -> None:
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    price_col = headers.index("price") + 1
    for (cell,) in sheet.iter_rows(min_row=2, min_col=price_col, max_col=price_col):
        cell.number_format = "£#,##0.00"
    _autosize_columns(sheet)


def _autosize_columns(sheet: Worksheet) -> None:
    for index, column in enumerate(sheet.iter_cols(), start=1):
        longest = max((len(str(c.value)) for c in column if c.value is not None), default=8)
        sheet.column_dimensions[get_column_letter(index)].width = min(longest + 2, MAX_COLUMN_WIDTH)


# ------------------------------------------------------------------ resume
def load_existing(path: Path, fmt: str) -> list[Book]:
    """Load records from a previous export (used by ``--resume``).

    Returns an empty list if the file is missing or unreadable.
    """
    if not path.exists():
        return []
    try:
        rows = _read_rows(path, fmt)
        return [Book.from_dict(row) for row in rows if row.get("product_url")]
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Could not load existing output %s (%s); starting fresh", path, exc)
        return []


def _read_rows(path: Path, fmt: str) -> list[dict]:
    if fmt == "csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    if fmt == "json":
        return json.loads(path.read_text(encoding="utf-8"))
    if fmt == "xlsx":
        sheet = load_workbook(path, read_only=True).active
        values = list(sheet.iter_rows(values_only=True))
        if not values:
            return []
        keys = Book.field_names()
        return [dict(zip(keys, row, strict=False)) for row in values[1:]]
    raise ValueError(f"Unsupported format {fmt!r}")
