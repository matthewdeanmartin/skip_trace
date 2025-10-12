# skip_trace/collectors/github_files.py
from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional, Set
from urllib.parse import urlparse

from github import GithubException

from ..analysis.evidence import generate_evidence_id
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils import http_client
from .github import _create_records_from_user_profile, get_github_client

logger = logging.getLogger(__name__)


def _parse_repo_url(url: str) -> Optional[str]:
    """Parses a GitHub URL to extract the 'owner/repo' string."""
    try:
        parsed = urlparse(url)
        if parsed.hostname and "github.com" in parsed.hostname:
            path = parsed.path.strip("/")
            if ".git" in path:
                path = path.replace(".git", "")
            if len(path.split("/")) >= 2:
                return "/".join(path.split("/")[:2])
    except Exception:  # nosec
        pass
    logger.warning(f"Could not parse a valid GitHub repository from URL: {url}")
    return None


def collect_security_policy(repo_url: str) -> List[EvidenceRecord]:
    """
    Fetches and parses SECURITY.md from a GitHub repo.

    Looks for security contact emails and responsible disclosure information.

    Args:
        repo_url: The full URL of the GitHub repository.

    Returns:
        A list of EvidenceRecord objects from the security policy.
    """
    evidence: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)

    # Try common locations for security policy
    security_paths = [
        "SECURITY.md",
        ".github/SECURITY.md",
        "docs/SECURITY.md",
        "security.md",
        ".github/security.md",
    ]

    repo_url = repo_url.rstrip("/")

    for path in security_paths:
        # Try both main and master branches
        for branch in ["main", "master"]:
            raw_url = f"{repo_url}/raw/{branch}/{path}"
            response = http_client.make_request_safe(raw_url)

            if response and response.status_code == 200:
                content = response.text
                logger.info(f"Found security policy at {raw_url}")

                # Extract emails from the security policy
                email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
                emails = re.findall(email_pattern, content)

                seen_emails: Set[str] = set()
                for email in emails:
                    from ..utils.validation import is_valid_email

                    if valid_email := is_valid_email(email):
                        if valid_email in seen_emails:
                            continue
                        seen_emails.add(valid_email)

                        value = {
                            "email": valid_email,
                            "context": "security contact",
                            "source_file": path,
                        }
                        evidence.append(
                            EvidenceRecord(
                                id=generate_evidence_id(
                                    EvidenceSource.REPO,
                                    EvidenceKind.CONTACT,
                                    raw_url,
                                    str(value),
                                    valid_email,
                                    hint="security",
                                ),
                                source=EvidenceSource.REPO,
                                locator=raw_url,
                                kind=EvidenceKind.CONTACT,
                                value=value,
                                observed_at=now,
                                confidence=0.85,
                                notes=f"Security contact email found in {path}.",
                            )
                        )

                # Found a security file, no need to check other locations
                return evidence

    logger.debug(f"No security policy found for {repo_url}")
    return evidence


def collect_funding_info(repo_url: str) -> List[EvidenceRecord]:
    """
    Parses .github/FUNDING.yml for sponsor/funding identities.

    GitHub sponsors, Patreon, Ko-fi, and other funding platforms often
    provide alternative contact/identity information.

    Args:
        repo_url: The full URL of the GitHub repository.

    Returns:
        A list of EvidenceRecord objects from funding configuration.
    """
    evidence: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)

    repo_url = repo_url.rstrip("/")

    # Try both main and master branches
    for branch in ["main", "master"]:
        funding_url = f"{repo_url}/raw/{branch}/.github/FUNDING.yml"
        response = http_client.make_request_safe(funding_url)

        if response and response.status_code == 200:
            logger.info(f"Found funding configuration at {funding_url}")

            try:
                import yaml

                data = yaml.safe_load(response.text)

                # GitHub sponsors
                if github := data.get("github"):
                    usernames = [github] if isinstance(github, str) else github
                    for username in usernames:
                        value = {
                            "username": username,
                            "platform": "github_sponsors",
                            "url": f"https://github.com/sponsors/{username}",
                        }
                        evidence.append(
                            EvidenceRecord(
                                id=generate_evidence_id(
                                    EvidenceSource.REPO,
                                    EvidenceKind.CONTACT,
                                    funding_url,
                                    str(value),
                                    username,
                                    hint="sponsor",
                                ),
                                source=EvidenceSource.REPO,
                                locator=funding_url,
                                kind=EvidenceKind.CONTACT,
                                value=value,
                                observed_at=now,
                                confidence=0.75,
                                notes=f"GitHub Sponsors profile: {username}",
                            )
                        )

                # Other funding platforms
                platform_configs = {
                    "patreon": "https://www.patreon.com/{}",
                    "ko_fi": "https://ko-fi.com/{}",
                    "open_collective": "https://opencollective.com/{}",
                    "tidelift": "https://tidelift.com/funding/github/{}",
                    "community_bridge": "https://funding.communitybridge.org/projects/{}",
                    "liberapay": "https://liberapay.com/{}",
                    "issuehunt": "https://issuehunt.io/r/{}",
                    "buy_me_a_coffee": "https://buymeacoffee.com/{}",
                }

                for platform, url_template in platform_configs.items():
                    if value := data.get(platform):
                        usernames = [value] if isinstance(value, str) else value
                        for username in usernames:
                            contact_value = {
                                "username": username,
                                "platform": platform,
                                "url": url_template.format(username),
                            }
                            evidence.append(
                                EvidenceRecord(
                                    id=generate_evidence_id(
                                        EvidenceSource.REPO,
                                        EvidenceKind.CONTACT,
                                        funding_url,
                                        str(contact_value),
                                        username,
                                        hint=platform,
                                    ),
                                    source=EvidenceSource.REPO,
                                    locator=funding_url,
                                    kind=EvidenceKind.CONTACT,
                                    value=contact_value,
                                    observed_at=now,
                                    confidence=0.70,
                                    notes=f"Funding platform {platform}: {username}",
                                )
                            )

                # Custom URLs (often personal websites or donation pages)
                if custom := data.get("custom"):
                    custom_urls = [custom] if isinstance(custom, str) else custom
                    for url in custom_urls:
                        value = {
                            "url": url,
                            "platform": "custom_funding",
                            "label": "Custom funding URL",
                        }
                        evidence.append(
                            EvidenceRecord(
                                id=generate_evidence_id(
                                    EvidenceSource.REPO,
                                    EvidenceKind.PROJECT_URL,
                                    funding_url,
                                    str(value),
                                    url,
                                    hint="funding",
                                ),
                                source=EvidenceSource.REPO,
                                locator=funding_url,
                                kind=EvidenceKind.PROJECT_URL,
                                value=value,
                                observed_at=now,
                                confidence=0.60,
                                notes=f"Custom funding URL: {url}",
                            )
                        )

                # Found funding file, return
                return evidence

            except Exception as e:
                logger.warning(f"Failed to parse FUNDING.yml from {funding_url}: {e}")

    logger.debug(f"No funding configuration found for {repo_url}")
    return evidence


