# skip_trace/analysis/scoring.py

import collections
import logging
from typing import Dict, List, Set, Tuple, Optional

import tldextract

from ..config import CONFIG
from ..schemas import Contact, ContactType, EvidenceRecord, OwnerCandidate, OwnerKind, EvidenceKind
from ..analysis.evidence import _parse_contact_string # Import the parser for reuse

# NEW: Words that indicate a regex grabbed junk from a license instead of a name.
JUNK_WORDS = {
    "copyright", "holders", "license", "document", "accompanies",
    "identifies", "endorse", "promote", "software", "permission",
    "danger", "warranty", "bsd", "liability",

    # duped
"copyright", "holders", "license", "document", "accompanies", "notice", "authors",
    "identifies", "endorse", "promote", "software", "permission", "conditions",
    # stop words
    "and", "other", "the", "for", "with", "this", "list", "following", "txt", "damages",
    "owner",
    # legalese
    "incidental", "holder", "liability",
    # license names
    "MIT", "BSD"
}

def _normalize_name(name: str) -> str:
    """Normalizes a name for entity grouping."""
    # Also parse out emails that might be part of the name
    parsed = _parse_contact_string(name)
    raw_name = parsed.get("name") or parsed.get("email") or name
    # MODIFIED: Strip common trailing punctuation for better grouping
    return raw_name.strip().rstrip(",.'").lower()


def _get_entity_from_record(record: EvidenceRecord) -> Tuple[Optional[str], OwnerKind]:
    """Extracts a primary entity name and kind from an evidence record."""
    kind = OwnerKind.INDIVIDUAL  # Default
    name = None

    if record.kind in (
            EvidenceKind.MAINTAINER,
            EvidenceKind.AUTHOR_TAG,
            EvidenceKind.COMMIT_AUTHOR,
            EvidenceKind.PYPI_USER,
            EvidenceKind.USER_PROFILE,
            EvidenceKind.CONTACT,  # NEW: Handle generic contacts
    ):
        raw_name = record.value.get("name") or record.value.get("email")
        if raw_name:
            # The name might be "Name <email>", so parse it
            parsed = _parse_contact_string(raw_name)
            name = parsed.get("name") or parsed.get("email")
        kind = OwnerKind.INDIVIDUAL
    elif record.kind in (
            EvidenceKind.ORGANIZATION,
            EvidenceKind.REPO_OWNER
    ):
        name = record.value.get("name")
        # Check if the name looks like a user or an org
        # A simple heuristic: if it contains spaces, it's likely a person's name
        if name and ' ' in name:
            kind = OwnerKind.INDIVIDUAL
        else:
            kind = OwnerKind.PROJECT
    # NEW: Handle user profile and company evidence
    elif record.kind == EvidenceKind.USER_PROFILE:
        name = record.value.get("user_name")
        kind = OwnerKind.INDIVIDUAL
    elif record.kind == EvidenceKind.USER_COMPANY:
        # The primary entity is the user, but this record also implies a company
        name = record.value.get("user_name")
        kind = OwnerKind.INDIVIDUAL
    elif record.kind == EvidenceKind.PROJECT_URL:
        url = record.value.get("url", "")
        domain_info = tldextract.extract(url)
        if domain_info.domain and domain_info.suffix:
            name = domain_info.domain.capitalize()
            kind = OwnerKind.COMPANY
    # NEW: Handle WHOIS domain evidence
    elif record.kind == EvidenceKind.DOMAIN:
        name = record.value.get("name")
        kind = OwnerKind.COMPANY
    # NEW: Handle COPYRIGHT evidence from file scans
    elif record.kind == EvidenceKind.COPYRIGHT:
        # The scanner is now responsible for pre-filtering junk.
        # This logic can now trust its input more.
        raw_holder = record.value.get("holder")
        if not raw_holder:
            return None, kind

        # --- NEW: Sanitize the raw string before accepting it as a name ---
        # 1. Reject if it's too long to be a name.
        if len(raw_holder) > 50:
             return None, kind
        # 2. Reject if it contains common license garbage words.
        if any(word in raw_holder.lower() for word in JUNK_WORDS):
            return None, kind

        parsed = _parse_contact_string(raw_holder)
        name = parsed.get("name") or parsed.get("email") or raw_holder
        if parsed.get("email") or ' ' in name or ',' in name:
            kind = OwnerKind.INDIVIDUAL
        else:
            kind = OwnerKind.COMPANY

    return name, kind


