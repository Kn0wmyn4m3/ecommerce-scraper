"""Exporter tests: CSV / JSON / XLSX round-trips and styling."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scraper.exporter import export, infer_format, load_existing
from scraper.models import Book


def test_csv_export_and_reload(tmp_path: Path, sample_books: list[Book]) -> None:
    path = export(sample_books, tmp_path / "out.csv", "csv")
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == Book.field_names()
    assert rows[0]["price"] == "45.17"
    assert load_existing(path, "csv") == sample_books


def test_json_export_and_reload(tmp_path: Path, sample_books: list[Book]) -> None:
    path = export(sample_books, tmp_path / "nested" / "out.json", "json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["description"].startswith("“Wherever")  # not \u-escaped
    assert data[1]["stock_count"] is None
    assert load_existing(path, "json") == sample_books


def test_xlsx_export_is_styled(tmp_path: Path, sample_books: list[Book]) -> None:
    path = export(sample_books, tmp_path / "out.xlsx", "xlsx")
    sheet = load_workbook(path).active
    assert sheet.title == "Products"
    assert sheet["A1"].value == "Title"
    assert sheet["A1"].font.bold is True
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:J3"
    assert sheet["B2"].value == 45.17 and "£" in sheet["B2"].number_format
    assert 10 < sheet.column_dimensions["A"].width <= 60
    assert load_existing(path, "xlsx") == sample_books


def test_unknown_format_raises(tmp_path: Path, sample_books: list[Book]) -> None:
    with pytest.raises(ValueError, match="Unsupported format"):
        export(sample_books, tmp_path / "out.txt", "txt")


def test_load_existing_missing_or_corrupt(tmp_path: Path) -> None:
    assert load_existing(tmp_path / "missing.csv", "csv") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_existing(bad, "json") == []


@pytest.mark.parametrize(
    ("name", "expected"), [("a.CSV", "csv"), ("b.xlsx", "xlsx"), ("c.json", "json"), ("d.txt", None)]
)
def test_infer_format(name: str, expected: str | None) -> None:
    assert infer_format(Path(name)) == expected
