# skip_trace/analysis/content_scanner.py
from __future__ import annotations

import datetime
import logging
import re
from typing import List

from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils.validation import is_valid_email
from . import ner
from .evidence import _parse_contact_string, generate_evidence_id

# Regex to find copyright notices, capturing the holder.
COPYRIGHT_RE = re.compile(
    r"copyright\s*(?:\(c\))?\s*(?:[0-9,\-\s]+)?\s*([^\n]+)", re.IGNORECASE
)

# Regex to find __author__ assignments
AUTHOR_RE = re.compile(r"__author__\s*=\s*['\"]([^'\"]+)['\"]")

# Regex for finding standalone email addresses - used as a fast pre-filter
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# --- Regex for finding URLs in text content ---
URL_RE = re.compile(
    r"""\b(?:https?://|www\.)[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?:[/?#]\S*)?"""
)

# Words that indicate a regex grabbed junk from a license instead of a name.
JUNK_WORDS = {
    "copyright",
    "holders",
    "license",
    "document",
    "accompanies",
    "notice",
    "authors",
    "identifies",
    "endorse",
    "promote",
    "software",
    "permission",
    "conditions",
    "and",
    "other",
    "the",
    "for",
    "with",
    "this",
    "list",
    "following",
    "txt",
    "damages",
    "owner",
    "incidental",
    "holder",
    "liability",
    "MIT",
    "BSD",
}

logger = logging.getLogger(__name__)


def scan_text(
    content: str, locator: str, source: EvidenceSource, is_python_file: bool = False
) -> List[EvidenceRecord]:
    """
    Scans a string of text content for ownership evidence.

    Args:
        content: The text content to scan.
        locator: The path or URL where the content was found.
        source: The EvidenceSource to assign to new records.
        is_python_file: Flag to enable Python-specific scans like `__author__`.

    Returns:
        A list of EvidenceRecord objects found in the text.
    """
    logger.info(f"Scanning {locator}")
    evidence_list: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    found_in_scan = set()  # Avoid creating duplicate records from the same scan

    # 1. Scan for copyright notices
    for match in COPYRIGHT_RE.finditer(content):
        copyright_text = match.group(1).strip().rstrip(",.")
        entities = ner.extract_entities(copyright_text)
        if entities:
            for entity_name, entity_label in entities:
                if entity_name.lower() not in JUNK_WORDS:
                    key = ("copyright", entity_name)
                    if key in found_in_scan:
                        continue
                    found_in_scan.add(key)
                    value: dict[str, str | None] = {"holder": entity_name}
                    record = EvidenceRecord(
                        id=generate_evidence_id(
                            source,
                            EvidenceKind.COPYRIGHT,
                            locator,
                            str(value),
                            entity_name,
                        ),
                        source=source,
                        locator=locator,
                        kind=EvidenceKind.COPYRIGHT,
                        value=value,
                        observed_at=now,
                        confidence=0.40,
                        notes=f"Found copyright holder '{entity_name}' via NER ({entity_label}) in '{locator}'.",
                    )
                    evidence_list.append(record)

    # 2. Scan for __author__ tags in Python files
    if is_python_file:
        for match in AUTHOR_RE.finditer(content):
            author_str = match.group(1).strip()
            key = ("author", author_str)
            if key in found_in_scan:
                continue
            found_in_scan.add(key)
            parsed = _parse_contact_string(author_str)
            if parsed.get("name") or parsed.get("email"):
                value = {"name": parsed["name"], "email": parsed["email"]}
                slug = parsed["name"] or parsed["email"] or "unknown"
                record = EvidenceRecord(
                    id=generate_evidence_id(
                        source, EvidenceKind.AUTHOR_TAG, locator, str(value), slug
                    ),
                    source=source,
                    locator=locator,
                    kind=EvidenceKind.AUTHOR_TAG,
                    value=value,
                    observed_at=now,
                    confidence=0.20,
                    notes=f"Found __author__ tag for '{author_str}' in '{locator}'.",
                )
                evidence_list.append(record)

    # 3. Scan for any standalone email address
    for match in EMAIL_RE.finditer(content):
        if valid_email := is_valid_email(match.group(0)):
            if ("email", valid_email) in found_in_scan:
                continue
            found_in_scan.add(("email", valid_email))
            value = {"name": None, "email": valid_email}
            record = EvidenceRecord(
                id=generate_evidence_id(
                    source, EvidenceKind.CONTACT, locator, str(value), valid_email
                ),
                source=source,
                locator=locator,
                kind=EvidenceKind.CONTACT,
                value=value,
                observed_at=now,
                confidence=0.15,
                notes=f"Found validated contact email '{valid_email}' in '{locator}'.",
            )
            evidence_list.append(record)

    # 4. Scan for any URLs
    for match in URL_RE.finditer(content):
        url = match.group(0)
        if ("url", url) in found_in_scan:
            continue
        found_in_scan.add(("url", url))
        value = {"label": "URL found in content", "url": url}
        record = EvidenceRecord(
            id=generate_evidence_id(
                source,
                EvidenceKind.PROJECT_URL,
                locator,
                str(value),
                url,
                hint="content-scan",
            ),
            source=source,
            locator=locator,
            kind=EvidenceKind.PROJECT_URL,
            value=value,
            observed_at=now,
            confidence=0.10,
            notes=f"Found URL '{url}' in '{locator}'.",
        )
        evidence_list.append(record)

    return evidence_list
