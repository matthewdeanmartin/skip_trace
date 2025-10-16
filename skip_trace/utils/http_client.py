# skip_trace/utils/http_client.py
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from ..config import CONFIG
from ..exceptions import NetworkError

_client: Optional[httpx.Client] = None
logger = logging.getLogger(__name__)


def normalize_url(url: str) -> Optional[str]:
    """
    Cleans and normalizes a URL string for HTTP requests.

    - Strips whitespace and trailing slashes.
    - Adds 'https://' if no scheme is present.
    - Returns None for invalid, empty, or non-http URLs.
    """
    if not isinstance(url, str) or not url.strip():
        return None

    cleaned_url = url.strip().rstrip("/")

    # Prepend scheme if missing
    if "://" not in cleaned_url:
        # Avoid prepending to mailto: links or local paths
        if cleaned_url.startswith(("mailto:", "file:", "/")):
            return None
        cleaned_url = f"https://{cleaned_url}"

    # Use urlparse for a final sanity check
    try:
        parsed = urlparse(cleaned_url)
        # Check if it has a scheme and a network location (hostname)
        if not all([parsed.scheme, parsed.netloc]):
            return None
        # Only allow http and https schemes
        if parsed.scheme not in ("http", "https"):
            return None
    except ValueError:
        return None

    return cleaned_url


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


def _attempt_request(client: httpx.Client, url: str) -> httpx.Response:
    """Internal helper to attempt requests with https->http fallback on connection errors."""
    try:
        # First, try the URL as is (which will be https by default from normalize)
        return client.get(url)
    except httpx.ConnectError as e:
        # If it was an https URL that failed to connect, try http
        if url.startswith("https://"):
            http_url = url.replace("https://", "http://", 1)
            logger.debug(
                f"HTTPS connection failed for '{url}', falling back to '{http_url}'"
            )
            try:
                # Second attempt with http
                return client.get(http_url)
            except httpx.RequestError as http_e:
                # If the http fallback also fails, raise the original error for context
                raise NetworkError(
                    f"Network request to {http_e.request.url} failed after fallback: {http_e}"
                ) from e
        # If it wasn't an https url or http fallback failed, re-raise the original error
        raise NetworkError(f"Network request to {e.request.url} failed: {e}") from e


def make_request(url: str) -> httpx.Response:
    """
    Makes a GET request using the shared client and handles common errors.
    Automatically attempts https and falls back to http on connection failure.

    :param url: The URL to fetch.
    :raises NetworkError: If the request fails due to network issues or an error status code.
    :return: The httpx.Response object.
    """
    clean_url = normalize_url(url)
    if not clean_url:
        raise NetworkError(f"Invalid or unsupported URL format: '{url}'")

    logger.info(f"Looking at {clean_url}")
    client = get_client()
    try:
        response = _attempt_request(client, clean_url)
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
    clean_url = normalize_url(url)
    if not clean_url:
        logger.debug(f"Skipping invalid or unsupported URL: '{url}'")
        return None

    logger.info(f"Looking at {clean_url}")
    client = get_client()

    try:
        return _attempt_request(client, clean_url)
    except NetworkError as e:
        logger.warning(str(e))
        return None
