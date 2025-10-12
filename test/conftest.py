# tests/conftest.py
from __future__ import annotations

import pytest

from skip_trace.utils import http_client
from skip_trace.exceptions import NetworkError

PYPI_PING_URL = "https://pypi.org/simple/"

@pytest.fixture(scope="session")
def require_pypi():
    """Skip the whole test session if PyPI is unreachable."""
    try:
        # use project http client to mirror real behavior
        http_client.make_request(PYPI_PING_URL)
    except NetworkError as e:
        pytest.skip(f"PyPI unreachable for integration tests: {e}")
