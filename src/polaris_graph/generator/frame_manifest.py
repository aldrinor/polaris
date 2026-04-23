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
    (section, subsection_title, doi, pmid) are carried so M-61
    task generation and operator dashboards don't have to re-join
    against the contract.
    """

    slot_id: str
    entity_id: str
    section: str
    subsection_title: str
    status: str                       # from ValidationVerdict enum value
    provenance_class: str
    failure_reason: str | None
    retrieval_attempt_log: list[dict[str, Any]]
    available_artifacts: list[str]
    human_completion_eligible: bool
    # Identifier echoes for M-61 consumption
    doi: str | None
    pmid: str | None


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
            "by_status": dict(self.by_status),
            "entries": [asdict(e) for e in self.entries],
        }


def compose_frame_coverage(
    compiled_frame: CompiledFrame,
    outline: ContractOutline,
    frame_rows: tuple[FrameRow, ...],
    validation_report: ValidationReport,
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

                if row is None:
                    # M-56 should have produced a row; defensive
                    # fallback.
                    entries.append(_empty_coverage_entry(
                        slot_id=slot.slot_id,
                        entity_id=entity_id,
                        section=section.section,
                        subsection_title=slot.subsection_title,
                        status=status,
                        validator_reason=reasons_by_key.get(
                            (slot.slot_id, entity_id), ""
                        ),
                    ))
                    gap_count += 1
                    continue

                is_gap_row = (
                    row.provenance_class
                    == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
                )
                is_partial_row = slot.is_partial

                if is_gap_row:
                    gap_count += 1
                elif status == ValidationVerdict.PASS.value:
                    pass_count += 1
                else:
                    # Non-gap row that failed validation counts as
                    # partial coverage (content exists but didn't
                    # meet min_fields or lacks citation).
                    partial_count += 1

                if is_partial_row and not is_gap_row:
                    # Slot has mixed outcome — flag as partial for
                    # manifest aggregate even if this specific
                    # entity passed.
                    partial_count += 0  # already counted via status

                entries.append(SlotCoverageEntry(
                    slot_id=slot.slot_id,
                    entity_id=entity_id,
                    section=section.section,
                    subsection_title=slot.subsection_title,
                    status=status,
                    provenance_class=row.provenance_class.value,
                    failure_reason=_failure_reason(
                        row, status, reasons_by_key.get(
                            (slot.slot_id, entity_id), ""
                        ),
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
                    human_completion_eligible=(
                        is_gap_row
                        or status != ValidationVerdict.PASS.value
                    ),
                    doi=row.doi,
                    pmid=row.pmid,
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
        by_status=by_status,
        entries=tuple(entries),
    )


def compose_methods_disclosure(
    coverage: FrameCoverageReport,
) -> str:
    """Compose the Methods-section snippet disclosing frame gap
    count. Attached to report.md so clinicians see at a glance
    how many contract slots weren't fully populated.

    Deterministic prose; no LLM."""
    if coverage.frame_gap_count == 0 and coverage.partial_count == 0:
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
        f"  - Fully populated: {coverage.pass_count}",
    ]
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

    Codex plan review #6: M-61 must produce a structured task
    file with per-entity doi/pmid/required_fields/failure_reason.
    M-60 provides the upstream source here; M-61's own layer
    threads provenance attestation (artifact hash, retention,
    curator_id) when the operator fulfills the task.

    Returns JSON-serializable list of task dicts; caller writes
    to human_gap_tasks.json or equivalent.
    """
    tasks: list[dict[str, Any]] = []
    for entry in coverage.entries:
        if not entry.human_completion_eligible:
            continue
        tasks.append({
            "entity_id": entry.entity_id,
            "slot_id": entry.slot_id,
            "section": entry.section,
            "subsection_title": entry.subsection_title,
            "doi": entry.doi,
            "pmid": entry.pmid,
            "failure_reason": entry.failure_reason,
            "status": entry.status,
            "retrieval_attempt_log": entry.retrieval_attempt_log,
            "available_artifacts": entry.available_artifacts,
            "needs": (
                "operator to provide direct_quote from licensed "
                "source with structured provenance (artifact hash, "
                "retention pointer)"
            ),
        })
    return tasks


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _available_artifacts(row: FrameRow) -> list[str]:
    """Deterministic ordered list of artifact kinds M-56 produced
    for this entity. M-61 operator dashboard shows this so the
    curator sees what's already available (e.g. "oa_pdf_url" means
    the operator can fetch full-text; "metadata_only" means they
    need to supply everything)."""
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
    return out


def _failure_reason(
    row: FrameRow, status: str, validator_reason: str,
) -> str | None:
    """Compose a single failure_reason string per manifest
    consumers' expectations. Gap rows carry M-56's failure_reason;
    partial/unbound rows carry M-59's validator reason."""
    if row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        return row.failure_reason
    if status == ValidationVerdict.PASS.value:
        return None
    return validator_reason or "unknown"


def _empty_coverage_entry(
    slot_id: str,
    entity_id: str,
    section: str,
    subsection_title: str,
    status: str,
    validator_reason: str,
) -> SlotCoverageEntry:
    """Fallback for the (should-not-happen) case where a FrameRow
    is missing for a contracted entity."""
    return SlotCoverageEntry(
        slot_id=slot_id,
        entity_id=entity_id,
        section=section,
        subsection_title=subsection_title,
        status=status,
        provenance_class="frame_gap_unrecoverable",
        failure_reason=(
            validator_reason
            or "FrameRow missing for contracted entity — M-56 did "
            "not produce a row (pipeline crossed wires)"
        ),
        retrieval_attempt_log=[],
        available_artifacts=[],
        human_completion_eligible=True,
        doi=None,
        pmid=None,
    )
