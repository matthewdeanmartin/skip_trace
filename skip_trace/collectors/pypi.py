# skip_trace/collectors/pypi.py
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional, Set

from bs4 import BeautifulSoup

from ..analysis.evidence import extract_from_pypi as analyze_pypi_metadata
from ..analysis.evidence import generate_evidence_id
from ..exceptions import NetworkError, NoEvidenceError
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils import http_client

logger = logging.getLogger(__name__)
PYPI_JSON_API_URL = "https://pypi.org/pypi"
PYPI_PROJECT_URL = "https://pypi.org/project"


def fetch_package_metadata(
    package_name: str, version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetches package metadata from the PyPI JSON API.

    :param package_name: The name of the package.
    :param version: The optional specific version of the package.
    :raises NoEvidenceError: If the package is not found (404).
    :raises NetworkError: For other network or HTTP errors.
    :return: A dictionary containing the package's JSON metadata.
    """
    if version:
        url = f"{PYPI_JSON_API_URL}/{package_name}/{version}/json"
    else:
        url = f"{PYPI_JSON_API_URL}/{package_name}/json"

    try:
        response = http_client.make_request(url)
        return response.json()
    except NetworkError as e:
        if "404" in str(e):
            raise NoEvidenceError(
                f"Package '{package_name}'"
                f"{f' version {version}' if version else ''} not found on PyPI."
            ) from e
        raise


def _scrape_user_profile_url(package_name: str) -> Optional[str]:
    """Scrapes the PyPI project page to find the user profile URL."""
    try:
        url = f"{PYPI_PROJECT_URL}/{package_name}/"
        logger.debug(f"Scraping project page for user link: {url}")
        response = http_client.make_request(url)
        soup = BeautifulSoup(response.text, "html.parser")

        # The user link is typically in a `p` tag with the class 'sidebar-section__user-gravatar-text'
        user_link = soup.find("a", href=lambda href: href and href.startswith("/user/"))
        if user_link and user_link.has_attr("href"):
            profile_url = f"https://pypi.org{user_link['href']}"
            logger.debug(f"Found user profile URL: {profile_url}")
            return profile_url
    except NetworkError as e:
        logger.warning(f"Could not scrape project page for '{package_name}': {e}")
    return None


def _fetch_other_package_urls(user_profile_url: str) -> Set[str]:
    """Scrapes a user's profile page to find their other packages."""
    packages = set()
    try:
        logger.debug(f"Scraping user profile for other packages: {user_profile_url}")
        response = http_client.make_request(user_profile_url)
        soup = BeautifulSoup(response.text, "html.parser")

        # Links to packages are in a 'package-snippet' class
        for link in soup.find_all("a", class_="package-snippet"):
            if link.has_attr("href") and link["href"].startswith("/project/"):  # type: ignore[union-attr]
                packages.add(link["href"].split("/")[2])  # type: ignore[union-attr]
        logger.debug(f"Found {len(packages)} other packages by user.")
        return packages
    except NetworkError as e:
        logger.warning(f"Could not scrape user profile page '{user_profile_url}': {e}")
    return packages


def cross_reference_by_user(package_name: str) -> List[EvidenceRecord]:
    """
    Finds other packages by the same user to uncover more evidence.
    Also creates an evidence record for the PyPI user itself and key PyPI URLs.

    Args:
        package_name: The name of the starting package.

    Returns:
        A list of new EvidenceRecord objects found from related packages.
    """
    new_evidence: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    project_page_url = f"{PYPI_PROJECT_URL}/{package_name}/"

    # --- NEW: Always add the PyPI project page itself as a URL to scan ---
    project_page_value = {"label": "PyPI Project Page", "url": project_page_url}
    new_evidence.append(
        EvidenceRecord(
            id=generate_evidence_id(
                EvidenceSource.PYPI,
                EvidenceKind.PROJECT_URL,
                project_page_url,
                str(project_page_value),
                package_name,
                hint="project-page",
            ),
            source=EvidenceSource.PYPI,
            locator=project_page_url,
            kind=EvidenceKind.PROJECT_URL,
            value=project_page_value,
            observed_at=now,
            confidence=0.1,  # Informational, not for direct scoring
            notes=f"The canonical PyPI project page for '{package_name}'.",
        )
    )

    profile_url = _scrape_user_profile_url(package_name)

    # --- Always create evidence for the PyPI user if found ---
    if profile_url:
        try:
            username = profile_url.strip("/").rsplit("/", maxsplit=1)[-1]
            user_value = {"name": username, "url": profile_url}
            new_evidence.append(
                EvidenceRecord(
                    id=generate_evidence_id(
                        EvidenceSource.PYPI,
                        EvidenceKind.PYPI_USER,
                        profile_url,
                        str(user_value),
                        username,
                    ),
                    source=EvidenceSource.PYPI,
                    locator=profile_url,
                    kind=EvidenceKind.PYPI_USER,
                    value=user_value,
                    observed_at=now,
                    confidence=0.50,
                    notes=f"Package is published by PyPI user '{username}'.",
                )
            )
            logger.debug(f"Created evidence record for PyPI user '{username}'.")

            # --- NEW: Also add the user profile page as a URL to scan ---
            user_page_value = {"label": "PyPI User Page", "url": profile_url}
            new_evidence.append(
                EvidenceRecord(
                    id=generate_evidence_id(
                        EvidenceSource.PYPI,
                        EvidenceKind.PROJECT_URL,
                        profile_url,
                        str(user_page_value),
                        username,
                        hint="user-page",
                    ),
                    source=EvidenceSource.PYPI,
                    locator=profile_url,
                    kind=EvidenceKind.PROJECT_URL,
                    value=user_page_value,
                    observed_at=now,
                    confidence=0.1,  # Informational
                    notes=f"The PyPI user profile page for '{username}'.",
                )
            )

        except (IndexError, TypeError) as e:
            logger.warning(
                f"Could not parse username from profile URL '{profile_url}': {e}"
            )

    # --- Continue with existing cross-referencing logic ---
    if not profile_url:
        return new_evidence  # Return just the project page URL evidence

    other_packages = _fetch_other_package_urls(profile_url)
    if not other_packages:
        return new_evidence

    # new_evidence: List[EvidenceRecord] = []
    # Limit to analyzing a few other packages to avoid excessive requests
    for other_pkg in list(other_packages)[:3]:
        if other_pkg == package_name:
            continue
        try:
            logger.info(f"Cross-referencing with related package: '{other_pkg}'")
            metadata = fetch_package_metadata(other_pkg)
            # We only care about strong signals (like repo URLs) from other packages
            evidence, _ = analyze_pypi_metadata(metadata)
            for record in evidence:
                if "repository URL" in record.notes:
                    new_evidence.append(record)
        except NoEvidenceError:
            logger.debug(f"Skipping related package '{other_pkg}', not found.")
            continue

    logger.info(
        f"Found {len(new_evidence)} new evidence records via user cross-reference."
    )
    return new_evidence
