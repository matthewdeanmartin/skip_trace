# skip_trace/collectors/github.py
from __future__ import annotations

import datetime
import logging
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from github import Github, GithubException

from github.NamedUser import NamedUser

from ..analysis.evidence import generate_evidence_id
from ..config import CONFIG
from ..exceptions import CollectorError, NetworkError
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils import http_client

logger = logging.getLogger(__name__)

_github_client: Optional[Github] = None


def get_github_client() -> Optional[Github]:
    """
    Initializes and returns a singleton PyGithub client instance.

    Uses the GITHUB_TOKEN from the config if available.

    Returns:
        An authenticated Github client instance, or None if the token is missing.
    """
    global _github_client
    if _github_client:
        return _github_client

    github_config = CONFIG.get("github", {})
    api_key = github_config.get("api_key")

    if not api_key:
        logger.warning(
            "GITHUB_TOKEN not found in environment. GitHub API requests will be unauthenticated and rate-limited."
        )
        _github_client = Github()
    else:
        logger.debug("Authenticating to GitHub API with token.")
        _github_client = Github(api_key)

    return _github_client


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
    except Exception:
        pass
    logger.debug(f"Could not parse a valid GitHub repository from URL: {url}")
    return None


def _scrape_socials_from_html(html_url: str) -> Dict[str, str]:
    """Scrapes a user's GitHub profile page for social media and blog links."""
    contacts: Dict[str, str] = {}
    try:
        logger.debug(f"Scraping GitHub profile HTML page for social links: {html_url}")
        response = http_client.make_request(html_url)
        soup = BeautifulSoup(response.text, "html.parser")

        # Find all links within the user profile section
        # profile_links = soup.select('div[data-bio-টারের] a[href], ul.vcard-details a[href]')
        # brittle!
        profile_links = soup.select(
            "div.user-profile-bio a[href], ul.vcard-details a[href]"
        )
        for link in profile_links:
            href = link.get("href")
            if not href:
                continue

            # Simple heuristic mapping of domain to platform name
            if "linkedin.com/in" in href and "linkedin" not in contacts:
                contacts["linkedin"] = href  # type: ignore[assignment]
            elif (
                "mastodon.social" in href or "fosstodon.org" in href
            ) and "mastodon" not in contacts:
                contacts["mastodon"] = href   # type: ignore[assignment]
            elif "twitter.com" in href and "twitter" not in contacts:
                # Prefer the twitter_username from API, but take this if needed
                contacts["twitter"] = href   # type: ignore[assignment]
            elif "blog." in href or "medium.com" in href and "blog" not in contacts:
                contacts["blog"] = href   # type: ignore[assignment]

    except NetworkError as e:
        logger.warning(f"Could not scrape GitHub profile page {html_url}: {e}")
    except Exception as e:
        logger.error(f"Error during social scraping for {html_url}: {e}")

    return contacts


def _create_records_from_user_profile(user: NamedUser) -> List[EvidenceRecord]:
    """Creates evidence records from a full GitHub user profile."""
    records = []
    name = user.name or user.login
    now = datetime.datetime.now(datetime.timezone.utc)

    # Evidence for company affiliation
    if user.company:
        value:dict[str, str | None] = {"user_name": name, "company_name": user.company}
        records.append(
            EvidenceRecord(
                id=generate_evidence_id(
                    EvidenceSource.REPO,
                    EvidenceKind.USER_COMPANY,
                    user.html_url,
                    str(value),
                    name,
                    hint="company",
                ),
                source=EvidenceSource.REPO,
                locator=user.html_url,
                kind=EvidenceKind.USER_COMPANY,
                value=value,
                observed_at=now,
                confidence=0.8,
                notes=f"User '{name}' lists company affiliation as '{user.company}'.",
            )
        )

    # Evidence for other profile contacts
    profile_contacts = {
        "email": user.email,
        "twitter": (
            f"https://twitter.com/{user.twitter_username}"
            if user.twitter_username
            else None
        ),
        "blog": user.blog,
    }

    # Scrape HTML for links not available in the API
    scraped_contacts = _scrape_socials_from_html(user.html_url)
    # The scraped contacts take precedence if they exist
    profile_contacts.update(scraped_contacts)

    # Filter out empty values
    profile_contacts = {k: v for k, v in profile_contacts.items() if v}
    if profile_contacts:
        profile_info = {"user_name": name, "contacts": profile_contacts}
        records.append(
            EvidenceRecord(
                id=generate_evidence_id(
                    EvidenceSource.REPO,
                    EvidenceKind.USER_PROFILE,
                    user.html_url,
                    str(profile_info), # TODO: stringify this better?
                    name,
                    hint="profile",
                ),
                source=EvidenceSource.REPO,
                locator=user.html_url,
                kind=EvidenceKind.USER_PROFILE,
                value=profile_info,
                observed_at=now,
                confidence=0.9,
                notes=f"Found contact details on GitHub user profile for '{name}'.",
            )
        )

    return records


def extract_from_repo_url(repo_url: str) -> List[EvidenceRecord]:
    """
    Extracts ownership evidence from a GitHub repository URL.

    Args:
        repo_url: The full URL of the GitHub repository.

    Returns:
        A list of EvidenceRecord objects.
    """
    evidence = []
    processed_users: Set[str] = set()
    repo_full_name = _parse_repo_url(repo_url)
    if not repo_full_name:
        return []

    client = get_github_client()
    if not client:
        return []

    try:
        logger.debug(f"Fetching repository details for '{repo_full_name}'")
        repo = client.get_repo(repo_full_name)

        # 1. Process the repository owner's full profile
        owner = repo.owner
        if owner.login not in processed_users:
            evidence.extend(_create_records_from_user_profile(owner))
            processed_users.add(owner.login)

        # 2. Process recent commit authors' full profiles
        logger.debug(f"Fetching recent commits for '{repo_full_name}'")
        commits = repo.get_commits()
        # Limit to the most recent 25 commits to avoid excessive API usage
        for i, commit in enumerate(commits):
            if i >= 10:  # Limit to recent 10 to reduce API calls
                break
            # commit.author is a full NamedUser if available
            if (
                isinstance(commit.author, NamedUser)
                and commit.author.login not in processed_users
            ):
                evidence.extend(_create_records_from_user_profile(commit.author))
                processed_users.add(commit.author.login)

    except GithubException as e:
        logger.error(f"GitHub API error for '{repo_full_name}': {e.status} {e.data}")
        raise CollectorError(
            f"Could not access GitHub repository '{repo_full_name}'"
        ) from e
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while processing GitHub repo '{repo_full_name}': {e}"
        )
        raise CollectorError(
            f"Unexpected error for GitHub repo '{repo_full_name}'"
        ) from e

    logger.info(
        f"Extracted {len(evidence)} evidence records from GitHub user profiles for repo '{repo_full_name}'."
    )
    return evidence
