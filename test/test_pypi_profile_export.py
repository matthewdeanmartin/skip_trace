from __future__ import annotations

import datetime

from skip_trace.pypi_profile_export import PypiProfileExchange, build_exchange
from skip_trace.schemas import (
    EvidenceKind,
    EvidenceRecord,
    EvidenceSource,
    Maintainer,
    OwnerCandidate,
    OwnerKind,
    PackageResult,
)


def test_build_exchange_collects_identity_details() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    result = PackageResult(
        package="demo-package",
        version="1.2.3",
        owners=[
            OwnerCandidate(name="Alice Example", kind=OwnerKind.INDIVIDUAL, score=0.9)
        ],
        maintainers=[
            Maintainer(name="Alice Example", email="alice@example.com", confidence=0.8)
        ],
        evidence=[
            EvidenceRecord(
                id="e1",
                source=EvidenceSource.PYPI,
                locator="https://pypi.org/pypi/demo-package/json",
                kind=EvidenceKind.PYPI_USER,
                value={"name": "alice", "url": "https://pypi.org/user/alice/"},
                observed_at=now,
                confidence=0.8,
            ),
            EvidenceRecord(
                id="e2",
                source=EvidenceSource.PYPI,
                locator="https://pypi.org/pypi/demo-package/json",
                kind=EvidenceKind.PERSON,
                value={"name": "Alice Example"},
                observed_at=now,
                confidence=0.7,
            ),
            EvidenceRecord(
                id="e3",
                source=EvidenceSource.PYPI,
                locator="https://pypi.org/pypi/demo-package/json",
                kind=EvidenceKind.EMAIL,
                value={"email": "alice@example.com"},
                observed_at=now,
                confidence=0.7,
            ),
            EvidenceRecord(
                id="e4",
                source=EvidenceSource.PYPI,
                locator="https://pypi.org/pypi/demo-package/json",
                kind=EvidenceKind.PROJECT_URL,
                value={"url": "https://github.com/alice/demo-package"},
                observed_at=now,
                confidence=0.6,
            ),
        ],
    )

    exchange = build_exchange(result)

    assert exchange.subject.display_name == "Alice Example"
    assert exchange.subject.pypi_usernames == ["alice"]
    assert exchange.subject.contacts[0].value == "alice@example.com"
    assert exchange.subject.profiles[0].kind in {"pypi", "github"}
    assert exchange.source_package.name == "demo-package"


def test_export_model_exposes_json_schema() -> None:
    schema = PypiProfileExchange.model_json_schema()

    assert "source_package" in schema["properties"]
    assert "subject" in schema["properties"]
