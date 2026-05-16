"""I-rdy-008 — live-run → EvidenceContract adapter.

Implements `docs/live_run_artifact_contract.md` (I-rdy-007): resolves a v6
`run_id` to its pipeline-A `artifact_dir` and adapts that artifact set into the
`EvidenceContract` the rich UI endpoints (bundle JSON, charts, follow-up,
compare) consume — so a real completed run is inspectable, not only the golden
fixtures.

Public surface:
  - resolve_run(run_id)                  — run_id -> (RunStatusResponse, artifact_dir)
  - artifact_dir_to_evidence_contract()  — artifact_dir -> EvidenceContract
  - live_run_evidence_contract(run_id)   — endpoint entry; None => no run_store row
                                           (caller falls back to the golden index)

Endpoints call `live_run_evidence_contract`; a return of `None` means no such
run exists in `run_store` (so a golden fixture id should be tried). A real but
non-serviceable run raises `HTTPException` per the I-rdy-007 §6 error matrix.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import HTTPException

from polaris_graph.audit_ir.loader import (
    AuditIR,
    AuditIRSchemaError,
    load_audit_ir,
)
from polaris_v6.api.artifact_to_slice_chain import (
    _full_text_for_evidence_id,
    _normalize_tier,
    _read_optional_json,
    _slugify,
)
from polaris_v6.queue import run_store
from polaris_v6.schemas.evidence_contract import (
    ContradictionRecord,
    EvidenceContract,
    FrameCoverage,
    SourceSpan,
    VerifiedSentence,
)
from polaris_v6.schemas.run_status import RunStatusResponse

logger = logging.getLogger("polaris_v6.api.live_run_adapter")


# ---------------------------------------------------------------------------
# Resolver — run_id -> artifact_dir, applying the I-rdy-007 §6 error matrix
# ---------------------------------------------------------------------------


def resolve_run(run_id: str) -> tuple[RunStatusResponse, Path]:
    """Resolve `run_id` to `(RunStatusResponse, artifact_dir)`.

    Raises `HTTPException` for any non-serviceable run, per the I-rdy-007
    error-state matrix:
      404 — run not found / not completed / artifact_dir missing or absent
      422 — run aborted (pipeline_status abort_*) / release-blocked
    """
    info = run_store.get_run(run_id)
    if info is None:
        raise HTTPException(
            status_code=404, detail={"error": f"run {run_id!r} not found"}
        )
    if info.lifecycle_status != "completed":
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"run not completed: lifecycle_status={info.lifecycle_status}"
            },
        )
    if info.pipeline_status and info.pipeline_status.startswith("abort_"):
        raise HTTPException(
            status_code=422,
            detail={"error": f"run aborted: pipeline_status={info.pipeline_status}"},
        )
    if not info.artifact_dir:
        raise HTTPException(
            status_code=404, detail={"error": "run has no artifact_dir recorded"}
        )
    artifact_dir = Path(info.artifact_dir)
    if not artifact_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail={"error": f"artifact_dir does not exist on disk: {artifact_dir}"},
        )
    # Release-blocked gate — read manifest.release_allowed (mirrors bundle.tar.gz).
    try:
        manifest_raw = json.loads(
            (artifact_dir / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": f"manifest.json missing or invalid: {exc}"},
        ) from exc
    if not manifest_raw.get("release_allowed", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": (
                    f"run release-blocked: pipeline_status={info.pipeline_status!r}, "
                    f"release_allowed=False"
                )
            },
        )
    return info, artifact_dir


# ---------------------------------------------------------------------------
# Adapter internals
# ---------------------------------------------------------------------------


def _model_identity(air: AuditIR, manifest_raw: dict) -> tuple[str, str, bool]:
    """dec-1: model identity. `AuditIR.model_provenance` -> raw `manifest.models`
    -> fail loud (422). Returns (generator_model, verifier_model, family_passed).
    """
    mp = air.model_provenance
    if mp is not None and mp.generator_model and mp.evaluator_model:
        gen, ver = mp.generator_model, mp.evaluator_model
        gen_fam, ver_fam = mp.generator_family, mp.evaluator_family
        if gen_fam and ver_fam:
            return gen, ver, gen_fam != ver_fam
        return gen, ver, gen.split("/")[0] != ver.split("/")[0]
    models = manifest_raw.get("models") or {}
    gen = str(models.get("generator") or "").strip()
    ver = str(models.get("evaluator") or "").strip()
    if not gen or not ver:
        raise HTTPException(
            status_code=422,
            detail={"error": "run not contract-conformant: no model identity"},
        )
    return gen, ver, gen.split("/")[0] != ver.split("/")[0]


def _build_evidence_pool(
    air: AuditIR, evidence_pool_raw: object
) -> list[SourceSpan]:
    """dec-5 (tier) + dec-6 (envelope span + clamp). One SourceSpan per distinct
    cited evidence_id; span is the envelope (min start / max end) over every
    token citing that id; span_text is the source body clamped to that span.
    """
    # Collect envelope spans per evidence_id across every sentence token.
    envelopes: dict[str, tuple[int, int]] = {}
    for section in air.verified_report.sections:
        for sent in section.sentences:
            for tok in sent.tokens:
                lo, hi = envelopes.get(tok.evidence_id, (tok.start, tok.end))
                envelopes[tok.evidence_id] = (
                    min(lo, tok.start),
                    max(hi, tok.end),
                )
    spans: list[SourceSpan] = []
    for evidence_id in sorted(envelopes):
        env_start, env_end = envelopes[evidence_id]
        bib = air.get_bibliography_by_evidence_id(evidence_id)
        source_url = bib.url if bib else ""
        source_tier = _normalize_tier(bib.tier if bib else "UNKNOWN")[0].value
        body = _full_text_for_evidence_id(evidence_id, evidence_pool_raw)
        if not body:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": (
                        f"run not contract-conformant: no source body for cited "
                        f"evidence_id {evidence_id!r} in evidence_pool.json"
                    )
                },
            )
        # dec-6: clamp the span to the available body; 422 if no non-empty overlap.
        start = max(0, min(env_start, len(body)))
        end = min(max(env_end, 0), len(body))
        if end <= start:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": (
                        f"run not contract-conformant: cited span [{env_start}:"
                        f"{env_end}] for {evidence_id!r} has no overlap with the "
                        f"{len(body)}-char source body"
                    )
                },
            )
        if (start, end) != (env_start, env_end):
            logger.info(
                "[live_run_adapter] clamped span for %s: [%d:%d] -> [%d:%d] "
                "(body len %d)",
                evidence_id, env_start, env_end, start, end, len(body),
            )
        spans.append(
            SourceSpan(
                evidence_id=evidence_id,
                source_url=source_url or "unknown",
                source_tier=source_tier,
                span_start=start,
                span_end=end,
                span_text=body[start:end],
            )
        )
    return spans


def _build_verified_sentences(air: AuditIR) -> list[VerifiedSentence]:
    """dec-2: both verifier passes <- ReportSentence.is_verified."""
    out: list[VerifiedSentence] = []
    for section in air.verified_report.sections:
        for sent in section.sentences:
            drop_reason = None
            if not sent.is_verified and sent.failure_reasons:
                drop_reason = sent.failure_reasons[0]
            out.append(
                VerifiedSentence(
                    section_id=_slugify(sent.section) or "section",
                    sentence_text=sent.text or "n/a",
                    provenance_tokens=[
                        f"[#ev:{t.evidence_id}:{t.start}-{t.end}]"
                        for t in sent.tokens
                    ],
                    verifier_local_pass=bool(sent.is_verified),
                    verifier_global_pass=bool(sent.is_verified),
                    drop_reason=drop_reason,
                )
            )
    return out


def _build_frame_coverage(air: AuditIR) -> list[FrameCoverage]:
    """dec-3: roll FrameCoverageEntry (per entity) up to FrameCoverage (per
    frame) — group by (section, slot_id); coverage = exact-"pass" / total.
    """
    groups: dict[tuple[str, str], list] = {}
    for entry in air.frame_coverage.entries:
        groups.setdefault((entry.section, entry.slot_id), []).append(entry)
    out: list[FrameCoverage] = []
    for (section, slot_id), entries in sorted(groups.items()):
        total = len(entries)
        passed = sum(1 for e in entries if e.status == "pass")
        out.append(
            FrameCoverage(
                frame_id=f"{section}:{slot_id}" if section else slot_id,
                frame_name=entries[0].subsection_title or slot_id or section,
                sources_assigned=total,
                coverage_percent=(passed / total * 100.0) if total else 0.0,
            )
        )
    return out


def _claim_text(claim) -> str:
    """Render a ContradictionClaim to display text — context_snippet else composed."""
    if claim.context_snippet:
        return claim.context_snippet
    parts = [
        claim.subject, claim.predicate, claim.arm, claim.dose,
        f"{claim.value} {claim.unit}".strip(),
    ]
    return " ".join(p for p in parts if p).strip() or "n/a"


def _build_contradictions(air: AuditIR) -> list[ContradictionRecord]:
    """dec-4: ContradictionCluster -> ContradictionRecord. >2 claims/cluster ->
    claims[2:] folded into evidence_b. section_id derived from the first
    verified_report section citing claims[0].evidence_id.
    """
    out: list[ContradictionRecord] = []
    for cluster in air.contradictions:
        claims = list(cluster.claims)
        if len(claims) < 2:
            continue  # loader guarantees >=2; defensive
        ev_a = claims[0].evidence_id
        section_id = "unsectioned"
        for section in air.verified_report.sections:
            if any(
                tok.evidence_id == ev_a
                for sent in section.sentences
                for tok in sent.tokens
            ):
                section_id = _slugify(section.title) or "unsectioned"
                break
        out.append(
            ContradictionRecord(
                contradiction_id=f"contradiction_{cluster.cluster_id}",
                section_id=section_id,
                claim_a=_claim_text(claims[0]),
                claim_b=_claim_text(claims[1]),
                evidence_a=[claims[0].evidence_id],
                evidence_b=[c.evidence_id for c in claims[1:]],
                resolution="unresolved",
            )
        )
    return out


# ---------------------------------------------------------------------------
# Adapter — artifact_dir -> EvidenceContract
# ---------------------------------------------------------------------------


def artifact_dir_to_evidence_contract(
    artifact_dir: Path, run_status: RunStatusResponse
) -> EvidenceContract:
    """Adapt a pipeline-A `artifact_dir` into an `EvidenceContract` v1.0.

    Raises `HTTPException` (404 incomplete artifact / 422 non-conformant run)
    per the I-rdy-007 contract.
    """
    try:
        air = load_audit_ir(artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError, NotADirectoryError) as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": f"artifact_dir incomplete or malformed: {exc}"},
        ) from exc

    evidence_pool_raw = _read_optional_json(artifact_dir / "evidence_pool.json")
    if evidence_pool_raw is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "artifact_dir incomplete: evidence_pool.json missing"},
        )
    manifest_raw = json.loads(
        (artifact_dir / "manifest.json").read_text(encoding="utf-8")
    )

    generator_model, verifier_model, family_passed = _model_identity(
        air, manifest_raw
    )

    return EvidenceContract(
        contract_version="1.0",
        run_id=run_status.run_id,
        template=run_status.template,
        question=run_status.question or air.manifest.question,
        queued_at=run_status.queued_at or "",
        finished_at=run_status.finished_at or "",
        pipeline_status=run_status.pipeline_status or air.manifest.status or "success",
        evidence_pool=_build_evidence_pool(air, evidence_pool_raw),
        verified_sentences=_build_verified_sentences(air),
        frame_coverage=_build_frame_coverage(air),
        contradictions=_build_contradictions(air),
        cost_usd=float(
            run_status.cost_usd
            if run_status.cost_usd is not None
            else (air.manifest.cost_usd or 0.0)
        ),
        generator_model=generator_model,
        verifier_model=verifier_model,
        family_segregation_passed=family_passed,
    )


def live_run_evidence_contract(run_id: str) -> EvidenceContract | None:
    """Endpoint entry point. Returns the `EvidenceContract` for a live completed
    run, or `None` when no `run_store` row exists for `run_id` (the caller then
    falls back to the golden fixture index). A real but non-serviceable run
    raises `HTTPException` per the error matrix.
    """
    if run_store.get_run(run_id) is None:
        return None
    info, artifact_dir = resolve_run(run_id)
    return artifact_dir_to_evidence_contract(artifact_dir, info)
