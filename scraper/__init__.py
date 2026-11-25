"""E-commerce Product Scraper — polite, robust scraping of books.toscrape.com."""

from .config import ScraperConfig
from .crawler import BookScraper, ScrapeResult
from .fetcher import Fetcher, FetchError, RobotsDisallowedError
from .models import Book, ListingItem, ListingPage

__all__ = [
    "Book",
    "BookScraper",
    "FetchError",
    "Fetcher",
    "ListingItem",
    "ListingPage",
    "RobotsDisallowedError",
    "ScrapeResult",
    "ScraperConfig",
]
__version__ = "1.0.0"
