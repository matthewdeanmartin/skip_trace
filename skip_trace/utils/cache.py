# skip_trace/utils/cache.py
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

from ..config import CONFIG

logger = logging.getLogger(__name__)


def get_cache_path(cache_type: str, key: str) -> str:
    """Constructs the full path for a given cache type and key."""
    cache_config = CONFIG.get("cache", {})
    base_dir = cache_config.get("dir", ".skip_trace_cache")
    cache_dir = os.path.join(base_dir, cache_type)
    os.makedirs(cache_dir, exist_ok=True)

    # Sanitize key for filesystem compatibility
    safe_key = "".join(c for c in key if c.isalnum() or c in ("-", "_", "."))
    return os.path.join(cache_dir, f"{safe_key}.json")


def get_cached_data(cache_type: str, key: str) -> Optional[Any]:
    """
    Retrieves data from the cache if it exists and is not expired.

    Args:
        cache_type: The category of the cache (e.g., 'whois').
        key: The unique identifier for the cached item.

    Returns:
        The cached data, or None if not found or expired.
    """
    cache_config = CONFIG.get("cache", {})
    if not cache_config.get("enabled", True):
        return None

    file_path = get_cache_path(cache_type, key)
    ttl = cache_config.get("ttl_seconds", 604800)  # Default to 7 days

    if os.path.exists(file_path):
        mod_time = os.path.getmtime(file_path)
        if (time.time() - mod_time) < ttl:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not read cache file {file_path}: {e}")
                return None
    return None


def set_cached_data(cache_type: str, key: str, data: Any):
    """
    Writes data to the cache.

    Args:
        cache_type: The category of the cache (e.g., 'whois').
        key: The unique identifier for the item to cache.
        data: The JSON-serializable data to store.
    """
    if not data:
        return
    cache_config = CONFIG.get("cache", {})
    if not cache_config.get("enabled", True):
        return

    file_path = get_cache_path(cache_type, key)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except IOError as e:
        logger.error(f"Could not write to cache file {file_path}: {e}")
