"""I-deepfix-001 (#1344) W1 — positive institutional-authority WEIGHT registry.

A data-driven, LAW-VI POSITIVE institutional-authority weight signal that is ORTHOGONAL to the
T1-T7 clinical-primary tier. The tier classifier is a hardcoded deny-list demoter: credible
NON-journal institutions (WEF/OECD/ILO/IMF/World Bank/UN/WHO, national statistical agencies,
major think-tanks, reputable news mastheads) are absent from every tier set, so they land at
UNKNOWN (0.20) — the SAME low band as an anonymous blog. Because ``weight_mass.cluster_mass =
authority_score`` and the selector fills slots by weight, a mis-low WEIGHT is a de-facto SOFT
FILTER: credible institutions sink and their facets never reach composition.

W1 corrects the WEIGHT (it never filters). A recognized institution's ``authority_score`` is
RAISED to a calibrated mid-high band; the caller applies it as a RAISE-ONLY floor (``max`` with
whatever weight the row already carries), so a freak-low weight can never demote a real
institution and a genuinely-higher computed weight is never lowered. Nothing is dropped, no tier
is changed, and the faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-
grounding) is untouched — this is purely a credibility WEIGHT.

The bands (~0.60-0.75) and the raised UNKNOWN prior (~0.45, applied by the caller) are CALIBRATED
CREDIBILITY WEIGHTS on a continuous authority scale — the honest position of these sources in the
weighting, NOT hard floors imposed to force a coverage number. No source is admitted or excluded
by hitting a band; the band only sets where a source SORTS among slots, and every source still
flows through. A WEF/OECD source and an anonymous blog differ by their honest weight — exactly
WEIGHT-not-FILTER.

Everything is env-overridable (LAW VI):
  * ``PG_INSTITUTIONAL_AUTHORITY_WEIGHT``   — kill-switch (default ON).
  * ``PG_INSTITUTIONAL_AUTHORITY_BANDS``    — JSON {band_key: float} merged over the defaults.
  * ``PG_INSTITUTIONAL_AUTHORITY_REGISTRY`` — JSON {host_suffix: band_key|float} merged over the
                                              default registry (extend/override any institution).
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

# ── Band definitions (calibrated credibility weights on the continuous authority scale) ─────────
# Per the W1 spec these sit in the ~0.60-0.75 institutional range and are RAISE-ONLY floors.
_ENV_BANDS = "PG_INSTITUTIONAL_AUTHORITY_BANDS"
_DEFAULT_BANDS: dict[str, float] = {
    # IGOs + national statistical agencies: highest institutional band (authoritative primary
    # producers of the data other sources cite).
    "igo": 0.72,
    "statistical_agency": 0.72,
    # Major think-tanks / research institutes: mid-high (rigorous, but secondary analysis).
    "think_tank": 0.65,
    # Reputable news mastheads: mid (edited, fact-checked reporting; still secondary).
    "news_masthead": 0.60,
}

# ── The institution registry: host-suffix -> band key ───────────────────────────────────────────
# Suffix match (parent-domain aware, like tier_classifier._domain_matches) so ``www.weforum.org``
# and ``reports.weforum.org`` both match ``weforum.org``. This is a REPRESENTATIVE seed set of the
# credible NON-journal institutions the tier sets omit; the operator extends it via the env JSON
# override (LAW VI). Predatory/fake journals + true junk are NOT here and stay low via the
# authority model's junk_detection Signal C (this registry only ever RAISES, never demotes).
_ENV_REGISTRY = "PG_INSTITUTIONAL_AUTHORITY_REGISTRY"
_DEFAULT_REGISTRY: dict[str, str] = {
    # ── Intergovernmental organizations (IGOs) ──────────────────────────────────────────────────
    "weforum.org": "igo",            # World Economic Forum
    "oecd.org": "igo",
    "oecd-ilibrary.org": "igo",
    "ilo.org": "igo",                # International Labour Organization
    "imf.org": "igo",
    "worldbank.org": "igo",
    "un.org": "igo",
    "who.int": "igo",
    "unesco.org": "igo",
    "unctad.org": "igo",
    "undp.org": "igo",
    "wto.org": "igo",
    "europa.eu": "igo",              # EU institutions
    "ec.europa.eu": "igo",
    "bis.org": "igo",                # Bank for International Settlements
    "imfsg.org": "igo",
    # ── National statistical agencies ───────────────────────────────────────────────────────────
    "bls.gov": "statistical_agency",     # US Bureau of Labor Statistics
    "census.gov": "statistical_agency",  # US Census Bureau
    "bea.gov": "statistical_agency",     # US Bureau of Economic Analysis
    "statcan.gc.ca": "statistical_agency",   # Statistics Canada
    "ons.gov.uk": "statistical_agency",  # UK Office for National Statistics
    "eurostat.ec.europa.eu": "statistical_agency",
    "destatis.de": "statistical_agency",     # Germany
    "insee.fr": "statistical_agency",        # France
    "abs.gov.au": "statistical_agency",      # Australia
    "stats.govt.nz": "statistical_agency",   # New Zealand
    # ── Major think-tanks / research institutes ─────────────────────────────────────────────────
    "brookings.edu": "think_tank",
    "rand.org": "think_tank",
    "kff.org": "think_tank",             # Kaiser Family Foundation
    "pewresearch.org": "think_tank",
    "aspeninstitute.org": "think_tank",
    "urban.org": "think_tank",           # Urban Institute
    "mckinsey.com": "think_tank",        # McKinsey Global Institute reports
    "bcg.com": "think_tank",
    "gartner.com": "think_tank",
    "mercatus.org": "think_tank",
    "nber.org": "think_tank",            # National Bureau of Economic Research
    "iza.org": "think_tank",             # IZA Institute of Labor Economics
    "resolutionfoundation.org": "think_tank",
    "bruegel.org": "think_tank",
    "cfr.org": "think_tank",             # Council on Foreign Relations
    "petersoninstitute.org": "think_tank",
    "piie.com": "think_tank",            # Peterson Institute for International Economics
    "epi.org": "think_tank",             # Economic Policy Institute
    "chathamhouse.org": "think_tank",
    # ── Reputable news mastheads ────────────────────────────────────────────────────────────────
    "nytimes.com": "news_masthead",
    "wsj.com": "news_masthead",
    "ft.com": "news_masthead",
    "economist.com": "news_masthead",
    "reuters.com": "news_masthead",
    "apnews.com": "news_masthead",
    "bbc.co.uk": "news_masthead",
    "bbc.com": "news_masthead",
    "bloomberg.com": "news_masthead",
    "washingtonpost.com": "news_masthead",
    "theguardian.com": "news_masthead",
    "nature.com": "news_masthead",       # news + comment surface (articles keep their journal weight)
    "science.org": "news_masthead",
}

_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def institutional_authority_enabled() -> bool:
    """W1 kill-switch ``PG_INSTITUTIONAL_AUTHORITY_WEIGHT`` (default ON). OFF => the registry is
    inert (``institutional_authority_for_url`` always returns None) => byte-identical legacy
    weighting."""
    return os.environ.get("PG_INSTITUTIONAL_AUTHORITY_WEIGHT", "on").strip().lower() not in _OFF_VALUES


def _clamp01(value: object) -> float | None:
    """Coerce to a float in [0, 1]; None/garbage/out-of-range -> None (fail-soft: a malformed
    override entry is simply ignored, never a wrong-weight)."""
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _band_values() -> dict[str, float]:
    """The band_key -> weight map (defaults merged with the ``PG_INSTITUTIONAL_AUTHORITY_BANDS``
    JSON override; a malformed override entry is ignored, never zeroing a band)."""
    bands = dict(_DEFAULT_BANDS)
    raw = os.environ.get(_ENV_BANDS, "").strip()
    if raw:
        try:
            override = json.loads(raw)
            if isinstance(override, dict):
                for key, val in override.items():
                    clamped = _clamp01(val)
                    if clamped is not None:
                        bands[str(key).strip().lower()] = clamped
        except (ValueError, TypeError):
            pass  # malformed JSON -> defaults (fail-safe: never an empty/zeroed band map)
    return bands


def _registry() -> dict[str, str]:
    """The host-suffix -> band_key registry (defaults merged with the
    ``PG_INSTITUTIONAL_AUTHORITY_REGISTRY`` JSON override). An override VALUE may be a band_key
    string OR a raw float (stored under a synthetic band key so it flows through ``_band_values``)."""
    registry = dict(_DEFAULT_REGISTRY)
    raw = os.environ.get(_ENV_REGISTRY, "").strip()
    if raw:
        try:
            override = json.loads(raw)
            if isinstance(override, dict):
                for host, band in override.items():
                    registry[str(host).strip().lower().lstrip(".")] = str(band).strip().lower()
        except (ValueError, TypeError):
            pass  # malformed JSON -> defaults only (fail-safe)
    return registry


def _host_of(url: str) -> str:
    """The lowercased hostname of ``url`` (empty on a blank/malformed URL)."""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.hostname or "").lower()
    except ValueError:
        return ""


def _suffix_match(host: str, registry: dict[str, str]) -> str | None:
    """Return the band key for ``host`` (or any parent domain) in ``registry``; else None.
    Parent-domain aware: ``reports.weforum.org`` matches the ``weforum.org`` entry."""
    if not host:
        return None
    if host in registry:
        return registry[host]
    parts = host.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in registry:
            return registry[parent]
    return None


def institutional_authority_for_url(url: str) -> float | None:
    """The calibrated institutional-authority WEIGHT for ``url`` when its host is a recognized
    institution, else None (not an institution => no raise). None whenever the kill-switch is OFF.

    A band_key that resolves to no band value (e.g. an override host pointed at an unknown key)
    is treated as "no raise" (None) rather than a wrong/zero weight. The value may also be given
    as a raw float directly in the registry override, in which case it is parsed here."""
    if not institutional_authority_enabled():
        return None
    host = _host_of(url)
    if not host:
        return None
    band_key = _suffix_match(host, _registry())
    if band_key is None:
        return None
    bands = _band_values()
    if band_key in bands:
        return bands[band_key]
    # An override may store a raw float directly as the registry value.
    return _clamp01(band_key)
