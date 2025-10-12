# skip_trace/exceptions.py
from __future__ import annotations


class SkipTraceError(Exception):
    """Base exception for all application-specific errors."""


class ConfigurationError(SkipTraceError):
    """Raised for invalid or missing configuration."""


class NetworkError(SkipTraceError):
    """Raised for network-related issues like timeouts or connection errors."""


class NoEvidenceError(SkipTraceError):
    """Raised when no usable evidence can be found for a package."""


class CollectorError(SkipTraceError):
    """Raised when a specific data collector fails."""
