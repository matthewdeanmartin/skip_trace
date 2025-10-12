# skip_trace/utils/http_client.py
from __future__ import annotations

import logging
from typing import Optional

import httpx

from ..config import CONFIG
from ..exceptions import NetworkError

_client: Optional[httpx.Client] = None
logger = logging.getLogger(__name__)


def get_client() -> httpx.Client:
    """Returns a shared httpx.Client instance."""
    global _client
    if _client is None:
        http_config = CONFIG.get("http", {})
        _client = httpx.Client(
            headers={"User-Agent": http_config.get("user_agent", "skip-trace")},
            timeout=http_config.get("timeout", 5),
            follow_redirects=True,
        )
    return _client


def make_request(url: str) -> httpx.Response:
    """
    Makes a GET request using the shared client and handles common errors.

    :param url: The URL to fetch.
    :raises NetworkError: If the request fails due to network issues or an error status code.
    :return: The httpx.Response object.
    """
    logger.info(f"Looking at {url}")
    client = get_client()
    try:
        response = client.get(url)
        response.raise_for_status()
        return response
    except httpx.RequestError as e:
        raise NetworkError(f"Network request to {e.request.url} failed: {e}") from e
    except httpx.HTTPStatusError as e:
        raise NetworkError(
            f"Request to {e.request.url} failed with status {e.response.status_code}"
        ) from e


def make_request_safe(url: str) -> Optional[httpx.Response]:
    """
    Makes a GET request but returns the response even on HTTP error codes,
    or None if a connection-level error occurs.
    """
    logger.info(f"Looking at {url}")
    client = get_client()
    try:
        response = client.get(url)
        return response
    except httpx.RequestError as e:
        logger.warning(f"Network request to {e.request.url} failed: {e}")
        return None  # Indicate a connection-level error
