# skip_trace/main.py
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from typing import Set
from urllib.parse import urlparse

import tldextract
from rich.logging import RichHandler

from . import schemas
from .analysis import backlinks  # Import the new module
from .analysis import evidence as evidence_analyzer
from .analysis import scoring
from .collectors import (
    github,
    github_files,
    package_files,
    pypi,
    pypi_attestations,
    urls,
    whois,
)
from .config import CONFIG
from .exceptions import CollectorError, NetworkError, NoEvidenceError
from .reporting import json_reporter, md_reporter

# Create a logger instance for this module
logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO"):
    """Configures the application's logger.

    Args:
        level: The minimum logging level to display (e.g., "INFO", "DEBUG").
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def run_who_owns(args: argparse.Namespace) -> int:
    """Handler for the 'who-owns' command."""
    logger.info(f"Executing 'who-owns' for package: {args.package}")

    try:
        # Collect initial data from PyPI
        metadata = pypi.fetch_package_metadata(args.package, args.version)
        package_name = metadata.get("info", {}).get("name", args.package)
        package_version = metadata.get("info", {}).get("version")
        logger.info(
            f"Successfully fetched metadata for {package_name} v{package_version}"
        )

        # Analyze primary package metadata
        evidence_records, pypi_maintainers = evidence_analyzer.extract_from_pypi(
            metadata
        )

        logger.info(f"Evidence records so far {len(evidence_records)} -- pypi metadata")

        # Check for PyPI attestations
        attestation_evidence = pypi_attestations.collect(metadata)
        evidence_records.extend(attestation_evidence)
        logger.info(
            f"Evidence records so far {len(evidence_records)} -- collected from PyPI attestations"
        )

        # Analyze package contents for deep evidence
        try:
            package_files_evidence = package_files.collect_from_package_files(metadata)
            evidence_records.extend(package_files_evidence)
            logger.info(
                f"Evidence records so far {len(evidence_records)} -- collected from source code in package"
            )
        except CollectorError as e:
            logger.warning(f"Could not analyze package files for {package_name}: {e}")

        # Cross-Reference for more PyPI evidence
        cross_ref_evidence = pypi.cross_reference_by_user(package_name)
        evidence_records.extend(cross_ref_evidence)
        logger.info(
            f"Evidence records so far {len(evidence_records)} -- user cross ref"
        )

        # Fetch evidence from code repositories found in PyPI evidence
        repo_urls = set()
        for record in evidence_records:
            if (
                record.source == schemas.EvidenceSource.PYPI
                and record.kind == schemas.EvidenceKind.ORGANIZATION
            ):
                url = record.value.get("url")
                if url and "github.com" in url:
                    repo_urls.add(url)

        for url in repo_urls:
            logger.info(f"Analyzing GitHub repository: {url}")
            try:
                github_evidence = github.extract_from_repo_url(url)
                evidence_records.extend(github_evidence)
                logger.info(
                    f"Evidence records so far {len(evidence_records)} -- collected from github"
                )
            except CollectorError as e:
                logger.warning(f"Could not fully analyze GitHub repo {url}: {e}")

            # NEW: Collect evidence from GitHub files (SECURITY.md, FUNDING.yml, contributors)
            try:
                github_files_evidence = github_files.collect_from_repo_url(url)
                evidence_records.extend(github_files_evidence)
                logger.info(
                    f"Evidence records so far {len(evidence_records)} -- collected from github files"
                )
            except CollectorError as e:
                logger.warning(f"Could not collect GitHub files for {url}: {e}")

        # Extract domains and perform WHOIS lookups
        domains_to_check: Set[str] = set()
        urls_to_scan: Set[str] = set()
        ignored_domains = set(CONFIG.get("whois_ignored_domains", []))

        for record in evidence_records:
            # Extract domains for WHOIS
            if email := record.value.get("email"):
                if "@" in email:
                    domain = email.split("@")[1]
                    if domain not in ignored_domains:
                        domains_to_check.add(domain)
            # Extract domains and full URLs
            if url := record.value.get("url"):
                urls_to_scan.add(url)

                # If it's a GitHub repo URL, also scan the user/org URL.
                try:
                    parsed_url = urlparse(url)
                    if "github.com" in parsed_url.netloc:
                        path_parts = [p for p in parsed_url.path.split("/") if p]
                        if len(path_parts) >= 2:  # e.g., /owner/repo
                            user_url = f"{parsed_url.scheme}://{parsed_url.netloc}/{path_parts[0]}"
                            urls_to_scan.add(user_url)
                except Exception as e:
                    logger.debug(f"Could not parse user URL from {url}: {e}")

                # Gather domains from URLs for WHOIS, respecting the ignore list
                extracted = tldextract.extract(url)
                if extracted.registered_domain:
                    if extracted.registered_domain not in ignored_domains:
                        domains_to_check.add(extracted.registered_domain)
                        urls_to_scan.add(url)

        # Perform WHOIS lookups
        logger.info(f"Domains for WHOIS: {', '.join(sorted(list(domains_to_check)))}")
        if domains_to_check:
            for domain in domains_to_check:
                try:
                    evidence_records.extend(whois.collect_from_domain(domain))
                    logger.info(
                        f"Evidence records so far {len(evidence_records)} -- collected from domains/whois"
                    )
                except CollectorError as e:
                    logger.warning(f"WHOIS failed for {domain}: {e}")

        # Scan homepage URLs
        logger.info(f"URLs to scan: {', '.join(sorted(list(urls_to_scan)))}")
        if urls_to_scan:
            try:
                evidence_records.extend(urls.collect_from_urls(urls_to_scan))
                logger.info(
                    f"Evidence records so far {len(evidence_records)} -- collected from urls"
                )
            except CollectorError as e:
                logger.warning(f"URL scanning failed: {e}")

        # --- NEW: Post-analysis backlink step ---
        logger.info("Starting backlink analysis phase.")
        all_url_map = backlinks.gather_urls_from_evidence(evidence_records)

        # --- NEW LOGIC: Separate trusted anchors from candidate URLs ---
        pypi_project_url = f"https://pypi.org/project/{package_name}/"
        trusted_anchor_urls: Set[str] = {pypi_project_url}

        # Candidates are all URLs that are not the trusted anchor itself
        candidate_urls = {
            url: record
            for url, record in all_url_map.items()
            if url not in trusted_anchor_urls
        }

        backlink_evidence = backlinks.analyze_backlinks(
            candidate_urls, trusted_anchor_urls
        )
        if backlink_evidence:
            evidence_records.extend(backlink_evidence)
            logger.info(
                f"Added {len(backlink_evidence)} new evidence records from backlink analysis."
            )

        # Score all collected evidence
        owner_candidates = scoring.score_owners(evidence_records)

        # Assemble final result object
        package_result = schemas.PackageResult(
            package=package_name,
            version=package_version,
            owners=owner_candidates,
            maintainers=pypi_maintainers,
            evidence=evidence_records,
        )

        # 10. Report
        if args.output_format == "json":
            json_reporter.render(package_result)
        else:
            md_reporter.render(package_result)

        # Exit codes
        top_score = owner_candidates[0].score if owner_candidates else 0
        return 0 if top_score >= 0.5 else 101
    except NoEvidenceError as e:
        logger.error(f"{type(e).__name__}: {e}")
        return 101  # As per the PEP for "No usable evidence"
    except NetworkError as e:
        print(f"Error: A network problem occurred: {e}", file=sys.stderr)
        return 101


# --- Handler for the `explain` command ---
def run_explain(args: argparse.Namespace) -> int:
    """Handler for the 'explain' command."""
    logger.info(f"Explaining evidence for package: {args.package}")
    try:
        metadata = pypi.fetch_package_metadata(args.package)
        evidence_records, _ = evidence_analyzer.extract_from_pypi(metadata)

        if args.id:
            record = next(
                (r for r in evidence_records if r.id.startswith(args.id)), None
            )
            if record:
                print(json.dumps(dataclasses.asdict(record), indent=2, default=str))
                return 0
            logger.error(f"Evidence ID matching '{args.id}' not found.")
            return 1
        # Show all evidence
        output: list[dict[str, str | None]] = [
            dataclasses.asdict(r) for r in evidence_records
        ]
        print(json.dumps(output, indent=2, default=str))
        return 0

    except (NoEvidenceError, NetworkError) as e:
        logger.error(f"{type(e).__name__}: {e}")
        return 101


def run_venv(args: argparse.Namespace) -> int:
    """Handler for the 'venv' command."""
    print("Executing 'venv' command...")
    print(f"  Path: {args.path or 'current environment'}")
    # TODO: Implement the actual logic
    return 200  # Placeholder for "No anonymous"


def run_reqs(args: argparse.Namespace) -> int:
    """Handler for the 'reqs' command."""
    print("Executing 'reqs' command...")
    print(f"  Requirements File: {args.requirements_file}")
    # TODO: Implement the actual logic
    return 200  # Placeholder for "No anonymous"


# ... Add placeholder functions for other commands ...


def run_command(args: argparse.Namespace) -> int:
    """
    Dispatches the parsed arguments to the appropriate handler function.

    Args:
        args: The parsed arguments from argparse.

    Returns:
        An exit code.
    """
    # Prefer --verbose if set
    log_level = "DEBUG" if args.log_level == "DEBUG" else args.log_level
    setup_logging(log_level)
    command_handlers = {
        "who-owns": run_who_owns,
        "explain": run_explain,
        "venv": run_venv,
        "reqs": run_reqs,
        # "graph": run_graph,
        # "cache": run_cache,
        # "policy": run_policy,
    }

    handler = command_handlers.get(args.command)

    if handler:
        return handler(args)
    print(f"Error: Command '{args.command}' is not yet implemented.", file=sys.stderr)
    return 2
