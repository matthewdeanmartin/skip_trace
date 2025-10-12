# skip_trace/exceptions.py

class SkipTraceError(Exception):
    """Base exception for all application-specific errors."""
    pass


class ConfigurationError(SkipTraceError):
    """Raised for invalid or missing configuration."""
    pass


class NetworkError(SkipTraceError):
    """Raised for network-related issues like timeouts or connection errors."""
    pass


class NoEvidenceError(SkipTraceError):
    """Raised when no usable evidence can be found for a package."""
    pass


class CollectorError(SkipTraceError):
    """Raised when a specific data collector fails."""
    pass