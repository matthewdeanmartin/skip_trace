# skip_trace/collectors/pypi_attestations.py

# I have no evidence that this works.
# It appears to crash, possibly because I'm on windows.

from __future__ import annotations

import datetime
import logging
import os
import shutil
import subprocess  # nosec
import tempfile
from typing import Any, Dict, List

from ..analysis.evidence import generate_evidence_id
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils import http_client

logger = logging.getLogger(__name__)


def collect(metadata: Dict[str, Any]) -> List[EvidenceRecord]:
    """
    Finds and verifies PyPI attestations by calling the `pypi-attestations` CLI.

    This collector manually queries the PyPI Integrity API to get the attestation,
    saves it to a temporary file, and then passes that file to the `inspect`
    command of the CLI tool for verification and parsing.

    Args:
        metadata: The PyPI JSON metadata for the package.

    Returns:
        A list of EvidenceRecord objects from verified attestations.
    """
    if not shutil.which("pypi-attestations"):
        logger.debug(
            "`pypi-attestations` CLI not found in PATH. Skipping attestation check."
        )
        return []

    evidence = []
    urls_data = metadata.get("urls", [])
    if not urls_data:
        return []

    project_name = metadata.get("info", {}).get("name")
    project_version = metadata.get("info", {}).get("version")

    # Find the first downloadable artifact (wheel or sdist) and check it.
    for url_info in urls_data:
        artifact_url = url_info.get("url")
        if not artifact_url or url_info.get("yanked", False):
            continue

        artifact_filename = os.path.basename(artifact_url)

        # 1. Construct the PyPI Integrity API URL for this specific file.
        integrity_api_url = f"https://pypi.org/integrity/{project_name}/{project_version}/{artifact_filename}/provenance"
        logger.info(f"Querying PyPI Integrity API: {integrity_api_url}")

        # 2. Make the API call to get the attestation.
        response = http_client.make_request_safe(integrity_api_url)
        if response is None or response.status_code != 200:
            logger.info(
                f"No attestation found for {artifact_filename} via Integrity API (Status: {response.status_code if response else 'N/A'})."
            )
            continue

        try:
            response.json()
        except Exception:
            logger.warning(
                f"Failed to parse JSON from Integrity API for {artifact_filename}"
            )
            continue

        # 3. Save the attestation to a temporary file for the CLI to use.
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".attestation.json", encoding="utf-8"
        ) as tmp_file:
            tmp_file.write(response.text)
            temp_attestation_path = tmp_file.name

        try:
            # 4. Call `pypi-attestations inspect` on the temporary attestation file.
            # The tool verifies the attestation as part of the inspect command.
            command = ["pypi-attestations", "inspect", temp_attestation_path]
            logger.info(f"Running command: {' '.join(command)}")
            result = subprocess.run(  # nosec
                command,
                capture_output=True,
                text=True,
                check=True,  # Raises CalledProcessError on non-zero exit codes
            )

            logger.info(f"Successfully verified attestation for {artifact_filename}")

            # Parse the human-readable output to find key details.
            repo_slug = None
            workflow = None
            lines = result.stdout.splitlines()
            print(lines)
            for line in lines:
                if "Repository:" in line:
                    repo_slug = line.split(":", 1)[1].strip()
                elif "Workflow:" in line:
                    workflow = line.split(":", 1)[1].strip()

            if not repo_slug:
                logger.warning(
                    "Verified attestation but could not parse repository slug from CLI output."
                )
                continue

            # Create the evidence record.
            org_name = repo_slug.split("/")[0]
            now = datetime.datetime.now(datetime.timezone.utc)
            value = {
                "publisher_kind": "github",
                "repository": repo_slug,
                "workflow": workflow,
            }

            record = EvidenceRecord(
                id=generate_evidence_id(
                    EvidenceSource.PYPI_ATTESTATION,
                    EvidenceKind.PYPI_PUBLISHER_ATTESTATION,
                    integrity_api_url,
                    str(value),
                    org_name,
                ),
                source=EvidenceSource.PYPI_ATTESTATION,
                locator=integrity_api_url,
                kind=EvidenceKind.PYPI_PUBLISHER_ATTESTATION,
                value=value,
                observed_at=now,
                confidence=1.0,
                notes=(
                    "Verified PyPI attestation proves publication from GitHub "
                    f"repo '{repo_slug}' via workflow '{workflow or 'unknown'}'."
                ),
            )
            evidence.append(record)
            break

        except subprocess.CalledProcessError as e:
            logger.warning(
                f"CLI verification failed for attestation of {artifact_filename}:\n{e.stderr}"
            )
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during CLI attestation processing: {e}"
            )
        finally:
            # Clean up the temporary file.
            os.remove(temp_attestation_path)

    return evidence
