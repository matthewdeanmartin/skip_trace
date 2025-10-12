# skip_trace/collectors/__init__.py
from . import github, github_files, package_files, pypi, sigstore, whois

__all__ = ["github", "github_files", "package_files", "pypi", "whois", "sigstore"]
