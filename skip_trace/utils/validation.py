# skip_trace/utils/validation.py

import logging
from typing import Optional

try:
    from email_validator import EmailNotValidError, validate_email

    EMAIL_VALIDATOR_AVAILABLE = True
except ImportError:
    EMAIL_VALIDATOR_AVAILABLE = False

logger = logging.getLogger(__name__)

RESERVED_DOMAINS = {
    "example.com", "example.net", "example.org",
    "localhost", "localhost.localdomain"
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

    if not EMAIL_VALIDATOR_AVAILABLE:
        # Fallback to a simple check if the library is not installed
        if "@" in email_string and "." in email_string and " " not in email_string:
            return email_string.strip().lower()
        return None

    try:
        # We only care about syntactic validity, not whether the domain's
        # mail server is reachable, so we disable deliverability checks.
        valid = validate_email(email_string, check_deliverability=False)

        for reserved in RESERVED_DOMAINS:
            if valid.domain.endswith(reserved):
                return None

        if valid.domain in RESERVED_DOMAINS or any(valid.domain.endswith(suffix) for suffix in RESERVED_SUFFIXES):
            return None

        return valid.normalized
    except EmailNotValidError as e:
        logger.debug(f"String '{email_string}' is not a valid email: {e}")
        return None