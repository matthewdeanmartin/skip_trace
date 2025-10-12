# skip_trace/analysis/source_scanner.py

import datetime
import logging
import os
import re
import string
from typing import List

import tldextract

from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils.validation import is_valid_email
from .evidence import generate_evidence_id, _parse_contact_string
from . import ner  # Import the new NER module

logger = logging.getLogger(__name__)

# Regex to find copyright notices, capturing the holder.
# Looks for "Copyright", optional (c) symbol, optional year, then the owner.
COPYRIGHT_RE = re.compile(
    r"copyright\s*(?:\(c\))?\s*(?:[0-9,\-\s]+)?\s*([^\n]+)", re.IGNORECASE
)

# Regex to find __author__ assignments
AUTHOR_RE = re.compile(r"__author__\s*=\s*['\"]([^'\"]+)['\"]")

# Regex for finding standalone email addresses - used as a fast pre-filter
EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

# NEW: Words that indicate a regex grabbed junk from a license instead of a name.
# This filter now lives in the scanner, where the bad evidence is generated.
JUNK_WORDS = {
    "copyright", "holders", "license", "document", "accompanies", "notice", "authors",
    "identifies", "endorse", "promote", "software", "permission", "conditions",
    # stop words
    "and", "other", "the", "for", "with", "this", "list", "following", "txt", "damages",
    "owner",
    # legalese
    "incidental", "holder", "liability",
    # license names
    "MIT", "BSD"
}

# --- NEW: Filename allowlist and more robust binary detection ---

# A set of common extensionless text files that should never be treated as binary.
TEXT_FILENAMES = {
    'readme', 'license', 'copying', 'notice', 'authors', 'contributors',
    'changelog', 'history', 'install', 'makefile', 'dockerfile', 'vagrantfile'
}


def _is_binary_file(filepath: str, chunk_size: int = 1024) -> bool:
    """
    Heuristically determines if a file is binary using a multi-step check.

    1. Checks against an allowlist of common text filenames (e.g., 'LICENSE').
    2. Checks for the presence of NULL bytes.
    3. Checks the ratio of non-printable text characters.

    Args:
        filepath: The path to the file to check.
        chunk_size: The number of bytes to read from the beginning of the file.

    Returns:
        True if the file is likely binary, False otherwise.
    """
    # 1. Check filename allowlist first.
    basename = os.path.basename(filepath).lower()
    if basename in TEXT_FILENAMES:
        return False

    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(chunk_size)
    except IOError:
        return True  # Cannot read, so skip it.

    if not chunk:
        return False  # Empty file is not binary.

    # 2. A null byte is a strong indicator of a binary file.
    if b'\0' in chunk:
        return True

    # 3. Check the ratio of text characters to total characters.
    # A high percentage of non-printable characters indicates binary data.
    printable = set(bytes(string.printable, 'ascii'))
    non_printable_count = sum(1 for byte in chunk if byte not in printable)

    # If more than 30% of the characters are non-printable, it's likely binary.
    ratio = non_printable_count / len(chunk)
    return ratio > 0.3


def _process_authors_file(
        content: str, locator: str, now: datetime.datetime
) -> List[EvidenceRecord]:
    """Processes an AUTHORS file, treating each non-blank line as a potential author."""
    evidence_list = []
    logger.debug(f"Processing AUTHORS file at: {locator}")
    lines = [line.strip() for line in content.splitlines()]
    for line in lines:
        if not line or line.startswith("#"):
            continue

        parsed = _parse_contact_string(line)
        if not parsed.get("name") and not parsed.get("email"):
            continue

        value = {"name": parsed["name"], "email": parsed["email"]}
        name_for_slug = parsed["name"] or parsed["email"] or "unknown"

        record = EvidenceRecord(
            id=generate_evidence_id(EvidenceSource.WHEEL, EvidenceKind.AUTHOR_TAG, locator, str(value), name_for_slug),
            source=EvidenceSource.WHEEL,
            locator=locator,
            kind=EvidenceKind.AUTHOR_TAG,
            value=value,
            observed_at=now,
            confidence=0.20,  # Higher confidence than a random email
            notes=f"Found author '{line}' in AUTHORS file."
        )
        evidence_list.append(record)
        logger.debug(f"Found author from AUTHORS file: {line}")

    return evidence_list


