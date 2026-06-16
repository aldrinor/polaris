"""Claim-graph (L4 / §6c-3) — Phase 5 of the credibility-weighted sourcing redesign.

Field-agnostic atomic-claim extraction + normalization, then stance clustering
(equivalent-claim grouping) plus contradiction/refutation edge construction. This
sits BEFORE the weighted aggregation (L5, Phase 6): equivalent claims are grouped
under one ``claim_cluster_id`` so a downstream vote runs over clustered-equivalent
claims, and contradictory claims carry an explicit edge so a conflict can never be
silently picked over.

WHY this is a real BUILD (not a rewire of ``finding_dedup``):
    ``finding_dedup.dedup_by_finding`` clusters by the clinical-pattern-tuned
    ``extract_numeric_claims`` extractor only — it is INERT on non-clinical numerics
    (GDP, emissions, model-accuracy) and on prose-only assertions. This module is
    FIELD-AGNOSTIC: it composes several extractors (clinical-numeric +
    qualitative-assertion) AND falls back to a conservative raw-text claim so EVERY
    evidence row yields at least one atomic claim. Nothing is silently dropped.

TWO INVARIANTS, pointing in OPPOSITE directions (each proven by its own test):
  1. CONSERVATIVE-SINGLETON / under-merge (clinical-lethal if violated). Two atomic
     claims share a ``claim_cluster_id`` ONLY when their conservative normalized key
     is equal AND that key is not the per-claim ``unknown`` sentinel. Any unknown
     subject, any field mismatch, or a raw-text claim keeps the claim a SEPARATE
     singleton cluster. The default on ambiguity is ALWAYS "keep separate" — we
     never over-merge two distinct claims. (Mirrors ``finding_dedup``'s
     ``_finding_key`` discipline: merge only when subject is KNOWN and equal.)
  2. RECALL-FIRST on contradictions / over-detect (a missed refutation is the lethal
     error per §4 L4). The contradiction/refutation edges are sourced from the three
     existing detectors used as edge sources; a real conflict is emitted and NEVER
     silently dropped. The injected NLI judge's fail-open (a judge ERROR skips that
     pair) only affects the LLM-pair path — the deterministic numeric + qualitative
     rule edges this module controls are recall-first and never suppressed.

DETERMINISM: ``claim_cluster_id`` is a stable SHA-1 hash of the conservative
normalized key (per-claim sentinel for ``unknown``), so it is reproducible across
runs and downstream P6 can join on ``(claim_cluster_id, origin_cluster_id)``. NO
uuid / random / time input feeds the id.

DEFAULT-OFF + LAW VI: the whole layer is gated by ``PG_SWEEP_CLAIM_GRAPH`` (default
OFF — flag-off, no caller invokes this and the production output is byte-identical).
The module itself is a pure library of functions: it constructs no client, makes no
network call, and reads no config beyond what the reused detectors already read
(the qualitative lexicon yaml). Every threshold is a named, env-overridable module
constant — no magic numbers. The edge-source detectors are dependency-INJECTED
(real defaults, overridable with fakes in tests), so the module is fully
offline-testable; the semantic NLI judge is injected as a
``(claim_a, claim_b) -> (label, confidence)`` callable exactly like
``semantic_conflict_detector.detect_semantic_conflicts`` expects.

Pure functions; snake_case; explicit imports; no faithfulness gate is touched.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.polaris_graph.retrieval.contradiction_detector import (
    ExtractedNumericClaim,
    detect_contradictions,
    extract_numeric_claims,
)
from src.polaris_graph.retrieval.qualitative_conflict_detector import (
    POLARITY_AMBIGUOUS,
    QualitativeAssertion,
    detect_qualitative_conflicts,
    extract_qualitative_assertions,
)
from src.polaris_graph.retrieval.semantic_conflict_detector import (
    cluster_candidate_rows,
    detect_semantic_conflicts,
    extract_pairs,
)

# ── configuration (LAW VI: every knob env-overridable, no magic numbers) ──────
_FLAG = "PG_SWEEP_CLAIM_GRAPH"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

# Wave-3 master flag (I-arch-002). When ON, the merge key is the spec-driven,
# FAIL-CLOSED ``build_merge_key``; when OFF the legacy positional
# ``_normalized_key_*`` keys run, so the SHA-1 grouping input — and therefore the
# whole claim-graph — is byte-identical to the pre-change tree. Read at CALL time
# (never import-time) so tests can monkeypatch os.environ per-invocation. Inlined
# here (mirrors contradiction_detector._credibility_redesign_enabled) to avoid
# importing the credibility_pass layer and coupling the import graph.
_CRED_REDESIGN_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"

# The subject sentinel the numeric extractor returns when it cannot identify the
# entity nearest the value. Such claims are NEVER mergeable (per-claim singleton).
_UNKNOWN_SUBJECT = "unknown"

# Stable id derivation. SHA-1 of the normalized key text, truncated. A NAMED
# constant (no inline magic) — widening only lowers an already-negligible
# collision chance and never changes which claims are grouped (grouping is by the
# exact key tuple; the id is a label ON the group, not the grouping criterion).
_CLAIM_ID_HASH_LEN = 16
_CLAIM_ID_PREFIX = "clm_"

# Recall-first stance/edge knobs for the semantic (NLI) edge source. Defaults
# mirror the semantic detector's own env defaults so behavior is consistent.
_ENV_NLI_MIN_OVERLAP = "PG_CLAIM_GRAPH_NLI_MIN_OVERLAP"
_ENV_NLI_MAX_ROWS = "PG_CLAIM_GRAPH_NLI_MAX_ROWS"
_ENV_NLI_MAX_PAIRS = "PG_CLAIM_GRAPH_NLI_MAX_PAIRS"
_ENV_NLI_MIN_CONFIDENCE = "PG_CLAIM_GRAPH_NLI_MIN_CONFIDENCE"

_DEFAULT_NLI_MIN_OVERLAP = 2
_DEFAULT_NLI_MAX_ROWS = 200
_DEFAULT_NLI_MAX_PAIRS = 60
_DEFAULT_NLI_MIN_CONFIDENCE = 0.7


def claim_graph_enabled() -> bool:
    """True unless ``PG_SWEEP_CLAIM_GRAPH`` is unset/falsey.

    Default OFF — flag-off is byte-identical: no production caller invokes the
    claim-graph, so the rendered report + manifest are unchanged. This helper is
    the single kill-switch the eventual Gate-B slate flips ON.
    """
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _credibility_redesign_enabled() -> bool:
    """True when ``PG_SWEEP_CREDIBILITY_REDESIGN`` is on. OFF => byte-identical
    (the legacy positional merge keys run, so clustering is unchanged).

    P0-A20 (I-arch-007): UNSET now evaluates ON (default ``"on"``), so the spec-driven
    ``build_merge_key`` clustering — which CONSOLIDATES equivalent claims across sources into
    multi-member baskets — is the coherent default. Pre-fix the empty-string default (a member
    of ``_OFF_VALUES``) left clustering on the legacy positional keys, so baskets stayed
    singletons (the A13 "diagnostic label only" symptom). An explicit ``=0/off/false/no`` still
    returns False -> legacy positional keys -> byte-identical regression path."""
    return os.environ.get(_CRED_REDESIGN_FLAG, "on").strip().lower() not in _OFF_VALUES


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


# ── atomic claim + normalized key ────────────────────────────────────────────


@dataclass
class AtomicClaim:
    """One field-agnostic atomic claim extracted + normalized from one evidence row.

    ``claim_cluster_id`` groups EQUIVALENT claims (assigned by
    ``cluster_equivalent_claims``); it is "" until clustering runs. ``normalized_key``
    is the conservative grouping key (the per-claim sentinel for an ``unknown``
    subject / a raw-text claim — never mergeable). ``kind`` records which extractor
    produced the claim (``numeric`` / ``qualitative`` / ``raw``) for audit.

    Wave-3 (I-arch-002 [5], design §4.2/§7) adds two additive fields that are
    DORMANT on the OFF path (default-value carriers — they do NOT feed
    ``normalized_key`` unless ``PG_SWEEP_CREDIBILITY_REDESIGN`` is ON, and only
    ``normalized_key`` is hashed into ``claim_cluster_id``, so OFF stays
    byte-identical):
      * ``domain`` — the normalized {clinical, nonclinical}|UNKNOWN hint
        ``build_merge_key`` dispatches on (design §4.2). Stamped at extraction from
        the threaded query domain (P3.1 wires the real value; '' until then).
      * ``atom_uid`` — a per-atom-unique id, set at extraction from the threaded
        ``claim_index`` so two distinct UNRESOLVED atoms from one ``evidence_id``
        (the §1 numeric fan-out produces these) cannot collide on the fail-closed
        singleton key (design §4.2 / §9.7, test #23).
    """

    evidence_id: str
    kind: str                      # "numeric" | "qualitative" | "raw"
    subject: str
    predicate: str
    normalized_key: tuple          # conservative grouping key (see _normalized_key_* / build_merge_key)
    text: str                      # original snippet / quote for display
    source_url: str = ""
    source_tier: str = ""
    claim_cluster_id: str = ""     # set by cluster_equivalent_claims
    domain: str = ""               # normalized {clinical, nonclinical}|UNKNOWN dispatch hint (Wave-3)
    atom_uid: str = ""             # per-atom-unique id for the fail-closed singleton key (Wave-3)


@dataclass
class ContradictionEdge:
    """A contradiction / refutation edge between two atomic claims (recall-first).

    ``source`` is one of ``numeric`` / ``qualitative`` / ``semantic`` — which detector
    produced the edge. ``claim_cluster_ids`` is the (sorted) pair of cluster ids the
    two sides belong to. ``severity`` is the producing detector's own severity label.
    The two endpoints are kept as evidence ids so an edge survives serialization.
    """

    source: str
    subject: str
    predicate: str
    evidence_ids: tuple            # the two (or more) endpoint evidence_ids
    claim_cluster_ids: tuple       # sorted pair of claim_cluster_id endpoints
    severity: str = "review"


@dataclass
class ClaimGraph:
    """The full claim-graph: atomic claims + equivalence clusters + contradiction edges."""

    claims: list[AtomicClaim]
    # claim_cluster_id -> the indices (into ``claims``) of its member claims
    clusters: dict[str, list[int]]
    edges: list[ContradictionEdge]
    raw_row_count: int
    distinct_cluster_count: int


def _norm_text_key(text: str) -> str:
    """Whitespace-collapsed, lowercased text — the conservative raw-claim identity.

    A raw-text claim is keyed by its own (evidence_id, normalized text) so it is
    NEVER merged with any other claim (conservative singleton). We still lowercase +
    collapse whitespace so a re-extraction of the SAME row text is stable.
    """
    return " ".join((text or "").lower().split())


def _normalized_key_numeric(
    claim: ExtractedNumericClaim, evidence_id: str, claim_index: int
) -> tuple:
    """Conservative key for a numeric atomic claim.

    Mirrors ``finding_dedup._finding_key``: an ``unknown`` (or empty) subject yields a
    per-CLAIM sentinel (cannot collide — two unknowns never merge). Otherwise the key
    is (subject, predicate, rounded value, unit, dose, arm, endpoint_phrase) — every
    extracted qualifier must match for two claims to share a cluster.
    """
    subject = (getattr(claim, "subject", "") or "").strip().lower()
    if not subject or subject == _UNKNOWN_SUBJECT:
        return ("__numeric_unknown__", evidence_id, claim_index)
    return (
        "numeric",
        subject,
        (getattr(claim, "predicate", "") or "").strip().lower(),
        float(getattr(claim, "value", 0.0) or 0.0),  # EXACT value (Codex iter-1 P1: rounding to 3dp over-merged 14.9001/14.9002 — conservative-singleton requires distinct values stay distinct claims)
        (getattr(claim, "unit", "") or "").strip().lower(),
        (getattr(claim, "dose", "") or "").strip().lower(),
        (getattr(claim, "arm", "") or "").strip().lower(),
        (getattr(claim, "endpoint_phrase", "") or "").strip().lower(),
    )


def _normalized_key_qualitative(
    assertion: QualitativeAssertion, evidence_id: str, claim_index: int
) -> tuple:
    """Conservative key for a qualitative atomic claim.

    An empty/absent subject yields a per-CLAIM sentinel (never mergeable). Otherwise
    the key is (subject, concept_type, object_slot, condition_scope, assertion_status)
    — same full-key discipline the qualitative detector uses for a HARD conflict, so
    two equivalent assertions cluster but any slot/scope/status difference keeps them
    separate. (Note: two assertions with OPPOSITE assertion_status get DIFFERENT keys
    here — they are distinct claims, and the contradiction EDGE, not the cluster,
    links them.)
    """
    subject = (getattr(assertion, "subject", "") or "").strip().lower()
    if not subject:
        return ("__qualitative_unknown__", evidence_id, claim_index)
    return (
        "qualitative",
        subject,
        (getattr(assertion, "concept_type", "") or "").strip().lower(),
        (getattr(assertion, "object_slot", "") or "").strip().lower(),
        (getattr(assertion, "condition_scope", "") or "").strip().lower(),
        (getattr(assertion, "assertion_status", "") or "").strip().lower(),
    )


# ── Wave-3 spec-generated, catalog-covered, FAIL-CLOSED merge key (design §4) ──
#
# THE keystone. ``strict_verify`` is basket-blind (design §0), so the merge key is
# the SOLE defence against over-merge — the clinical-lethal direction. Therefore
# the key is GENERATED from one ordered spec, and the spec is REQUIRED to cover a
# declared dimension catalog, so omission is impossible BY CONSTRUCTION (design
# §4.2), not by a one-way test.
#
# Reached only when ``PG_SWEEP_CREDIBILITY_REDESIGN`` is ON (the extraction sites
# branch on it). OFF keeps the legacy ``_normalized_key_*`` keys -> byte-identical.

# Slot roles (design §4.2). NAMED constants (no inline magic strings).
_ROLE_TAG = "TAG"                  # constant header (e.g. the kind literal)
_ROLE_EXACT = "EXACT"             # compared exactly, never rounded (e.g. value)
_ROLE_DISCRIMINATOR = "DISCRIMINATOR"  # MUST be positively known or -> singleton

# Normalized domain buckets the spec dispatches on (design §4.2).
_DOMAIN_CLINICAL = "clinical"
_DOMAIN_NONCLINICAL = "nonclinical"
_DOMAIN_UNKNOWN = "UNKNOWN"

# Free-form domain hints (from the query router / scope templates) that map to the
# clinical bucket. Anything not positively recognised maps to UNKNOWN -> the
# fail-closed dispatch forces a singleton (NEVER a coarse default spec).
_CLINICAL_DOMAIN_HINTS = frozenset({
    "clinical", "clinical_research", "medical", "medicine", "pharma",
    "pharmaceutical", "drug", "health", "healthcare", "regulatory_clinical",
})
_NONCLINICAL_DOMAIN_HINTS = frozenset({
    "nonclinical", "non_clinical", "non-clinical", "economics", "economic",
    "finance", "financial", "policy", "technology", "tech", "climate",
    "environment", "general", "scientific", "science", "social",
})


@dataclass(frozen=True)
class Slot:
    """One ordered field of the merge key (design §4.2).

    ``value_getter`` reads the raw field off the claim view (a numeric/qualitative
    extractor object carrying ``kind`` / ``domain`` / ``evidence_id`` / ``atom_uid``
    plus its own discriminator fields). ``role`` is TAG / EXACT / DISCRIMINATOR.
    ``unknown_predicate`` returns True when a DISCRIMINATOR value is NOT positively
    known (design §4.3) — a defaulted/derived value is unknown -> singleton.
    """

    name: str
    value_getter: Callable[[Any], Any]
    role: str
    unknown_predicate: Callable[[Any], bool] = lambda v: False


def _get(name: str) -> Callable[[Any], Any]:
    """A value_getter reading ``name`` off the claim view, normalized (strip+lower
    for strings; EXACT slots override this). '' for a missing attribute."""
    def getter(claim: Any) -> Any:
        return (str(getattr(claim, name, "") or "")).strip().lower()
    return getter


def _get_value(claim: Any) -> float:
    """EXACT numeric value getter — preserves the exact float (no rounding, design
    §4.5 / the close-value invariant); 14.9001 stays distinct from 14.9002."""
    return float(getattr(claim, "value", 0.0) or 0.0)


def _unknown_blank(v: Any) -> bool:
    """A string DISCRIMINATOR is unknown on '' / None (design §4.3)."""
    return not (str(v or "").strip())


def _unknown_arm(v: Any) -> bool:
    """``arm`` is unknown unless a placebo/comparator cue fired. The extractor's
    legacy no-cue DEFAULT ``'treatment'`` (kept for OFF byte-identity — Codex
    Slice-B P1) is treated as UNKNOWN per the design's arm lesson (§4.3), as are
    ``''`` and ``None`` (defense-in-depth for any caller). Only a positively
    extracted arm (e.g. ``'comparator_adjacent'``) anchors a merge — so a
    defaulted arm still forces a singleton flag-ON without needing a None default."""
    s = str(v or "").strip().lower()
    return s in ("", "treatment")


def _ambiguous_polarity(v: Any) -> bool:
    """``condition_polarity`` is UNKNOWN (⇒ singleton) ONLY on the extractor's
    ``POLARITY_AMBIGUOUS`` sentinel — a population that is present but whose with/without
    polarity could not be confidently resolved (e.g. an unparsed relative clause "patients
    WHO HAVE renal impairment"). 'with' / 'without' / '' are all POSITIVELY known and compare
    normally; only the ambiguous sentinel fails closed. Codex Slice-B iter-4 P0: the only
    LETHAL error is reading a without/excluded population as a mergeable 'with', so anything
    not provably clean fails to a singleton (over-fragment is SAFE)."""
    return str(v or "").strip().lower() == POLARITY_AMBIGUOUS


def _unknown_subject(v: Any) -> bool:
    """``subject`` is unknown on '' / None OR the extractor's ``_UNKNOWN_SUBJECT``
    sentinel ('unknown' — the contradiction_detector unresolved-subject fallback).
    Codex Slice-B P0: _unknown_blank missed the 'unknown' STRING, so two distinct
    unresolved-subject clinical claims could share a key and over-merge. The legacy
    key guarded exactly this at :232; a defaulted 'unknown' subject must NEVER anchor
    a merge -> forced singleton."""
    s = str(v or "").strip().lower()
    return s in ("", _UNKNOWN_SUBJECT)


# ── §4.1 the dimension catalog: the authoritative set of dimensions where a
#    difference changes WHAT the claim asserts (so a merge across it fabricates a
#    different claim). The single source of truth; test #1(a) forces every entry
#    into the corresponding MERGE_KEY_SPEC as a DISCRIMINATOR slot.
DISCRIMINATING_DIMENSIONS: dict[str, frozenset] = {
    "numeric_clinical": frozenset({
        "subject", "predicate", "value", "unit", "dose", "dose_frequency",
        "arm", "comparator", "effect_measure", "direction", "endpoint_phrase",
        "population", "route_formulation",
    }),
    "numeric_nonclinical": frozenset({
        "subject", "predicate", "value", "unit", "endpoint_phrase",
    }),
    "qualitative_clinical": frozenset({
        "subject", "concept_type", "causal_strength", "warning_severity",
        "object_slot", "condition_scope", "condition_polarity", "assertion_status",
    }),
    "qualitative_nonclinical": frozenset({
        "subject", "concept_type", "object_slot", "condition_scope",
        "condition_polarity", "assertion_status",
    }),
}


# ── §4.2 the spec generates the key. ``MERGE_KEY_SPEC[(kind, domain)]`` is an
#    ORDERED list of Slot. field-in-key == field-in-spec BY CONSTRUCTION (the
#    tuple is emitted FROM the spec). Any (kind, domain) NOT here -> fail-closed
#    singleton (incl. kind=='raw', UNKNOWN domain). 'value' is EXACT; every
#    catalog dimension above appears here as a DISCRIMINATOR.
MERGE_KEY_SPEC: dict[tuple, list] = {
    ("numeric", _DOMAIN_CLINICAL): [
        Slot("kind_tag", lambda c: "numeric", _ROLE_TAG),
        Slot("subject", _get("subject"), _ROLE_DISCRIMINATOR, _unknown_subject),
        Slot("predicate", _get("predicate"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("value", _get_value, _ROLE_EXACT),
        Slot("unit", _get("unit"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("dose", _get("dose"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("dose_frequency", _get("dose_frequency"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("arm", _get("arm"), _ROLE_DISCRIMINATOR, _unknown_arm),
        Slot("comparator", _get("comparator"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("effect_measure", _get("effect_measure"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("direction", _get("direction"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("endpoint_phrase", _get("endpoint_phrase"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("population", _get("population"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("route_formulation", _get("route_formulation"), _ROLE_DISCRIMINATOR, _unknown_blank),
    ],
    ("numeric", _DOMAIN_NONCLINICAL): [
        Slot("kind_tag", lambda c: "numeric", _ROLE_TAG),
        Slot("subject", _get("subject"), _ROLE_DISCRIMINATOR, _unknown_subject),
        Slot("predicate", _get("predicate"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("value", _get_value, _ROLE_EXACT),
        Slot("unit", _get("unit"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("endpoint_phrase", _get("endpoint_phrase"), _ROLE_DISCRIMINATOR, _unknown_blank),
    ],
    ("qualitative", _DOMAIN_CLINICAL): [
        Slot("kind_tag", lambda c: "qualitative", _ROLE_TAG),
        Slot("subject", _get("subject"), _ROLE_DISCRIMINATOR, _unknown_subject),
        Slot("concept_type", _get("concept_type"), _ROLE_DISCRIMINATOR, _unknown_blank),
        # causal_strength / warning_severity are EXACT, NOT DISCRIMINATOR (design
        # §4.3 enumerates every singleton-forcing slot and deliberately OMITS these
        # two; §4.4 requires only the SPLIT — "causes" != "associated", boxed !=
        # routine — which EXACT delivers since the bucket strings differ exactly,
        # exactly as the design's own cataloged-and-EXACT ``value`` dimension). A
        # concept-conditional discriminator ('' is "not applicable" for a non-matching
        # concept_type, not "unknown") would otherwise paralyse EVERY clinical
        # qualitative merge: an ae_causation claim always has warning_severity='' and
        # vice-versa. The five surrounding DISCRIMINATORs (subject/concept_type/
        # object_slot/condition_scope/assertion_status) must all be positively-known-
        # and-equal for any merge, so a '' strength only co-merges genuinely-same
        # claims; a PRESENT cue always carries a non-empty bucket (the lexicon
        # partitions every present cue) so different-strength claims still split.
        Slot("causal_strength", _get("causal_strength"), _ROLE_EXACT),
        Slot("warning_severity", _get("warning_severity"), _ROLE_EXACT),
        Slot("object_slot", _get("object_slot"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("condition_scope", _get("condition_scope"), _ROLE_DISCRIMINATOR, _unknown_blank),
        # condition_polarity is a DISCRIMINATOR whose unknown_predicate fires ONLY on the
        # POLARITY_AMBIGUOUS sentinel (Codex Slice-B iter-4 P0 fail-closed): 'with' ==
        # 'with', 'without' == 'without', '' == '' all compare normally, 'with' != 'without'
        # SPLITS the lethal over-merge ("causes nausea WITH renal" vs "...WITHOUT"), and an
        # AMBIGUOUS polarity (a population present under an unresolved relative clause —
        # "patients WHO HAVE renal") forces a SINGLETON rather than a guessed 'with'. It only
        # adds discrimination when condition_scope is itself EQUAL and non-empty (an
        # unstratified claim is already a singleton via the blank condition_scope
        # DISCRIMINATOR, so the merge never reaches this slot) — so it never over-fragments
        # genuine same-population claims, only fails closed on truly-ambiguous populations.
        Slot("condition_polarity", _get("condition_polarity"), _ROLE_DISCRIMINATOR, _ambiguous_polarity),
        Slot("assertion_status", _get("assertion_status"), _ROLE_DISCRIMINATOR, _unknown_blank),
    ],
    ("qualitative", _DOMAIN_NONCLINICAL): [
        Slot("kind_tag", lambda c: "qualitative", _ROLE_TAG),
        Slot("subject", _get("subject"), _ROLE_DISCRIMINATOR, _unknown_subject),
        Slot("concept_type", _get("concept_type"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("object_slot", _get("object_slot"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("condition_scope", _get("condition_scope"), _ROLE_DISCRIMINATOR, _unknown_blank),
        Slot("condition_polarity", _get("condition_polarity"), _ROLE_DISCRIMINATOR, _ambiguous_polarity),
        Slot("assertion_status", _get("assertion_status"), _ROLE_DISCRIMINATOR, _unknown_blank),
    ],
}


def normalize_domain(hint: str | None) -> str:
    """Map a free-form domain hint to ``{clinical, nonclinical}`` else ``UNKNOWN``.

    UNKNOWN is the fail-closed default (design §4.2): an unrecognised / unset /
    empty hint dispatches to NO spec -> forced singleton, NEVER a coarse default.
    """
    s = (str(hint or "")).strip().lower()
    if not s:
        return _DOMAIN_UNKNOWN
    if s in (_DOMAIN_CLINICAL, _DOMAIN_NONCLINICAL):
        return s
    if s in _CLINICAL_DOMAIN_HINTS:
        return _DOMAIN_CLINICAL
    if s in _NONCLINICAL_DOMAIN_HINTS:
        return _DOMAIN_NONCLINICAL
    return _DOMAIN_UNKNOWN


def _canonicalize(slot: Slot, value: Any) -> Any:
    """Render a slot value into the key tuple. EXACT slots keep the raw value (the
    exact float); all others are already strip+lower normalized by their getter."""
    return value


def build_merge_key(claim: Any) -> tuple:
    """Spec-generated, FAIL-CLOSED merge key for one atomic claim (design §4.2).

    ``claim`` is a claim view carrying ``kind`` / ``domain`` / ``evidence_id`` /
    ``atom_uid`` plus the extractor discriminator fields the slots read.

    FAIL-CLOSED on two axes (the clinical-lethal direction is OVER-merge, so every
    ambiguity resolves to a SINGLETON):
      1. DISPATCH: any ``(kind, domain)`` with no spec — incl. ``kind=='raw'``, a
         None/unnormalizable domain, or any uncatalogued pair — returns a globally
         unique singleton ``('__unresolved__', kind, str(domain), evidence_id,
         atom_uid)``. NEVER a coarse/default spec (silent over-merge).
      2. PER-SLOT: any DISCRIMINATOR not positively known (its ``unknown_predicate``
         is True) returns the SAME singleton. A defaulted/derived value is unknown
         (design §4.3).
    Otherwise the tuple is emitted FROM the spec (field-in-key == field-in-spec).

    P1-A13 (I-arch-007) RESIDUAL: this fail-closed-on-ANY-unknown rule is WHY clinical
    numeric baskets stay singletons (the extractor leaves dose/comparator/effect_measure/
    endpoint_phrase/route_formulation blank, each forcing ``__unresolved__``). Letting a
    BLANK optional consolidate (ABSENT==ABSENT) would close A13 for clinical numerics, but
    that change DIRECTLY violates the Codex-hardened arch002 contracts
    (test_20_unknown_discriminator_forces_singleton_even_with_spec / test_5 / test_23 assert
    a blank ``comparator``/``direction`` MUST singleton) and the defaulted-arm Slice-B P0 — a
    relaxation NOT in this campaign's scope; it needs its own Codex gate. A13 is CLOSED for the
    A20-activated path (multi-member clustering IS the default once the redesign flag is on —
    fully-populated specs, incl. nonclinical numerics, DO consolidate; smoke-proven) and a
    documented residual for the blank-clinical-qualifier case.
    """
    raw_domain = getattr(claim, "domain", "")
    domain = normalize_domain(raw_domain)
    kind = str(getattr(claim, "kind", "") or "")
    evidence_id = str(getattr(claim, "evidence_id", "") or "")
    atom_uid = str(getattr(claim, "atom_uid", "") or "")
    spec = MERGE_KEY_SPEC.get((kind, domain))
    if spec is None:
        # raw / unknown-domain / any uncatalogued (kind, domain) -> forced singleton.
        return ("__unresolved__", kind, str(raw_domain), evidence_id, atom_uid)
    parts: list[Any] = []
    for slot in spec:
        v = slot.value_getter(claim)
        if slot.role == _ROLE_DISCRIMINATOR and slot.unknown_predicate(v):
            return ("__unresolved__", kind, domain, evidence_id, atom_uid)
        parts.append(_canonicalize(slot, v))
    return tuple(parts)


def _merge_key_view(extractor_claim: Any, *, kind: str, evidence_id: str,
                    domain: str, atom_uid: str) -> Any:
    """A lightweight claim view that exposes the extractor object's discriminator
    fields PLUS ``kind`` / ``domain`` / ``evidence_id`` / ``atom_uid`` so a single
    ``build_merge_key(view)`` call reads everything it needs.

    We wrap (not mutate) the extractor object so its real dataclass is untouched;
    ``__getattr__`` delegates any field the spec slots request to the underlying
    extractor object (test #21 spec<->extractor binding holds against the real
    dataclass fields).
    """
    return _MergeKeyView(extractor_claim, kind, evidence_id, domain, atom_uid)


class _MergeKeyView:
    """Read-only view over an extractor claim for ``build_merge_key`` (see above)."""

    __slots__ = ("_inner", "kind", "evidence_id", "domain", "atom_uid")

    def __init__(self, inner: Any, kind: str, evidence_id: str,
                 domain: str, atom_uid: str) -> None:
        self._inner = inner
        self.kind = kind
        self.evidence_id = evidence_id
        self.domain = domain
        self.atom_uid = atom_uid

    def __getattr__(self, name: str) -> Any:
        # only reached for names NOT in __slots__ (i.e. the extractor's own fields)
        return getattr(self._inner, name, "")


def _row_text(row: dict[str, Any]) -> str:
    return str(row.get("direct_quote") or row.get("statement") or row.get("text") or "")


def _atom_uid(kind: str, evidence_id: str, claim_index: int) -> str:
    """Per-atom-unique id (design §4.2 / §9.7, test #23): ``kind:evidence_id:index``.

    Two distinct atoms from one ``evidence_id`` (the numeric fan-out produces these)
    get DIFFERENT indices, so the fail-closed singleton key cannot collide them.
    Deterministic (no uuid/random/time) so the cluster id stays reproducible.
    """
    return f"{kind}:{evidence_id}:{claim_index}"


def extract_atomic_claims(
    rows: list[dict[str, Any]],
    *,
    domain: str | None = None,
    numeric_extractor: Callable[..., list[ExtractedNumericClaim]] = extract_numeric_claims,
    qualitative_extractor: Callable[..., list[QualitativeAssertion]] = extract_qualitative_assertions,
) -> list[AtomicClaim]:
    """Field-agnostic atomic-claim extraction over evidence ``rows``.

    Composes the injected numeric + qualitative extractors and ALWAYS falls back to a
    conservative raw-text claim, so EVERY non-empty row yields >=1 atomic claim and
    nothing is silently dropped. The extractors are dependency-injected (real
    defaults; tests pass fakes / fixtures) — keeping this function pure + offline.

    Args:
        rows: evidence rows (each a dict with at least ``evidence_id`` and a text
            field — ``direct_quote`` / ``statement`` / ``text``).
        domain: optional domain hint forwarded to the numeric extractor (it routes to
            a broader predicate set for non-clinical queries).
        numeric_extractor: ``(rows, domain) -> list[ExtractedNumericClaim]``.
        qualitative_extractor: ``(rows, domain) -> list[QualitativeAssertion]``.

    Returns:
        ``list[AtomicClaim]`` with ``claim_cluster_id`` still "" (assigned by
        ``cluster_equivalent_claims``). A row that yields a structured claim does NOT
        additionally yield a raw claim (avoid double-counting); a row that yields NO
        structured claim yields exactly one raw singleton claim.
    """
    rows = list(rows or [])
    out: list[AtomicClaim] = []
    structured_evidence_ids: set[str] = set()
    # Read the master flag ONCE per call (never import-time). OFF -> the legacy
    # positional _normalized_key_* keys run, so the SHA-1 grouping input — and thus
    # the whole graph — is byte-identical to the pre-change tree. ON -> the
    # spec-driven, fail-closed build_merge_key keys run (design §4).
    redesign_on = _credibility_redesign_enabled()
    # Normalized domain stamped on each claim (design §4.2 / P3.1). '' on the OFF
    # path is inert (never read); on the ON path normalize_domain maps it.
    claim_domain = domain or ""

    # 1. numeric extractor (per-row so we can attribute claim ids deterministically).
    for row in rows:
        evid = str(row.get("evidence_id", ""))
        try:
            numeric_claims = numeric_extractor([row], domain) if domain is not None \
                else numeric_extractor([row])
        except TypeError:
            # an injected extractor that does not accept a domain kwarg
            numeric_claims = numeric_extractor([row])
        for ci, nc in enumerate(numeric_claims):
            structured_evidence_ids.add(evid)
            uid = _atom_uid("numeric", evid, ci)
            if redesign_on:
                nkey = build_merge_key(_merge_key_view(
                    nc, kind="numeric", evidence_id=evid,
                    domain=claim_domain, atom_uid=uid))
            else:
                nkey = _normalized_key_numeric(nc, evid, ci)
            out.append(AtomicClaim(
                evidence_id=evid,
                kind="numeric",
                subject=(getattr(nc, "subject", "") or "").strip().lower(),
                predicate=(getattr(nc, "predicate", "") or "").strip().lower(),
                normalized_key=nkey,
                text=str(getattr(nc, "context_snippet", "") or _row_text(row))[:200],
                source_url=str(getattr(nc, "source_url", "") or row.get("source_url", "")),
                source_tier=str(getattr(nc, "source_tier", "") or row.get("tier", "")),
                domain=claim_domain,
                atom_uid=uid,
            ))

    # 2. qualitative extractor (whole-corpus; one row may yield several assertions).
    try:
        qual_assertions = qualitative_extractor(rows, domain) if domain is not None \
            else qualitative_extractor(rows)
    except TypeError:
        qual_assertions = qualitative_extractor(rows)
    # group qualitative assertions by evidence_id so the per-claim sentinel index is
    # stable + distinct per row.
    qual_index_by_evid: dict[str, int] = {}
    for qa in qual_assertions:
        evid = str(getattr(qa, "evidence_id", "") or "")
        ci = qual_index_by_evid.get(evid, 0)
        qual_index_by_evid[evid] = ci + 1
        structured_evidence_ids.add(evid)
        uid = _atom_uid("qualitative", evid, ci)
        if redesign_on:
            nkey = build_merge_key(_merge_key_view(
                qa, kind="qualitative", evidence_id=evid,
                domain=claim_domain, atom_uid=uid))
        else:
            nkey = _normalized_key_qualitative(qa, evid, ci)
        out.append(AtomicClaim(
            evidence_id=evid,
            kind="qualitative",
            subject=(getattr(qa, "subject", "") or "").strip().lower(),
            predicate=(getattr(qa, "concept_type", "") or "").strip().lower(),
            normalized_key=nkey,
            text=str(getattr(qa, "context_snippet", "") or "")[:200],
            source_url=str(getattr(qa, "source_url", "") or ""),
            source_tier=str(getattr(qa, "source_tier", "") or ""),
            domain=claim_domain,
            atom_uid=uid,
        ))

    # 3. conservative raw fallback: any row that produced NO structured claim yields
    #    exactly one raw singleton, keyed by (evidence_id, normalized text), so it is
    #    NEVER merged and NEVER dropped. Field-agnostic coverage guarantee.
    for row in rows:
        evid = str(row.get("evidence_id", ""))
        text = _row_text(row)
        if not text.strip():
            continue
        if evid in structured_evidence_ids:
            continue
        norm_text = _norm_text_key(text)
        # ATOM_UID-RAW-SITE (design §9.7): the raw site has no threaded claim_index.
        # Retain the normalized text in atom_uid so even on a duplicate/empty
        # evidence_id two raw atoms cannot collide on the fail-closed singleton key
        # (build_merge_key returns a singleton for kind=='raw'). On the OFF path the
        # key is byte-identical to today's ("__raw__", evid, norm_text).
        if redesign_on:
            uid = f"raw:{evid}:{norm_text}"
            nkey = build_merge_key(_merge_key_view(
                row, kind="raw", evidence_id=evid,
                domain=claim_domain, atom_uid=uid))
        else:
            uid = ""
            nkey = ("__raw__", evid, norm_text)
        out.append(AtomicClaim(
            evidence_id=evid,
            kind="raw",
            subject="",
            predicate="",
            normalized_key=nkey,
            text=text[:200],
            source_url=str(row.get("source_url", "")),
            source_tier=str(row.get("tier", "")),
            domain=claim_domain,
            atom_uid=uid,
        ))

    return out


def _claim_cluster_id(normalized_key: tuple) -> str:
    """Deterministic, stable id for an equivalence cluster.

    SHA-1 over a canonical string rendering of the normalized key, truncated +
    prefixed. Deterministic (no uuid/random/time), so the SAME key always yields the
    SAME id across runs — required for the downstream P6 join on
    ``(claim_cluster_id, origin_cluster_id)``.
    """
    canonical = repr(tuple(normalized_key))
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:_CLAIM_ID_HASH_LEN]
    return f"{_CLAIM_ID_PREFIX}{digest}"


def cluster_equivalent_claims(
    claims: list[AtomicClaim],
) -> dict[str, list[int]]:
    """Group EQUIVALENT atomic claims under one stable ``claim_cluster_id``.

    Conservative-singleton safety: claims share a cluster ONLY when their
    ``normalized_key`` is EQUAL. Per-claim sentinel keys (unknown subject / raw text)
    are unique by construction, so such claims are always singletons — two distinct
    claims NEVER over-merge. MUTATES each claim's ``claim_cluster_id`` in place (the
    claims are this module's own objects, never the caller's evidence rows).

    Returns ``{claim_cluster_id: [member indices into ``claims``]}``.
    """
    clusters: dict[str, list[int]] = {}
    for idx, claim in enumerate(claims):
        cid = _claim_cluster_id(claim.normalized_key)
        claim.claim_cluster_id = cid
        clusters.setdefault(cid, []).append(idx)
    return clusters


# ── contradiction / refutation edges (recall-first) ───────────────────────────


def _cluster_id_for_evidence(claims: list[AtomicClaim]) -> dict[str, set[str]]:
    """Map evidence_id -> the set of claim_cluster_ids its claims belong to (fallback only)."""
    out: dict[str, set[str]] = {}
    for claim in claims:
        out.setdefault(claim.evidence_id, set()).add(claim.claim_cluster_id)
    return out


def _cluster_ids_by_subject(claims: list[AtomicClaim]) -> dict[tuple, set[str]]:
    """Map ``(evidence_id, subject)`` -> claim_cluster_ids.

    Used to attach a contradiction edge ONLY to the clusters that share the edge's
    SUBJECT on an endpoint row — so when a row hosts several distinct atomic claims, a
    contradiction about one subject does NOT pull in the unrelated clusters of a
    DIFFERENT subject on the same row (Codex iter-1 P2). Subject is normalized
    (strip+lower) to match both the edge record's subject and the AtomicClaim subject.
    """
    out: dict[tuple, set[str]] = {}
    for claim in claims:
        sig = (claim.evidence_id, (claim.subject or "").strip().lower())
        out.setdefault(sig, set()).add(claim.claim_cluster_id)
    return out


def _edge_cluster_pair(
    subject: str,
    evidence_ids: tuple,
    cluster_by_subject: dict[tuple, set[str]],
    cluster_by_evid: dict[str, set[str]],
) -> tuple:
    """Sorted claim_cluster_ids of the SUBJECT-matching claims on the endpoint rows.

    For each endpoint evidence row, attach the clusters whose claims share the edge's
    subject. If an endpoint has no subject-matching claim (e.g. an empty-subject
    semantic edge), fall back to that row's clusters so the edge is never lost
    (recall-first) — coarser only in that rare case, never the common multi-subject-row
    contamination (Codex iter-1 P2).
    """
    subj = (subject or "").strip().lower()
    ids: set[str] = set()
    for evid in evidence_ids:
        matched = cluster_by_subject.get((str(evid), subj), set())
        ids.update(matched if matched else cluster_by_evid.get(str(evid), set()))
    return tuple(sorted(ids))


def build_contradiction_edges(
    rows: list[dict[str, Any]],
    claims: list[AtomicClaim],
    *,
    domain: str | None = None,
    nli_judge: Optional[Callable[[str, str], tuple]] = None,
    numeric_extractor: Callable[..., list[ExtractedNumericClaim]] = extract_numeric_claims,
    qualitative_extractor: Callable[..., list[QualitativeAssertion]] = extract_qualitative_assertions,
) -> list[ContradictionEdge]:
    """Build contradiction / refutation edges over the atomic claims — RECALL-FIRST.

    Reuses the three existing detectors as edge sources (used, not re-implemented):
      * numeric: ``detect_contradictions`` over ``extract_numeric_claims`` — a
        >threshold numeric disagreement on the same (subject, predicate, unit, dose).
      * qualitative: ``detect_qualitative_conflicts`` over
        ``extract_qualitative_assertions`` — present-vs-absent assertion-status
        conflicts + review flags (the no-number lethal-miss class).
      * semantic (OPTIONAL): only when an ``nli_judge`` is injected. Clusters rows by
        shared salient words, judges pairs, keeps ``contradict`` pairs. The judge is
        ``(claim_a, claim_b) -> (label, confidence)``; its per-pair fail-open (a judge
        ERROR skips THAT pair) is the only place an edge can be missed, and it is
        confined to the LLM path — the deterministic numeric + qualitative edges are
        never suppressed. NO judge is constructed here: off-mode / no-judge ⇒ no
        network, no spend (the production judge is wired by the caller, not this
        pure library).

    Recall-first: we OVER-detect (coarse review flags included) and NEVER silently
    drop a real conflict. Endpoints are attached to their ``claim_cluster_id`` via the
    already-clustered ``claims`` so a downstream vote (P6) sees the conflict.

    Returns ``list[ContradictionEdge]``, de-duplicated by
    (source, subject, predicate, sorted endpoint evidence_ids).
    """
    rows = list(rows or [])
    cluster_by_evid = _cluster_id_for_evidence(claims)
    cluster_by_subject = _cluster_ids_by_subject(claims)
    edges: list[ContradictionEdge] = []
    seen: set[tuple] = set()

    def _add(source: str, subject: str, predicate: str,
             evidence_ids: list, severity: str) -> None:
        evid_tuple = tuple(sorted(str(e) for e in evidence_ids if str(e)))
        if len(evid_tuple) < 2:
            return  # an edge needs two distinct endpoints
        dedup_key = (source, subject, predicate, evid_tuple)
        if dedup_key in seen:
            return
        seen.add(dedup_key)
        edges.append(ContradictionEdge(
            source=source,
            subject=subject,
            predicate=predicate,
            evidence_ids=evid_tuple,
            claim_cluster_ids=_edge_cluster_pair(
                subject, evid_tuple, cluster_by_subject, cluster_by_evid
            ),
            severity=str(severity or "review"),
        ))

    # 1. numeric contradictions (deterministic, recall-first within its threshold).
    try:
        numeric_claims = numeric_extractor(rows, domain) if domain is not None \
            else numeric_extractor(rows)
    except TypeError:
        numeric_claims = numeric_extractor(rows)
    # B9: thread the deterministic is_clinical signal so a non-clinical numeric
    # gap with unconfirmed scope is labeled possible_metric_mismatch, not a hard
    # contradiction. Clinical (default True) is byte-identical.
    from src.polaris_graph.domain.domain_signal import is_clinical_domain
    _is_clinical_cg = is_clinical_domain(domain, rows)
    for rec in detect_contradictions(numeric_claims, is_clinical=_is_clinical_cg):
        _add(
            "numeric",
            getattr(rec, "subject", ""),
            getattr(rec, "predicate", ""),
            [getattr(c, "evidence_id", "") for c in getattr(rec, "claims", [])],
            getattr(rec, "severity", "review"),
        )

    # 2. qualitative conflicts (present-vs-absent + review flags, never silent-drop).
    try:
        qual_assertions = qualitative_extractor(rows, domain) if domain is not None \
            else qualitative_extractor(rows)
    except TypeError:
        qual_assertions = qualitative_extractor(rows)
    for rec in detect_qualitative_conflicts(qual_assertions):
        _add(
            "qualitative",
            getattr(rec, "subject", ""),
            getattr(rec, "predicate", ""),
            [c.get("evidence_id", "") for c in getattr(rec, "claims", [])],
            getattr(rec, "severity", "review"),
        )

    # 3. semantic NLI conflicts — ONLY when a judge is injected (no judge ⇒ no spend).
    if nli_judge is not None:
        clusters = cluster_candidate_rows(
            rows,
            min_overlap=_int_env(_ENV_NLI_MIN_OVERLAP, _DEFAULT_NLI_MIN_OVERLAP),
            max_rows=_int_env(_ENV_NLI_MAX_ROWS, _DEFAULT_NLI_MAX_ROWS),
        )
        if clusters:
            pairs = extract_pairs(
                clusters,
                max_pairs=_int_env(_ENV_NLI_MAX_PAIRS, _DEFAULT_NLI_MAX_PAIRS),
            )
            sem_records = detect_semantic_conflicts(
                pairs,
                nli_judge,
                min_confidence=_float_env(
                    _ENV_NLI_MIN_CONFIDENCE, _DEFAULT_NLI_MIN_CONFIDENCE
                ),
            )
            for rec in sem_records:
                _add(
                    "semantic",
                    getattr(rec, "subject", ""),
                    getattr(rec, "predicate", ""),
                    [c.get("evidence_id", "") for c in getattr(rec, "claims", [])],
                    getattr(rec, "severity", "review"),
                )

    return edges


def build_claim_graph(
    rows: list[dict[str, Any]],
    *,
    domain: str | None = None,
    nli_judge: Optional[Callable[[str, str], tuple]] = None,
    numeric_extractor: Callable[..., list[ExtractedNumericClaim]] = extract_numeric_claims,
    qualitative_extractor: Callable[..., list[QualitativeAssertion]] = extract_qualitative_assertions,
) -> ClaimGraph:
    """End-to-end: extract atomic claims -> cluster equivalents -> build edges.

    Pure orchestration over the building blocks above. The edge-source detectors +
    the optional NLI judge are dependency-injected so the whole graph builds offline
    with fakes / fixtures. No flag check here — the caller gates the invocation via
    ``claim_graph_enabled()`` (default-OFF), keeping this a pure library function.
    """
    claims = extract_atomic_claims(
        rows,
        domain=domain,
        numeric_extractor=numeric_extractor,
        qualitative_extractor=qualitative_extractor,
    )
    clusters = cluster_equivalent_claims(claims)
    edges = build_contradiction_edges(
        rows,
        claims,
        domain=domain,
        nli_judge=nli_judge,
        numeric_extractor=numeric_extractor,
        qualitative_extractor=qualitative_extractor,
    )
    return ClaimGraph(
        claims=claims,
        clusters=clusters,
        edges=edges,
        raw_row_count=len(list(rows or [])),
        distinct_cluster_count=len(clusters),
    )
