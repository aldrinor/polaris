"""ENTRY: score_source_authority — blends the five field-agnostic signals.

Phase 0a (GH #983). Data-driven (LAW VI). ZERO host names in code.

    authority_score = clamp01( sum_signal(w * score) ) * junk_cap * corroboration

`source_class` comes from junk detection (if any junk fired) else from the
institutional signal; falls back to a scholarly/secondary class from the
structural cues so it is never spuriously UNKNOWN for a real source.

`authority_confidence` = MIN over the per-signal confidences that fired
(honest: a thin-OpenAlex source lands LOW, never silently HIGH — brief §5).
"""
from __future__ import annotations

import datetime
from typing import Any
from urllib.parse import urlparse

from src.polaris_graph.authority import citation_graph, corroboration, institutional, recency
from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.authority.junk_detection import detect_junk
from src.polaris_graph.authority.source_class import (
    AuthorityConfidence,
    AuthorityResult,
    AuthoritySignals,
    SourceClass,
)

_CONFIDENCE_RANK = {
    AuthorityConfidence.LOW: 0,
    AuthorityConfidence.MEDIUM: 1,
    AuthorityConfidence.HIGH: 2,
}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _host_of(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.hostname or "").lower()
    except ValueError:
        return ""


def _path_of(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.path or "").lower()
    except ValueError:
        return ""


def _min_confidence(confidences: list[AuthorityConfidence]) -> AuthorityConfidence:
    if not confidences:
        return AuthorityConfidence.LOW
    return min(confidences, key=lambda c: _CONFIDENCE_RANK[c])


def _structural_secondary_class(
    pub_type: str, src_type: str, view_data: dict
) -> SourceClass:
    """Fallback source_class from OpenAlex structural cues (no host)."""
    pub = (pub_type or "").lower()
    src = (src_type or "").lower()
    scholarly = view_data["scholarly_primary_types"]
    if pub in scholarly["publication_type"] and src in scholarly["source_type"]:
        return SourceClass.PRIMARY_SCHOLARLY
    repo = view_data["preprint_repo"]
    if pub in repo["publication_type"] or src in repo["source_type"]:
        return SourceClass.SECONDARY
    if pub in view_data["secondary_doc_types"]:
        return SourceClass.SECONDARY
    return SourceClass.UNKNOWN


def score_source_authority(
    signals: Any, *, corpus_ctx: dict | None = None
) -> AuthorityResult:
    """Compute the field-agnostic AuthorityResult for one source.

    `signals` is a `ClassificationSignals` (carries url/title/content + the
    additive `authority` AuthoritySignals payload). `corpus_ctx` (optional)
    may carry {"corroborating_hosts": [...]} for Signal D; absent in 0a single-
    source scoring (defaults to count=1).
    """
    data = load_authority_data()
    blend = data["blend_weights"]
    view_data = data["clinical_view"]

    payload: AuthoritySignals = getattr(signals, "authority", None) or AuthoritySignals()
    url = getattr(signals, "url", "") or ""
    host = _host_of(url)
    url_path = _path_of(url)
    body = getattr(signals, "fetched_body", "") or ""   # optional structural body
    jsonld = getattr(signals, "structured_jsonld", "") or ""
    claim_vendor = getattr(signals, "claim_vendor_token", "") or ""

    reasons: list[str] = []
    confidences: list[AuthorityConfidence] = []
    signal_scores: dict[str, float] = {}

    # ── Signal A — scholarly graph ───────────────────────────────────────
    a = citation_graph.compute_signal_a(payload, data["scholarly_weights"])
    signal_scores["signal_a_scholarly"] = a.score
    reasons.extend(a.reasons)
    if a.fired:
        confidences.append(a.confidence)

    # ── Signal B — institutional ─────────────────────────────────────────
    b = institutional.compute_signal_b(
        host, payload, jsonld + "\n" + body,
        data["ror_type_class_map"], data["psl_gov_suffixes"],
    )
    signal_scores["signal_b_institutional"] = b.score
    reasons.extend(b.reasons)
    if b.fired:
        confidences.append(b.confidence)

    # ── Signal C — structural junk ───────────────────────────────────────
    junk = detect_junk(
        host=host, url_path=url_path, body=body, jsonld=jsonld,
        claim_vendor_token=claim_vendor, junk_data=data["junk_patterns"],
    )
    # A clean (non-junk) source contributes a neutral-positive structural score.
    signal_scores["signal_c_structural"] = 0.0 if junk.fired else 1.0
    if junk.fired:
        reasons.extend(junk.reasons)
        confidences.append(junk.confidence)

    # ── Signal E — recency ───────────────────────────────────────────────
    current_year = datetime.datetime.now(datetime.timezone.utc).year
    e = recency.compute_signal_e(
        payload.publication_year, current_year, data["recency_profile"],
    )
    signal_scores["signal_e_recency"] = e.score
    reasons.extend(e.reasons)

    # ── Signal D — corroboration ─────────────────────────────────────────
    corroborating_hosts: list[str] = []
    if corpus_ctx:
        corroborating_hosts = list(corpus_ctx.get("corroborating_hosts", []))
    count = (
        corroboration.count_independent_hosts(corroborating_hosts, data["psl_gov_suffixes"])
        if corroborating_hosts
        else 1
    )
    d = corroboration.compute_signal_d(count, blend)
    signal_scores["signal_d_corroboration"] = d.score
    reasons.extend(d.reasons)

    # ── Blend A/B/C/E ────────────────────────────────────────────────────
    sw = blend["signal_weights"]
    base = (
        sw["signal_a_scholarly"] * a.score
        + sw["signal_b_institutional"] * b.score
        + sw["signal_c_structural"] * signal_scores["signal_c_structural"]
        + sw["signal_e_recency"] * e.score
    )
    # Corroboration bounded multiplier.
    floor = blend["corroboration_floor"]
    base *= floor + (1.0 - floor) * d.score
    score = _clamp01(base)

    # Junk ceiling overrides downward.
    if junk.fired:
        score = min(score, blend["JUNK_CEIL"])

    # ── source_class resolution ──────────────────────────────────────────
    if junk.fired:
        source_class = junk.source_class
    elif b.fired and b.source_class != SourceClass.UNKNOWN:
        source_class = b.source_class
    else:
        source_class = _structural_secondary_class(
            getattr(signals, "openalex_publication_type", "") or "",
            getattr(signals, "openalex_source_type", "") or "",
            view_data,
        )

    # ── confidence = MIN over fired signals ──────────────────────────────
    confidence = _min_confidence(confidences)
    if not confidences:
        confidence = AuthorityConfidence.LOW
        reasons.append("thin OpenAlex coverage: no signal had data -> LOW confidence")

    return AuthorityResult(
        authority_score=score,
        source_class=source_class,
        corroboration_count=d.corroboration_count,
        authority_confidence=confidence,
        reasons=reasons,
        signal_scores=signal_scores,
        # Diff-gate P1-B: surface the fine-grained junk-class + the predatory-OA
        # smell so the clinical VIEW can demote SIGNAL-DRIVEN (no host list).
        junk_class=junk.junk_class if junk.fired else "",
        predatory_oa=a.predatory,
    )
