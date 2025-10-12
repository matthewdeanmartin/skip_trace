# skip_trace/collectors/package_files.py
from __future__ import annotations

import datetime
import glob
import logging
import os
import shutil
import tarfile
import zipfile
from email.parser import Parser
from typing import Any, Dict, List, Optional

from ..analysis import source_scanner
from ..analysis.evidence import generate_evidence_id
from ..exceptions import CollectorError, NetworkError
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils import http_client
from ..utils.safe_targz import safe_extract_auto
from ..utils.validation import is_valid_email
from . import sigstore

logger = logging.getLogger(__name__)
PACKAGE_DOWNLOAD_DIR = ".packages"


def _create_evidence_from_contact(
    contact_str: str,
    role_kind: EvidenceKind,
    locator: str,
    confidence: float,
    notes_prefix: str,
) -> List[EvidenceRecord]:
    """Helper to create PERSON and EMAIL evidence from a 'Name <email>' string."""
    from ..analysis.evidence import _parse_contact_string

    evidence_list = []
    now = datetime.datetime.now(datetime.timezone.utc)
    parsed = _parse_contact_string(contact_str)
    name = parsed.get("name")
    email = parsed.get("email")
    source = EvidenceSource.WHEEL

    if name:
        value = {"name": name}
        record = EvidenceRecord(
            id=generate_evidence_id(
                source, EvidenceKind.PERSON, locator, str(value), name
            ),
            source=source,
            locator=locator,
            kind=EvidenceKind.PERSON,
            value=value,
            observed_at=now,
            confidence=confidence,
            notes=f"{notes_prefix} name '{name}' from {role_kind.value} field in package metadata.",
        )
        evidence_list.append(record)

    if email:
        value = {"email": email}
        slug = name or email.split("@")[0]
        record = EvidenceRecord(
            id=generate_evidence_id(
                source, EvidenceKind.EMAIL, locator, str(value), slug
            ),
            source=source,
            locator=locator,
            kind=EvidenceKind.EMAIL,
            value=value,
            observed_at=now,
            confidence=confidence + 0.1,  # Email is a stronger signal
            notes=f"{notes_prefix} email for '{slug}' from {role_kind.value} field in package metadata.",
        )
        evidence_list.append(record)

    return evidence_list


def _parse_metadata_file(content: str, locator: str) -> List[EvidenceRecord]:
    """Parses a PKG-INFO or METADATA file for evidence."""
    evidence_list: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    headers = Parser().parsestr(content)

    # Author/Maintainer information
    if author_email := headers.get("Author-email"):
        evidence_list.extend(
            _create_evidence_from_contact(
                author_email, EvidenceKind.AUTHOR_TAG, locator, 0.35, "Found"
            )
        )
    if author := headers.get("Author"):
        evidence_list.extend(
            _create_evidence_from_contact(
                author, EvidenceKind.AUTHOR_TAG, locator, 0.30, "Found"
            )
        )

    if maintainer_email := headers.get("Maintainer-email"):
        evidence_list.extend(
            _create_evidence_from_contact(
                maintainer_email, EvidenceKind.MAINTAINER, locator, 0.35, "Found"
            )
        )
    if maintainer := headers.get("Maintainer"):
        evidence_list.extend(
            _create_evidence_from_contact(
                maintainer, EvidenceKind.MAINTAINER, locator, 0.30, "Found"
            )
        )

    # Project URLs
    urls = headers.get_all("Project-URL", [])
    if home_page := headers.get("Home-page"):
        urls.append(f"Homepage, {home_page}")

    for url_entry in urls:
        try:
            label, url = [part.strip() for part in url_entry.split(",", 1)]
            if not is_valid_email(label):  # Filter out email-like labels
                value = {"label": label, "url": url}
                record = EvidenceRecord(
                    id=generate_evidence_id(
                        EvidenceSource.WHEEL,
                        EvidenceKind.PROJECT_URL,
                        locator,
                        str(value),
                        label,
                        hint="metadata-file",
                    ),
                    source=EvidenceSource.WHEEL,
                    locator=locator,
                    kind=EvidenceKind.PROJECT_URL,
                    value=value,
                    observed_at=now,
                    confidence=0.30,
                    notes=f"Found project URL '{label}' in package metadata file.",
                )
                evidence_list.append(record)
        except ValueError:
            logger.debug(f"Could not parse Project-URL from metadata file: {url_entry}")

    return evidence_list


