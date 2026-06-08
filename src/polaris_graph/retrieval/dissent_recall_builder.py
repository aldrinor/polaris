"""I-cred-010 (Phase 10, retrieval) — dissent-recall query + stratification builder (pure module).

For a CONTESTED claim (one carrying a Phase-5 ``ContradictionEdge``), BUILD (a) query strings that seek
MORE EVIDENCE FOR THE MINORITY (under-evidenced) side, and (b) an advisory source-type stratification
plan — so a contested claim ends with real evidence on EACH side, not just the majority view.

WHY a side signal is required (Codex #1159 iter-1): a ``ContradictionEdge`` carries only subject /
predicate / SORTED claim_cluster_ids — it does NOT say which side is the minority. So the builder takes
the Phase-6 ``weight_mass`` per cluster and targets the LOWEST-weight cluster's assertion (the
under-evidenced minority). Without that signal, generic "contrary" queries could just reinforce the
majority — exactly the failure this phase exists to prevent.

POSTURE (binding):
  * ADDITIVE / ADVISORY ONLY. This module BUILDS queries + a plan; it makes NO retrieval call. Everything
    a flagged caller fetches with these queries still passes the EXISTING gates — tier classification,
    ``authority_model.score_source_authority``, ``evidence_selector`` (tier quotas + ``PG_RELEVANCE_FLOOR``),
    and ``strict_verify`` (the only binding faithfulness gate). Dissent-recall ADDS breadth for the
    minority side; it NEVER lowers adequacy thresholds, NEVER bypasses authority / relevance scoring,
    NEVER changes ``strict_verify``.
  * DEFAULT-OFF byte-identical: ``PG_SWEEP_DISSENT_RECALL`` (no production caller; the saturation-loop
    wiring is the follow-up I-cred-010b). Empty inputs → empty outputs.
  * PURE: no network in the builder, no input mutation, deterministic; LAW VI; snake_case. An optional
    injected ``query_fn`` lets a flagged caller plug an LLM minority-query generator later (mirrors the
    Phase-2 injected-judge seam); the default builds NO network call.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

_FLAG = "PG_SWEEP_DISSENT_RECALL"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

_ENV_MAX_QUERIES = "PG_DISSENT_QUERIES_MAX"
_ENV_PER_BACKEND = "PG_DISSENT_PER_BACKEND"
_ENV_ASSERTION_CHARS = "PG_DISSENT_ASSERTION_CHARS"
_DEFAULT_MAX_QUERIES = 8
_DEFAULT_PER_BACKEND = 2
_DEFAULT_ASSERTION_CHARS = 120


def dissent_recall_enabled() -> bool:
    """True unless ``PG_SWEEP_DISSENT_RECALL`` is unset/falsey (default OFF => byte-identical)."""
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _coerce_weight_map(weight_by_cluster: Any) -> dict[str, float]:
    """Accept either a ``{claim_cluster_id: weight_mass}`` dict or a list of Phase-6 ClaimWeightMass
    objects, and return a normalized ``{cluster_id: float}`` map."""
    out: dict[str, float] = {}
    if isinstance(weight_by_cluster, dict):
        for key, value in weight_by_cluster.items():
            try:
                out[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return out
    for item in (weight_by_cluster or []):
        cid = str(getattr(item, "claim_cluster_id", "") or "")
        if not cid:
            continue
        try:
            out[cid] = float(getattr(item, "weight_mass", 0.0))
        except (TypeError, ValueError):
            out[cid] = 0.0
    return out


def _minority_queries(assertion: str) -> list[str]:
    """Deterministic, search-friendly queries that seek MORE EVIDENCE FOR the minority assertion."""
    base = (assertion or "").strip()[:_int_env(_ENV_ASSERTION_CHARS, _DEFAULT_ASSERTION_CHARS)]
    if not base:
        return []
    return [
        base,                       # the minority assertion itself
        f"{base} evidence",
        f"{base} studies",
        f"{base} supporting research",
    ]


def build_dissent_queries(
    contradiction_edges: list,
    claims: list,
    weight_by_cluster: Any,
    *,
    max_queries: int | None = None,
    query_fn: Optional[Callable[[str, str], list]] = None,
) -> list[str]:
    """Pure: emit deduped queries that seek evidence FOR the MINORITY side of each contested claim.

    ``weight_by_cluster``: ``{claim_cluster_id: Phase-6 weight_mass}`` (dict) or a list of ClaimWeightMass.
    For each edge, the minority is the cluster with the LOWEST weight_mass (ties -> the
    lexicographically smaller cluster_id; an UNKNOWN weight is treated as 0.0 = under-evidenced); its
    claim TEXT becomes the assertion to seek evidence for. Returns ``[]`` for no edges (byte-identity).
    An injected ``query_fn`` (minority_cluster_id, minority_assertion) -> list[str] plugs an LLM
    generator; a ``query_fn`` that raises falls back to the templates for that edge. NO retrieval call.
    """
    if max_queries is None:
        max_queries = _int_env(_ENV_MAX_QUERIES, _DEFAULT_MAX_QUERIES)
    if max_queries <= 0:
        return []  # a zero/negative cap emits NOTHING (spend/recall control — Codex #1159 diff P1)

    text_by_cluster: dict[str, str] = {}
    sp_by_cluster: dict[str, tuple] = {}
    for claim in (claims or []):
        cid = str(getattr(claim, "claim_cluster_id", "") or "")
        if not cid or cid in text_by_cluster:
            continue
        text_by_cluster[cid] = str(getattr(claim, "text", "") or "").strip()
        sp_by_cluster[cid] = (
            str(getattr(claim, "subject", "") or "").strip(),
            str(getattr(claim, "predicate", "") or "").strip(),
        )

    weight_map = _coerce_weight_map(weight_by_cluster)

    out: list[str] = []
    seen: set[str] = set()
    for edge in (contradiction_edges or []):
        cids = [str(c) for c in (getattr(edge, "claim_cluster_ids", ()) or ())]
        if len(cids) < 2:
            continue
        # Minority = lowest weight_mass; ties + unknown-weight broken deterministically by cluster_id.
        minority_cid = min(cids, key=lambda c: (weight_map.get(c, 0.0), c))
        assertion = text_by_cluster.get(minority_cid, "")
        if not assertion:
            subject, predicate = sp_by_cluster.get(minority_cid, ("", ""))
            assertion = " ".join(part for part in (subject, predicate) if part).strip()
        if query_fn is not None:
            try:
                queries = list(query_fn(minority_cid, assertion) or [])
            except Exception:
                queries = _minority_queries(assertion)
        else:
            queries = _minority_queries(assertion)
        for query in queries:
            normalized = str(query or "").strip()
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                out.append(normalized)
                if len(out) >= max_queries:
                    return out
    return out


def build_source_stratification_plan(
    contested_count: int,
    available_backends: list,
    *,
    per_type_quota: dict | None = None,
) -> dict:
    """Pure: an ADVISORY per-source-type quota hint so dissent retrieval is stratified across web /
    academic / open-access / regulatory — never a hard override that could STARVE the consensus side.

    Empty plan for ``contested_count <= 0`` or no backends (byte-identity). When ``per_type_quota`` is
    given it is used (filtered to positive quotas on listed backends); otherwise a small even per-backend
    floor is emitted so each available source type gets some dissent budget.
    """
    if contested_count <= 0:
        return {}
    backends = [str(b).strip() for b in (available_backends or []) if str(b).strip()]
    if not backends:
        return {}
    if per_type_quota:
        plan = {b: int(per_type_quota.get(b, 0)) for b in backends}
        return {b: q for b, q in plan.items() if q > 0}
    per_backend = max(1, _int_env(_ENV_PER_BACKEND, _DEFAULT_PER_BACKEND))
    return {b: per_backend for b in backends}
