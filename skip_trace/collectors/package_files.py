# skip_trace/collectors/package_files.py
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import zipfile
from typing import Any, Dict, List, Optional

from ..analysis import source_scanner
from ..exceptions import CollectorError, NetworkError
from ..schemas import EvidenceRecord
from ..utils import http_client
from ..utils.safe_targz import safe_extract_auto

logger = logging.getLogger(__name__)
PACKAGE_DOWNLOAD_DIR = ".packages"


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
        packagetype = url_info.get("packagetype")
        if packagetype == "bdist_wheel":
            wheel_url = url_info.get("url")
        elif packagetype == "sdist":
            sdist_url = url_info.get("url")

    # Return in order of preference: wheel, then sdist, then fallback
    return wheel_url or sdist_url or (urls[0].get("url") if urls else None)


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
    filename = os.path.basename(download_url)
    download_path = os.path.join(PACKAGE_DOWNLOAD_DIR, filename)

    # Download the file if it doesn't already exist
    if not os.path.exists(download_path):
        logger.info(f"Downloading {filename} from {download_url}")
        try:
            with http_client.get_client().stream("GET", download_url) as response:
                response.raise_for_status()
                with open(download_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        except (
            NetworkError,
            http_client.httpx.RequestError,
            http_client.httpx.HTTPStatusError,
        ) as e:
            raise CollectorError(f"Failed to download package {filename}: {e}") from e

    # Determine the persistent extraction directory path from the filename
    base_filename = filename
    for ext in [".whl", ".zip", ".tar.gz", ".tgz", ".tar.bz2"]:
        if base_filename.endswith(ext):
            base_filename = base_filename[: -len(ext)]
            break
    extract_dir = os.path.join(PACKAGE_DOWNLOAD_DIR, base_filename)

    # Extract the archive ONLY if the destination directory doesn't already exist
    if not os.path.exists(extract_dir):
        logger.info(f"Extracting {download_path} to {extract_dir}")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            if download_path.endswith((".whl", ".zip")):
                with zipfile.ZipFile(download_path, "r") as zf:  # nosec # noqa
                    zf.extractall(extract_dir)  # nosec # noqa
            elif download_path.endswith(
                (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")
            ):
                safe_extract_auto(download_path, extract_dir)
            # elif download_path.endswith((".tar.gz", ".tgz")):
            #     with tarfile.open(download_path, "r:gz") as tf:  # nosec # noqa
            #         tf.extractall(extract_dir)  # nosec # noqa
            # elif download_path.endswith(".tar.bz2"):
            #     with tarfile.open(download_path, "r:bz2") as tf:  # nosec # noqa
            #         tf.extractall(extract_dir)  # nosec # noqa
            else:
                logger.warning(
                    f"Unsupported archive format for {filename}. Skipping file scan."
                )
                shutil.rmtree(extract_dir)  # Clean up the empty dir
                return []
        except (zipfile.BadZipFile, tarfile.TarError, PermissionError) as e:
            logger.error(f"Failed to extract archive {download_path}: {e}")
            # Clean up potentially corrupted extraction on error
            shutil.rmtree(extract_dir, ignore_errors=True)
            return []
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
            return []

    locator_prefix = f"{package_name}-{package_version}"
    evidence = source_scanner.scan_directory(scan_target_dir, locator_prefix)
    return evidence