def collect_top_contributors(repo_url: str) -> List[EvidenceRecord]:
    """
    Fetches top contributors from a GitHub repo via the API.

    Contributors often have rich profile information that can provide
    additional identity and contact evidence.

    Args:
        repo_url: The full URL of the GitHub repository.

    Returns:
        A list of EvidenceRecord objects from contributor profiles.
    """
    evidence: List[EvidenceRecord] = []

    repo_full_name = _parse_repo_url(repo_url)
    if not repo_full_name:
        return []

    client = get_github_client()
    if not client:
        logger.warning("GitHub client not available, skipping contributor analysis")
        return []

    try:
        logger.info(f"Fetching contributors for {repo_full_name}")
        repo = client.get_repo(repo_full_name)
        contributors = repo.get_contributors()

        # Limit to top 10 to avoid excessive API usage
        processed_count = 0
        for contributor in contributors:
            if processed_count >= 10:
                break

            # Skip bots and automated accounts
            if contributor.type == "Bot":
                continue

            # Reuse the existing profile extraction logic from github.py
            contributor_evidence = _create_records_from_user_profile(contributor)
            evidence.extend(contributor_evidence)
            processed_count += 1

        logger.info(f"Extracted evidence from {processed_count} contributors")

    except GithubException as e:
        logger.warning(
            f"GitHub API error for contributors of '{repo_full_name}': {e.status}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error fetching contributors for '{repo_full_name}': {e}"
        )

    return evidence


def collect_from_repo_url(repo_url: str) -> List[EvidenceRecord]:
    """
    Main entry point: collects evidence from all GitHub file sources.

    This function coordinates the collection of evidence from:
    - SECURITY.md files (security contacts)
    - FUNDING.yml (funding/sponsor information)
    - Contributors API (contributor profiles)

    Args:
        repo_url: The full URL of the GitHub repository.

    Returns:
        A combined list of all EvidenceRecord objects found.
    """
    all_evidence: List[EvidenceRecord] = []

    logger.info(f"Collecting evidence from GitHub files for {repo_url}")

    # Collect from security policy
    try:
        security_evidence = collect_security_policy(repo_url)
        all_evidence.extend(security_evidence)
        logger.debug(f"Found {len(security_evidence)} records from security policy")
    except Exception as e:
        logger.warning(f"Error collecting security policy: {e}")

    # Collect from funding configuration
    try:
        funding_evidence = collect_funding_info(repo_url)
        all_evidence.extend(funding_evidence)
        logger.debug(f"Found {len(funding_evidence)} records from funding config")
    except Exception as e:
        logger.warning(f"Error collecting funding info: {e}")

    # Collect from contributors
    try:
        contributor_evidence = collect_top_contributors(repo_url)
        all_evidence.extend(contributor_evidence)
        logger.debug(f"Found {len(contributor_evidence)} records from contributors")
    except Exception as e:
        logger.warning(f"Error collecting contributors: {e}")

    logger.info(f"Total evidence from GitHub files: {len(all_evidence)} records")
    return all_evidence
