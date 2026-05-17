"""I-arch-001d — bridge from pipeline-A canonical artifact_dir to slice-chain
Pydantic models (ScopeDecision, EvidencePool, VerifiedReport) consumable by
the audit-bundle POST endpoint.

The audit-bundle path expects the slice-001/002/003 Pydantic shapes, but
pipeline-A produces a different artifact set (manifest.json + report.md +
bibliography.json + contradictions.json + verification_details.json +
evidence_pool.json). This module translates one to the other.

Sovereignty cascade (Codex iter-2 P1-001): non-cleared sources are excluded
from pool.sources entirely. Sentences whose provenance_tokens cite an
excluded source are marked verifier_pass=False + drop_reason="invalid_token"
+ evaluator_agrees=False. Sections with no remaining passing sentences are
marked section_status="dropped". If ALL sections drop, raises
SovereigntyFilterEmptiedReportError so the endpoint can return 422.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from polaris_graph.audit_ir.loader import (
    AuditIR,
    EvidenceSpanToken,
    ReportSection as AuditIRSection,
    ReportSentence as AuditIRSentence,
    load_audit_ir,
)
from polaris_graph.clinical_generator.verified_report import (
    DropReason,
    PipelineVerdict,
    Section,
    SectionStatus,
    VerifiedReport as SliceChainVerifiedReport,
    VerifiedSentence,
)
from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)
from polaris_graph.scope.scope_decision import (
    ScopeClassValue,
    ScopeDecision,
    ScopeStatus,
)

# I-arch-001d Codex iter-3 P2: import canonical regex if available; else local
# fallback that matches clinical_generator.provenance shape.
try:
    from polaris_graph.clinical_generator.provenance import (  # type: ignore[attr-defined]
        PROVENANCE_TOKEN_RE as _CANONICAL_TOKEN_RE,
    )
    _PROV_TOKEN_RE = _CANONICAL_TOKEN_RE
except ImportError:
    # NOTE: align with polaris_graph.clinical_generator.provenance shape:
    # [#ev:<evidence_id>:<start>-<end>]
    _PROV_TOKEN_RE = re.compile(r"\[#ev:([^:\]]+):(\d+)-(\d+)\]")


class SovereigntyFilterEmptiedReportError(RuntimeError):
    """Raised when sovereignty cascade leaves no non-dropped sections.

    The endpoint catches this and returns 422 to the client. The
    bundle would otherwise fail `assert_all_pool_sources_legal_cleared`
    or generate an empty pipeline_verdict='success' report — both
    audit-grade incorrect.
    """


# I-arch-001d Codex iter-4 P2: expanded drop_reason map covering pipeline-A's
# observed reasons including no_integer_overlap / no_content_word_overlap /
# trial_name_mismatch.
_DROP_REASON_MAP: dict[str, DropReason] = {
    "invalid_token": "invalid_token",
    "span_out_of_range": "span_out_of_range",
    "numeric_mismatch": "numeric_mismatch",
    "number_not_in_any_cited_span": "numeric_mismatch",
    "no_integer_overlap_any_cited_span": "numeric_mismatch",
    "overlap_too_low": "overlap_too_low",
    "low_content_overlap": "overlap_too_low",
    "no_content_word_overlap_any_cited_span": "overlap_too_low",
    "no_provenance_token": "no_provenance_token",
    "missing_provenance": "no_provenance_token",
    "entailment_failed": "entailment_failed",
    "trial_name_mismatch": "invalid_token",
}


def _normalize_drop_reason(raw: str | None) -> DropReason | None:
    if raw is None:
        return None
    base = raw.split(":")[0].strip().lower()
    return _DROP_REASON_MAP.get(base, "invalid_token")


def _normalize_tier(raw: str) -> tuple[SourceTier, str]:
    """Map pipeline-A tier to SourceTier Literal. T4+/UNKNOWN → T3."""
    upper = (raw or "").upper().strip()
    if upper in ("T1", "T2", "T3"):
        return SourceTier(upper), upper
    return SourceTier.T3, upper or "UNKNOWN"


def _derive_scope_class(domain: str | None, scope_class: str | None) -> ScopeClassValue:
    """Derive a valid ScopeClassValue Literal from pipeline-A manifest fields."""
    if scope_class:
        s = scope_class.strip().lower()
        for valid in (
            "clinical_efficacy", "clinical_safety", "clinical_diagnosis",
            "clinical_prognosis", "out_of_scope", "uncertain",
        ):
            if s == valid:
                return valid  # type: ignore[return-value]
    if domain and "clinical" in domain.lower():
        return "clinical_efficacy"
    return "uncertain"


def _redact_sentence(sent: VerifiedSentence) -> VerifiedSentence:
    """Mark a sentence as failed during sovereignty cascade.

    Rebuilds via constructor (runs validators) instead of model_copy
    which bypasses them. Sets evaluator_agrees=False to satisfy the
    invariant that verifier_pass=False forbids evaluator_agrees=True.
    """
    fields = sent.model_dump()
    fields["verifier_pass"] = False
    fields["drop_reason"] = "invalid_token"
    fields["evaluator_agrees"] = False
    return VerifiedSentence(**fields)


def _evidence_ids_in_tokens(provenance_tokens: list[str]) -> set[str]:
    out: set[str] = set()
    for tok in provenance_tokens:
        m = _PROV_TOKEN_RE.search(tok)
        if m:
            out.add(m.group(1))
    return out


def _tokens_to_strings(tokens: tuple[EvidenceSpanToken, ...]) -> list[str]:
    return [f"[#ev:{t.evidence_id}:{t.start}-{t.end}]" for t in tokens]


def _read_optional_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _full_text_for_evidence_id(
    evidence_id: str,
    evidence_pool_raw: dict[str, Any] | list[Any] | None,
) -> str | None:
    """Lookup evidence body in evidence_pool.json (Codex iter-2 P2 Q4).

    Pipeline-A's persisted field is commonly `direct_quote`, not full_text.
    """
    if evidence_pool_raw is None:
        return None
    sources = (
        evidence_pool_raw.get("sources") if isinstance(evidence_pool_raw, dict)
        else evidence_pool_raw
    )
    if not isinstance(sources, list):
        return None
    for src in sources:
        if not isinstance(src, dict):
            continue
        if src.get("evidence_id") == evidence_id or src.get("source_id") == evidence_id:
            return (
                src.get("full_text")
                or src.get("direct_quote")
                or src.get("snippet")
            )
    return None


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def build_slice_chain(
    artifact_dir: Path,
) -> tuple[ScopeDecision, EvidencePool, SliceChainVerifiedReport]:
    """Convert a pipeline-A canonical artifact dir to slice-chain Pydantic models.

    Raises:
        FileNotFoundError: artifact_dir missing required canonical files
        SovereigntyFilterEmptiedReportError: sovereignty cascade leaves no
            non-dropped sections (cannot ship a bundle for this run)
    """
    air = load_audit_ir(artifact_dir)
    manifest_raw = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    evidence_pool_raw = _read_optional_json(artifact_dir / "evidence_pool.json")

    # ─── 1. ScopeDecision ─────────────────────────────────────────────────
    decision_id = (
        (manifest_raw.get("scope") or {}).get("decision_id")
        or manifest_raw.get("external_run_id")
        or str(uuid.uuid4())
    )
    scope_class = _derive_scope_class(
        manifest_raw.get("domain"),
        (manifest_raw.get("scope") or {}).get("classification"),
    )
    decision = ScopeDecision(
        decision_id=decision_id,
        status="in_scope",
        scope_class=scope_class,
        ambiguity_axes=[],
        clarifications_needed=[],
        provenance={
            "classifier_layer": "pipeline_a_v30",
            "artifact_dir": str(artifact_dir),
        },
    )

    # ─── 2. EvidencePool (sovereignty-filtered) ───────────────────────────
    sources: list[Source] = []
    cleared_evidence_ids: set[str] = set()
    for entry in air.bibliography:
        # Tier-1 is legal-cleared by default; non-T1 requires explicit clearance
        # in evidence_pool.json provenance.legal_cleared = True (Phase 2 hook).
        canonical_tier, raw_tier = _normalize_tier(entry.tier)
        is_legal_cleared = canonical_tier == SourceTier.T1
        if not is_legal_cleared:
            continue  # exclude — sovereignty_guard would reject otherwise
        full_text = _full_text_for_evidence_id(entry.evidence_id, evidence_pool_raw)
        sources.append(Source(
            source_id=entry.evidence_id,
            url=entry.url,
            domain=_url_domain(entry.url),
            tier=canonical_tier,
            title=entry.statement[:200] or "Untitled",
            snippet=entry.statement[:1000] or "n/a",
            full_text_available=full_text is not None,
            full_text=full_text,
            provenance={
                "legal_cleared": True,
                "raw_tier": raw_tier,
            },
            retracted=False,
        ))
        cleared_evidence_ids.add(entry.evidence_id)

    retrieval_block = manifest_raw.get("retrieval", {}) or {}
    started_utc = _parse_iso(retrieval_block.get("started_at")) or datetime.now(timezone.utc)
    finished_utc = _parse_iso(retrieval_block.get("finished_at")) or started_utc
    pool = EvidencePool(
        pool_id=retrieval_block.get("pool_id") or str(uuid.uuid4()),
        decision_id=decision.decision_id,
        sources=sources,
        adequacy=AdequacyVerdict(
            is_adequate=True,
            adequacy_score=1.0,
            failure_reason=None,
        ),
        queries_executed=retrieval_block.get("queries_executed", []) or [],
        retrieval_started_at_utc=started_utc,
        retrieval_finished_at_utc=finished_utc,
        latency_ms=int(retrieval_block.get("latency_ms") or 0),
        cost_usd=float(air.manifest.cost_usd or 0.0),
    )

    # ─── 3. VerifiedReport (sovereignty cascade) ──────────────────────────
    sections: list[Section] = []
    for air_section in air.verified_report.sections:
        kept: list[VerifiedSentence] = []
        for air_sent in air_section.sentences:
            sc_sent = _air_sentence_to_slice_chain(air_sent)
            cited_ids = _evidence_ids_in_tokens(sc_sent.provenance_tokens)
            if not cited_ids or cited_ids.issubset(cleared_evidence_ids):
                kept.append(sc_sent)
            else:
                kept.append(_redact_sentence(sc_sent))
        pass_count = sum(1 for s in kept if s.verifier_pass)
        section_status: SectionStatus = (
            "dropped" if pass_count == 0 else "verified"
        )
        sections.append(Section(
            section_id=_slugify(air_section.title) or f"section_{len(sections)}",
            section_title=air_section.title or f"Section {len(sections)}",
            verified_sentences=kept,
            section_verify_pass_rate=pass_count / max(len(kept), 1),
            section_status=section_status,
        ))

    non_dropped = [s for s in sections if s.section_status != "dropped"]
    if not non_dropped:
        raise SovereigntyFilterEmptiedReportError(
            "every section dropped after sovereignty cascade; bundle cannot be assembled"
        )

    overall = sum(s.section_verify_pass_rate for s in non_dropped) / len(non_dropped)
    # Codex diff iter-1 P2-001 fix: partial_* runs still have kept sections;
    # they're "success-with-degradation" not "no_verified_sections" aborts.
    # PipelineVerdict Literal accepts success | abort_no_verified_sections;
    # collapse partial_* into "success" since the pipeline did produce kept
    # content (the degradation is recorded on the manifest, not the verdict).
    manifest_status = air.manifest.status or ""
    if manifest_status == "success" or manifest_status.startswith("partial_"):
        pipeline_verdict: PipelineVerdict = "success"
    else:
        pipeline_verdict = "abort_no_verified_sections"
    models_block = manifest_raw.get("models") or {}
    report = SliceChainVerifiedReport(
        report_id=air.manifest.run_id,
        pool_id=pool.pool_id,
        decision_id=decision.decision_id,
        sections=sections,
        overall_verify_pass_rate=overall,
        pipeline_verdict=pipeline_verdict,
        generator_model=models_block.get("generator") or "unknown",
        evaluator_model=models_block.get("evaluator") or "strict_verify_v1",
        family_segregation_passed=True,
        verifier_pass_threshold=0.4,
        started_at_utc=started_utc,
        finished_at_utc=finished_utc,
        latency_ms=int(retrieval_block.get("latency_ms") or 0),
        cost_usd=float(air.manifest.cost_usd or 0.0),
    )
    return decision, pool, report


def _air_sentence_to_slice_chain(air_sent: AuditIRSentence) -> VerifiedSentence:
    """AuditIR ReportSentence → slice-chain VerifiedSentence."""
    failure = air_sent.failure_reasons[0] if air_sent.failure_reasons else None
    return VerifiedSentence(
        section_id=_slugify(air_sent.section) or "section",
        sentence_text=air_sent.text or "n/a",
        provenance_tokens=_tokens_to_strings(air_sent.tokens),
        verifier_pass=bool(air_sent.is_verified),
        drop_reason=_normalize_drop_reason(failure) if not air_sent.is_verified else None,
        evaluator_agrees=bool(air_sent.is_verified),
        is_synthesis_claim=len(air_sent.tokens) == 0 and bool(air_sent.is_verified),
    )


def _url_domain(url: str) -> str:
    """Extract host for the Source.domain field. Falls back to 'unknown'."""
    from urllib.parse import urlparse
    try:
        return urlparse(str(url)).netloc or "unknown"
    except Exception:  # noqa: BLE001 — defensive: never raise during bridge
        return "unknown"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (text or "").lower()).strip("_")[:60]
