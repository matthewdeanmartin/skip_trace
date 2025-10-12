# skip_trace/collectors/__init__.py
from . import github, package_files, pypi, whois

__all__ = ["github", "pypi", "whois", "package_files"]
