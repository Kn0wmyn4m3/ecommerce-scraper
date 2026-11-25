"""End-to-end crawler and CLI tests against the offline fixture site."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from scraper import cli
from scraper.crawler import BookScraper

from .conftest import BASE, TRAVEL, FakeFetcher

HIMALAYAS = BASE + "catalogue/its-only-the-himalayas_981/index.html"
SEE_AMERICA = BASE + "catalogue/see-america-a-celebration-of-our-national-parks-treasured-sites_732/index.html"


@pytest.mark.parametrize("name", ["travel", "Travel", "travel_2", " TRAVEL "])
def test_resolve_category(site: FakeFetcher, name: str) -> None:
    assert BookScraper(site, BASE).resolve_start_url(name) == TRAVEL + "index.html"


def test_resolve_all_books(site: FakeFetcher) -> None:
    assert BookScraper(site, BASE).resolve_start_url(None) == BASE + "catalogue/page-1.html"


def test_unknown_category_lists_options(site: FakeFetcher) -> None:
    with pytest.raises(ValueError, match="Available: .*Travel"):
        BookScraper(site, BASE).resolve_start_url("cooking")


def test_collect_follows_pagination(site: FakeFetcher) -> None:
    urls = BookScraper(site, BASE).collect_product_urls(TRAVEL + "index.html")
    assert len(urls) == 3
    assert urls[0] == HIMALAYAS and urls[-1] == SEE_AMERICA


def test_collect_respects_max_pages(site: FakeFetcher) -> None:
    urls = BookScraper(site, BASE).collect_product_urls(TRAVEL + "index.html", max_pages=1)
    assert len(urls) == 2
    assert TRAVEL + "page-2.html" not in site.requested


def test_run_logs_and_continues_on_failures(site: FakeFetcher, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        result = BookScraper(site, BASE, workers=3).run(category="travel")
    assert len(result.books) == 2
    assert result.books[0].product_url == HIMALAYAS  # listing order preserved
    assert result.failed_urls == [SEE_AMERICA]
    assert "Failed" in caplog.text


def test_run_skips_already_scraped(site: FakeFetcher) -> None:
    result = BookScraper(site, BASE).run(category="travel", skip_urls=[HIMALAYAS])
    assert result.skipped == 1
    assert HIMALAYAS not in [b.product_url for b in result.books]


# ---------------------------------------------------------------------- CLI
@pytest.fixture
def patched_cli(site: FakeFetcher, monkeypatch: pytest.MonkeyPatch) -> FakeFetcher:
    """Make the CLI use the offline fixture site instead of the network."""

    class OfflineFetcher:
        def __init__(self, config) -> None:
            self.config = config

        def __enter__(self) -> FakeFetcher:
            return site

        def __exit__(self, *exc) -> None:
            return None

    monkeypatch.setattr(cli, "Fetcher", OfflineFetcher)
    return site


@pytest.mark.parametrize(
    ("output", "fmt", "expected"),
    [(None, None, ("books.csv", "csv")), ("x.xlsx", None, ("x.xlsx", "xlsx")),
     ("x.dat", "json", ("x.dat", "json")), (None, "json", ("books.json", "json"))],
)
def test_resolve_output(output: str | None, fmt: str | None, expected: tuple[str, str]) -> None:
    path, resolved = cli.resolve_output(Path(output) if output else None, fmt)
    assert (str(path), resolved) == expected


def test_cli_end_to_end_xlsx(patched_cli: FakeFetcher, tmp_path: Path) -> None:
    out = tmp_path / "books.xlsx"
    code = cli.main(["--category", "travel", "--format", "xlsx", "--output", str(out), "--workers", "2"])
    assert code == 0
    assert out.exists()


def test_cli_resume(patched_cli: FakeFetcher, tmp_path: Path) -> None:
    out = tmp_path / "books.json"
    assert cli.main(["--category", "travel", "--output", str(out)]) == 0
    patched_cli.requested.clear()
    assert cli.main(["--category", "travel", "--output", str(out), "--resume"]) == 0
    assert HIMALAYAS not in patched_cli.requested


def test_cli_unknown_category_exit_code(patched_cli: FakeFetcher, tmp_path: Path) -> None:
    assert cli.main(["--category", "nope", "--output", str(tmp_path / "x.csv")]) == 2


def test_cli_list_categories(patched_cli: FakeFetcher, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--list-categories"]) == 0
    assert "Sequential Art" in capsys.readouterr().out


def test_cli_rejects_bad_workers() -> None:
    with pytest.raises(SystemExit):
        cli.main(["--workers", "0"])