def scan_directory(
        directory_path: str, locator_prefix: str
) -> List[EvidenceRecord]:
    """
    Scans a directory of files for ownership evidence.

    Args:
        directory_path: The absolute path to the directory to scan.
        locator_prefix: A prefix for the evidence locator (e.g., package name/version).

    Returns:
        A list of EvidenceRecord objects found in the files.
    """
    evidence_list: List[EvidenceRecord] = []
    now = datetime.datetime.now(datetime.timezone.utc)

    skip_dirs = {".git", "__pycache__", ".idea", ".vscode", "dist", "build", ".egg-info", "node_modules"}
    # More comprehensive list of binary extensions
    skip_extensions = {
        ".pyc", ".pyo", ".so", ".pyd", ".egg", ".whl",  # Python
        ".o", ".a", ".dll", ".exe",  # Compiled
        ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",  # Images
        ".woff", ".woff2", ".ttf", ".eot", ".otf",  # Fonts
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",  # Archives
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",  # Docs
        ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".mov", ".avi", ".mkv"  # Media
    }

    file_count = 0
    for root, dirs, files in os.walk(directory_path):
        # Modify dirs in-place to prune the search
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for filename in files:
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, directory_path)
            file_count += 1

            _, extension = os.path.splitext(filename)
            if extension.lower() in skip_extensions:
                continue

            if _is_binary_file(file_path):
                logger.debug(f"Skipping binary file detected by content: {relative_path}")
                continue

            logger.debug(f"Scanning file: {relative_path}")

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                locator = f"{locator_prefix}/{relative_path}"

                # 1. Special handling for AUTHORS files
                if filename.lower().startswith("authors") or filename.lower().startswith("contributors"):
                    evidence_list.extend(_process_authors_file(content, locator, now))
                    continue  # Don't process this file further for generic matches

                # MODIFIED: Use NER for copyright lines
                for match in COPYRIGHT_RE.finditer(content):
                    copyright_text = match.group(1).strip().rstrip(",.")

                    # Try NER first
                    entities = ner.extract_entities(copyright_text)
                    if entities:
                        for entity_name, entity_label in entities:
                            if entity_name.lower() not in JUNK_WORDS:
                                value = {"holder": entity_name, "file": relative_path}
                                notes = f"Found copyright holder '{entity_name}' via NER ({entity_label})."
                                record = EvidenceRecord(
                                    id=generate_evidence_id(EvidenceSource.WHEEL, EvidenceKind.COPYRIGHT, locator,
                                                            str(value), entity_name),
                                    source=EvidenceSource.WHEEL, locator=locator, kind=EvidenceKind.COPYRIGHT,
                                    value=value, observed_at=now, confidence=0.40,  # Higher confidence for NER
                                    notes=notes
                                )
                                already_in = False
                                for already in evidence_list:
                                    if already.notes == notes:
                                        already_in = True
                                if not already_in:
                                    evidence_list.append(record)
                    # else:
                    #     # --- MODIFIED: Stricter filtering for the regex fallback ---
                    #     # 1. Reject if it's too long to be a name.
                    #     if len(copyright_text) > 50: continue
                    #     # 2. Reject if it contains common license garbage words.
                    #     if any(word in copyright_text.lower() for word in JUNK_WORDS): continue
                    #
                    #     value = {"holder": copyright_text, "file": relative_path}
                    #     record = EvidenceRecord(
                    #         id=generate_evidence_id(EvidenceSource.WHEEL, EvidenceKind.COPYRIGHT, locator, str(value),
                    #                                 copyright_text),
                    #         source=EvidenceSource.WHEEL, locator=locator, kind=EvidenceKind.COPYRIGHT,
                    #         value=value, observed_at=now, confidence=0.25,
                    #         notes=f"Found copyright notice for '{copyright_text}' in file (regex fallback)."
                    #     )
                    #     evidence_list.append(record)else:
                    #     # --- MODIFIED: Stricter filtering for the regex fallback ---
                    #     # 1. Reject if it's too long to be a name.
                    #     if len(copyright_text) > 50: continue
                    #     # 2. Reject if it contains common license garbage words.
                    #     if any(word in copyright_text.lower() for word in JUNK_WORDS): continue
                    #
                    #     value = {"holder": copyright_text, "file": relative_path}
                    #     record = EvidenceRecord(
                    #         id=generate_evidence_id(EvidenceSource.WHEEL, EvidenceKind.COPYRIGHT, locator, str(value),
                    #                                 copyright_text),
                    #         source=EvidenceSource.WHEEL, locator=locator, kind=EvidenceKind.COPYRIGHT,
                    #         value=value, observed_at=now, confidence=0.25,
                    #         notes=f"Found copyright notice for '{copyright_text}' in file (regex fallback)."
                    #     )
                    #     evidence_list.append(record)

                # 3. Scan for __author__ tags in Python files
                if filename.endswith(".py"):
                    for match in AUTHOR_RE.finditer(content):
                        author_str = match.group(1).strip()
                        parsed = _parse_contact_string(author_str)
                        if not parsed.get("name") and not parsed.get("email"):
                            continue

                        value = {"name": parsed["name"], "email": parsed["email"]}
                        name_for_slug = parsed["name"] or parsed["email"] or "unknown"
                        record = EvidenceRecord(
                            id=generate_evidence_id(EvidenceSource.WHEEL, EvidenceKind.AUTHOR_TAG, locator, str(value),
                                                    name_for_slug),
                            source=EvidenceSource.WHEEL,
                            locator=locator,
                            kind=EvidenceKind.AUTHOR_TAG,
                            value=value,
                            observed_at=now,
                            confidence=0.20,
                            notes=f"Found __author__ tag for '{author_str}' in file."
                        )
                        evidence_list.append(record)

                # 4. Scan for any standalone email address (lower confidence)
                # First, find candidates with regex, then validate them properly.
                for match in EMAIL_RE.finditer(content):
                    potential_email = match.group(0)
                    if valid_email := is_valid_email(potential_email):
                        value = {"name": None, "email": valid_email}
                        notes = f"Found validated contact email '{valid_email}' in file."
                        record = EvidenceRecord(
                            id=generate_evidence_id(EvidenceSource.WHEEL, EvidenceKind.CONTACT, locator, str(value), valid_email),
                            source=EvidenceSource.WHEEL,
                            locator=locator,
                            kind=EvidenceKind.CONTACT,
                            value=value,
                            observed_at=now,
                            confidence=0.15,  # Slightly higher confidence now that it's validated
                            notes=notes
                        )
                        already_in = False
                        for already in evidence_list:
                            if already.notes == notes:
                                already_in = True
                        if not already_in:
                            evidence_list.append(record)


            except (IOError, UnicodeDecodeError) as e:
                logger.debug(f"Could not read or process file {file_path}: {e}")
                continue

    logger.info(f"Scanned {file_count} files in directory, found {len(evidence_list)} potential evidence records.")
    return evidence_list