# skip_trace/collectors/__init__.py
from . import github, pypi, whois, package_files

__all__ = ["github", "pypi", "whois", "package_files"]