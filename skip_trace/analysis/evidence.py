# skip_trace/analysis/evidence.py

import datetime
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import tldextract

from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource, Maintainer
from ..utils.validation import is_valid_email
from . import ner  # Import the NER module

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """
    Creates a URL-friendly slug from a string.

    Converts to lowercase, folds to ASCII, replaces non-alphanumeric
    characters with hyphens, and removes duplicate hyphens.

    Args:
        text: The string to slugify.

    Returns:
        A slugified string.
    """
    if not text:
        return ""
    # Simple ASCII folding
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    # Replace non-alphanumeric with hyphen
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text


def generate_evidence_id(
        source: EvidenceSource,
        kind: EvidenceKind,
        locator: str,
        value: Any,  # Changed to Any for dataclasses
        slug_subject: str,
        hint: Optional[str] = None
) -> str:
    """
    Generates a human-readable and deterministic Evidence ID.

    Format: e-<source>-<kind>-<slug>[--<hint>]~<hash8>

    Args:
        source: The source of the evidence.
        kind: The kind of evidence.
        locator: The URL or path where the evidence was found.
        value: The value of the evidence itself.
        slug_subject: The primary entity to use for the slug (e.g., person, org).
        hint: An optional hint to add to the slug for disambiguation.

    Returns:
        A formatted, unique evidence ID string.
    """
    slug = _slugify(slug_subject)
    if hint:
        slug = f"{slug}--{_slugify(hint)}"

    # Truncate slug to a reasonable length to keep ID under 96 chars
    max_slug_len = 60
    slug = slug[:max_slug_len]

    # Create the hash
    hasher = hashlib.sha256()
    hasher.update(f"{source.value}|{kind.value}|{locator}|{value}".encode('utf-8'))
    hash8 = hasher.hexdigest()[:8]

    return f"e-{source.value}-{kind.value}-{slug}~{hash8}"

def _parse_contact_string(contact_str: str) -> Dict[str, Optional[str]]:
    """
    Parses a contact string into its name and email components.

    Handles formats like "Name <email>", "email", and "Name".

    Args:
        contact_str: The string to parse.

    Returns:
        A dictionary with "name" and "email" keys.
    """
    if not contact_str or not contact_str.strip():
        return {"name": None, "email": None}

    # Pattern for "Name <email@domain.com>"
    match = re.search(r'(.+)<(.+)>', contact_str)
    if match:
        name = match.group(1).strip()
        # Validate the email part using the robust validator
        email = is_valid_email(match.group(2).strip())
        return {"name": name, "email": email}

    # If the whole string is a valid email, use it.
    if email := is_valid_email(contact_str):
        return {"name": None, "email": email}

    # Fallback to NER if it's not a clear email format
    list_of_entities = ner.extract_entities(contact_str.strip())
    for entity, kind in list_of_entities:
        if kind == "PERSON":
            return {"name": entity, "email": None}

    # If no email and no person from NER, we got nothing
    return {"name": None, "email": None}


# NEW: Helper to sanitize fields that might contain the literal string "None"
def _clean_pypi_field(field_value: Any) -> str:
    """Returns an empty string if the field is None or the literal string 'None'."""
    if field_value is None or str(field_value).strip().lower() == "none":
        return ""
    return str(field_value).strip()


