"""B9 domain-pack loader.

Loads the per-domain configuration packs in ``config/domain_packs/`` — each
pack owns the domain-specific WEIGHTS and LABELS (report sections, contradiction
predicates, qualitative lexicon pointer, source-tier credibility priors, safety
policy). A pack is NEVER a hard DROP/CAP; the faithfulness engine remains the
only hard gate (CLAUDE.md §-1.3).

POLARIS is GENERAL by default: an unknown / blank / unrecognised domain resolves
to the ``general`` pack — NEVER ``clinical``. The clinical pack is the only one
with ``is_clinical: true``; it is selected only when the clinical domain is
positively detected (``domain_signal.is_clinical_domain``).

LAW VI: no hard-coded pack content — everything is read from YAML. Fail-loud on a
malformed pack (a required key missing), but NEVER fail on an unknown domain
(degrade to general).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from src.polaris_graph.domain.domain_signal import (
    CLINICAL_DOMAIN,
    GENERAL_DOMAIN,
    normalize_domain,
)
from src.polaris_graph.settings import resolve

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DOMAIN_PACKS_DIR = _REPO_ROOT / "config" / "domain_packs"

# Codex iter-2 P2.1: map the canonical-8 scope tokens whose pack file uses a
# different (more descriptive) name onto the pack name, so e.g. the `tech` scope
# token resolves the `technology` pack instead of silently falling back to
# general. Free-text classifier labels (economics/policy/science/...) match pack
# filenames directly and need no alias.
_DOMAIN_PACK_ALIASES: dict[str, str] = {
    "tech": "technology",
    "workforce": "economics",   # labor/workforce questions are economics-shaped
    "due_diligence": "economics",
}

# Required top-level keys every pack must define (schema contract).
_REQUIRED_KEYS = (
    "domain",
    "is_clinical",
    "sections",
    "contradiction_predicates",
    "qualitative_lexicon",
    "source_tier_priors",
    "safety_policy",
)

_pack_cache: dict[str, dict[str, Any]] = {}


def _packs_dir() -> Path:
    """The packs directory, env-overridable for tests (LAW VI)."""
    override = resolve("PG_DOMAIN_PACKS_DIR")
    return Path(override) if override else _DOMAIN_PACKS_DIR


def available_packs() -> list[str]:
    """Sorted list of domain-pack names present on disk (``<name>.yaml``)."""
    d = _packs_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def _validate_pack(name: str, data: Any) -> dict[str, Any]:
    """Fail-loud schema validation of a single pack dict."""
    if not isinstance(data, dict):
        raise RuntimeError(
            f"domain pack {name!r} did not parse to a mapping "
            f"(got {type(data).__name__})."
        )
    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise RuntimeError(
            f"domain pack {name!r} missing required keys: {missing}."
        )
    if not isinstance(data["is_clinical"], bool):
        raise RuntimeError(
            f"domain pack {name!r}: 'is_clinical' must be a bool."
        )
    declared = normalize_domain(str(data.get("domain")))
    # Codex P2.1: the pack's declared domain MUST match its FILENAME so a
    # non-clinical file (e.g. economics.yaml) cannot declare domain: clinical
    # and inherit the clinical is_clinical allowance below.
    if declared != normalize_domain(name):
        raise RuntimeError(
            f"domain pack {name!r}: declared domain {declared!r} does not match "
            f"its filename. Each pack file must declare its own domain."
        )
    # Only the clinical pack may declare is_clinical true (single source of the
    # clinical specialization — prevents a stray non-clinical pack from
    # re-activating clinical logic). Filename-anchored after the check above.
    if data["is_clinical"] and declared != CLINICAL_DOMAIN:
        raise RuntimeError(
            f"domain pack {name!r}: only the clinical pack may set "
            f"is_clinical: true (got domain={data.get('domain')!r})."
        )
    return data


def load_domain_pack(domain: Optional[str]) -> dict[str, Any]:
    """Load the pack for ``domain``; degrade to the ``general`` pack on unknown.

    Never raises on an unknown domain (operator-locked: unknown -> general,
    never clinical, never abort). Raises only when the RESOLVED pack file is
    malformed (fail-loud) or when neither the requested pack NOR the general
    fallback exists on disk (a real config-integrity error).
    """
    name = normalize_domain(domain)
    # Resolve a canonical-8 scope token onto its descriptively-named pack file.
    name = _DOMAIN_PACK_ALIASES.get(name, name)
    if name in _pack_cache:
        return _pack_cache[name]
    d = _packs_dir()
    path = d / f"{name}.yaml"
    if not path.exists():
        # Unknown domain -> general fallback (never clinical).
        if name != GENERAL_DOMAIN:
            return load_domain_pack(GENERAL_DOMAIN)
        raise RuntimeError(
            f"general domain pack not found at {path}. config/domain_packs/"
            f"general.yaml is required (the domain-agnostic default)."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pack = _validate_pack(name, raw)
    _pack_cache[name] = pack
    return pack


def pack_is_clinical(domain: Optional[str]) -> bool:
    """Convenience: does the resolved pack activate clinical rigor?"""
    return bool(load_domain_pack(domain).get("is_clinical", False))


def _reset_pack_cache() -> None:
    """Test hook: clear the loaded-pack cache."""
    _pack_cache.clear()
