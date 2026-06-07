"""M-60 (2026-04-23): V30 explicit gap reporting + manifest.

V30 Report Contract Architecture Layer 4c. Codex plan review #4:
  "add machine-readable metadata for every incomplete slot:
   slot_id, entity_id, status, failure_reason, retrieval_attempt_log,
   available_artifacts, human_completion_eligible. The prose gap
   paragraph is appropriate for report.md, but it is not enough
   by itself."

M-60 has two responsibilities:
  1. Compose the structured `frame_coverage_report` block that
     ships in manifest.json — consumed by M-61 human-completion
     task generation + by downstream build gates + by the
     operator dashboard.
  2. Compose a Methods-section snippet for report.md disclosing
     the frame_gap_count so clinicians can see at a glance how
     many contract slots weren't fully populated.

## What M-60 does NOT do

- Does NOT own the per-slot rendered prose. M-58 render_slot_prose
  handles that; M-58 ships the GAP_PROSE_MARKER constant; M-59
  validates the marker is present. M-60 consumes M-59's
  ValidationReport to decide which slots need coverage entries.
- Does NOT write to disk. The manifest composer returns a dict;
  the caller (sweep assembly) decides whether to write it.

## Pure function

Same inputs → byte-identical coverage report. No wall-clock, no
network. `retrieval_attempt_log` passthrough preserves M-56's
already-deterministic attempt log (payload-deterministic via
M-56 pass-2 Blocker-1 fix).

## Interaction with other layers

  M-55 CompiledFrame         → entity bindings + research_question
  M-56 FrameRows             → provenance_class + retrieval_attempts
                               + failure_reason + available artifacts
  M-57 ContractOutline       → slot membership + sections
  M-58 SlotFillPayload       → completion_count, not used here
                               directly but M-59 feeds per-slot
                               verdicts to M-60
  M-59 ValidationReport      → per-entity verdicts that become the
                               `status` field in coverage entries
  M-60 FrameCoverageReport   → structured manifest block (this)
  M-61 human_gap_tasks.json  → consumes
                               `human_completion_eligible=True`
                               entries
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..nodes.contract_outline import ContractOutline
from ..nodes.frame_compiler import CompiledFrame
from ..retrieval.frame_fetcher import FrameRow, ProvenanceClass
from .slot_validator import ValidationReport, ValidationVerdict


@dataclass(frozen=True)
class SlotCoverageEntry:
    """One entry per contract slot in the manifest.

    Codex plan review #4 required all seven fields below. Extras
    (section, subsection_title, doi, pmid, required_fields,
    entity_type) are carried so M-61 task generation and operator
    dashboards don't have to re-join against the contract.

    `is_pipeline_fault` flags the defensive path where M-56 did
    not emit a FrameRow for a contracted entity (pipeline
    crossed wires). Codex M-60 audit Medium: these entries should
    NOT be routed to human completion — they need engineer
    attention, not curator attention.

    `human_curated_provenance` surfaces the M-61 StructuredProvenance
    dict (curator_id, artifact_sha256, retention path, attestation,
    etc.) directly in the manifest entry when the row was supplied
    via Path B. Codex M-61 audit Blocker 3 — audit evidence must
    survive the FrameRow → manifest boundary, not live in an
    in-memory side channel.
    """

    slot_id: str
    entity_id: str
    entity_type: str
    section: str
    subsection_title: str
    status: str                       # from ValidationVerdict enum value
    provenance_class: str
    failure_reason: str | None
    retrieval_attempt_log: list[dict[str, Any]]
    available_artifacts: list[str]
    human_completion_eligible: bool
    is_pipeline_fault: bool
    # Contract echoes for M-61 consumption (Codex M-60 audit Blocker)
    required_fields: list[str]
    min_fields_for_completion: int
    doi: str | None
    pmid: str | None
    # M-61 audit evidence passthrough
    human_curated_provenance: dict[str, str] | None = None


@dataclass(frozen=True)
class FrameCoverageReport:
    """Top-level manifest block. Composed by M-60; serialized as
    manifest["frame_coverage_report"] at sweep assembly time."""

    research_question: str
    schema_version: str
    total_slots: int
    total_entities: int
    frame_gap_count: int
    partial_count: int
    pass_count: int
    # Codex M-60 audit Medium: distinguish pipeline faults (M-56
    # did not emit a FrameRow for a contracted entity — engineer
    # attention needed) from retrieval gaps (curator/human
    # completion needed).
    pipeline_fault_count: int
    by_status: dict[str, int]
    entries: tuple[SlotCoverageEntry, ...]

    def to_manifest_dict(self) -> dict[str, Any]:
        """JSON-serializable dict shape for manifest.json write.

        Uses `dataclasses.asdict` on entries then converts the
        tuple to list so the result is a plain Python dict tree
        that json.dump can handle without a custom encoder.
        """
        return {
            "research_question": self.research_question,
            "schema_version": self.schema_version,
            "total_slots": self.total_slots,
            "total_entities": self.total_entities,
            "frame_gap_count": self.frame_gap_count,
            "partial_count": self.partial_count,
            "pass_count": self.pass_count,
            "pipeline_fault_count": self.pipeline_fault_count,
            "by_status": dict(self.by_status),
            "entries": [asdict(e) for e in self.entries],
        }


def compose_frame_coverage(
    compiled_frame: CompiledFrame,
    outline: ContractOutline,
    frame_rows: tuple[FrameRow, ...],
    validation_report: ValidationReport,
    strict_verify_by_key: dict[Any, Any] | None = None,
) -> FrameCoverageReport:
    """M-60 entrypoint. Produce the structured coverage block for
    manifest.json.

    Args:
        compiled_frame: M-55 CompiledFrame (research_question,
            schema_version, evidence_bindings).
        outline: M-57 ContractOutline (slot membership + sections).
        frame_rows: M-56 FrameRows parallel to compiled_frame.evidence_bindings.
        validation_report: M-59 ValidationReport with per-entity
            verdicts.

    Returns:
        FrameCoverageReport — one SlotCoverageEntry per (slot, entity)
        combination in outline order, with aggregate counts.

    Deterministic: iteration follows outline order; frame_rows are
    keyed by entity_id; validation_report entities read in order.
    Same inputs → byte-identical output.
    """
    rows_by_eid: dict[str, FrameRow] = {
        r.entity_id: r for r in frame_rows
    }
    # Pull contract for per-entity required_fields lookup (Codex
    # M-60 audit Blocker — M-61 task payload needs missing-field
    # detail).
    contract_entities = compiled_frame.contract.entities_by_id()
    # Build verdicts keyed by (slot_id, entity_id) for O(1) lookup
    verdicts_by_key: dict[tuple[str, str], str] = {}
    reasons_by_key: dict[tuple[str, str], str] = {}
    for ev in validation_report.entity_validations:
        verdicts_by_key[(ev.slot_id, ev.entity_id)] = ev.verdict.value
        reasons_by_key[(ev.slot_id, ev.entity_id)] = ev.reason

    entries: list[SlotCoverageEntry] = []
    gap_count = 0
    partial_count = 0
    pass_count = 0
    pipeline_fault_count = 0
    by_status: dict[str, int] = {}

    for section in outline.sections:
        for slot in section.slots:
            for entity_id in slot.entity_ids:
                row = rows_by_eid.get(entity_id)
                status = verdicts_by_key.get(
                    (slot.slot_id, entity_id),
                    ValidationVerdict.FAIL_MISSING_PAYLOAD.value,
                )
                by_status[status] = by_status.get(status, 0) + 1
                contract_entity = contract_entities.get(entity_id)
                required_fields = (
                    list(contract_entity.required_fields)
                    if contract_entity else []
                )
                min_fields = (
                    contract_entity.min_fields_for_completion
                    if contract_entity else 0
                )

                if row is None:
                    # M-56 should have produced a row; defensive
                    # fallback. Codex M-60 audit Medium: this is a
                    # pipeline-integrity fault, not a retrieval
                    # gap. NOT routed to human completion.
                    entries.append(_empty_coverage_entry(
                        slot_id=slot.slot_id,
                        entity_id=entity_id,
                        entity_type=(
                            contract_entity.type
                            if contract_entity else "unknown"
                        ),
                        section=section.section,
                        subsection_title=slot.subsection_title,
                        status=status,
                        validator_reason=reasons_by_key.get(
                            (slot.slot_id, entity_id), ""
                        ),
                        required_fields=required_fields,
                        min_fields_for_completion=min_fields,
                    ))
                    pipeline_fault_count += 1
                    continue

                is_gap_row = (
                    row.provenance_class
                    == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
                )

                # I-ready-017 FX-07b leg-2 (#1111): pipeline-fault honesty
                # override. A non-gap entity that VALIDATED (verdict==pass) and
                # whose generator DID produce content sentences but ALL of them
                # failed strict_verify is a PIPELINE FAULT — it must NOT read as
                # pass (the report has no verified prose for it). Triple-gated so
                # an extraction gap (verdict!=pass) or a no-content-attempted row
                # (generated==0) or a FRAME_GAP_UNRECOVERABLE row is NEVER
                # reclassified. Unknown/missing metrics → non-overriding.
                _sv_meta = (strict_verify_by_key or {}).get(
                    (slot.slot_id, entity_id)
                )
                _is_gen_failed = bool(
                    (not is_gap_row)
                    and status == ValidationVerdict.PASS.value
                    and isinstance(_sv_meta, dict)
                    and (_sv_meta.get("sentences_generated_content") or 0) > 0
                    and (_sv_meta.get("sentences_kept") or 0) == 0
                )
                if _is_gen_failed:
                    # Correct the aggregate: this would-be pass is a fault.
                    pipeline_fault_count += 1
                    by_status[status] = max(0, by_status.get(status, 0) - 1)
                    by_status["generation_failed"] = (
                        by_status.get("generation_failed", 0) + 1
                    )
                elif is_gap_row:
                    gap_count += 1
                elif status == ValidationVerdict.PASS.value:
                    pass_count += 1
                else:
                    # Non-gap row that failed validation counts as
                    # partial coverage (content exists but didn't
                    # meet min_fields or lacks citation).
                    partial_count += 1

                entries.append(SlotCoverageEntry(
                    slot_id=slot.slot_id,
                    entity_id=entity_id,
                    entity_type=row.entity_type,
                    section=section.section,
                    subsection_title=slot.subsection_title,
                    status=("generation_failed" if _is_gen_failed else status),
                    provenance_class=row.provenance_class.value,
                    failure_reason=(
                        "strict_verify dropped all generated content sentences "
                        "(pipeline fault — no verified prose for this entity)"
                        if _is_gen_failed
                        else _failure_reason(
                            row, status, reasons_by_key.get(
                                (slot.slot_id, entity_id), ""
                            ),
                        )
                    ),
                    retrieval_attempt_log=[
                        {
                            "source": a.source,
                            "url": a.url,
                            "attempt_index": a.attempt_index,
                            "http_status": a.http_status,
                            "outcome": a.outcome,
                        }
                        for a in row.retrieval_attempts
                    ],
                    available_artifacts=_available_artifacts(row),
                    # Codex M-60 audit pass-2 blocker: eligibility is
                    # strictly "curator can fix". Engineer-owned
                    # statuses (unbound citation, gap-no-language,
                    # payload mismatch) and already-passing entries
                    # are NOT routed to human completion.
                    human_completion_eligible=(
                        False if _is_gen_failed
                        else _is_curator_actionable(
                            is_gap_row=is_gap_row, status=status,
                        )
                    ),
                    is_pipeline_fault=_is_gen_failed,
                    required_fields=required_fields,
                    min_fields_for_completion=min_fields,
                    doi=row.doi,
                    pmid=row.pmid,
                    # M-61 audit evidence passthrough (Codex M-61
                    # audit Blocker 3 fix). None for non-human-
                    # curated rows.
                    human_curated_provenance=row.human_curated_provenance,
                ))

    return FrameCoverageReport(
        research_question=compiled_frame.research_question,
        schema_version=compiled_frame.schema_version,
        total_slots=sum(
            len(s.slots) for s in outline.sections
        ),
        total_entities=len(entries),
        frame_gap_count=gap_count,
        partial_count=partial_count,
        pass_count=pass_count,
        pipeline_fault_count=pipeline_fault_count,
        by_status=by_status,
        entries=tuple(entries),
    )


def compose_methods_disclosure(
    coverage: FrameCoverageReport,
) -> str:
    """Compose the Methods-section snippet disclosing frame gap
    count. Attached to report.md so clinicians see at a glance
    how many contract slots weren't fully populated.

    Deterministic prose; no LLM. Three shapes:
      - all-pass (zero partial, zero gap, zero pipeline-fault)
      - partial-only (some partial, no gap, no pipeline-fault)
      - gaps-present (at least one retrieval gap)
      - pipeline-fault (surfaces separately; Codex M-60 Medium)
    """
    # FX-07 (I-ready-017) leg 1: a slot can be status=PASS yet its evidence is
    # only abstract_only / metadata_only (NOT full text). Those count toward
    # pass_count, so the old "all N populated with bound evidence" footer
    # contradicted the body ("did not survive strict verification" / abstract-
    # only). Surface shallow-provenance pass entries as a disclosed gap; only
    # claim "all bound" when every pass entry is full-text (open_access).
    _SHALLOW_PROVENANCE = {
        ProvenanceClass.ABSTRACT_ONLY.value,
        ProvenanceClass.METADATA_ONLY.value,
    }
    shallow_entries = [
        e for e in coverage.entries
        if e.status == ValidationVerdict.PASS.value
        and e.provenance_class in _SHALLOW_PROVENANCE
    ]
    shallow_count = len(shallow_entries)
    fully_bound_count = coverage.pass_count - shallow_count

    has_issues = (
        coverage.frame_gap_count
        or coverage.partial_count
        or coverage.pipeline_fault_count
        or shallow_count
    )
    if not has_issues:
        return (
            f"Frame coverage: all {coverage.total_entities} "
            f"contract-required entities populated with bound evidence."
        )

    lines = [
        "Frame coverage disclosure (V30 Report Contract):",
        (
            f"  - Total contract-required entities: "
            f"{coverage.total_entities}"
        ),
        f"  - Fully populated (full-text bound evidence): {fully_bound_count}",
    ]
    if shallow_count:
        shallow_names = ", ".join(
            sorted(e.entity_id for e in shallow_entries)
        )
        lines.append(
            f"  - Populated from abstract/metadata only (full text NOT "
            f"retrieved): {shallow_count} ({shallow_names})"
        )
    if coverage.partial_count:
        lines.append(
            f"  - Partial coverage (below min_fields or unbound "
            f"citation): {coverage.partial_count}"
        )
    if coverage.frame_gap_count:
        lines.append(
            f"  - Unretrievable (paywalled with no OA/abstract): "
            f"{coverage.frame_gap_count}"
        )
    if coverage.pipeline_fault_count:
        # Codex M-60 audit Medium: distinct line item. A pipeline
        # fault is NOT an unretrievable paywalled gap — it's an
        # engineering bug (M-56 failed to produce a row for a
        # contracted entity). Surface it explicitly so readers
        # don't mistake it for an expected retrieval failure.
        lines.append(
            f"  - Pipeline faults (engineer investigation "
            f"required): {coverage.pipeline_fault_count}"
        )
    lines.append(
        "  - Gap slots render explicit gap language in the "
        "relevant subsection; see manifest.json "
        "frame_coverage_report for per-slot detail."
    )
    return "\n".join(lines)


def compose_human_completion_tasks(
    coverage: FrameCoverageReport,
) -> list[dict[str, Any]]:
    """Compose M-61 hybrid-completion task list (Path B).

    Codex plan review #6 + M-60 audit Blocker: M-61 must receive
    per-entity doi/pmid/required_fields/failure_reason. Each
    task dict now carries the full contract's required_fields
    list plus a failure-specific `needs` string telling the
    operator what the curator must deliver for this entry.

    M-60 provides the upstream source here; M-61's own layer
    threads provenance attestation (artifact hash, retention,
    curator_id) when the operator fulfills the task.

    Returns JSON-serializable list of task dicts; caller writes
    to human_gap_tasks.json or equivalent.

    Pipeline-fault entries (is_pipeline_fault=True) are NOT
    included — those need engineer attention, not curator
    attention.
    """
    tasks: list[dict[str, Any]] = []
    for entry in coverage.entries:
        if not entry.human_completion_eligible:
            continue
        if entry.is_pipeline_fault:
            # Defensive: human_completion_eligible should already
            # be False for pipeline faults, but guard explicitly.
            continue
        tasks.append({
            "entity_id": entry.entity_id,
            "entity_type": entry.entity_type,
            "slot_id": entry.slot_id,
            "section": entry.section,
            "subsection_title": entry.subsection_title,
            "doi": entry.doi,
            "pmid": entry.pmid,
            "failure_reason": entry.failure_reason,
            "status": entry.status,
            "retrieval_attempt_log": entry.retrieval_attempt_log,
            "available_artifacts": entry.available_artifacts,
            # Codex M-60 audit Blocker: M-61 task payload must
            # carry required_fields so the operator knows what to
            # deliver. Also include min_fields_for_completion so
            # the curator sees the success threshold.
            "required_fields": list(entry.required_fields),
            "min_fields_for_completion": entry.min_fields_for_completion,
            "needs": _compose_task_needs(entry),
        })
    return tasks


def _compose_task_needs(entry: SlotCoverageEntry) -> str:
    """Failure-specific operator guidance.

    Codex M-60 audit pass-2 realignment: this function is ONLY
    called for curator-actionable entries (engineer-owned statuses
    and already-passing entries are filtered upstream by
    `_is_curator_actionable`). So only two branches matter:

      - gap row: RETRIEVAL guidance (curator provides licensed
        content to fill the primary-publication gap).
      - non-gap row with fail_min_fields: EXTRACTION guidance
        (curator provides richer licensed copy to cover fields
        that M-56's abstract / metadata couldn't supply).

    Any other status reaching here is a routing bug — emit a
    defensive catch-all so it shows up in manifest rather than
    being silently invisible.
    """
    required_csv = ", ".join(entry.required_fields) or "(none declared)"
    if entry.provenance_class == "frame_gap_unrecoverable":
        return (
            f"RETRIEVAL gap: source not reachable via open-access, "
            f"abstract, or metadata paths. Operator must provide "
            f"direct_quote from a licensed copy covering at least "
            f"{entry.min_fields_for_completion} of "
            f"[{required_csv}], with structured provenance "
            f"(artifact hash, retention pointer, curator_id)."
        )
    if entry.status == "fail_min_fields":
        return (
            f"EXTRACTION gap: retrieval succeeded but only a "
            f"subset of required fields was extractable from the "
            f"available content. Operator must supplement with "
            f"a direct_quote from a richer licensed copy covering "
            f"the missing fields in [{required_csv}]."
        )
    # Defensive catch-all. Should not fire if _is_curator_actionable
    # is kept in sync with this function. Surface the routing drift
    # loudly in the manifest rather than silently mislabeling it.
    return (
        f"ROUTING CHECK: entry status={entry.status!r} reached "
        f"the curator task composer but does not match a known "
        f"curator-actionable case. Verify "
        f"_is_curator_actionable / _compose_task_needs alignment."
    )


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _is_curator_actionable(is_gap_row: bool, status: str) -> bool:
    """Codex M-60 audit pass-2 + pass-3: strict allowlist of
    curator-actionable (status, row-type) combinations.

    Pass-3 residual: pass-2 used a denylist that defaulted unknown
    statuses to True. A future verdict added without updating this
    predicate would silently route to curator. Pass-3 switches to
    an allowlist so new statuses default to engineer routing.

    Curator-actionable:
      (gap,     FAIL_MIN_FIELDS)      — gap row, curator can
                                        supply licensed content
      (gap,     FAIL_MISSING_PAYLOAD) — gap row, M-58 never ran
                                        or couldn't run
      (non-gap, FAIL_MIN_FIELDS)      — retrieval worked but
                                        extraction fell short;
                                        curator supplies richer copy

    NOT curator-actionable (engineer or no-op):
      (any,     PASS)                 — nothing to do
      (any,     FAIL_UNBOUND_CITATION) — M-58 render wiring
      (any,     FAIL_GAP_NO_LANGUAGE)  — M-58 gap-template
      (any,     FAIL_PAYLOAD_MISMATCH) — pipeline crossed wires
      (non-gap, FAIL_MISSING_PAYLOAD)  — non-gap without payload
                                        usually means M-58
                                        didn't run; engineer
                                        attention more likely
                                        than curator content

    Any (row_type, status) not in the allowlist defaults to
    engineer routing. New verdicts MUST be explicitly added.
    """
    curator_actionable = {
        (True,  ValidationVerdict.FAIL_MIN_FIELDS.value),
        (True,  ValidationVerdict.FAIL_MISSING_PAYLOAD.value),
        (False, ValidationVerdict.FAIL_MIN_FIELDS.value),
    }
    return (is_gap_row, status) in curator_actionable


def _available_artifacts(row: FrameRow) -> list[str]:
    """Deterministic ordered list of artifact kinds M-56 produced
    for this entity. M-61 operator dashboard shows this so the
    curator sees what's already available (e.g. "oa_pdf_url" means
    the operator can fetch full-text; "metadata_only" means they
    need to supply everything). For HUMAN_CURATED rows, adds
    "human_curated_provenance" so auditors see the structured
    evidence is attached."""
    out: list[str] = []
    if row.oa_pdf_url:
        out.append("oa_url")
    if row.direct_quote:
        out.append(row.quote_source)
    if row.title:
        out.append("crossref_metadata")
    if row.doi:
        out.append("doi")
    if row.pmid:
        out.append("pmid")
    if row.url:
        out.append("url_pattern")
    if row.human_curated_provenance is not None:
        out.append("human_curated_provenance")
    return out


def _failure_reason(
    row: FrameRow, status: str, validator_reason: str,
) -> str | None:
    """Compose a single failure_reason string per manifest
    consumers' expectations. Gap rows carry M-56's failure_reason;
    partial/unbound rows carry M-59's validator reason.

    The pipeline-fault path is handled by `_empty_coverage_entry`,
    not by this function.
    """
    if row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        return row.failure_reason
    if status == ValidationVerdict.PASS.value:
        return None
    return validator_reason or "unknown"


def _empty_coverage_entry(
    slot_id: str,
    entity_id: str,
    entity_type: str,
    section: str,
    subsection_title: str,
    status: str,
    validator_reason: str,
    required_fields: list[str],
    min_fields_for_completion: int,
) -> SlotCoverageEntry:
    """Fallback for the (should-not-happen) case where a FrameRow
    is missing for a contracted entity.

    Codex M-60 audit Medium fix: this is a pipeline-integrity
    fault, not a retrieval gap. Pipeline-fault message dominates
    validator wording so engineers see the root cause first. NOT
    routed to human completion — a curator cannot fix a pipeline
    bug.
    """
    # Prepend the pipeline-fault diagnosis so it leads. Append
    # validator wording only if it adds specificity.
    pipeline_msg = (
        "FrameRow missing for contracted entity — M-56 did not "
        "produce a row (pipeline crossed wires; engineer "
        "attention required)"
    )
    failure_reason = (
        f"{pipeline_msg}; validator also noted: {validator_reason}"
        if validator_reason
        else pipeline_msg
    )
    return SlotCoverageEntry(
        slot_id=slot_id,
        entity_id=entity_id,
        entity_type=entity_type,
        section=section,
        subsection_title=subsection_title,
        status=status,
        provenance_class="pipeline_fault",
        failure_reason=failure_reason,
        retrieval_attempt_log=[],
        available_artifacts=[],
        # Codex M-60 audit Medium: do NOT route pipeline faults to
        # human completion. A curator cannot reconcile a missing
        # M-56 row; this needs engineer intervention.
        human_completion_eligible=False,
        is_pipeline_fault=True,
        required_fields=required_fields,
        min_fields_for_completion=min_fields_for_completion,
        doi=None,
        pmid=None,
        human_curated_provenance=None,
    )
