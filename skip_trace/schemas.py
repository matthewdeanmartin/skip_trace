# skip_trace/schemas.py
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# --- Enums for controlled vocabularies ---


class OwnerKind(str, Enum):
    INDIVIDUAL = "individual"
    COMPANY = "company"
    FOUNDATION = "foundation"
    PROJECT = "project"


class ContactType(str, Enum):
    EMAIL = "email"
    URL = "url"
    SECURITY = "security"
    REPO = "repo"
    MATRIX = "matrix"
    SLACK = "slack"
    TWITTER = "twitter"
    MASTODON = "mastodon"
    LINKEDIN = "linkedin"
    # Add more common social platforms
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    OTHER = "other"


class EvidenceSource(str, Enum):
    PYPI = "pypi"
    REPO = "repo"
    WHEEL = "wheel"
    LOCAL = "local"
    DOCS = "docs"
    SIGSTORE = "sigstore"
    WHOIS = "whois"
    VENV_SCAN = "venv-scan"
    LLM_NER = "llm-ner"
    URL = "url"  # For evidence from scanned homepages
    PYPI_ATTESTATION = "pypi-attestation"  # New source
    BACKLINKS = "backlinks"  # New kind


class EvidenceKind(str, Enum):
    PERSON = "person"
    EMAIL = "email"
    MAINTAINER = "maintainer"
    ORGANIZATION = "org"
    DOMAIN = "domain"
    GOVERNANCE = "governance"
    SIGNATURE = "signature"
    COPYRIGHT = "copyright"
    AUTHOR_TAG = "author-tag"
    CODEOWNERS = "codeowners"
    CONTACT = "contact"
    PROJECT_URL = "project-url"
    PYPI_USER = "pypi-user"
    # GitHub-specific evidence kinds
    REPO_OWNER = "repo-owner"
    COMMIT_AUTHOR = "commit-author"
    # GitHub profile-specific evidence kinds
    USER_PROFILE = "user-profile"
    USER_COMPANY = "user-company"
    URL_STATUS = "url-status"  # To track HTTP status of found URLs
    # Sigstore-specific evidence kinds
    SIGSTORE_SIGNER_IDENTITY = "sigstore-signer-identity"
    SIGSTORE_BUILD_PROVENANCE = "sigstore-build-provenance"
    # PyPI Attestation-specific evidence kind
    PYPI_PUBLISHER_ATTESTATION = "pypi-publisher-attestation"
    BACKLINK = "backlink"  # New kind


# --- Core Data Schemas ---


@dataclass
class Contact:
    """Represents a method of contacting an entity."""

    type: ContactType
    value: str
    verified: bool = False


@dataclass
class EvidenceRecord:
    """A single piece of evidence supporting an ownership claim."""

    id: str
    source: EvidenceSource
    locator: str  # URL, file path, or PURL
    kind: EvidenceKind
    value: Any
    observed_at: datetime.datetime
    linkage: List[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        """Logs every instantiation."""
        logger.info(
            "EvidenceRecord created: id=%s source=%s kind=%s notes=%r",
            self.id,
            self.source,
            self.kind,
            self.notes,
        )


@dataclass
class OwnerCandidate:
    """Represents a potential owner with an aggregated score."""

    name: str
    kind: OwnerKind
    score: float = 0.0
    contacts: List[Contact] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)  # List of EvidenceRecord IDs
    rationale: str = ""


@dataclass
class Maintainer:
    """A simplified maintainer record, distinct from a scored owner."""

    name: str
    email: Optional[str] = None
    confidence: float = 0.0


@dataclass
class PackageResult:
    """The final JSON output for a single package."""

    package: str
    version: Optional[str] = None
    owners: List[OwnerCandidate] = field(default_factory=list)
    maintainers: List[Maintainer] = field(default_factory=list)
    evidence: List[EvidenceRecord] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    schema_version: str = "1.0"
