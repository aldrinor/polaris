"""Clinical source registry — T1/T2/T3 domain classifier.

Per `.codex/slices/slice_002/architecture_proposal.md` §"clinical_source_registry".

Static, deterministic mapping from a URL/domain to a SourceTier:

  T1 — regulatory + Cochrane systematic reviews. Highest evidentiary weight.
       Examples: cochrane.org, fda.gov/drugs, ema.europa.eu, hc-sc.gc.ca,
                 who.int (WHO position), pubmed.ncbi.nlm.nih.gov on
                 systematic-review subset (path-pattern matched).

  T2 — peer-reviewed primary research. RCTs, cohort studies, meta-analyses
       in indexed medical journals.
       Examples: nejm.org, thelancet.com, jamanetwork.com, bmj.com,
                 plos.org, biomedcentral.com, springer.com (medical journals).

  T3 — registries, clinical guidelines, government health agencies.
       Examples: clinicaltrials.gov, nice.org.uk, guidelines.gov,
                 cdc.gov, nih.gov, who.int (general).

Out — anything not matching the above. Returned as None.

Pure-data module: no I/O, no network, no LLM. Suitable for unit-testing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from polaris_graph.clinical_retrieval.evidence_pool import SourceTier


@dataclass(frozen=True)
class _DomainRule:
    """A domain-pattern rule.

    The domain is matched as a *suffix* of the URL's hostname (after
    case-folding), so 'pubmed.ncbi.nlm.nih.gov' matches both
    'pubmed.ncbi.nlm.nih.gov' and any subdomain ending in that suffix.
    The optional path_pattern filters by URL path; if None, any path
    matches.
    """

    domain_suffix: str
    tier: SourceTier
    path_pattern: re.Pattern[str] | None = None


# ---------------------------------------------------------------------------
# T1 — regulatory + systematic reviews
# ---------------------------------------------------------------------------

_T1_RULES: tuple[_DomainRule, ...] = (
    _DomainRule("cochrane.org", SourceTier.T1),
    _DomainRule("cochranelibrary.com", SourceTier.T1),
    _DomainRule("fda.gov", SourceTier.T1, re.compile(r"/(drugs|medical-devices|vaccines|safety)/", re.I)),
    _DomainRule("ema.europa.eu", SourceTier.T1),
    _DomainRule("hc-sc.gc.ca", SourceTier.T1),
    _DomainRule("canada.ca", SourceTier.T1, re.compile(r"/health/|/services/health/", re.I)),
    _DomainRule(
        "pubmed.ncbi.nlm.nih.gov",
        SourceTier.T1,
        # PubMed entries that explicitly carry a systematic-review or
        # meta-analysis filter ?term=..&filter=pubt.systematicreview
        re.compile(r"systematicreview|meta-analysis|cochrane", re.I),
    ),
    _DomainRule("who.int", SourceTier.T1, re.compile(r"/publications/|/teams/|/news-room/fact-sheets/", re.I)),
    _DomainRule("nice.org.uk", SourceTier.T1, re.compile(r"/guidance/", re.I)),
)


# ---------------------------------------------------------------------------
# T2 — peer-reviewed primary research
# ---------------------------------------------------------------------------

_T2_RULES: tuple[_DomainRule, ...] = (
    _DomainRule("nejm.org", SourceTier.T2),
    _DomainRule("thelancet.com", SourceTier.T2),
    _DomainRule("jamanetwork.com", SourceTier.T2),
    _DomainRule("bmj.com", SourceTier.T2),
    _DomainRule("plos.org", SourceTier.T2),
    _DomainRule("biomedcentral.com", SourceTier.T2),
    _DomainRule("link.springer.com", SourceTier.T2),
    _DomainRule("sciencedirect.com", SourceTier.T2, re.compile(r"/science/article/", re.I)),
    _DomainRule("wiley.com", SourceTier.T2, re.compile(r"/doi/|/journal/", re.I)),
    _DomainRule("nature.com", SourceTier.T2, re.compile(r"/articles/", re.I)),
    _DomainRule("oup.com", SourceTier.T2, re.compile(r"/", re.I)),
    _DomainRule("pubmed.ncbi.nlm.nih.gov", SourceTier.T2),  # fallback after T1 systematic-review rule
    _DomainRule("ncbi.nlm.nih.gov", SourceTier.T2, re.compile(r"/pmc/", re.I)),
)


# ---------------------------------------------------------------------------
# T3 — registries, guidelines, government health agencies
# ---------------------------------------------------------------------------

_T3_RULES: tuple[_DomainRule, ...] = (
    _DomainRule("clinicaltrials.gov", SourceTier.T3),
    _DomainRule("who.int", SourceTier.T3, re.compile(r"/ictrp/|/trials/", re.I)),
    _DomainRule("guidelines.gov", SourceTier.T3),
    _DomainRule("cdc.gov", SourceTier.T3, re.compile(r"/", re.I)),
    _DomainRule("nih.gov", SourceTier.T3),
    _DomainRule("phac-aspc.gc.ca", SourceTier.T3),
    _DomainRule("publichealthontario.ca", SourceTier.T3),
)


# Order matters: T1 rules checked first (path-specific), then T2, then T3.
_ALL_RULES: tuple[_DomainRule, ...] = _T1_RULES + _T2_RULES + _T3_RULES


# ---------------------------------------------------------------------------
# Out-of-bounds denylist (always returns None even if domain otherwise matches)
# ---------------------------------------------------------------------------

_DENY_DOMAINS: frozenset[str] = frozenset({
    "wikipedia.org",
    "reddit.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "linkedin.com",
    "medium.com",
    "substack.com",
    "youtube.com",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _hostname(url: str) -> str:
    """Extract a normalized lowercase hostname from a URL.

    Returns "" if the URL is malformed.
    """
    try:
        parsed = urlparse(url.strip())
    except (ValueError, AttributeError):
        return ""
    host = (parsed.hostname or "").lower()
    return host


def _matches_suffix(host: str, suffix: str) -> bool:
    """True if `host` is exactly suffix or ends with .suffix."""
    return host == suffix or host.endswith("." + suffix)


def classify_url(url: str) -> SourceTier | None:
    """Return the SourceTier for a given URL, or None if out of bounds.

    Rules are checked in order: T1 (with path filters) → T2 → T3.
    First match wins. Denylist takes precedence: any URL on a denied
    domain returns None regardless of matching rules.
    """
    host = _hostname(url)
    if not host:
        return None

    for denied in _DENY_DOMAINS:
        if _matches_suffix(host, denied):
            return None

    path_and_query = ""
    try:
        parsed = urlparse(url)
        path_and_query = (parsed.path or "")
        if parsed.query:
            path_and_query = f"{path_and_query}?{parsed.query}"
    except (ValueError, AttributeError):
        path_and_query = ""

    for rule in _ALL_RULES:
        if not _matches_suffix(host, rule.domain_suffix):
            continue
        if rule.path_pattern is None:
            return rule.tier
        if rule.path_pattern.search(path_and_query):
            return rule.tier

    return None


def is_allowed(url: str) -> bool:
    """Convenience: True iff classify_url returns a tier (not None)."""
    return classify_url(url) is not None


def filter_allowed(urls: Iterable[str]) -> list[str]:
    """Filter to only URLs that classify to a tier."""
    return [u for u in urls if is_allowed(u)]


def known_t1_domains() -> tuple[str, ...]:
    """Introspection: list T1 domain suffixes (for diagnostics + UI)."""
    return tuple(rule.domain_suffix for rule in _T1_RULES)


def known_t2_domains() -> tuple[str, ...]:
    return tuple(rule.domain_suffix for rule in _T2_RULES)


def known_t3_domains() -> tuple[str, ...]:
    return tuple(rule.domain_suffix for rule in _T3_RULES)


def deny_domains() -> tuple[str, ...]:
    return tuple(sorted(_DENY_DOMAINS))
