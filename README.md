# E-commerce Product Scraper

A production-style, ethical Python web scraper built for [books.toscrape.com](https://books.toscrape.com) — demonstrating clean scraping architecture, polite rate limiting, retry backoff, resume support, and multi-format export (**CSV**, **JSON**, and styled **Excel `.xlsx`**).

## Why This Architecture Matters

Many quick-and-dirty scrapers break on the first network hiccup, hammer target servers, or produce messy spreadsheets. This project is structured for real client workloads:

- **Polite & Ethical by Default**: Checks `robots.txt` (`urllib.robotparser`), uses a configurable request delay (`--delay`), and sends a clear custom `User-Agent`.
- **Resilient Networking**: Persistent `requests.Session` with automatic retries, exponential backoff, and per-request timeouts; failed product pages are logged and skipped without crashing the crawl.
- **Concurrent & Resumable**: Multi-threaded product scraping (`ThreadPoolExecutor`) plus `--resume` support to skip already-scraped URLs.
- **Client-Ready Exports**: Outputs clean **CSV**, **JSON**, or formatted **Excel `.xlsx`** (styled header row, auto-fitted column widths, frozen header pane).
- **Decoupled & Tested**: Pure HTML parsers separated from HTTP fetching, verified with **59 offline `pytest` unit and end-to-end tests**.

## Quickstart

```bash
pip install -r requirements.txt

# List available categories
python3 -m scraper --list-categories

# Scrape a category and export to a styled Excel workbook
python3 -m scraper --category travel --format xlsx --output examples/sample_books.xlsx

# Resume an interrupted crawl with 6 concurrent workers
python3 -m scraper --category "Sequential Art" --workers 6 --output books.json --resume
```

## CLI Options

| Flag | Default | Description |
|---|---|---|
| `--category` | *(all books)* | Category name or slug (e.g. `travel`, `"Sequential Art"`) |
| `--max-pages` | *(unlimited)* | Maximum number of paginated listing pages to crawl |
| `--workers` | `4` | Concurrent worker threads for product detail pages |
| `--format` | *(inferred)* | Output format: `csv`, `json`, or `xlsx` |
| `--output` | `books.<fmt>` | Output file path |
| `--delay` | `0.5` | Minimum seconds between requests |
| `--timeout` | `15.0` | HTTP request timeout in seconds |
| `--retries` | `3` | Retry attempts per failed request |
| `--resume` | `False` | Skip product URLs already present in `--output` |
| `--list-categories` | `False` | Print all available categories and exit |
| `-v`, `--verbose` | `False` | Enable debug logging |

## Extracted Fields

Each scraped product record contains:
`title`, `price`, `rating` (1–5), `in_stock`, `stock_count`, `category`, `upc`, `product_url`, `image_url`, and `description`.

Sample outputs generated from the test fixtures are available in [`examples/sample_books.csv`](examples/sample_books.csv) and [`examples/sample_books.xlsx`](examples/sample_books.xlsx).

## Project Structure

```text
ecommerce-scraper/
├── scraper/
│   ├── config.py      # Dataclass configuration & defaults
│   ├── models.py      # Book & Listing dataclasses
│   ├── fetcher.py     # Session, retries, rate limiting & robots.txt
│   ├── parser.py      # Pure BeautifulSoup HTML parsers
│   ├── crawler.py     # Pagination, ThreadPoolExecutor & resume logic
│   ├── exporter.py    # CSV, JSON & styled openpyxl XLSX exporters
│   └── cli.py         # argparse CLI entry point
├── tests/             # 59 offline pytest tests + HTML fixtures
├── examples/          # Sample CSV & Excel outputs
└── requirements.txt
```

## Running Tests

```bash
python3 -m pytest -q
```

## Ethics & Adaptation

This demo targets `books.toscrape.com`, a sandbox site intentionally built for scraping practice. The fetcher, concurrency engine, resume logic, and exporters are modular—adapting this pipeline to a new target site or API only requires swapping `parser.py` and the field schema in `models.py`.

---

**Need a custom scraper, price monitor, or data extraction pipeline?**  
Reach out via [GitHub](https://github.com/Kn0wmyn4m3) or email **ytxy0114@gmail.com**.
