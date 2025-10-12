# skip_trace/utils/http_client.py

import httpx
from typing import Optional

from ..config import CONFIG
from ..exceptions import NetworkError

_client: Optional[httpx.Client] = None


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