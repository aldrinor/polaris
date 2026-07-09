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
    # Government institutions (generic ``*.gov`` / ``ed.gov`` via the additive suffix rule below):
    # authoritative primary/regulatory producers, just under the IGO band.
    "government": 0.68,
    # Major think-tanks / research institutes: mid-high (rigorous, but secondary analysis).
    "think_tank": 0.65,
    # Universities / business schools / academic research centres (named hosts + generic ``*.edu``
    # via the suffix rule): rigorous research surface, but a generic ``.edu`` page is secondary.
    "university": 0.62,
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
    # ── I-deepfix-003 (#1374): credible institutions the drb_72 corpus surfaced but the tier sets
    # bury at T6/UNKNOWN (future-of-work / labor / education economics). Each maps to a band so the
    # WEIGHT leg AND the credibility-pass TIER floor recognise it. Registry entries always win over
    # the additive ``*.gov`` / ``*.edu`` suffix rule below (an explicit classification is authoritative).
    "reports.weforum.org": "igo",            # WEF reports host (also matches weforum.org)
    "philadelphiafed.org": "igo",            # Federal Reserve Bank of Philadelphia (central-bank research)
    "commerce.nc.gov": "government",         # NC Dept of Commerce (also matches the *.gov rule)
    "ed.gov": "government",                  # US Dept of Education (also matches the *.gov rule)
    # ── Think-tanks / research institutes / policy + labor organizations ──
    "institute.global": "think_tank",        # Tony Blair Institute for Global Change
    "americanprogress.org": "think_tank",    # Center for American Progress
    "equitablegrowth.org": "think_tank",     # Washington Center for Equitable Growth
    "bipartisanpolicy.org": "think_tank",    # Bipartisan Policy Center
    "jff.org": "think_tank",                 # Jobs for the Future
    "naceweb.org": "think_tank",             # National Association of Colleges and Employers
    "caixabankresearch.com": "think_tank",   # CaixaBank Research
    "sefofuncas.com": "think_tank",          # Funcas (Spanish savings-banks foundation research)
    "ibm.com": "think_tank",                 # IBM corporate research reports
    "microsoft.com": "think_tank",           # Microsoft research reports
    "calaborfed.org": "think_tank",          # California Labor Federation
    "aflcio.org": "think_tank",              # AFL-CIO
    "nationalacademies.org": "think_tank",   # National Academies of Sciences, Engineering, and Medicine
    "vttresearch.com": "think_tank",         # VTT Technical Research Centre of Finland
    "lightcast.io": "think_tank",            # Lightcast labor-market analytics/research
    "socialfinance.org": "think_tank",       # Social Finance
    "educause.edu": "think_tank",            # EDUCAUSE higher-ed IT research association
    "voced.edu.au": "think_tank",            # NCVER VOCEDplus vocational-education research database
    "ideas.repec.org": "think_tank",         # RePEc economics research repository
    # ── Universities / business schools / academic research centres ──
    "hbsp.harvard.edu": "university",        # Harvard Business School Publishing
    "library.hbs.edu": "university",         # Harvard Business School (Baker Library)
    "clp.law.harvard.edu": "university",     # Harvard Law School (Corporate Governance)
    "law.vanderbilt.edu": "university",      # Vanderbilt Law School
    "mitsloan.mit.edu": "university",        # MIT Sloan School of Management
    "business.purdue.edu": "university",     # Purdue University (Daniels School of Business)
    "laborcenter.berkeley.edu": "university",  # UC Berkeley Labor Center
    "mpra.ub.uni-muenchen.de": "university",   # Munich Personal RePEc Archive (LMU Munich)
    "cccco.edu": "university",               # California Community Colleges Chancellor's Office
    "news.gsu.edu": "university",            # Georgia State University news
    # ── News mastheads ──
    "hbr.org": "news_masthead",              # Harvard Business Review
    "thehill.com": "news_masthead",          # The Hill (political news)
    "edsource.org": "news_masthead",         # EdSource (education news)
}

