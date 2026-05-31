"""SourceClass / AuthorityConfidence enums + AuthoritySignals + AuthorityResult.

Phase 0a (GH #983). Field-agnostic computed source-authority primitives.

These types are the stable schema emitted by the authority model. They are
additive: nothing here references a host name, a suffix, or a platform. All
source knowledge lives in versioned DATA under ``config/authority/*`` and is
read via :mod:`src.polaris_graph.authority.data_loader`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceClass(str, Enum):
    """Field-agnostic credibility class (NOT a clinical tier).

    The clinical T1-T7 view is rendered FROM these primitives by
    ``clinical_view.py``; this enum is domain-general.
    """

    PRIMARY_OFFICIAL = "PRIMARY_OFFICIAL"     # government / regulator / healthcare-regulator
    PRIMARY_SCHOLARLY = "PRIMARY_SCHOLARLY"   # peer-reviewed primary scholarship
    SECONDARY = "SECONDARY"                   # narrative / unreviewed secondary
    COMMENTARY = "COMMENTARY"                 # commentary / marketing / blog
    PRESS_RELEASE = "PRESS_RELEASE"           # press / news release
    UGC = "UGC"                               # user-generated / social / login-walled
    UNKNOWN = "UNKNOWN"                        # could not classify


class AuthorityConfidence(str, Enum):
    """Honest confidence in the computed authority result.

    LOW when the OpenAlex/ROR coverage feeding the signals is thin — the
    contract requires this be honest, never silently HIGH (S4 / brief §5).
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class AuthoritySignals:
    """ADDITIVE optional payload carrying the OpenAlex/ROR fields the authority
    model needs (brief ADDENDUM C1).

    Every field is optional; an absent/partial payload drives the model to
    ``AuthorityConfidence.LOW`` (fail-honest, never fabricate authority).
    Wired end-to-end via the LIVE path (brief ADDENDUM C5):
    ``live_retriever._openalex_enrich`` populates this -> carried at
    ``live_retriever.py:1751`` -> attached to ``ClassificationSignals`` -> read
    by ``score_source_authority``.
    """

    # Signal A — scholarly graph (OpenAlex /works + /sources).
    cited_by_count: int | None = None
    source_id: str = ""                       # OpenAlex source id (venue)
    venue_summary_stats: dict | None = None   # {h_index, 2yr_mean_citedness}
    is_core: bool | None = None               # venue is_core (CWTS)
    is_in_doaj: bool | None = None            # venue listed in DOAJ
    apc_prices: list | None = None            # venue APC price entries
    publication_year: int | None = None
    # Signal B — institutional (OpenAlex ROR).
    ror_id: str = ""                          # first resolved institution ROR id
    institution_type: str = ""                # ROR/OpenAlex institution type
    country_code: str = ""                    # ISO-2 country of the institution


@dataclass
class AuthorityResult:
    """Computed field-agnostic authority result (brief §4 blend output)."""

    authority_score: float                    # [0, 1]
    source_class: SourceClass
    corroboration_count: int                  # independent-host agreement count
    authority_confidence: AuthorityConfidence
    reasons: list[str] = field(default_factory=list)
    # Per-signal sub-scores, surfaced for the shadow harness / audit trail.
    signal_scores: dict = field(default_factory=dict)
