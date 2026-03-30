"""
Domain configuration loader for polaris graph.

LAW VI: All domain-specific parameters loaded from config files,
not hardcoded in source code. This module loads config/settings/domain_lists.yaml
and provides accessor functions for domain-specific lists.

Usage:
    from src.polaris_graph.config_loader import get_domain_config
    cfg = get_domain_config()
    low_cred = cfg.low_credibility_domains
    blocked = cfg.blocked_domains
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("config/settings/domain_lists.yaml")


@dataclass
class DomainConfig:
    """Loaded domain-specific configuration."""

    low_credibility_domains: frozenset[str] = field(default_factory=frozenset)
    blocked_domains: frozenset[str] = field(default_factory=frozenset)
    tier1_domains: frozenset[str] = field(default_factory=frozenset)
    tier2_domains: frozenset[str] = field(default_factory=frozenset)
    tier3_domains: frozenset[str] = field(default_factory=frozenset)
    low_authority_patterns: Optional[re.Pattern] = None
    synonym_sets: list[list[str]] = field(default_factory=list)
    unit_patterns: Optional[re.Pattern] = None
    clinical_keywords: list[str] = field(default_factory=list)


_cached_config: Optional[DomainConfig] = None


def get_domain_config() -> DomainConfig:
    """Load and cache domain configuration from YAML file.

    Config path: PG_DOMAIN_CONFIG_PATH env var or config/settings/domain_lists.yaml.
    Caches after first load.
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    config_path = Path(os.getenv("PG_DOMAIN_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH)))

    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(
            "[config] Domain config not found at %s — using empty defaults",
            config_path,
        )
        _cached_config = DomainConfig()
        return _cached_config
    except Exception as exc:
        logger.error(
            "[config] Failed to load domain config: %s — using empty defaults",
            str(exc)[:200],
        )
        _cached_config = DomainConfig()
        return _cached_config

    # Build low-authority regex from pattern list
    low_auth_patterns = raw.get("low_authority_patterns", [])
    low_auth_re = None
    if low_auth_patterns:
        try:
            low_auth_re = re.compile("|".join(low_auth_patterns), re.IGNORECASE)
        except re.error as exc:
            logger.warning("[config] Invalid low_authority_patterns regex: %s", exc)

    # Build unit patterns regex
    unit_pat_str = raw.get("unit_patterns", "")
    unit_re = None
    if unit_pat_str:
        try:
            unit_re = re.compile(unit_pat_str, re.IGNORECASE)
        except re.error as exc:
            logger.warning("[config] Invalid unit_patterns regex: %s", exc)

    _cached_config = DomainConfig(
        low_credibility_domains=frozenset(raw.get("low_credibility_domains", [])),
        blocked_domains=frozenset(raw.get("blocked_domains", [])),
        tier1_domains=frozenset(raw.get("tier1_domains", [])),
        tier2_domains=frozenset(raw.get("tier2_domains", [])),
        tier3_domains=frozenset(raw.get("tier3_domains", [])),
        low_authority_patterns=low_auth_re,
        synonym_sets=raw.get("synonym_sets", []),
        unit_patterns=unit_re,
        clinical_keywords=raw.get("clinical_keywords", []),
    )

    logger.info(
        "[config] Loaded domain config from %s: %d low-cred, %d blocked, "
        "%d tier1, %d tier2, %d tier3, %d synonym sets",
        config_path,
        len(_cached_config.low_credibility_domains),
        len(_cached_config.blocked_domains),
        len(_cached_config.tier1_domains),
        len(_cached_config.tier2_domains),
        len(_cached_config.tier3_domains),
        len(_cached_config.synonym_sets),
    )

    return _cached_config


def reload_config() -> DomainConfig:
    """Force reload of domain configuration (clears cache)."""
    global _cached_config
    _cached_config = None
    return get_domain_config()
