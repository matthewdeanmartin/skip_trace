# skip_trace/utils/validation.py
from __future__ import annotations

import logging
from typing import Optional

from email_validator import EmailNotValidError, validate_email

logger = logging.getLogger(__name__)

RESERVED_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "localhost",
    "localhost.localdomain",
}

RESERVED_SUFFIXES = {".test", ".example", ".invalid", ".localhost"}


def is_valid_email(email_string: str) -> Optional[str]:
    """
    Checks if a string is a valid email address using a robust library.

    Args:
        email_string: The string to validate.

    Returns:
        The normalized email address if valid, otherwise None.
    """
    if not isinstance(email_string, str):
        return None

    try:
        # We only care about syntactic validity, not whether the domain's
        # mail server is reachable, so we disable deliverability checks.
        valid = validate_email(email_string, check_deliverability=False)

        for reserved in RESERVED_DOMAINS:
            if valid.domain.endswith(reserved):
                return None

        if valid.domain in RESERVED_DOMAINS or any(
            valid.domain.endswith(suffix) for suffix in RESERVED_SUFFIXES
        ):
            return None

        return valid.normalized
    except EmailNotValidError as e:
        logger.debug(f"String '{email_string}' is not a valid email: {e}")
        return None
