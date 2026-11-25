"""Fetcher tests — the network is fully mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from scraper.config import ScraperConfig
from scraper.fetcher import Fetcher, FetchError, RateLimiter, RobotsDisallowedError

URL = "https://example.com/page.html"
ROBOTS = "https://example.com/robots.txt"


def make_response(status: int = 200, body: str = "", headers: dict | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body.encode("utf-8")
    response.headers.update(headers or {"Content-Type": "text/html"})
    return response


def make_fetcher(routes: dict[str, list], **config_kwargs) -> tuple[Fetcher, MagicMock, list[float]]:
    """Build a Fetcher whose session returns queued responses per URL."""
    queues = {url: list(items) for url, items in routes.items()}

    def fake_get(url: str, timeout: float) -> requests.Response:
        item = queues[url].pop(0) if len(queues[url]) > 1 else queues[url][0]
        if isinstance(item, Exception):
            raise item
        return item

    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = fake_get
    sleeps: list[float] = []
    config = ScraperConfig(delay=0, backoff_factor=0.5, **config_kwargs)
    return Fetcher(config, session=session, sleep=sleeps.append), session, sleeps


def test_sets_user_agent_and_decodes_utf8_without_charset() -> None:
    fetcher, session, _ = make_fetcher(
        {ROBOTS: [make_response(404)], URL: [make_response(body="<p>£51.77</p>")]},
        user_agent="TestBot/1.0",
    )
    assert fetcher.get(URL) == "<p>£51.77</p>"
    assert session.headers["User-Agent"] == "TestBot/1.0"
    session.get.assert_called_with(URL, timeout=15.0)


def test_retries_with_exponential_backoff_then_succeeds() -> None:
    fetcher, session, sleeps = make_fetcher(
        {
            ROBOTS: [make_response(404)],
            URL: [requests.ConnectionError("boom"), make_response(503), make_response(body="ok")],
        }
    )
    assert fetcher.get(URL) == "ok"
    assert sleeps == [0.5, 1.0]


def test_honours_retry_after_header() -> None:
    fetcher, _, sleeps = make_fetcher(
        {
            ROBOTS: [make_response(404)],
            URL: [make_response(429, headers={"Retry-After": "7"}), make_response(body="ok")],
        }
    )
    assert fetcher.get(URL) == "ok"
    assert sleeps == [7.0]


def test_gives_up_after_max_retries() -> None:
    fetcher, session, sleeps = make_fetcher(
        {ROBOTS: [make_response(404)], URL: [requests.Timeout("slow")]}, max_retries=2
    )
    with pytest.raises(FetchError, match="after 3 attempts"):
        fetcher.get(URL)
    assert len(sleeps) == 2


def test_does_not_retry_client_errors() -> None:
    fetcher, session, sleeps = make_fetcher({ROBOTS: [make_response(404)], URL: [make_response(404)]})
    with pytest.raises(FetchError, match="HTTP 404"):
        fetcher.get(URL)
    assert sleeps == []


def test_respects_robots_disallow() -> None:
    robots = make_response(body="User-agent: *\nDisallow: /page.html\n", headers={"Content-Type": "text/plain"})
    fetcher, session, _ = make_fetcher({ROBOTS: [robots], URL: [make_response(body="secret")]})
    with pytest.raises(RobotsDisallowedError):
        fetcher.get(URL)
    assert all(call.args[0] != URL for call in session.get.call_args_list)


def test_robots_403_disallows_everything_and_is_cached() -> None:
    fetcher, session, _ = make_fetcher({ROBOTS: [make_response(403)]})
    assert fetcher.can_fetch(URL) is False
    assert fetcher.can_fetch("https://example.com/other") is False
    assert [c.args[0] for c in session.get.call_args_list] == [ROBOTS]


def test_robots_network_error_assumes_allowed() -> None:
    fetcher, _, _ = make_fetcher({ROBOTS: [requests.ConnectionError("down")]})
    assert fetcher.can_fetch(URL) is True


def test_robots_can_be_disabled() -> None:
    fetcher, session, _ = make_fetcher({URL: [make_response(body="ok")]}, respect_robots=False)
    assert fetcher.get(URL) == "ok"
    session.get.assert_called_once()


def test_rate_limiter_spaces_requests() -> None:
    clock_value = [100.0]
    sleeps: list[float] = []
    limiter = RateLimiter(1.0, sleep=sleeps.append, clock=lambda: clock_value[0])
    limiter.wait()  # first call: no wait
    limiter.wait()  # immediately again: must wait ~1s
    clock_value[0] += 5
    limiter.wait()  # long after: no wait
    assert sleeps == [1.0]
