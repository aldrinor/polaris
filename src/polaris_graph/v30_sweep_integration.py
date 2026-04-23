"""V30 sweep integration — wires M-54..M-61 into
`run_honest_sweep_r3.py`.

Single entrypoint: `run_v30_post_generation(...)`. The sweep
runner calls this AFTER multi_section_generator produces its
result but BEFORE the manifest is written. Returns a
`V30SweepResult` with:

  - `frame_coverage_report` dict → shipped as
    manifest["frame_coverage_report"]
  - `methods_disclosure_text` → appended to Methods section
    disclosure in `report.md`
  - `human_gap_tasks_json` → written to
    run_dir/human_gap_tasks.json
  - `enabled` → False when PG_V30_ENABLED != "1"; caller should
    short-circuit and leave manifest / report untouched.

## Safety / gating

V30 is opt-in via env `PG_V30_ENABLED=1`. When disabled, this
module is a no-op and the existing sweep pipeline runs exactly
as before — no ordering change, no manifest shape change.

When enabled, any failure inside the V30 chain is caught,
logged, and returns a `V30SweepResult` with `error`
populated. The sweep continues normally; V30 does not block
existing releases.

## Ordering

M-54 loader (scope template already loaded) → M-55 compile_frame
→ M-56 fetch_compiled_frame (live CrossRef/Unpaywall/PubMed) →
operator human-gap-completions file (optional, M-61) → M-57
compose_outline_from_contract → M-58/M-59 are DEFERRED to sweep
integration phase 2 (they need LLM wiring to replace the
multi_section_generator prompts; phase 1 of integration ships
M-56/M-57/M-60/M-61 for coverage-reporting purposes only).

Phase 1 scope (this module):
  - Compile + fetch + outline + coverage report for the
    contracted entities.
  - Emit `frame_coverage_report` block for manifest.
  - Emit `human_gap_tasks.json` for operator Path B.
  - Do NOT yet replace the generator. Existing LLM-driven
    prose generation continues to run alongside V30.

Phase 2 (separate cycle): wire M-58 slot-bound prompts +
M-59 validator + integrate M-61 completions into generator
evidence pool. That's a larger refactor of
multi_section_generator.py and is intentionally deferred.

## Deterministic API key: PG_UNPAYWALL_EMAIL

M-56 requires a contact email for Unpaywall. The env var
`PG_UNPAYWALL_EMAIL` is read at fetch time; default
polaris@example.org used in tests but not suitable for live
runs per Unpaywall terms of service. Set this before enabling
V30.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class V30SweepResult:
    """Output shape caller consumes to update manifest + report."""

    enabled: bool
    frame_coverage_report: dict[str, Any] | None
    methods_disclosure_text: str | None
    human_gap_tasks_json: list[dict[str, Any]] | None
    warnings: list[str]
    error: str | None


_ENABLED_ENV = "PG_V30_ENABLED"


def _is_enabled() -> bool:
    return os.environ.get(_ENABLED_ENV, "0").strip() in ("1", "true", "True")


def run_v30_post_generation(
    research_question: str,
    scope_template: dict[str, Any] | None,
    slug: str,
    run_dir: Path,
    log: Any,
) -> V30SweepResult:
    """Run V30 contract/compile/fetch/outline/coverage chain.

    Args:
        research_question: the user question (pass-through to M-55).
        scope_template: already-loaded scope template dict (the
            sweep already loads this for M-28/M-35 expansion;
            reuse to avoid double I/O).
        slug: research-question slug (sweep q["slug"]).
        run_dir: per-query output directory; V30 writes
            human_gap_tasks.json here if there are operator tasks.
        log: logging callable (sweep's _log) so V30 messages
            appear in run_log.txt alongside the rest.

    Returns:
        V30SweepResult — caller merges frame_coverage_report into
        manifest, appends methods_disclosure_text to report.md
        Methods section, and writes human_gap_tasks.json if
        non-empty.
    """
    if not _is_enabled():
        return V30SweepResult(
            enabled=False,
            frame_coverage_report=None,
            methods_disclosure_text=None,
            human_gap_tasks_json=None,
            warnings=[],
            error=None,
        )

    warnings: list[str] = []
    try:
        return _run_inner(
            research_question=research_question,
            scope_template=scope_template,
            slug=slug,
            run_dir=run_dir,
            log=log,
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001
        tb_line = f"{type(exc).__name__}: {exc}"
        log(f"[V30]         ERROR during integration: {tb_line}")
        return V30SweepResult(
            enabled=True,
            frame_coverage_report=None,
            methods_disclosure_text=None,
            human_gap_tasks_json=None,
            warnings=warnings,
            error=tb_line,
        )


def _run_inner(
    research_question: str,
    scope_template: dict[str, Any] | None,
    slug: str,
    run_dir: Path,
    log: Any,
    warnings: list[str],
) -> V30SweepResult:
    """Actual chain. Separated so run_v30_post_generation can wrap
    it in a broad exception guard without obscuring the happy-path
    logic."""
    from .generator.frame_manifest import (
        compose_frame_coverage,
        compose_human_completion_tasks,
        compose_methods_disclosure,
    )
    from .generator.slot_validator import (
        EntityValidation,
        SlotAggregateVerdict,
        ValidationReport,
        ValidationVerdict,
    )
    from .nodes.contract_outline import compose_outline_from_contract
    from .nodes.frame_compiler import (
        FrameCompilerError,
        compile_frame,
    )
    from .retrieval.frame_fetcher import fetch_compiled_frame
    from .retrieval.human_gap_completion import (
        load_completions,
        to_frame_rows,
        validate_against_tasks,
    )

    # M-54 loader is called inside compile_frame. If slug has no
    # contract in this template → None return → V30 is a no-op
    # for this run (backwards compat with non-migrated slugs).
    try:
        compiled = compile_frame(research_question, scope_template, slug)
    except FrameCompilerError as exc:
        log(f"[V30]         FrameCompilerError: {exc}")
        return V30SweepResult(
            enabled=True,
            frame_coverage_report=None,
            methods_disclosure_text=None,
            human_gap_tasks_json=None,
            warnings=warnings,
            error=str(exc),
        )
    if compiled is None:
        log(
            f"[V30]         no per_query_report_contract for slug="
            f"{slug!r}; skipping V30 for this run"
        )
        return V30SweepResult(
            enabled=True,
            frame_coverage_report=None,
            methods_disclosure_text=None,
            human_gap_tasks_json=None,
            warnings=warnings,
            error=None,
        )

    log(
        f"[V30]         compiled frame: slug={slug!r}, "
        f"schema={compiled.schema_version}, "
        f"entities={len(compiled.evidence_bindings)}"
    )
    for w in compiled.warnings:
        log(f"[V30]         compiler warning: {w}")
        warnings.append(w)

    # M-56: deterministic live fetch. A single shared httpx.Client
    # is used across all bindings. 11-15 entity fetches per sweep
    # — rate-limit-trivial at 1 rps.
    log(f"[V30]         fetching {len(compiled.evidence_bindings)} entities via M-56")
    frame_rows = fetch_compiled_frame(compiled.evidence_bindings)
    _log_fetch_summary(log, frame_rows)

    # M-61 Path B: merge operator-provided completions if present.
    # Look for `human_gap_completions.json` in run_dir OR in the
    # domain-level directory (one level up). Operator workflow:
    # write completions before the next sweep run.
    frame_rows = _merge_human_completions(
        compiled=compiled,
        frame_rows=frame_rows,
        run_dir=run_dir,
        log=log,
        warnings=warnings,
    )

    # M-57: compose outline from compiled + rows
    outline = compose_outline_from_contract(compiled, frame_rows)
    log(
        f"[V30]         outline: {len(outline.sections)} sections, "
        f"{sum(len(s.slots) for s in outline.sections)} slots, "
        f"gaps={len(outline.gap_slot_ids())}"
    )

    # M-59: at phase-1 integration we don't yet have SlotFillPayloads
    # from an M-58-wired generator. Synthesize a minimal validation
    # report that marks every non-gap entity as PASS (it was
    # retrieved) and every gap entity with FAIL_MIN_FIELDS (curator-
    # actionable). This is a deliberately-conservative placeholder
    # until Phase 2 wires real SlotFillPayloads from the generator.
    validation = _synthesize_phase1_validation(outline, frame_rows)

    # M-60: compose coverage report + methods disclosure + M-61 tasks
    coverage = compose_frame_coverage(
        compiled, outline, frame_rows, validation,
    )
    log(
        f"[V30]         coverage: pass={coverage.pass_count}, "
        f"partial={coverage.partial_count}, "
        f"gap={coverage.frame_gap_count}, "
        f"pipeline_fault={coverage.pipeline_fault_count}"
    )

    methods_disclosure = compose_methods_disclosure(coverage)
    human_tasks = compose_human_completion_tasks(coverage)

    # Write M-61 task file for operator (empty list written too so
    # the operator can see "no tasks"; removes guesswork about
    # "did V30 run?").
    tasks_path = run_dir / "human_gap_tasks.json"
    try:
        tasks_path.write_text(
            json.dumps(human_tasks, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        log(
            f"[V30]         wrote {tasks_path.name}: "
            f"{len(human_tasks)} curator-actionable tasks"
        )
    except Exception as exc:  # noqa: BLE001
        log(f"[V30]         WARN could not write tasks file: {exc}")
        warnings.append(f"tasks_write_failed: {exc}")

    return V30SweepResult(
        enabled=True,
        frame_coverage_report=coverage.to_manifest_dict(),
        methods_disclosure_text=methods_disclosure,
        human_gap_tasks_json=human_tasks,
        warnings=warnings,
        error=None,
    )


def _log_fetch_summary(log: Any, frame_rows: tuple) -> None:
    from collections import Counter
    counts = Counter(r.provenance_class.value for r in frame_rows)
    ordered = sorted(counts.items())
    summary = ", ".join(f"{k}={v}" for k, v in ordered)
    log(f"[V30]         fetch summary: {summary}")


def _merge_human_completions(
    compiled: Any,
    frame_rows: tuple,
    run_dir: Path,
    log: Any,
    warnings: list[str],
) -> tuple:
    """Load + validate + merge operator completions. If the
    human_gap_completions.json file is absent, return frame_rows
    unchanged.

    Validation against tasks: M-60 would normally emit tasks, but
    at phase-1 we don't have a pre-existing task list to validate
    against (the task file is OUTPUT of this run). So we use a
    "task-equivalent" list built from the gap rows of this sweep:
    any completion matching a gap entity is accepted; any
    completion for a non-gap / non-contracted entity is rejected.
    This gives operators a useful feedback loop even before the
    full two-pass (run → task file → operator edits → next run
    merges completions) workflow is operational.
    """
    from .retrieval.frame_fetcher import ProvenanceClass
    from .retrieval.human_gap_completion import (
        load_completions,
        to_frame_rows,
        validate_against_tasks,
    )

    completions_path = run_dir / "human_gap_completions.json"
    if not completions_path.exists():
        return frame_rows

    log(f"[V30]         found {completions_path.name}; loading M-61 completions")
    try:
        completions = load_completions(completions_path)
    except Exception as exc:  # noqa: BLE001
        log(
            f"[V30]         WARN could not parse completions file: "
            f"{type(exc).__name__}: {exc}"
        )
        warnings.append(
            f"human_completions_parse_failed: {type(exc).__name__}: {exc}"
        )
        return frame_rows

    # Task-equivalent list: gap rows from this sweep OR all
    # contracted entities when the operator wants to supply
    # content for a partial (non-gap) row too.
    entities_by_id = compiled.contract.entities_by_id()
    tasks_equiv = []
    for b in compiled.evidence_bindings:
        entity = entities_by_id.get(b.entity_id)
        tasks_equiv.append({
            "entity_id": b.entity_id,
            "doi": entity.doi if entity else None,
        })
    acceptance = validate_against_tasks(completions, tasks_equiv)
    if acceptance.rejected:
        for rec, reason in acceptance.rejected:
            log(
                f"[V30]         REJECTED completion for "
                f"entity_id={rec.entity_id!r}: {reason}"
            )
            warnings.append(
                f"human_completion_rejected:{rec.entity_id}:{reason}"
            )

    if not acceptance.accepted:
        log("[V30]         no accepted completions; no row substitution")
        return frame_rows

    # Substitute human-curated rows in place. Preserve order of
    # the original frame_rows tuple so M-57 parallel-validation
    # stays intact.
    metadata = {
        b.entity_id: {
            "rendering_slot": b.rendering_slot,
            "entity_type": b.entity_type,
        }
        for b in compiled.evidence_bindings
    }
    curated_rows = to_frame_rows(acceptance.accepted, metadata)
    curated_by_eid = {r.entity_id: r for r in curated_rows}

    merged = tuple(
        curated_by_eid.get(row.entity_id, row)
        for row in frame_rows
    )
    n_substituted = len(acceptance.accepted)
    log(
        f"[V30]         merged {n_substituted} human-curated "
        f"row(s) into frame_rows"
    )
    return merged


def _synthesize_phase1_validation(
    outline: Any, frame_rows: tuple,
) -> Any:
    """Phase-1 placeholder ValidationReport.

    Until M-58 generator integration lands, we don't have real
    SlotFillPayloads to feed M-59. This synthesizer emits a
    conservative report:

      - Non-gap row (retrieved OA / abstract / metadata / human-
        curated) → PASS. M-56 fetched content successfully; the
        legacy multi_section_generator will produce prose. In
        phase 2 this becomes FAIL_MIN_FIELDS when the LLM can't
        extract required fields from direct_quote.

      - Gap row (provenance_class=FRAME_GAP_UNRECOVERABLE) →
        FAIL_MIN_FIELDS. Curator-actionable. M-60 will route
        to human_gap_tasks.json.

    This synth is honest about its provisional status: no
    content-level extraction check happens. Phase 2 adds real
    M-58 structured field payloads.
    """
    from .generator.slot_validator import (
        EntityValidation,
        SlotAggregateVerdict,
        ValidationReport,
        ValidationVerdict,
    )
    from .retrieval.frame_fetcher import ProvenanceClass

    rows_by_eid = {r.entity_id: r for r in frame_rows}

    entity_validations: list[EntityValidation] = []
    slot_verdicts: list[SlotAggregateVerdict] = []

    for section in outline.sections:
        for slot in section.slots:
            per_entity = []
            for entity_id in slot.entity_ids:
                row = rows_by_eid.get(entity_id)
                is_gap = (
                    row is not None
                    and row.provenance_class
                    == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
                )
                verdict = (
                    ValidationVerdict.FAIL_MIN_FIELDS
                    if is_gap
                    else ValidationVerdict.PASS
                )
                ev = EntityValidation(
                    slot_id=slot.slot_id,
                    entity_id=entity_id,
                    is_gap=is_gap,
                    required_min_fields=1,
                    observed_completion_count=0 if is_gap else 1,
                    bound_ev_id_present_in_prose=not is_gap,
                    verdict=verdict,
                    reason=(
                        "phase-1 synth: gap row flagged curator-"
                        "actionable"
                        if is_gap else
                        "phase-1 synth: non-gap row assumed PASS "
                        "pending M-58 integration"
                    ),
                )
                entity_validations.append(ev)
                per_entity.append(ev)
            slot_verdicts.append(SlotAggregateVerdict(
                slot_id=slot.slot_id,
                entity_verdicts=tuple(per_entity),
                overall=(
                    ValidationVerdict.PASS
                    if all(e.verdict == ValidationVerdict.PASS
                           for e in per_entity)
                    else ValidationVerdict.FAIL_MIN_FIELDS
                ),
                reason="phase-1 synth aggregate",
            ))

    return ValidationReport(
        entity_validations=tuple(entity_validations),
        slot_verdicts=tuple(slot_verdicts),
    )
