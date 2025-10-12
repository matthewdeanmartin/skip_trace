# skip_trace/collectors/whois.py
from __future__ import annotations

import datetime as _dt
import logging
from typing import Dict, List, Optional, Any

from whoisit import domain as rdap_domain

import whois as python_whois

from ..analysis.evidence import generate_evidence_id
from ..exceptions import CollectorError
from ..schemas import EvidenceKind, EvidenceRecord, EvidenceSource
from ..utils.cache import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)


def _normalize_org_name(name: Optional[str]) -> Optional[str]:
    """Cleans up organization names from WHOIS/RDAP data."""
    if not isinstance(name, str):
        return None
    name = name.strip()
    common_suffixes = [
        "LLC", "L.L.C.", "INC", "INCORPORATED", "CORP",
        "CORPORATION", "LTD", "LIMITED", "GMBH", "S.A.", "S.L."
    ]
    up = name.upper()
    for suf in common_suffixes:
        suf_dot = f"{suf}."
        if up.endswith(f" {suf}") or up.endswith(f",{suf}"):
            name = name[:-(len(suf) + 1)].strip().rstrip(",")
            break
        if up.endswith(f" {suf_dot}") or up.endswith(f",{suf_dot}"):
            name = name[:-(len(suf_dot) + 1)].strip().rstrip(",")
            break
    return name.title()


def _rdap_extract(w: Dict[str, Any]) -> Dict[str, Any]:
    """Map RDAP JSON -> normalized fields: org, registrar, creation_date, expiration_date."""
    org = None
    registrar = None
    creation_date = None
    expiration_date = None

    # Entities: find registrant/registrar
    for ent in w.get("entities", []) or []:
        roles = {r.lower() for r in (ent.get("roles") or [])}
        v = ent.get("vcardArray")
        fn = None
        org_v = None
        if isinstance(v, list) and len(v) == 2 and isinstance(v[1], list):
            for item in v[1]:
                # item like ["fn", {}, "text", "Example Corp"]
                if isinstance(item, list) and len(item) >= 4:
                    if item[0] == "fn" and isinstance(item[3], str):
                        fn = item[3]
                    if item[0] == "org" and isinstance(item[3], str):
                        org_v = item[3]
        if "registrant" in roles and not org:
            org = org_v or fn
        if "registrar" in roles and not registrar:
            registrar = org_v or fn

    # Some registries put registrar at top-level
    registrar = registrar or w.get("registrar")

    # Events: registration/expiration
    for ev in w.get("events", []) or []:
        action = str(ev.get("eventAction", "")).lower()
        date = ev.get("eventDate")
        if action in {"registration", "registered"} and not creation_date:
            creation_date = date
        if action in {"expiration", "expiry", "paid-through"} and not expiration_date:
            expiration_date = date

    # ISO8601 -> datetime with tz
    def _parse_dt(x: Any) -> Optional[_dt.datetime]:
        if not x:
            return None
        try:
            # RDAP dates are ISO-8601; fromisoformat handles 'Z' only in 3.11+; fall back simple replace.
            s = str(x).replace("Z", "+00:00")
            return _dt.datetime.fromisoformat(s)
        except Exception:
            return None

    return {
        "org": org,
        "registrar": registrar,
        "creation_date": _parse_dt(creation_date),
        "expiration_date": _parse_dt(expiration_date),
        "source": "RDAP",
    }


def _whois_extract(w: Any) -> Dict[str, Any]:
    """Map python-whois result -> normalized fields."""
    get = (w.get if hasattr(w, "get") else lambda k, d=None: getattr(w, k, d))
    return {
        "org": get("org"),
        "registrar": get("registrar"),
        "creation_date": get("creation_date"),
        "expiration_date": get("expiration_date"),
        "source": "WHOIS",
    }


def _lookup(domain: str) -> Dict[str, Any]:
    """RDAP first, WHOIS fallback. Returns normalized dict or {'error': ...}."""
    # 1) RDAP (HTTP/JSON; far more reliable)
    if rdap_domain is not None:
        try:
            rd = rdap_domain(domain, timeout=10)  # type: ignore[arg-type]
            if isinstance(rd, dict):
                data = _rdap_extract(rd)
                if data.get("org") or data.get("registrar"):
                    return data
        except Exception as e:
            logger.debug("RDAP error for %s: %s", domain, e)

    # 2) WHOIS fallback (may be blocked/rate-limited)
    if python_whois is not None:
        try:
            w = python_whois.whois(domain, timeout=5)
            data = _whois_extract(w)
            if data.get("org") or data.get("registrar"):
                return data
        except Exception as e:
            return {"error": f"WHOIS error: {e}"}

    return {"error": "No RDAP/WHOIS client available or no usable data returned."}


def collect_from_domain(domain: str) -> List[EvidenceRecord]:
    """
    Collect registration ownership signals for a domain using RDAP (preferred) with WHOIS fallback.
    Uses caching to avoid repeated lookups and rate limits.
    """
    logger.info("Checking %s", domain)
    now = _dt.datetime.now(_dt.timezone.utc)
    cache_key_ns = "rdap"  # new namespace; do not collide with legacy "whois"
    locator_base = "rdap://"

    cached = get_cached_data(cache_key_ns, domain)
    if cached:
        logger.debug("Using cached RDAP/WHOIS data for %s", domain)
        info = cached
    else:
        info = _lookup(domain)
        set_cached_data(cache_key_ns, domain, info if info else {"error": "empty"})

    if not info or "error" in info:
        logger.warning("RDAP/WHOIS lookup for %s failed: %s", domain, info.get("error") if info else "unknown")
        return []

    org_name = _normalize_org_name(info.get("org"))
    if not org_name:
        logger.warning(f"No org name for {domain}")
        # Even without org, keep cache; just no evidence emitted.
        return []

    value = {
        "name": org_name,
        "domain": domain,
        "registrar": info.get("registrar"),
        "source": info.get("source", "RDAP"),
        "creation_date": info.get("creation_date"),
        "expiration_date": info.get("expiration_date"),
    }

    # Keep EvidenceSource.WHOIS for backward compatibility if RDAP enum doesn't exist in your schema.
    record = EvidenceRecord(
        id=generate_evidence_id(
            EvidenceSource.WHOIS,  # if you add EvidenceSource.RDAP later, switch based on info["source"]
            EvidenceKind.DOMAIN,
            f"{locator_base}{domain}",
            str(value),
            org_name,
        ),
        source=EvidenceSource.WHOIS,
        locator=f"{locator_base}{domain}",
        kind=EvidenceKind.DOMAIN,
        value=value,
        observed_at=now,
        confidence=0.30,
        notes=f"Domain '{domain}' registration entity normalized to '{org_name}' via {value['source']}.",
    )
    return [record]
