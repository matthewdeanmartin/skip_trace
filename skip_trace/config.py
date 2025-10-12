# skip_trace/config.py

import os
from typing import Any, Dict, Optional, cast

# Use tomllib if available (Python 3.11+), otherwise fall back to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from dotenv import load_dotenv

from .exceptions import ConfigurationError

# Load .env file at module level
load_dotenv()

DEFAULT_CONFIG: Dict[str, Any] = {
    "default_min_score": 0.70,
    "default_fail_under": 0.50,
    "entity_resolution_llm": False,
    "weights": {
        "verified_release_signature": 0.50,
        "repo_org_matches_email_domain": 0.35,
        "codeowners_org_team": 0.25,
        "pypi_maintainer_corporate_domain": 0.20,
        "local_copyright_header_org": 0.25,
        "governance_doc_org": 0.20,
        "llm_ner_claim": 0.20,
        "conflict": -0.15,
    },
    "llm": {
        "provider": "openrouter",
        "model": "mistralai/mistral-7b-instruct",
        "api_key_env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
    },
    "http": {
        "user_agent": "skip-trace/0.1.0",
        "timeout": 30,
    },
    # NEW: GitHub API configuration
    "github": {
        "api_key_env_var": "GITHUB_TOKEN",
    },
    # NEW: Cache configuration
    "cache": {
        "enabled": True,
        "dir": ".skip_trace_cache",
        "ttl_seconds": 604800,  # 7 days
    },
    # NEW: Domains to ignore for WHOIS lookups
    "whois_ignored_domains": [
        "gmail.com", "googlemail.com", "google.com",
        "yahoo.com", "hotmail.com", "outlook.com", "live.com", "msn.com",
        "aol.com", "icloud.com", "me.com", "mac.com",
        "protonmail.com", "pm.me",
        "github.com", "users.noreply.github.com",
        "gitlab.com",
        "sourceforge.net",
        "readthedocs.io",
        "twitter.com", "mastodon.social",
        "linkedin.com",
        "googlegroups.com"
    ],
    "suppressed_tool_orgs": [
        "github",
        "gitlab",
        "bitbucket",
        "sourceforge",
        "readthedocs",
        "codeberg",
        "pypi",  # PSF owns PyPI, but not the packages on it
    ],
}


def find_pyproject_toml(start_dir: str = ".") -> Optional[str]:
    """Finds pyproject.toml by searching upwards from start_dir."""
    path = os.path.abspath(start_dir)
    while True:
        pyproject_path = os.path.join(path, "pyproject.toml")
        if os.path.exists(pyproject_path):
            return pyproject_path
        parent = os.path.dirname(path)
        if parent == path:  # Reached the root
            return None
        path = parent


def load_config(test_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Loads configuration, allowing for test overrides.

    Priority order:
    1. test_config (if provided)
    2. [tool.skip-trace] in pyproject.toml
    3. DEFAULT_CONFIG

    Args:
        test_config: A dictionary to use as the config, for testing.

    Returns:
        The final configuration dictionary.
    """
    if test_config:
        return test_config

    config = DEFAULT_CONFIG.copy()
    pyproject_path = find_pyproject_toml()

    if pyproject_path:
        try:
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomllib.load(f)

            if tool_config := pyproject_data.get("tool", {}).get("skip-trace", {}):
                # Deep merge user config into default
                for key, value in tool_config.items():
                    if isinstance(value, dict) and isinstance(config.get(key), dict):
                        config[key].update(value)
                    else:
                        config[key] = value
        except Exception as e:
            raise ConfigurationError(f"Error reading {pyproject_path}: {e}") from e

    # Load secrets from environment variables
    # LLM API Key
    llm_config = config.get("llm", {})
    api_key_env_var = llm_config.get("api_key_env_var")
    if api_key_env_var:
        api_key = os.getenv(api_key_env_var)
        # Ensure the key is nested correctly in the final config object
        config["llm"]["api_key"] = api_key

    # NEW: GitHub API Key
    github_config = config.get("github", {})
    gh_api_key_env_var = github_config.get("api_key_env_var")
    if gh_api_key_env_var:
        gh_api_key = os.getenv(gh_api_key_env_var)
        config["github"]["api_key"] = gh_api_key

    config["lenient_mode_enabled"] = os.getenv("SKIP_TRACE_INCLUDE_TOOL_ORGS") is not None

    return cast(Dict[str, Any], config)


# Load once at module level to be imported by other parts of the app
CONFIG = load_config()