# skip_trace/main.py

import argparse
import dataclasses
import json
import logging
import sys
from typing import Set

import tldextract
from rich.logging import RichHandler

from . import schemas
from .analysis import evidence as evidence_analyzer
from .analysis import scoring
from .collectors import github, pypi, whois, package_files
from .config import CONFIG
from .exceptions import CollectorError, NetworkError, NoEvidenceError
from .reporting import json_reporter, md_reporter
from .utils.validation import is_valid_email

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
        # 1. Collect initial data from PyPI
        metadata = pypi.fetch_package_metadata(args.package, args.version)
        package_name = metadata.get("info", {}).get("name", args.package)
        package_version = metadata.get("info", {}).get("version")
        logger.debug(f"Successfully fetched metadata for {package_name} v{package_version}")

        # 2. Analyze primary package metadata
        evidence_records, pypi_maintainers = evidence_analyzer.extract_from_pypi(metadata)

        # 3. Cross-Reference for more PyPI evidence
        cross_ref_evidence = pypi.cross_reference_by_user(package_name)
        evidence_records.extend(cross_ref_evidence)

        # 4. Fetch evidence from code repositories found in PyPI evidence
        repo_urls = set()
        for record in evidence_records:
            if record.source == schemas.EvidenceSource.PYPI and record.kind == schemas.EvidenceKind.ORGANIZATION:
                url = record.value.get("url")
                if url and "github.com" in url:
                    repo_urls.add(url)

        for url in repo_urls:
            logger.info(f"Analyzing GitHub repository: {url}")
            try:
                github_evidence = github.extract_from_repo_url(url)
                evidence_records.extend(github_evidence)
            except CollectorError as e:
                logger.warning(f"Could not fully analyze GitHub repo {url}: {e}")

        # 5. Extract domains and perform WHOIS lookups
        domains_to_check: Set[str] = set()
        ignored_domains = set(CONFIG.get("whois_ignored_domains", []))

        for record in evidence_records:
            potential_domains: Set[str] = set()

            # Case 1: Maintainer/Author email
            if record.kind in (schemas.EvidenceKind.EMAIL, schemas.EvidenceKind.MAINTAINER, schemas.EvidenceKind.AUTHOR_TAG):
                if email := record.value.get("email"):
                    if "@" in email:
                        potential_domains.add(email.split("@")[1])

            # Case 2: URL from project_urls or org links
            elif record.kind in (schemas.EvidenceKind.ORGANIZATION, schemas.EvidenceKind.PROJECT_URL):
                if url := record.value.get("url"):
                    extracted = tldextract.extract(url)
                    if extracted.registered_domain:
                        potential_domains.add(extracted.registered_domain)

            # Case 3: Contacts from a user profile (email, blog, etc.)
            elif record.kind == schemas.EvidenceKind.USER_PROFILE:
                if contacts := record.value.get("contacts"):
                    for contact_value in contacts.values():
                        if not contact_value:
                            continue
                        if valid_email := is_valid_email(contact_value):
                            potential_domains.add(valid_email.split("@")[1])
                        elif contact_value and "://" in contact_value:
                            extracted = tldextract.extract(contact_value)
                            if extracted.registered_domain:
                                potential_domains.add(extracted.registered_domain)

            # Add valid domains to the main set to be checked
            for domain in potential_domains:
                if domain not in ignored_domains:
                    domains_to_check.add(domain)

        if domains_to_check:
            logger.info(f"Found domains for WHOIS lookup: {', '.join(sorted(list(domains_to_check)))}")
            for domain in domains_to_check:
                try:
                    whois_evidence = whois.collect_from_domain(domain)
                    evidence_records.extend(whois_evidence)
                except CollectorError as e:
                    logger.warning(f"Could not get WHOIS evidence for {domain}: {e}")

        # 6. Analyze package contents for deep evidence
        try:
            package_files_evidence = package_files.collect_from_package_files(metadata)
            evidence_records.extend(package_files_evidence)
        except CollectorError as e:
            logger.warning(f"Could not analyze package files for {package_name}: {e}")

        # 7. Score all collected evidence
        owner_candidates = scoring.score_owners(evidence_records)

        # 8. Assemble final result object
        package_result = schemas.PackageResult(
            package=package_name,
            version=package_version,
            owners=owner_candidates,
            maintainers=pypi_maintainers,
            evidence=evidence_records,
        )

        # 9. Report
        if args.output_format == 'json':
            json_reporter.render(package_result)
        else:
            md_reporter.render(package_result)

        # PEP specified exit codes based on score
        # Using placeholder thresholds for now
        top_score = owner_candidates[0].score if owner_candidates else 0
        if top_score >= 0.7:
            return 0  # Success
        elif top_score >= 0.5:
            return 100  # Indeterminate
        else:
            return 101  # No usable evidence

        # TODO: Pass evidence_records to the scoring engine
        # Later, this will be replaced by a call to the analysis and reporting modules.
        # For example:
        #
        # evidence = analysis.evidence.extract_from_pypi(metadata)
        # owners = analysis.scoring.score_owners(evidence)
        # package_result = schemas.PackageResult(package=args.package, owners=owners, evidence=evidence)
        # reporting.json_reporter.render(package_result)

        return 0
    except NoEvidenceError as e:
        raise
        logger.error(f"{type(e).__name__}: {e}")
        return 101  # As per the PEP for "No usable evidence"
    except NetworkError as e:
        raise
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
            # Filter for a specific evidence ID
            record = next((r for r in evidence_records if r.id.startswith(args.id)), None)
            if record:
                output = dataclasses.asdict(record)
            else:
                logger.error(f"Evidence ID matching '{args.id}' not found.")
                return 1
        else:
            # Show all evidence
            output = [dataclasses.asdict(r) for r in evidence_records]

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
        # "explain": run_explain,
        # "graph": run_graph,
        # "cache": run_cache,
        # "policy": run_policy,
    }

    handler = command_handlers.get(args.command)

    if handler:
        return handler(args)
    else:
        print(f"Error: Command '{args.command}' is not yet implemented.", file=sys.stderr)
        return 2