def score_owners(evidence_records: List[EvidenceRecord]) -> List[OwnerCandidate]:
    """
    Scores and ranks potential owners from a list of evidence.

    This function performs entity resolution by normalizing names, aggregates
    evidence for each unique entity, and calculates a score based on the
    weights defined in the application configuration.

    Args:
        evidence_records: A list of EvidenceRecord objects to analyze.

    Returns:
        A list of OwnerCandidate objects, sorted by score in descending order.
    """
    # Get suppression settings from config
    suppressed_orgs = CONFIG.get("suppressed_tool_orgs", [])
    lenient_mode = CONFIG.get("lenient_mode_enabled", False)

    # --- 1. Initial Entity Extraction & Alias Mapping ---
    entities: Dict[str, OwnerCandidate] = {}
    evidence_by_entity: Dict[str, List[EvidenceRecord]] = collections.defaultdict(list)

    # 1. First pass: extract all entities and map evidence
    for record in evidence_records:
        name, kind = _get_entity_from_record(record)
        # if not name:
        #     logging.warning(f"Skipping {record.kind}")
        #     continue

        if not name:
            name = ""

        # Suppress tool orgs like 'github' unless in lenient mode
        if name and (name.lower() in suppressed_orgs) and not lenient_mode:
            continue

        norm_name = _normalize_name(name)
        evidence_by_entity[norm_name].append(record)
        if norm_name not in entities:
            # Use the raw name for display, but the normalized name for grouping
            entities[norm_name] = OwnerCandidate(name=name.strip().rstrip(",.'"), kind=kind)

        # Also create entities for companies mentioned in user profiles
        if record.kind == EvidenceKind.USER_COMPANY:
            company_name = record.value.get("company_name")
            if company_name:
                norm_co_name = _normalize_name(company_name)
                if norm_co_name not in entities:
                    entities[norm_co_name] = OwnerCandidate(name=company_name, kind=OwnerKind.COMPANY)
                evidence_by_entity[norm_co_name].append(record)  # Associate this evidence with the company too

    # --- 2. Score each candidate and collect contacts ---
    contact_map = {
        'email': ContactType.EMAIL,
        'twitter': ContactType.TWITTER,
        'linkedin': ContactType.LINKEDIN,
        'mastodon': ContactType.MASTODON,
        'facebook': ContactType.FACEBOOK,
        'instagram': ContactType.INSTAGRAM,
        'youtube': ContactType.YOUTUBE,
        'tiktok': ContactType.TIKTOK,
    }
    for norm_name, owner in entities.items():
        score = 0.0
        seen_rationale_keys = set()
        contacts: Dict[Tuple[ContactType, str], Contact] = {}

        for record in evidence_by_entity[norm_name]:
            owner.evidence.append(record.id)
            rationale_key = f"{record.source.value}-{record.kind.value}"
            weight = record.confidence  # Use confidence from collector

            if rationale_key not in seen_rationale_keys:
                score += weight
                seen_rationale_keys.add(rationale_key)
            else:
                score += weight * 0.1  # Diminishing return

            # --- UPDATED: Collect contact info from all relevant evidence kinds ---
            contact_source_string = None
            if record.kind in (EvidenceKind.MAINTAINER, EvidenceKind.AUTHOR_TAG, EvidenceKind.COMMIT_AUTHOR,
                               EvidenceKind.CONTACT):
                contact_source_string = record.value.get("email") or record.value.get("name")
            elif record.kind in (EvidenceKind.ORGANIZATION, EvidenceKind.REPO_OWNER):
                if url := record.value.get("url", record.locator):
                    contacts[(ContactType.REPO, url)] = Contact(type=ContactType.REPO, value=url)
            elif record.kind == EvidenceKind.PYPI_USER:
                if url := record.value.get("url"):
                    contacts[(ContactType.URL, url)] = Contact(type=ContactType.URL, value=url)
            # NEW: Collect contacts from USER_PROFILE evidence
            elif record.kind == EvidenceKind.USER_PROFILE:
                for key, value in record.value.get("contacts", {}).items():
                    contact_type = contact_map.get(key, ContactType.URL)  # Default to generic URL
                    contacts[(contact_type, value)] = Contact(type=contact_type, value=value)
            elif record.kind == EvidenceKind.COPYRIGHT:
                contact_source_string = record.value.get("holder")

            # Parse any found string for an email
            if contact_source_string:
                parsed_contact = _parse_contact_string(contact_source_string)
                if email := parsed_contact.get("email"):
                    contacts[(ContactType.EMAIL, email)] = Contact(type=ContactType.EMAIL, value=email)

        owner.score = min(round(score, 2), 1.0)
        owner.evidence = sorted(list(set(owner.evidence)))
        owner.rationale = " + ".join(sorted(list(seen_rationale_keys)))
        owner.contacts = sorted(list(contacts.values()), key=lambda c: (c.type.value, c.value))

    # 4. Filter and Sort
    # filtered_candidates = [
    #     c for c in entities.values()
    #     if not (c.name.lower() in ["nobody", "nobody in particular", "example"] and c.score < 0.3)
    # ]

    return sorted(entities.values(), key=lambda c: c.score, reverse=True)