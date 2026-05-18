"""v6 live-inspector AuditIR resolver routes.

I-rdy-008 (#504): the rich UI surfaces migrate onto the canonical
completed-run path `run_id -> artifact_dir -> load_audit_ir() -> AuditIR`
(slice 1, Option A — Codex architecture-decision consult
`.codex/I-rdy-008/arch_decision_verdict.txt`).

Routes:
- `GET /api/inspector/runs/{run_id}` (slice 1) — the full faithful AuditIR.
- `GET /api/inspector/runs/{run_id}/evidence` (slice 7a) — the verified
  evidence spans cited by the run, reconstructed from `evidence_pool.json`
  (Codex arch consult `.codex/I-rdy-008/slice7_arch_consult_verdict.txt`).

This is the demo-scoped v6 facade — it exposes completed-run reads only. It
deliberately does NOT mount `polaris_graph.audit_ir.inspector_router`, which
in current HEAD also carries non-demo surfaces (jobs, workspaces, operator
dashboards, metrics) per the consult's stale-correction.

Per `docs/live_run_artifact_contract.md` (#503) §2.3: `abort_*` / `error_*`
runs are pipeline-verdict artifacts, NOT AuditIR-loadable — rejected before
the loader is called.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from polaris_graph.audit_ir.loader import load_audit_ir
from polaris_graph.audit_ir.serializer import to_json_dict
from polaris_v6.queue import run_store

router = APIRouter(prefix="/api/inspector", tags=["inspector"])


def _resolve_completed_artifact_dir(run_id: str) -> Path:
    """Resolve a completed run to its on-disk artifact_dir, or raise.

    The shared run-resolution for every inspector route (slice 7a extracted
    this from `get_inspector_run` so the evidence route reuses identical
    behavior — same status codes, same messages):

    - unknown run -> 404
    - run not completed -> 409
    - abort_* / error_* run -> 422 (no AuditIR-loadable artifacts)
    - missing / absent artifact_dir -> 404
    """
    record = run_store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    if record.lifecycle_status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id} is not completed "
                f"(lifecycle_status={record.lifecycle_status!r})"
            ),
        )

    status = record.pipeline_status or ""
    if status.startswith("abort_") or status.startswith("error_"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"run {run_id} produced no AuditIR-loadable artifacts "
                f"(pipeline_status={status!r}); it is a pipeline-verdict "
                f"artifact, not a renderable run"
            ),
        )

    if not record.artifact_dir:
        raise HTTPException(
            status_code=404,
            detail=f"run {run_id} has no artifact_dir recorded",
        )
    artifact_dir = Path(record.artifact_dir)
    if not artifact_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"artifact_dir does not exist on disk: {artifact_dir}",
        )
    return artifact_dir


def _load_evidence_pool(artifact_dir: Path, run_id: str) -> dict[str, dict[str, Any]]:
    """Index `evidence_pool.json` by evidence id. Fail loud if absent/malformed.

    Mirrors `artifact_to_slice_chain._full_text_for_evidence_id`: the pool is
    EITHER a bare JSON list OR `{"sources": [...]}`; a row is keyed by
    `evidence_id` or `source_id`. Returns `{evidence_id: row}`.

    A run with no `evidence_pool.json` predates evidence-pool persistence — it
    is not span-renderable; 422 (fail loud, no `bibliography.statement`
    fallback) per the Codex arch consult + LAW II.
    """
    pool_path = artifact_dir / "evidence_pool.json"
    if not pool_path.is_file():
        raise HTTPException(
            status_code=422,
            detail=(
                f"run {run_id} has no evidence_pool.json — the verified "
                f"evidence spans cannot be reconstructed (this run predates "
                f"evidence-pool persistence)"
            ),
        )
    try:
        raw = json.loads(pool_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"run {run_id} evidence_pool.json is unreadable: {exc}",
        ) from exc

    rows = raw.get("sources") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise HTTPException(
            status_code=422,
            detail=(
                f"run {run_id} evidence_pool.json is not a list of sources "
                f"(nor a {{'sources': [...]}} object)"
            ),
        )

    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ev_id = row.get("evidence_id") or row.get("source_id")
        if ev_id:
            indexed[str(ev_id)] = row
    return indexed


def _evidence_body(row: dict[str, Any]) -> str:
    """The per-row evidence body text — `full_text`/`direct_quote`/`snippet`
    precedence, mirroring `artifact_to_slice_chain._full_text_for_evidence_id`.
    """
    for key in ("full_text", "direct_quote", "snippet"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


@router.get("/runs/{run_id}")
def get_inspector_run(run_id: str) -> dict[str, Any]:
    """Return the full faithful AuditIR for a completed run as a JSON dict.

    The canonical data source for the Evidence Inspector and every derivative
    rich surface (I-rdy-008 #504, Option A). Resolution:

    - unknown run -> 404
    - run not completed -> 409
    - abort_* / error_* run -> 422 (no AuditIR-loadable artifacts)
    - missing / absent artifact_dir -> 404
    - artifact_dir present but unloadable -> 422 (fail loud, no zero-fill)
    - completed loadable run -> 200, full AuditIR JSON
    """
    artifact_dir = _resolve_completed_artifact_dir(run_id)

    try:
        ir = load_audit_ir(artifact_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError, TypeError) as exc:
        # AuditIRSchemaError and json.JSONDecodeError are both ValueError
        # subclasses; plain ValueError / TypeError also catch malformed
        # numeric fields (Codex brief iter-2 P2). Fail loud per audit-grade
        # discipline — no silent zero-fill of canonical structures.
        raise HTTPException(
            status_code=422,
            detail=f"run {run_id} artifact_dir failed AuditIR load: {exc}",
        ) from exc

    return to_json_dict(ir)


@router.get("/runs/{run_id}/evidence")
def get_inspector_run_evidence(run_id: str) -> dict[str, Any]:
    """Return the verified evidence spans cited by a completed run.

    I-rdy-008 (#504) slice 7a (Codex arch consult
    `.codex/I-rdy-008/slice7_arch_consult_verdict.txt`). Every verified-report
    sentence carries `[#ev:<id>:<start>-<end>]` tokens; this route resolves
    each token's `evidence_id` against `evidence_pool.json` and reconstructs
    the exact cited span as `body[start:end]` — the auditable source text an
    auditor verifies a claim against. Spans are range-keyed
    (`evidence_id, start, end`) and de-duplicated; `claim_ids` lists every
    sentence that cites the span.

    Fails loud (422) — never degrades to a bibliography statement — when
    `evidence_pool.json` is absent/malformed, a token cites an evidence id
    absent from the pool, a row has no body text, or a token's offsets are
    out of range.

    Resolution: unknown 404 / not-completed 409 / abort 422 / missing
    artifact_dir 404 / unloadable AuditIR 422 / no evidence_pool.json 422 /
    completed + loadable + pooled -> 200.
    """
    artifact_dir = _resolve_completed_artifact_dir(run_id)
    pool = _load_evidence_pool(artifact_dir, run_id)

    try:
        ir = load_audit_ir(artifact_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"run {run_id} artifact_dir failed AuditIR load: {exc}",
        ) from exc

    # Range key (evidence_id, start, end) -> set of citing sentence claim_ids.
    claim_ids_by_span: dict[tuple[str, int, int], set[str]] = {}
    for section in ir.verified_report.sections:
        for sentence in section.sentences:
            for token in sentence.tokens:
                key = (token.evidence_id, token.start, token.end)
                claim_ids_by_span.setdefault(key, set()).add(sentence.claim_id)

    spans: list[dict[str, Any]] = []
    for evidence_id, start, end in sorted(claim_ids_by_span):
        row = pool.get(evidence_id)
        if row is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"run {run_id}: a verified sentence token cites evidence "
                    f"{evidence_id!r}, which is absent from evidence_pool.json"
                ),
            )
        body = _evidence_body(row)
        if not body:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"run {run_id}: evidence {evidence_id!r} has no body text "
                    f"in evidence_pool.json — the span cannot be reconstructed"
                ),
            )
        if start < 0 or start > end or end > len(body):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"run {run_id}: evidence {evidence_id!r} span "
                    f"[{start}:{end}] is out of range for its {len(body)}-char "
                    f"body text"
                ),
            )
        spans.append(
            {
                "evidence_id": evidence_id,
                "span_start": start,
                "span_end": end,
                "span_text": body[start:end],
                "tier": str(row.get("tier", "")),
                "source_url": str(row.get("source_url") or row.get("url") or ""),
                "claim_ids": sorted(claim_ids_by_span[(evidence_id, start, end)]),
            }
        )

    return {"run_id": run_id, "spans": spans}
