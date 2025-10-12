# skip_trace/collectors/sigstore.py
from __future__ import annotations

import datetime
import logging
from typing import List
from urllib.parse import urlparse

from ..analysis.evidence import generate_evidence_id
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource


from sigstore.errors import VerificationError
from sigstore.models import Bundle
from sigstore.verify import Verifier, policy

logger = logging.getLogger(__name__)


def _parse_san_from_cert(bundle: Bundle) -> str | None:
    """Extracts the Subject Alternative Name from the signing certificate."""
    try:
        # The SAN extension is a list of GeneralName objects.
        # We look for rfc822Name (email) or uniformResourceIdentifier.
        sans = bundle.signing_certificate.subject_alternative_names
        for san in sans:
            # The value attribute of the GeneralName object holds the identity.
            return san.value
    except Exception:
        return None


def _parse_repo_from_github_uri(uri: str | None) -> str | None:
    """Parses a GitHub workflow URI to get the 'owner/repo' string."""
    if not uri or not uri.startswith("https://github.com/"):
        try:
            parsed = urlparse(uri)
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                return f"{path_parts[0]}/{path_parts[1]}"
        except Exception:
            pass
    return None


def verify_and_collect(
    artifact_path: str, bundle_path: str, package_name: str, package_version: str
) -> List[EvidenceRecord]:
    """
    Verifies a package artifact against a Sigstore bundle and collects evidence.

    Args:
        artifact_path: Path to the downloaded package file (.whl, .tar.gz).
        bundle_path: Path to the downloaded .sigstore bundle file.
        package_name: The name of the package.
        package_version: The version of the package.

    Returns:
        A list of EvidenceRecord objects from the verification.
    """
    # if not SIGSTORE_AVAILABLE:
    #     logger.warning("sigstore library not installed, skipping verification.")
    #     return []

    evidence: list[EvidenceRecord] = []
    locator = f"pkg:pypi/{package_name}@{package_version}"
    now = datetime.datetime.now(datetime.timezone.utc)

    logger.info(f"Performing Sigstore verification for {artifact_path}")

    try:
        # 1. Load the bundle from the file
        with open(bundle_path, "r", encoding="utf-8") as f:
            bundle = Bundle.from_json(f.read())

        # 2. Create a verifier. We use the production instance by default.
        verifier = Verifier.production()

        # 3. Define a verification policy.
        # WARNING: UnsafeNoOp is for demonstration and testing only.
        # It performs no identity verification. Replace with a real policy
        # like `policy.Identity(identity=..., issuer=...)` for security.
        verification_policy = policy.UnsafeNoOp()

        # 4. Verify the artifact. This will raise VerificationError on failure.
        with open(artifact_path, "rb") as artifact:
            verifier.verify_artifact(artifact, bundle, verification_policy)

        logger.info(f"Sigstore verification successful for {package_name}")

        # 5. If verification succeeds, extract evidence from the trusted bundle.

        # Evidence for the signer's identity from the certificate's SAN
        if identity := _parse_san_from_cert(bundle):
            value = {
                "identity": identity,
                "issuer": bundle.signing_certificate.issuer.rfc4514_string(),
            }
            record = EvidenceRecord(
                id=generate_evidence_id(
                    EvidenceSource.SIGSTORE,
                    EvidenceKind.SIGSTORE_SIGNER_IDENTITY,
                    locator,
                    str(value),
                    identity,
                ),
                source=EvidenceSource.SIGSTORE,
                locator=locator,
                kind=EvidenceKind.SIGSTORE_SIGNER_IDENTITY,
                value=value,
                observed_at=now,
                confidence=0.95,
                notes=(
                    f"Package cryptographically signed by identity '{identity}' "
                    f"(issuer: {value['issuer']})."
                ),
            )
            evidence.append(record)

        # Evidence from GitHub workflow info in the certificate extensions
        # OID 1.3.6.1.4.1.57264.1.5 = GitHub Workflow Repository
        oid_repo = "1.3.6.1.4.1.57264.1.5"
        try:
            repo_ext = bundle.signing_certificate.extensions.get_extension_for_oid(
                oid_repo
            )
            repo_uri = repo_ext.value.value.decode("utf-8")
            repo_slug = _parse_repo_from_github_uri(repo_uri) or repo_uri

            value = {"repo_uri": repo_uri}
            record = EvidenceRecord(
                id=generate_evidence_id(
                    EvidenceSource.SIGSTORE,
                    EvidenceKind.SIGSTORE_BUILD_PROVENANCE,
                    locator,
                    str(value),
                    repo_slug,
                ),
                source=EvidenceSource.SIGSTORE,
                locator=locator,
                kind=EvidenceKind.SIGSTORE_BUILD_PROVENANCE,
                value=value,
                observed_at=now,
                confidence=0.90,
                notes=f"Sigstore certificate attests build from repo '{repo_slug}'.",
            )
            evidence.append(record)
        except Exception:
            # This is not an error; the extension is optional.
            pass

    except (VerificationError, FileNotFoundError, ValueError) as e:
        logger.info(f"Sigstore verification failed for {package_name}: {e}")
        return []
    except Exception as e:
        logger.warning(
            f"An unexpected error occurred during Sigstore verification: {e}"
        )
        return []

    logger.info(f"Found {len(evidence)} evidence records from Sigstore.")
    return evidence