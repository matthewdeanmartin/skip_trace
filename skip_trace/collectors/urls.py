# skip_trace/collectors/urls.py
from __future__ import annotations

import datetime
import logging
import os
from typing import List, Set

from bs4 import BeautifulSoup

from ..analysis.content_scanner import scan_text
from ..analysis.evidence import generate_evidence_id
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils import http_client
from ..utils.cache import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)
URL_CACHE_DIR = ".urls"


def _ensure_download_dir():
    """Ensures the URL cache directory and .gitignore exist."""
    os.makedirs(URL_CACHE_DIR, exist_ok=True)
    gitignore_path = os.path.join(URL_CACHE_DIR, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("*\n")


def collect_from_urls(urls: Set[str]) -> List[EvidenceRecord]:
    """
    Downloads, caches, and scans a list of URLs for evidence.

    Args:
        urls: A set of unique URLs to scan.

    Returns:
        A list of EvidenceRecord objects from the URLs.
    """
    _ensure_download_dir()
    all_evidence: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)

    for url in urls:
        logger.info(f"Analyzing URL: {url}")
        cached_data = get_cached_data("url", url)

        status_code = -1
        content = ""

        if cached_data:
            logger.debug(f"Using cached content for {url}")
            status_code = cached_data.get("status_code", -1)
            content = cached_data.get("content", "")
        else:
            response = http_client.make_request_safe(url)
            if response:
                status_code = response.status_code
                if status_code == 200:
                    content = response.text
                set_cached_data(
                    "url", url, {"status_code": status_code, "content": content}
                )
            else:
                set_cached_data(
                    "url", url, {"status_code": -1, "content": ""}
                )  # Cache connection failure

        # Create an evidence record for the URL status itself
        status_value = {"status_code": status_code}
        status_record = EvidenceRecord(
            id=generate_evidence_id(
                EvidenceSource.URL, EvidenceKind.URL_STATUS, url, str(status_value), url
            ),
            source=EvidenceSource.URL,
            locator=url,
            kind=EvidenceKind.URL_STATUS,
            value=status_value,
            observed_at=now,
            confidence=0.0,  # This is informational, not for scoring
            notes=f"HTTP status for {url} was {status_code}.",
        )
        all_evidence.append(status_record)

        if content:
            try:
                # Scan page content for non-URL evidence like copyright and emails.
                soup = BeautifulSoup(content, "html.parser")
                text_content = soup.get_text(separator=" ", strip=True)

                claim_evidence = scan_text(text_content, url, EvidenceSource.URL)

                if claim_evidence:
                    found_count = len(claim_evidence)
                    logger.info(f"Found {found_count} evidence records on {url}")
                    all_evidence.extend(claim_evidence)

                # # 1. Scan for non-URL claims (copyrights, emails) from plain text
                # soup = BeautifulSoup(content, "html.parser")
                # text_content = soup.get_text(separator=" ", strip=True)
                # # Scan for claims (copyrights, emails)
                # claim_evidence = scan_text(text_content, url, EvidenceSource.URL)
                # all_evidence.extend(claim_evidence)
                # # Scan for more URLs
                #
                # # 2. Use the new, smarter URL scanner for HTML content
                # url_evidence = url_scanner.scan_text_for_urls(
                #     content, url, EvidenceSource.URL, file_type='html'
                # )
                # all_evidence.extend(url_evidence)
                #
                # found_count = len(claim_evidence) + len(url_evidence)
                # if found_count > 0:
                #     logger.info(f"Found {found_count} evidence records on {url}")
            except Exception as e:
                logger.warning(f"Could not parse or scan HTML from {url}: {e}")

    return all_evidence
