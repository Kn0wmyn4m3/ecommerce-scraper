"""Runtime configuration for the scraper."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BASE_URL = "https://books.toscrape.com/"
DEFAULT_USER_AGENT = (
    "EcommerceProductScraper/1.0 (+https://github.com/Kn0wmyn4m3; polite portfolio bot)"
)


@dataclass(frozen=True, slots=True)
class ScraperConfig:
    """All tunable knobs in one immutable object.

    Attributes:
        base_url: Root URL of the target site (must end with ``/``).
        user_agent: User-Agent header sent with every request.
        timeout: Per-request timeout in seconds.
        max_retries: How many times a failed request is retried.
        backoff_factor: Base for exponential backoff (``factor * 2**n`` seconds).
        delay: Minimum seconds between two requests (shared across all threads).
        workers: Number of threads used to download product pages.
        respect_robots: Whether to honour the site's ``robots.txt``.
    """

    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 15.0
    max_retries: int = 3
    backoff_factor: float = 0.5
    delay: float = 0.5
    workers: int = 4
    respect_robots: bool = True

    def __post_init__(self) -> None:
        if not self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url + "/")
        if self.workers < 1:
            raise ValueError("workers must be >= 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.delay < 0 or self.timeout <= 0:
            raise ValueError("delay must be >= 0 and timeout > 0")
