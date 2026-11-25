"""HTTP layer: a polite, resilient wrapper around ``requests.Session``.

Features:
    * custom User-Agent and per-request timeout
    * automatic retries with exponential backoff (honours ``Retry-After``)
    * a thread-safe rate limiter shared by all worker threads
    * ``robots.txt`` compliance via :mod:`urllib.robotparser`
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from types import TracebackType
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .config import ScraperConfig

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

SleepFn = Callable[[float], None]


class FetchError(Exception):
    """Raised when a URL cannot be downloaded after all retries."""


class RobotsDisallowedError(FetchError):
    """Raised when ``robots.txt`` forbids fetching a URL."""


class RateLimiter:
    """Guarantee a minimum interval between consecutive requests (thread-safe)."""

    def __init__(
        self,
        min_interval: float,
        sleep: SleepFn = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        """Block until the caller is allowed to send the next request."""
        if self._interval <= 0:
            return
        with self._lock:
            now = self._clock()
            wait_for = self._next_allowed - now
            self._next_allowed = max(now, self._next_allowed) + self._interval
        if wait_for > 0:
            self._sleep(wait_for)


class Fetcher:
    """Download pages politely and robustly.

    Args:
        config: Scraper configuration.
        session: Optional pre-built session (handy for tests / proxies).
        sleep: Sleep function, injectable so tests run instantly.
    """

    def __init__(
        self,
        config: ScraperConfig,
        session: requests.Session | None = None,
        sleep: SleepFn = time.sleep,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": config.user_agent, "Accept-Language": "en-US,en;q=0.8"}
        )
        self._sleep = sleep
        self._limiter = RateLimiter(config.delay, sleep=sleep)
        self._robots: dict[str, RobotFileParser] = {}
        self._robots_lock = threading.Lock()

    # ------------------------------------------------------------------ public
    def get(self, url: str) -> str:
        """Return the decoded HTML of ``url``.

        Raises:
            RobotsDisallowedError: if ``robots.txt`` disallows the URL.
            FetchError: if the request keeps failing after all retries.
        """
        if not self.can_fetch(url):
            raise RobotsDisallowedError(f"Blocked by robots.txt: {url}")
        return self._get_with_retries(url)

    def can_fetch(self, url: str) -> bool:
        """Check ``url`` against the host's ``robots.txt`` (cached per host)."""
        if not self.config.respect_robots:
            return True
        return self._robots_for(url).can_fetch(self.config.user_agent, url)

    def close(self) -> None:
        """Release pooled connections."""
        self.session.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ----------------------------------------------------------------- helpers
    def _get_with_retries(self, url: str) -> str:
        attempts = self.config.max_retries + 1
        last_error = "unknown error"
        for attempt in range(1, attempts + 1):
            self._limiter.wait()
            retry_after: float | None = None
            try:
                response = self.session.get(url, timeout=self.config.timeout)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code < 400:
                    return _decode(response)
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in RETRYABLE_STATUSES:
                    raise FetchError(f"{last_error} for {url}")
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))

            if attempt < attempts:
                pause = retry_after if retry_after is not None else self._backoff(attempt)
                logger.warning(
                    "Attempt %d/%d failed for %s (%s); retrying in %.1fs",
                    attempt, attempts, url, last_error, pause,
                )
                self._sleep(pause)
        raise FetchError(f"Giving up on {url} after {attempts} attempts: {last_error}")

    def _backoff(self, attempt: int) -> float:
        return self.config.backoff_factor * (2 ** (attempt - 1))

    def _robots_for(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}/"
        with self._robots_lock:
            if root not in self._robots:
                self._robots[root] = self._load_robots(urljoin(root, "robots.txt"))
            return self._robots[root]

    def _load_robots(self, robots_url: str) -> RobotFileParser:
        """Fetch and parse robots.txt with the same rules as the stdlib parser.

        401/403 -> everything disallowed; other 4xx or network errors -> allowed.
        """
        parser = RobotFileParser(robots_url)
        try:
            response = self.session.get(robots_url, timeout=self.config.timeout)
        except requests.RequestException as exc:
            logger.warning("Could not read %s (%s); assuming allowed", robots_url, exc)
            parser.allow_all = True
            return parser
        if response.status_code in (401, 403):
            parser.disallow_all = True
        elif response.status_code >= 400:
            parser.allow_all = True
        else:
            parser.parse(_decode(response).splitlines())
        logger.debug("Loaded robots.txt from %s (status %s)", robots_url, response.status_code)
        return parser


def _decode(response: requests.Response) -> str:
    """Decode a response, defaulting to UTF-8 when the server omits a charset."""
    content_type = response.headers.get("Content-Type", "").lower()
    if "charset" not in content_type:
        response.encoding = "utf-8"
    return response.text


def _parse_retry_after(value: str | None) -> float | None:
    """Return ``Retry-After`` seconds if given as a number (capped at 60s)."""
    if not value:
        return None
    try:
        return min(max(float(value), 0.0), 60.0)
    except ValueError:
        return None
