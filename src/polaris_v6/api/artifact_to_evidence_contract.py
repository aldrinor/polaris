"""I-cd-680 — bridge a real pipeline-A artifact_dir to a typed EvidenceContract.

Reuses `build_slice_chain` (I-arch-001d, the same path `GET /runs/{id}/
bundle.tar.gz` already proves on real runs) and maps the slice-chain into the
`EvidenceContract` v1.0 schema that the follow-up (#542) and compare (#543)
endpoints consume.

Scope (Codex Option B, 2026-05-20): real-run RESOLUTION only. We do NOT
synthesize rich source-document char offsets — pipeline-A does not record
them. `SourceSpan.span_start`/`span_end` are the truthful 0..len(span_text)
offsets of the recorded evidence text within ITSELF (the recorded quote IS
the span). Rich offsets into the original source body are the deferred
Phase-2 capability (#710), NOT fabricated here (LAW II).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from polaris_v6.api.artifact_to_slice_chain import build_slice_chain
from polaris_v6.schemas.evidence_contract import (
    ContradictionRecord,
    EvidenceContract,
    SourceSpan,
    VerifiedSentence,
)


def _read_contradictions(artifact_dir: Path) -> list[ContradictionRecord]:
    """Load contradictions.json if present. Real pipeline-A runs write a list
    of contradiction records; absent/empty → no contradictions."""
    path = artifact_dir / "contradictions.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    records: list[ContradictionRecord] = []
    items = raw if isinstance(raw, list) else raw.get("contradictions", [])
    for i, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        try:
            records.append(
                ContradictionRecord(
                    contradiction_id=str(item.get("contradiction_id") or f"c{i}"),
                    section_id=str(item.get("section_id") or "unknown"),
                    claim_a=str(item.get("claim_a") or ""),
                    claim_b=str(item.get("claim_b") or ""),
                    evidence_a=[str(x) for x in (item.get("evidence_a") or [])],
                    evidence_b=[str(x) for x in (item.get("evidence_b") or [])],
                    resolution=item.get("resolution")
                    if item.get("resolution")
                    in ("unresolved", "claim_a_preferred", "claim_b_preferred", "noted_both")
                    else "noted_both",
                )
            )
        except Exception:  # noqa: BLE001 — a malformed record is skipped, not fatal
            continue
    return records


def build_evidence_contract_from_artifact(
    artifact_dir: Path,
    *,
    run_id: str,
    template: str,
    question: str,
    queued_at: str,
    finished_at: str,
    pipeline_status: str,
) -> EvidenceContract:
    """Synthesize a fully-valid EvidenceContract from a REAL artifact_dir.

    Run metadata (run_id/template/question/timestamps/status) is supplied by
    the caller from run_store (the authoritative source); the evidence + the
    verified sentences come from the slice-chain.

    Raises FileNotFoundError / SovereigntyFilterEmptiedReportError from
    build_slice_chain — the caller maps these to 404 / 422.
    """
    _decision, pool, report = build_slice_chain(artifact_dir)

    evidence_pool: list[SourceSpan] = []
    for src in pool.sources:
        # The recorded evidence text. build_slice_chain only admits T1
        # legal-cleared sources, so source_tier is within SourceSpan's
        # T1/T2/T3 Literal.
        span_text = src.full_text or src.snippet or src.title or "n/a"
        evidence_pool.append(
            SourceSpan(
                evidence_id=src.source_id,
                source_url=str(src.url),
                source_tier=src.tier.value,
                # Truthful self-offset of the recorded span; rich
                # source-document offsets are deferred to #710.
                span_start=0,
                span_end=len(span_text),
                span_text=span_text,
            )
        )

    verified_sentences: list[VerifiedSentence] = []
    for section in report.sections:
        for sent in section.verified_sentences:
            verified_sentences.append(
                VerifiedSentence(
                    section_id=sent.section_id,
                    sentence_text=sent.sentence_text,
                    provenance_tokens=list(sent.provenance_tokens),
                    # The slice-chain records a single verifier_pass (Local AND
                    # Global must both hold for a sentence to pass strict_verify),
                    # so it maps to both EvidenceContract flags.
                    verifier_local_pass=sent.verifier_pass,
                    verifier_global_pass=sent.verifier_pass,
                    drop_reason=sent.drop_reason,
                )
            )

    return EvidenceContract(
        run_id=run_id,
        template=template,
        question=question,
        queued_at=queued_at,
        finished_at=finished_at,
        pipeline_status=pipeline_status,
        evidence_pool=evidence_pool,
        verified_sentences=verified_sentences,
        frame_coverage=[],
        contradictions=_read_contradictions(artifact_dir),
        cost_usd=float(report.cost_usd or 0.0),
        generator_model=report.generator_model,
        verifier_model=report.evaluator_model,
        family_segregation_passed=report.family_segregation_passed,
    )