# ── I-deepfix-003 (#1374): additive RULE-BASED recognition ───────────────────────────────────────
# Beyond the enumerated registry, any government (``*.gov`` / ``ed.gov``) or academic (``*.edu``)
# host is recognised as an institution even when it is not individually listed. RAISE-ONLY like every
# registry entry (it only ever lifts a weight/tier, never lowers one) and applied AFTER the registry
# so an explicit classification (e.g. ``brookings.edu`` -> think_tank) always wins over the rule.
# Multi-part government/academic ccTLDs (``*.gov.uk`` / ``*.edu.au``) are NOT matched by the bare
# ``.gov`` / ``.edu`` suffix and are handled by explicit registry entries where they matter.
_RULE_GOV_SUFFIX = ".gov"
_RULE_EDU_SUFFIX = ".edu"

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


def _rule_band(host: str) -> str | None:
    """I-deepfix-003: the additive suffix-rule band for ``host`` (``*.gov`` / ``ed.gov`` ->
    ``government``; ``*.edu`` -> ``university``), else None. RAISE-ONLY like every band; applied
    only AFTER the enumerated registry (an explicit entry always wins). Pure — no kill-switch."""
    if not host:
        return None
    if host == "ed.gov" or host.endswith(_RULE_GOV_SUFFIX):
        return "government"
    if host.endswith(_RULE_EDU_SUFFIX):
        return "university"
    return None


def _resolve_band(url: str) -> str | None:
    """The institutional band KEY for ``url`` — the enumerated registry FIRST (an explicit entry
    always wins), then the additive ``*.gov`` / ``*.edu`` suffix rule. None when the host is not a
    recognised institution. Pure classification: NOT gated by any kill-switch (each caller applies
    its own switch — the WEIGHT leg gates ``institutional_authority_for_url`` on
    ``PG_INSTITUTIONAL_AUTHORITY_WEIGHT``; the TIER-floor leg in ``credibility_pass`` gates on
    ``PG_INSTITUTIONAL_AUTHORITY_TIER``)."""
    host = _host_of(url)
    if not host:
        return None
    band_key = _suffix_match(host, _registry())
    if band_key is not None:
        return band_key
    return _rule_band(host)


def institutional_band_for_url(url: str) -> str | None:
    """I-deepfix-003 (#1374): the institutional band KEY (``igo`` / ``statistical_agency`` /
    ``government`` / ``think_tank`` / ``news_masthead`` / ``university``) for ``url``'s host, or None
    when the host is not a recognised institution.

    This surfaces the band NAME (the WEIGHT accessor ``institutional_authority_for_url`` returns only
    the numeric weight). The credibility-pass TIER-floor leg maps this key to a RAISE-ONLY anchor-
    eligible tier (igo/statistical_agency/government -> T3; think_tank/news_masthead/university -> T3)
    and to the explicit ``authority_note`` label. An env-override registry entry that stores a raw
    float (not a named band) is returned verbatim; the TIER map has no entry for it, so it drives the
    WEIGHT leg only (no tier floor). Pure — the caller applies the kill-switch."""
    return _resolve_band(url)


def institutional_authority_for_url(url: str) -> float | None:
    """The calibrated institutional-authority WEIGHT for ``url`` when its host is a recognized
    institution (enumerated registry OR the ``*.gov`` / ``*.edu`` suffix rule), else None (not an
    institution => no raise). None whenever the kill-switch is OFF.

    A band_key that resolves to no band value (e.g. an override host pointed at an unknown key)
    is treated as "no raise" (None) rather than a wrong/zero weight. The value may also be given
    as a raw float directly in the registry override, in which case it is parsed here."""
    if not institutional_authority_enabled():
        return None
    band_key = _resolve_band(url)
    if band_key is None:
        return None
    bands = _band_values()
    if band_key in bands:
        return bands[band_key]
    # An override may store a raw float directly as the registry value.
    return _clamp01(band_key)
