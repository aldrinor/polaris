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
    """

    evidence_id: str
    kind: str                      # "numeric" | "qualitative" | "raw"
    subject: str
    predicate: str
    normalized_key: tuple          # conservative grouping key (see _normalized_key_*)
    text: str                      # original snippet / quote for display
    source_url: str = ""
    source_tier: str = ""
    claim_cluster_id: str = ""     # set by cluster_equivalent_claims


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


def _row_text(row: dict[str, Any]) -> str:
    return str(row.get("direct_quote") or row.get("statement") or row.get("text") or "")


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
            out.append(AtomicClaim(
                evidence_id=evid,
                kind="numeric",
                subject=(getattr(nc, "subject", "") or "").strip().lower(),
                predicate=(getattr(nc, "predicate", "") or "").strip().lower(),
                normalized_key=_normalized_key_numeric(nc, evid, ci),
                text=str(getattr(nc, "context_snippet", "") or _row_text(row))[:200],
                source_url=str(getattr(nc, "source_url", "") or row.get("source_url", "")),
                source_tier=str(getattr(nc, "source_tier", "") or row.get("tier", "")),
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
        out.append(AtomicClaim(
            evidence_id=evid,
            kind="qualitative",
            subject=(getattr(qa, "subject", "") or "").strip().lower(),
            predicate=(getattr(qa, "concept_type", "") or "").strip().lower(),
            normalized_key=_normalized_key_qualitative(qa, evid, ci),
            text=str(getattr(qa, "context_snippet", "") or "")[:200],
            source_url=str(getattr(qa, "source_url", "") or ""),
            source_tier=str(getattr(qa, "source_tier", "") or ""),
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
        out.append(AtomicClaim(
            evidence_id=evid,
            kind="raw",
            subject="",
            predicate="",
            normalized_key=("__raw__", evid, _norm_text_key(text)),
            text=text[:200],
            source_url=str(row.get("source_url", "")),
            source_tier=str(row.get("tier", "")),
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
    for rec in detect_contradictions(numeric_claims):
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
