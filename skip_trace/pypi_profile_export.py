from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .__about__ import __version__
from .schemas import EvidenceKind, OwnerKind, PackageResult


class ExportContactMethod(BaseModel):
    kind: str
    label: str = ""
    value: str
    source: str = ""
    confidence: float = 0.0


class ExportProfileLink(BaseModel):
    kind: str
    label: str = ""
    url: str
    source: str = ""
    confidence: float = 0.0


class ExportPackageEntry(BaseModel):
    name: str
    version: str = ""
    summary: str = ""
    url: str = ""
    role: str = "maintainer"
    pypi_usernames: list[str] = Field(default_factory=list)
    owner_candidates: list[str] = Field(default_factory=list)


class ExportSubject(BaseModel):
    kind: str = "individual"
    display_name: str = ""
    legal_name: str = ""
    pypi_usernames: list[str] = Field(default_factory=list)
    summary: str = ""
    contacts: list[ExportContactMethod] = Field(default_factory=list)
    profiles: list[ExportProfileLink] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    owner_candidates: list[str] = Field(default_factory=list)
    packages: list[ExportPackageEntry] = Field(default_factory=list)


class ExportGenerator(BaseModel):
    name: str = "skip-trace"
    version: str = __version__


class PypiProfileExchange(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    generator: ExportGenerator = Field(default_factory=ExportGenerator)
    source_package: ExportPackageEntry
    subject: ExportSubject


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _coerce_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name", "")).strip()
    return str(value or "").strip()


def _coerce_email(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("email", "")).strip()
    return ""


def _coerce_url(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("url", "")).strip()
    return ""


def _infer_link_kind(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "github.com" in host:
        return "github", "GitHub"
    if "gitlab.com" in host:
        return "gitlab", "GitLab"
    if "mastodon" in host or "/@" in path:
        return "mastodon", "Mastodon"
    if "linkedin.com" in host:
        return "linkedin", "LinkedIn"
    if "twitter.com" in host or "x.com" in host:
        return "twitter", "Twitter/X"
    if "pypi.org" in host and "/user/" in path:
        return "pypi", "PyPI"
    if "pypi.org" in host:
        return "pypi-project", "PyPI Project"
    return "website", parsed.netloc or "Website"


def build_exchange(result: PackageResult) -> PypiProfileExchange:
    """Convert a package analysis into a pypi_profile exchange payload."""

    people = sorted(
        (
            (record.confidence, _coerce_name(record.value))
            for record in result.evidence
            if record.kind == EvidenceKind.PERSON and _coerce_name(record.value)
        ),
        reverse=True,
    )
    pypi_usernames = sorted(
        {
            _coerce_name(record.value)
            for record in result.evidence
            if record.kind == EvidenceKind.PYPI_USER and _coerce_name(record.value)
        }
    )
    owner_candidates = [owner.name for owner in result.owners if owner.name]
    organization_names = sorted(
        {
            _coerce_name(record.value)
            for record in result.evidence
            if record.kind
            in (
                EvidenceKind.ORGANIZATION,
                EvidenceKind.REPO_OWNER,
                EvidenceKind.USER_COMPANY,
            )
            and _coerce_name(record.value)
        }
        | {
            owner.name
            for owner in result.owners
            if owner.kind
            in (OwnerKind.COMPANY, OwnerKind.FOUNDATION, OwnerKind.PROJECT)
            and owner.name
        }
    )
    display_name = _first_non_empty(
        [name for _confidence, name in people]
        + [owner.name for owner in result.owners if owner.kind == OwnerKind.INDIVIDUAL]
        + pypi_usernames
    )

    emails_seen: set[str] = set()
    contacts: list[ExportContactMethod] = []
    for maintainer in result.maintainers:
        if maintainer.email and maintainer.email not in emails_seen:
            emails_seen.add(maintainer.email)
            contacts.append(
                ExportContactMethod(
                    kind="email",
                    label="PyPI maintainer email",
                    value=maintainer.email,
                    source="pypi",
                    confidence=maintainer.confidence,
                )
            )
    for record in result.evidence:
        email = _coerce_email(record.value)
        if record.kind == EvidenceKind.EMAIL and email and email not in emails_seen:
            emails_seen.add(email)
            contacts.append(
                ExportContactMethod(
                    kind="email",
                    label="Discovered email",
                    value=email,
                    source=record.source.value,
                    confidence=record.confidence,
                )
            )

    urls_seen: set[str] = set()
    profiles: list[ExportProfileLink] = []
    for record in result.evidence:
        if record.kind not in (
            EvidenceKind.PROJECT_URL,
            EvidenceKind.PYPI_USER,
            EvidenceKind.ORGANIZATION,
            EvidenceKind.REPO_OWNER,
            EvidenceKind.USER_PROFILE,
        ):
            continue
        url = _coerce_url(record.value)
        if not url or url in urls_seen:
            continue
        urls_seen.add(url)
        kind, label = _infer_link_kind(url)
        profiles.append(
            ExportProfileLink(
                kind=kind,
                label=label,
                url=url,
                source=record.source.value,
                confidence=record.confidence,
            )
        )

    package_url = _first_non_empty(
        [
            next(
                (
                    link.url
                    for link in profiles
                    if link.kind == "pypi-project"
                    and f"/project/{result.package.lower()}/" in link.url.lower()
                ),
                "",
            ),
            f"https://pypi.org/project/{result.package}/",
        ]
    )
    source_package = ExportPackageEntry(
        name=result.package,
        version=result.version or "",
        summary="",
        url=package_url,
        role="maintainer",
        pypi_usernames=pypi_usernames,
        owner_candidates=owner_candidates,
    )
    subject_kind = (
        "company" if organization_names and not display_name else "individual"
    )
    subject = ExportSubject(
        kind=subject_kind,
        display_name=display_name,
        legal_name=display_name,
        pypi_usernames=pypi_usernames,
        summary=f"Maintains Python packages including {result.package}.",
        contacts=contacts,
        profiles=profiles,
        organizations=organization_names,
        owner_candidates=owner_candidates,
        packages=[source_package],
    )
    return PypiProfileExchange(source_package=source_package, subject=subject)