def extract_from_pypi(metadata: Dict[str, Any]) -> Tuple[List[EvidenceRecord], List[Maintainer]]:
    """
    Extracts evidence from raw PyPI package metadata.

    Args:
        metadata: The dictionary of package metadata from the PyPI JSON API.

    Returns:
        A tuple containing:
         - A list of EvidenceRecord objects.
         - A list of Maintainer objects from direct PyPI fields.
    """
    evidence_list: List[EvidenceRecord] = []
    maintainer_list: List[Maintainer] = []
    seen_maintainers = set()

    info = metadata.get("info", {})
    if not info:
        logger.warning("PyPI metadata is missing the 'info' dictionary.")
        return [], []

    package_name = info.get("name", "unknown")
    package_version = info.get("version", "latest")
    locator = f"https://pypi.org/pypi/{package_name}/{package_version}/json"
    now = datetime.datetime.now(datetime.timezone.utc)

    # --- Create separate evidence for names and emails ---
    def process_contact_string(
            raw_string: str, role_kind: EvidenceKind, field_name: str
    ) -> None:
        """
        Parses a string for contacts and creates separate evidence records
        for each piece of information (name, email).
        """
        if not raw_string:
            return

        def add_separate_evidence(
            parsed_contact: Dict[str, Optional[str]],
            source_note: str,
            confidence: float
        ) -> None:
            """Creates and appends separate evidence for name and email."""
            name = parsed_contact.get("name")
            email = parsed_contact.get("email")

            # Also create a simple Maintainer object for direct reporting
            if name or email:
                key = (name, email)
                if key not in seen_maintainers:
                    maintainer_list.append(Maintainer(
                        name=name or "Unknown", email=email, confidence=confidence
                    ))
                    seen_maintainers.add(key)


            # Create evidence for the name, if it exists
            if name:
                # NOTE: Assumes EvidenceKind.PERSON exists in your schema
                kind = EvidenceKind.PERSON
                value = {"name": name}
                record = EvidenceRecord(
                    id=generate_evidence_id(EvidenceSource.PYPI, kind, locator, str(value), name),
                    source=EvidenceSource.PYPI,
                    locator=locator,
                    kind=kind,
                    value=value,
                    observed_at=now,
                    confidence=confidence,
                    notes=f"Found person '{name}' from PyPI '{field_name}' field ({source_note}). Designated as {role_kind.value}."
                )
                evidence_list.append(record)
                logger.debug(f"Created {kind.value} evidence for '{name}' from '{field_name}'.")

            # Create evidence for the email, if it exists
            if email:
                # NOTE: Assumes EvidenceKind.EMAIL exists in your schema
                kind = EvidenceKind.EMAIL
                value = {"email": email}
                # Use the name for the slug if available, otherwise email's local part
                slug_subject = name or email.split('@')[0]
                record = EvidenceRecord(
                    id=generate_evidence_id(EvidenceSource.PYPI, kind, locator, str(value), slug_subject),
                    source=EvidenceSource.PYPI,
                    locator=locator,
                    kind=kind,
                    value=value,
                    observed_at=now,
                    confidence=confidence + 0.1,  # Emails are slightly more reliable
                    notes=f"Found email for '{slug_subject}' from PyPI '{field_name}' field ({source_note}). Designated as {role_kind.value}."
                )
                evidence_list.append(record)
                logger.debug(f"Created {kind.value} evidence for '{email}' from '{field_name}'.")

        # Attempt to use NER to find multiple entities
        entities = ner.extract_entities(raw_string)
        if entities:
            logger.debug(f"NER found {len(entities)} entities in PyPI field '{field_name}': {entities}")
            for entity_name, entity_label in entities:
                parsed = _parse_contact_string(entity_name)
                add_separate_evidence(parsed, "NER", confidence=0.45)
        # else:
        #     # Fallback to simple parsing if NER finds nothing
        #     parsed = _parse_contact_string(raw_string)
        #     add_separate_evidence(parsed, "regex fallback", confidence=0.30)

    # Process author and maintainer fields
    author_name = _clean_pypi_field(info.get("author"))
    author_email = _clean_pypi_field(info.get("author_email"))
    # Prefer email string as it's more likely to contain both name and email
    author_string = author_email or author_name
    if author_string:
        process_contact_string(author_string, EvidenceKind.AUTHOR_TAG, "author/author_email")

    maintainer_name = _clean_pypi_field(info.get("maintainer"))
    maintainer_email = _clean_pypi_field(info.get("maintainer_email"))
    maintainer_string = maintainer_email or maintainer_name

    # Only process maintainer if it's different from the author string
    if maintainer_string and maintainer_string != author_string:
        process_contact_string(maintainer_string, EvidenceKind.MAINTAINER, "maintainer/maintainer_email")

    # --- Project URL parsing ---
    project_urls = info.get("project_urls")
    if isinstance(project_urls, dict):
        logger.debug(f"Found {len(project_urls)} project URLs to analyze.")
        for label, url in project_urls.items():
            if not url or not isinstance(url, str):
                continue

            domain_info = tldextract.extract(url)
            repo_host = domain_info.domain
            logger.debug(f"Parsing project URL ({label}): {url}")

            if repo_host in ("github", "gitlab", "codeberg"):
                path_parts = url.strip('/').split('/')
                if len(path_parts) >= 4:
                    org_or_user = path_parts[3]
                    logger.debug(f"Extracted user/org '{org_or_user}' from URL.")
                    value = {"name": org_or_user, "url": url}
                    notes = f"Found user/org '{org_or_user}' from repository URL in project_urls."
                    record = EvidenceRecord(
                        id=generate_evidence_id(
                            EvidenceSource.PYPI, EvidenceKind.ORGANIZATION, locator, str(value), org_or_user,
                            hint=f"{repo_host}-user"
                        ),
                        source=EvidenceSource.PYPI,
                        locator=locator,
                        kind=EvidenceKind.ORGANIZATION,
                        value=value,
                        observed_at=now,
                        confidence=0.35,
                        notes=notes
                    )
                    already_in = False
                    for already in evidence_list:
                        if already.notes == notes:
                            already_in = True
                    if not already_in:
                        evidence_list.append(record)

    logger.info(f"Extracted {len(evidence_list)} evidence records and {len(maintainer_list)} maintainers from PyPI.")
    return evidence_list, maintainer_list