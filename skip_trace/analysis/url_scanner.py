# skip_trace/analysis/url_scanner.py
from __future__ import annotations

import datetime
import logging
import os
import re
from typing import List, Set
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils.http_client import normalize_url
from .evidence import generate_evidence_id

# Import directory scanning utilities from the existing source_scanner
from .source_scanner import _is_binary_file, skip_dirs, skip_extensions

logger = logging.getLogger(__name__)

# --- Start of new context-aware extraction logic ---

# Regex for Markdown links: [text](url)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
# Regex for reStructuredText links: `text <url>`_ or .. _text: url
RST_LINK_RE = re.compile(r"`[^`]+`_?\s*<([^>]+)>|.. _[^:]+:\s*(\S+)")
# Generic URL regex, matches greedily. We clean up trailing chars in post-processing.
GENERIC_URL_RE = re.compile(r"(?:https?://|www\.)\S+")
# Characters to strip from the end of a found URL
TRAILING_CHARS = ".,:;!?'\"`)]}>"


def _clean_url(url: str) -> str:
    """Strips common trailing punctuation from a URL, respecting paired parentheses."""
    while len(url) > 1 and url[-1] in TRAILING_CHARS:
        # Don't strip a parenthesis if it closes a matching one in the URL
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        if url[-1] == "]" and url.count("[") >= url.count("]"):
            break
        if url[-1] == "}" and url.count("{") >= url.count("}"):
            break
        url = url[:-1]
    return url


def _from_html(content: str, source_url: str | None = None) -> Set[str]:
    """Extracts URLs from <a> and other tags in HTML content."""
    urls = set()
    try:
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup.find_all(href=True):
            href = tag.get("href")
            if (
                isinstance(href, str)
                and href.strip()
                and not href.startswith(("mailto:", "javascript:"))
            ):
                full_url = urljoin(source_url, href) if source_url else href
                urls.add(full_url)
    except Exception:
        pass  # Ignore parsing errors # nosec # noqa
    return urls


def _from_markdown(content: str) -> Set[str]:
    """Extracts URLs from Markdown specific syntax."""
    urls = set()
    for match in MARKDOWN_LINK_RE.finditer(content):
        urls.add(match.group(1))
    for match in re.finditer(r"<((?:https?://|www\.)\S+)>", content):
        urls.add(match.group(1))
    return urls


def _from_rst(content: str) -> Set[str]:
    """Extracts URLs from reStructuredText specific syntax."""
    urls = set()
    for match in RST_LINK_RE.finditer(content):
        url = match.group(1) or match.group(2)
        if url:
            urls.add(url)
    return urls


def _from_generic_text(content: str) -> Set[str]:
    """Extracts URLs from generic text using regex as a last resort."""
    return {_clean_url(match.group(0)) for match in GENERIC_URL_RE.finditer(content)}


def _extract_urls_from_content(
    content: str, file_type: str, source_url: str | None = None
) -> List[str]:
    """Dispatches URL extraction based on file type."""
    found_urls: Set[str] = set()

    # Always run generic scan as a baseline, except for HTML where we get text first.
    if file_type != "html":
        found_urls.update(_from_generic_text(content))

    # Use specialized parsers which are more accurate
    if file_type == "html":
        found_urls.update(_from_html(content, source_url))
        try:
            # Also scan the visible text for URLs not in hrefs
            soup = BeautifulSoup(content, "html.parser")
            text_content = soup.get_text()
            found_urls.update(_from_generic_text(text_content))
        except Exception:
            # Fallback to generic scan on raw content if soup fails
            found_urls.update(_from_generic_text(content))
    elif file_type == "md":
        found_urls.update(_from_markdown(content))
    elif file_type == "rst":
        found_urls.update(_from_rst(content))

    return sorted(
        {normalized for url in found_urls if (normalized := normalize_url(url))}
    )


def scan_text_for_urls(
    content: str, locator: str, source: EvidenceSource, file_type: str = "txt"
) -> List[EvidenceRecord]:
    """
    Scans a string of text content specifically for URLs.

    Args:
        content: The text content to scan.
        locator: The path or URL where the content was found.
        source: The EvidenceSource to assign to new records.

    Returns:
        A list of EvidenceRecord objects for any URLs found.
    """
    evidence_list: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)

    source_url = locator if source == EvidenceSource.URL else None
    extracted_urls = _extract_urls_from_content(content, file_type, source_url)

    for url in extracted_urls:
        value = {"label": f"URL found in {file_type} content", "url": url}
        record = EvidenceRecord(
            id=generate_evidence_id(
                source,
                EvidenceKind.PROJECT_URL,
                locator,
                str(value),
                url,
                hint=f"{file_type}-scan",
            ),
            source=source,
            locator=locator,
            kind=EvidenceKind.PROJECT_URL,
            value=value,
            observed_at=now,
            confidence=0.15,
            notes=f"Found URL '{url}' in '{locator}'.",
        )
        evidence_list.append(record)

    return evidence_list


def scan_directory_for_urls(
    directory_path: str, locator_prefix: str
) -> List[EvidenceRecord]:
    """
    Scans a directory of files specifically for URL evidence.

    Args:
        directory_path: The absolute path to the directory to scan.
        locator_prefix: A prefix for the evidence locator (e.g., package name/version).

    Returns:
        A list of EvidenceRecord objects found in the files.
    """
    evidence_list: List[EvidenceRecord] = []
    file_count = 0

    for root, dirs, files in os.walk(directory_path):
        # Prune the search by removing directories to skip
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for filename in files:
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, directory_path)
            file_count += 1

            _, extension = os.path.splitext(filename.lower())
            extension = extension.lstrip(".")

            if extension in skip_extensions or _is_binary_file(file_path):
                continue

            # still don't want to scan binary files!
            if _is_binary_file(file_path):
                continue

            file_type = "txt"
            if extension in ("html", "htm"):
                file_type = "html"
            elif extension == "md":
                file_type = "md"
            elif extension == "rst":
                file_type = "rst"

            logger.debug(
                f"Scanning for URLs in file: {relative_path} (type: {file_type})"
            )

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                locator = f"{locator_prefix}/{relative_path}"
                url_evidence = scan_text_for_urls(
                    content, locator, EvidenceSource.WHEEL, file_type=file_type
                )
                evidence_list.extend(url_evidence)

            except (IOError, UnicodeDecodeError) as e:
                logger.debug(f"Could not read or process file {file_path}: {e}")
                continue

    logger.info(
        f"Scanned {file_count} files for URLs, found {len(evidence_list)} records."
    )
    return evidence_list
