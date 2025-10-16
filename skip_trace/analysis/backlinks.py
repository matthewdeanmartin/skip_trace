# skip_trace/analysis/backlinks.py
from __future__ import annotations

import datetime
import logging
from typing import Dict, List, Set  # <--- Add Dict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import CONFIG
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils import http_client
from .evidence import generate_evidence_id

logger = logging.getLogger(__name__)


def gather_urls_from_evidence(
    evidence_records: List[EvidenceRecord],
) -> Dict[str, EvidenceRecord]:  # <--- Changed return type
    """
    Gathers all unique URLs from evidence, mapping them to their source record.

    Args:
        evidence_records: A list of EvidenceRecord objects.

    Returns:
        A dictionary mapping a unique URL to its original EvidenceRecord.
    """
    urls: Dict[str, EvidenceRecord] = {}  # <--- Changed to a Dict

    for record in evidence_records:
        if isinstance(record.value, dict):
            if url := record.value.get("url"):
                if isinstance(url, str) and url not in urls:
                    urls[url] = record  # <--- Store the whole record

    logger.info(f"Gathered {len(urls)} unique URLs for backlink analysis.")
    return urls


def classify_domain(domain: str) -> str:
    """
    Classifies a domain based on configured lists.

    Args:
        domain: The domain name to classify.

    Returns:
        A string classification: 'ownership', 'neutral', or 'non-ownership'.
    """
    ownership_domains = set(
        CONFIG.get("backlinks", {}).get("ownership_control_domains", [])
    )
    non_ownership_domains = set(
        CONFIG.get("backlinks", {}).get("non_ownership_domains", [])
    )

    if domain in ownership_domains:
        return "ownership"
    if domain in non_ownership_domains:
        return "non-ownership"

    return "neutral"


def analyze_backlinks(
    candidate_url_map: Dict[str, EvidenceRecord], trusted_anchor_urls: Set[str]
) -> List[EvidenceRecord]:
    """
    Verifies candidate URLs by checking if they link back to a trusted anchor URL.

    Args:
        candidate_url_map: A dictionary of potential project URLs to verify.
        trusted_anchor_urls: A set of canonical URLs (e.g., the PyPI project page).

    Returns:
        A list of new EvidenceRecord objects for each verified backlink.
    """
    evidence: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    # seen_links: Set[Tuple[str, str]] = set()
    # urls = url_evidence_map.keys() # <--- Get URLs from the map keys

    # --- NEW LOGIC: Iterate through candidate URLs to verify them ---
    for source_url, source_record in candidate_url_map.items():
        logger.debug(f"Verifying claimed URL by scanning for backlinks: {source_url}")
        response = http_client.make_request_safe(source_url)

        if not response or response.status_code != 200:
            continue

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            logger.warning(f"Failed to parse HTML from {source_url}: {e}")
            continue

        # Find all hyperlinks on the source page
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not isinstance(href, str):
                continue

            # --- FIX: Resolve relative URLs ---
            # This joins the base URL (source_url) with the link's href
            absolute_href = urljoin(source_url, href)

            # --- NEW LOGIC: Check if the link points to a trusted anchor ---
            for target_anchor_url in trusted_anchor_urls:
                if target_anchor_url in absolute_href:
                    logger.info(
                        f"✅ VERIFIED: {source_url} links back to {target_anchor_url}"
                    )

                    value = {
                        "claimed_url": source_url,
                        "claimed_url_origin": f"{source_record.source.value}: {source_record.notes}",
                        "verified_by_linking_to": target_anchor_url,
                    }
                    record = EvidenceRecord(
                        id=generate_evidence_id(
                            EvidenceSource.BACKLINKS,
                            EvidenceKind.BACKLINK,
                            source_url,
                            str(value),
                            target_anchor_url,
                        ),
                        source=EvidenceSource.BACKLINKS,
                        locator=source_url,
                        kind=EvidenceKind.BACKLINK,
                        value=value,
                        observed_at=now,
                        confidence=0.90,  # This is a very high-confidence signal
                        notes=f"The claimed URL '{source_url}' verifies its connection by linking back to the PyPI page.",
                    )
                    evidence.append(record)
                    # Once verified, no need to check for other anchors on this page
                    break
            else:
                continue
            break

    if evidence:
        logger.info(f"Verified {len(evidence)} claimed URLs via backlinks.")
    return evidence