def _ensure_download_dir():
    """Ensures the package download directory and .gitignore exist."""
    os.makedirs(PACKAGE_DOWNLOAD_DIR, exist_ok=True)
    gitignore_path = os.path.join(PACKAGE_DOWNLOAD_DIR, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("*\n")


def _find_download_url(metadata: Dict[str, Any]) -> Optional[str]:
    """Finds the best distribution URL from PyPI metadata."""
    urls = metadata.get("urls", [])
    if not urls:
        return None

    # Prioritize wheels, then sdist, then anything else
    wheel_url = None
    sdist_url = None
    for url_info in urls:
        if url_info.get("yanked"):
            continue
        packagetype = url_info.get("packagetype")
        if packagetype == "bdist_wheel":
            wheel_url = url_info.get("url")
        elif packagetype == "sdist":
            sdist_url = url_info.get("url")

    # Return in order of preference: wheel, then sdist, then fallback
    return wheel_url or sdist_url or (urls[0].get("url") if urls else None)


def _download_file(url: str, download_dir: str) -> str | None:
    """Downloads a file to a directory if it doesn't exist, returns the path."""
    filename = os.path.basename(url)
    download_path = os.path.join(download_dir, filename)

    if not os.path.exists(download_path):
        logger.info(f"Downloading {filename} from {url}")
        try:
            with http_client.get_client().stream("GET", url) as response:
                response.raise_for_status()
                with open(download_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        except (
            NetworkError,
            http_client.httpx.RequestError,
            http_client.httpx.HTTPStatusError,
        ) as e:
            # A 404 is expected for bundles, so we don't raise a CollectorError
            if response and response.status_code == 404:
                logger.info(f"No file found at {url} (404 Not Found)")
                return None
            raise CollectorError(f"Failed to download file {filename}: {e}") from e

    return download_path


def collect_from_package_files(metadata: Dict[str, Any]) -> List[EvidenceRecord]:
    """
    Downloads, extracts, and scans a package's files for evidence.

    Args:
        metadata: The PyPI JSON metadata for the package.

    Returns:
        A list of EvidenceRecord objects found within the package files.
    """
    info = metadata.get("info", {})
    package_name = info.get("name", "unknown")
    package_version = info.get("version", "latest")
    logger.info(f"Starting file analysis for {package_name} v{package_version}")

    download_url = _find_download_url(metadata)
    if not download_url:
        logger.warning(
            f"No download URL found for {package_name}. Skipping file analysis."
        )
        return []

    _ensure_download_dir()

    # Download the main package artifact
    artifact_path = _download_file(download_url, PACKAGE_DOWNLOAD_DIR)
    if not artifact_path:
        return []  # Can't proceed without the artifact

    # Attempt to download the corresponding Sigstore bundle
    bundle_url = f"{download_url}.sigstore"
    bundle_path = _download_file(bundle_url, PACKAGE_DOWNLOAD_DIR)

    # Initialize evidence list
    evidence: list[EvidenceRecord] = []

    # Verify with Sigstore if the bundle was found
    if bundle_path:
        sigstore_evidence = sigstore.verify_and_collect(
            artifact_path, bundle_path, package_name, package_version
        )
        evidence.extend(sigstore_evidence)

    # Determine the persistent extraction directory path from the filename
    filename = os.path.basename(artifact_path)
    base_filename, _ = os.path.splitext(filename)
    if filename.endswith(".tar.gz"):
        base_filename, _ = os.path.splitext(base_filename)
    extract_dir = os.path.join(PACKAGE_DOWNLOAD_DIR, base_filename)

    # Extract the archive ONLY if the destination directory doesn't already exist
    if not os.path.exists(extract_dir):
        logger.info(f"Extracting {artifact_path} to {extract_dir}")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            if artifact_path.endswith((".whl", ".zip")):
                with zipfile.ZipFile(artifact_path, "r") as zf:
                    zf.extractall(extract_dir)  # nosec
            elif artifact_path.endswith(
                (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")
            ):
                safe_extract_auto(artifact_path, extract_dir)
            else:
                logger.warning(
                    f"Unsupported archive format for {filename}. Skipping file scan."
                )
                shutil.rmtree(extract_dir)  # Clean up the empty dir
                return evidence  # Return any Sigstore evidence found
        except (zipfile.BadZipFile, tarfile.TarError, PermissionError) as e:
            logger.error(f"Failed to extract archive {artifact_path}: {e}")
            shutil.rmtree(extract_dir, ignore_errors=True)
            return evidence  # Return any Sigstore evidence found
    else:
        logger.info(f"Using cached package files from {extract_dir}")

    # Determine the actual directory to scan (handles sdists with a single top-level folder)
    scan_target_dir = extract_dir
    # This logic applies to sdists, which often have a root folder. Wheels do not.
    if filename.endswith((".tar.gz", ".tgz", ".tar.bz2")):
        try:
            dir_contents = os.listdir(extract_dir)
            if len(dir_contents) == 1 and os.path.isdir(
                os.path.join(extract_dir, dir_contents[0])
            ):
                scan_target_dir = os.path.join(extract_dir, dir_contents[0])
        except FileNotFoundError:
            logger.error(
                f"Extraction directory {extract_dir} not found after apparent success. Check permissions."
            )
            return evidence

    locator_prefix = f"{package_name}-{package_version}"
    source_scan_evidence = source_scanner.scan_directory(
        scan_target_dir, locator_prefix
    )
    evidence.extend(source_scan_evidence)

    # --- Scan for PKG-INFO/METADATA file ---
    metadata_file_path = None
    # Use a recursive glob to find the relevant .dist-info or .egg-info directory
    # This is more robust for sdists that may have a nested src/ directory.
    dist_info_pattern = os.path.join(scan_target_dir, "**", "*.dist-info")
    egg_info_pattern = os.path.join(scan_target_dir, "**", "*.egg-info")

    info_dirs = glob.glob(dist_info_pattern, recursive=True) + glob.glob(
        egg_info_pattern, recursive=True
    )

    if info_dirs:
        info_dir_path = info_dirs[0]  # Assume there's only one
        potential_files = [
            os.path.join(info_dir_path, "METADATA"),
            os.path.join(info_dir_path, "PKG-INFO"),
        ]
        for f_path in potential_files:
            if os.path.exists(f_path):
                metadata_file_path = f_path
                break

    if metadata_file_path:
        rel_path = os.path.relpath(metadata_file_path, PACKAGE_DOWNLOAD_DIR)
        logger.info(f"Found package metadata file: {rel_path}")
        try:
            with open(metadata_file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Create a locator relative to the package root
            relative_locator_path = os.path.relpath(metadata_file_path, scan_target_dir)
            locator = f"{locator_prefix}/{relative_locator_path}"
            metadata_evidence = _parse_metadata_file(content, locator)
            evidence.extend(metadata_evidence)
            logger.info(
                f"Extracted {len(metadata_evidence)} evidence records from package metadata file."
            )
        except IOError as e:
            logger.warning(f"Could not read metadata file {metadata_file_path}: {e}")

    return evidence
