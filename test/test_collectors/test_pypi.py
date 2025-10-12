# tests/test_pypi_collector_integration.py
from __future__ import annotations

import datetime
from typing import Any, Dict, Set

import pytest

from skip_trace.collectors import pypi as pypi_collector
from skip_trace.exceptions import NoEvidenceError
from skip_trace.schemas import EvidenceKind, EvidenceRecord

# Stable, high-signal packages. Adjust if they ever go away.
PKG = "requests"
PKG_VERSION = "2.32.3"  # pick a widely mirrored, recent stable; update if yanked
FAKE = "this-package-name-should-not-exist-zzxxyyqq"


def test_fetch_package_metadata_latest(require_pypi):
    meta: Dict[str, Any] = pypi_collector.fetch_package_metadata(PKG)
    assert isinstance(meta, dict)
    assert "info" in meta and isinstance(meta["info"], dict)
    assert meta["info"].get("name", "").lower() == PKG


def test_fetch_package_metadata_specific_version(require_pypi):
    meta: Dict[str, Any] = pypi_collector.fetch_package_metadata(PKG, PKG_VERSION)
    assert meta["info"].get("version") == PKG_VERSION


def test_fetch_package_metadata_missing_raises(require_pypi):
    with pytest.raises(NoEvidenceError):
        pypi_collector.fetch_package_metadata(FAKE)


def test_scrape_user_profile_url_found(require_pypi):
    url = pypi_collector._scrape_user_profile_url(
        PKG
    )  # integration: call private is fine
    # Not all projects expose a single maintainer prominently; accept None but prefer a URL.
    assert (url is None) or url.startswith("https://pypi.org/user/")
    # If present, it should end with a username path segment
    if url:
        assert url.rstrip("/").count("/") >= 4  # https://pypi.org/user/<name>


def test_fetch_other_package_urls_has_results_when_profile_exists(require_pypi):
    profile_url = pypi_collector._scrape_user_profile_url(PKG)
    if profile_url is None:
        pytest.skip("No visible PyPI user profile on project page; cannot cross-check.")
    pkgs: Set[str] = pypi_collector._fetch_other_package_urls(profile_url)
    # Some maintainers only have one package; allow empty but prefer >= 1.
    assert isinstance(pkgs, set)
    assert all(isinstance(n, str) and n for n in pkgs)


def test_cross_reference_by_user_emits_user_evidence(require_pypi):
    records = pypi_collector.cross_reference_by_user(PKG)
    assert isinstance(records, list)
    # Must include a PYPI_USER record when a profile URL is discoverable
    kinds = {r.kind for r in records}
    # If no profile was found, cross_reference_by_user may legally return []
    if records:
        assert EvidenceKind.PYPI_USER in kinds
        # basic schema sanity on at least one record
        user_records = [r for r in records if r.kind is EvidenceKind.PYPI_USER]
        r0: EvidenceRecord = user_records[0]
        assert r0.source.name == "PYPI"
        assert isinstance(r0.locator, str) and r0.locator.startswith(
            "https://pypi.org/user/"
        )
        assert isinstance(r0.value, dict) and "name" in r0.value and "url" in r0.value
        assert (
            isinstance(r0.observed_at, datetime.datetime)
            and r0.observed_at.tzinfo is not None
        )
        assert 0.0 <= r0.confidence <= 1.0
