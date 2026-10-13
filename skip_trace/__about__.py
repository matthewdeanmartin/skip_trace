"""Metadata for skip_trace."""

__all__ = [
    "__credits__",
    "__dependencies__",
    "__description__",
    "__keywords__",
    "__license__",
    "__readme__",
    "__requires_python__",
    "__status__",
    "__title__",
    "__version__",
]

__title__ = "skip-trace"
__version__ = "0.1.1"
__description__ = "Ownership Attribution for Python Packages"
__readme__ = "README.md"
__license__ = "MIT"
__credits__ = [{"name": "Matthew Dean Martin", "email": "matthewdeanmartin@gmail.com"}]
__requires_python__ = ">=3.14"
__status__ = "3 - Alpha"
__dependencies__ = [
    "pydantic>=2.12.0",
    "httpx2[http2]>=2.0,<3",
    "rich>=13.0.0",
    "tldextract>=5.0.0",
    "python-dotenv>=1.0.0",
    "tomli; python_version < '3.11'",
    "python-dotenv",
    "tldextract",
    "beautifulsoup4>=4.12.0",
    "PyGithub>=1.59.0",
    "openai>=1.3.0",
    "sigstore>=1.0.0",
    "python-whois>=0.8.0",
    "whoisit>=1.2",
    "spacy>=3.0.0; python_version < '3.15'",
    "pip>=20",
    "email-validator>=2.0.0",
    "rich-argparse",
    "en-core-web-sm; python_version < '3.15'",
    "PyYAML>=6.0",
]
__keywords__ = [
    "PyPI maintainers",
    "package owners",
    "package provenance",
    "software supply chain",
    "PEP 541",
]
