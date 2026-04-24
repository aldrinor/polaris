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
    """Output shape caller consumes to update manifest + report.

    `skipped_reason` is populated when V30 was enabled but could
    not produce a coverage report — e.g. slug has no contract.
    Codex sweep-integration audit Nit: lets live-run manifests
    distinguish "no V30 attempted" from "V30 skipped because of
    known non-migrated slug".
    """

    enabled: bool
    frame_coverage_report: dict[str, Any] | None
    methods_disclosure_text: str | None
    human_gap_tasks_json: list[dict[str, Any]] | None
    warnings: list[str]
    error: str | None
    skipped_reason: str | None = None


_ENABLED_ENV = "PG_V30_ENABLED"


def _is_enabled() -> bool:
    return os.environ.get(_ENABLED_ENV, "0").strip() in ("1", "true", "True")


def merge_v30_into_manifest(
    manifest: dict[str, Any], v30_result: V30SweepResult,
) -> None:
    """Runner-hook helper (Codex sweep-integration audit Medium):
    factored out of the sweep runner so the manifest merge can
    be unit-tested without running a full sweep. Mutates
    `manifest` in place per the Phase 1 contract:

      - PG_V30_ENABLED=0 → no mutation whatsoever.
      - enabled + error → manifest["v30_error"] populated.
      - enabled + skipped_reason → manifest["v30_skipped_reason"]
        populated.
      - enabled + warnings → manifest["v30_warnings"] list.
      - enabled + frame_coverage_report → inline merged.
    """
    if not v30_result.enabled:
        return
    manifest["v30_enabled"] = True
    if v30_result.frame_coverage_report is not None:
        manifest["frame_coverage_report"] = (
            v30_result.frame_coverage_report
        )
    if v30_result.skipped_reason is not None:
        manifest["v30_skipped_reason"] = v30_result.skipped_reason
    if v30_result.error is not None:
        manifest["v30_error"] = v30_result.error
    if v30_result.warnings:
        manifest["v30_warnings"] = list(v30_result.warnings)


def append_disclosure_to_report(
    report_path: Path, disclosure_text: str,
) -> bool:
    """Append the V30 Phase-1 retrieval-coverage disclosure to
    report.md.

    Runner-hook helper (Codex sweep-integration audit Medium +
    pass-4 Blocker 1: header + disclosure text both reflect
    retrieval-coverage-only semantics for Phase 1). Returns
    True on successful append, False when report.md is missing
    (never creates a disclosure-only file, matching the
    intended boundary).
    """
    if not report_path.exists():
        return False
    existing = report_path.read_text(encoding="utf-8")
    disclosure_block = (
        "\n\n---\n\n"
        "## V30 Phase-1 Retrieval Coverage Disclosure\n\n"
        f"{disclosure_text}\n"
    )
    report_path.write_text(
        existing + disclosure_block, encoding="utf-8",
    )
    return True


def run_v30_post_generation(
    research_question: str,
    scope_template: dict[str, Any] | None,
    slug: str,
    run_dir: Path,
    log: Any,
    legacy_report_text: str | None = None,
    legacy_bibliography: list[dict[str, Any]] | None = None,
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
        legacy_report_text: DEPRECATED at Phase 1 (pass-4 scope
            change). Previously used for report-coverage cross-
            check; three rounds of Codex audit showed the
            heuristic can't reliably distinguish cited from
            paraphrased / shared-locator. Retained for call-site
            backwards compatibility; value is ignored.
        legacy_bibliography: DEPRECATED at Phase 1 (same reason).
            Retained for call-site backwards compat; value is
            ignored.

    Returns:
        V30SweepResult — caller merges `frame_coverage_report`
        into manifest (field name preserved for manifest
        compatibility; its Phase-1 semantics are retrieval
        coverage only — see _synthesize_phase1_validation
        docstring + the mandatory warning emitted on every V30
        run). Caller appends methods_disclosure_text to
        report.md, and writes human_gap_tasks.json if non-empty.
    """
    if not _is_enabled():
        return V30SweepResult(
            enabled=False,
            frame_coverage_report=None,
            methods_disclosure_text=None,
            human_gap_tasks_json=None,
            warnings=[],
            error=None,
            skipped_reason=None,
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
            legacy_report_text=legacy_report_text,
            legacy_bibliography=legacy_bibliography,
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
            skipped_reason=None,
        )


def _run_inner(
    research_question: str,
    scope_template: dict[str, Any] | None,
    slug: str,
    run_dir: Path,
    log: Any,
    warnings: list[str],
    legacy_report_text: str | None = None,
    legacy_bibliography: list[dict[str, Any]] | None = None,
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
            skipped_reason="compile_frame_error",
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
            skipped_reason="no_contract_for_slug",
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
    # from an M-58-wired generator. Phase 1 ships RETRIEVAL-COVERAGE
    # semantics, NOT report-coverage: a PASS verdict means M-56
    # retrieved the entity. It does NOT claim that the legacy
    # generator cited the entity in the verified report.
    #
    # Codex sweep-integration audit pass-1→pass-3 arc: heuristic
    # cross-checks against legacy report text (anchor/label_name/
    # url_pattern word-bounded, line-granular co-occurrence)
    # kept finding false-passes and false-negatives at each
    # tightening. Rather than continue the heuristic arms race,
    # pass-4 scopes the verdict semantics to retrieval-coverage
    # ONLY and renames manifest fields accordingly.
    #
    # Phase 2 (when M-58 + M-59 replace the legacy generator)
    # will claim report-coverage truthfully because every slot
    # will have a real SlotFillPayload with a verified citation
    # token.
    validation = _synthesize_phase1_validation(
        outline=outline,
        frame_rows=frame_rows,
        compiled=compiled,
        warnings=warnings,
    )

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

    # Codex pass-4 Blocker 1: the M-60 `compose_methods_disclosure`
    # prose uses "Frame coverage" and "Fully populated with bound
    # evidence" which reads as report-coverage. Phase-1 ships
    # retrieval-coverage semantics only, so wrap the M-60 prose
    # with an explicit Phase-1 preamble that keeps the reader
    # honest. M-60 prose format is preserved (its audit chain
    # doesn't need to change); the preamble makes the semantic
    # boundary explicit in the report.md surface.
    _m60_prose = compose_methods_disclosure(coverage)
    methods_disclosure = (
        "PHASE-1 RETRIEVAL COVERAGE (V30 Report Contract, not yet "
        "report-coverage):\n"
        "  This disclosure reports whether M-56 (deterministic "
        "DOI / PMID / Unpaywall retrieval) succeeded for each "
        "contract-required entity. It does NOT claim the legacy "
        "generator cited each entity in the verified report — "
        "that validation lands in Phase 2 when M-58 slot-bound "
        "prompts replace the legacy generator.\n"
        "\n"
        f"{_m60_prose}"
    )
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
    outline: Any,
    frame_rows: tuple,
    compiled: Any,
    warnings: list[str],
) -> Any:
    """Phase-1 ValidationReport with RETRIEVAL-COVERAGE semantics.

    Pass-4 scope (post-3-round Codex audit): stop claiming report-
    coverage. Phase-1 verdicts reflect only whether M-56
    successfully retrieved each contracted entity:

      - gap row (FRAME_GAP_UNRECOVERABLE) → FAIL_MIN_FIELDS
        (curator-actionable). Retrieval failed; operator can
        provide licensed content.
      - non-gap row                       → PASS. M-56 retrieved
        the entity successfully. Phase-1 makes NO claim about
        whether the legacy generator cited the entity.

    This is narrower than the pass-1 heuristic but honest.

    Manifest key naming: the block is shipped as
    `manifest["frame_coverage_report"]` (key preserved to avoid
    breaking downstream dashboards + M-60 schema compatibility).
    The Phase-1 scope boundary is signalled through THREE
    orthogonal surfaces instead:
      1. A mandatory `phase1_retrieval_coverage_only` warning
         in `manifest.v30_warnings[]`.
      2. The report.md disclosure block is renamed to
         `## V30 Phase-1 Retrieval Coverage Disclosure` and
         prefixed with an explicit "does NOT claim ... cited
         ... in the verified report" preamble.
      3. Every PASS `EntityValidation.reason` explicitly notes
         "does NOT claim the legacy generator cited the entity
         in report.md".
    Phase 2 (when M-58 + M-59 replace the legacy generator) will
    populate `frame_coverage_report` with true report-coverage
    semantics; the manifest key stays stable across the
    transition.
    """
    from .generator.slot_validator import (
        EntityValidation,
        SlotAggregateVerdict,
        ValidationReport,
        ValidationVerdict,
    )
    from .retrieval.frame_fetcher import ProvenanceClass

    rows_by_eid = {r.entity_id: r for r in frame_rows}
    contract_entities = compiled.contract.entities_by_id()

    warnings.append(
        "phase1_retrieval_coverage_only: Phase-1 V30 "
        "manifest.frame_coverage_report reflects retrieval "
        "success only, NOT whether the legacy generator cited "
        "each entity in the verified report. Phase-2 (M-58 "
        "slot-bound generator integration) will populate the "
        "same key with true report-coverage semantics. See "
        "manifest.frame_coverage_report.entries[*].status = "
        "'pass' only confirms M-56 fetched the entity."
    )

    entity_validations: list[EntityValidation] = []
    slot_verdicts: list[SlotAggregateVerdict] = []

    for section in outline.sections:
        for slot in section.slots:
            per_entity = []
            for entity_id in slot.entity_ids:
                row = rows_by_eid.get(entity_id)
                contract_entity = contract_entities.get(entity_id)
                is_gap = (
                    row is not None
                    and row.provenance_class
                    == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
                )

                # Codex pass-4 Blocker 2: rubber-stamping every
                # non-gap row as PASS is unsafe. M-56 can emit
                # degraded rows — e.g. METADATA_ONLY with no
                # direct_quote, or ABSTRACT_ONLY that happens to
                # have empty content. Enforce a retrieval-evidence
                # guard: PASS requires row exists AND has
                # non-empty direct_quote or oa_pdf_url.
                if is_gap:
                    verdict = ValidationVerdict.FAIL_MIN_FIELDS
                    reason = (
                        "phase-1 synth (retrieval-coverage): gap "
                        "row → curator-actionable"
                    )
                    ev_cited = False
                elif row is None:
                    verdict = ValidationVerdict.FAIL_MISSING_PAYLOAD
                    reason = (
                        "phase-1 synth (retrieval-coverage): no "
                        "FrameRow for contracted entity — pipeline "
                        "crossed wires"
                    )
                    ev_cited = False
                elif not _row_has_retrieval_evidence(row):
                    # Row exists + non-gap provenance, but content
                    # is empty. Degraded retrieval — curator can
                    # supply licensed content.
                    verdict = ValidationVerdict.FAIL_MIN_FIELDS
                    reason = (
                        "phase-1 synth (retrieval-coverage): "
                        "non-gap row but direct_quote + oa_pdf_url "
                        "both empty — degraded retrieval → "
                        "curator-actionable"
                    )
                    ev_cited = False
                else:
                    verdict = ValidationVerdict.PASS
                    reason = (
                        "phase-1 synth (retrieval-coverage): M-56 "
                        "retrieved entity successfully with "
                        "non-empty evidence. NOTE: this verdict "
                        "does NOT claim the legacy generator "
                        "cited the entity in report.md — M-58 "
                        "integration (Phase 2) will add true "
                        "report-coverage validation."
                    )
                    ev_cited = True

                ev = EntityValidation(
                    slot_id=slot.slot_id,
                    entity_id=entity_id,
                    is_gap=is_gap,
                    required_min_fields=(
                        contract_entity.min_fields_for_completion
                        if contract_entity else 1
                    ),
                    observed_completion_count=(
                        0 if is_gap else 1
                    ),
                    bound_ev_id_present_in_prose=ev_cited,
                    verdict=verdict,
                    reason=reason,
                )
                entity_validations.append(ev)
                per_entity.append(ev)

            first_fail = next(
                (e for e in per_entity
                 if e.verdict != ValidationVerdict.PASS),
                None,
            )
            slot_verdicts.append(SlotAggregateVerdict(
                slot_id=slot.slot_id,
                entity_verdicts=tuple(per_entity),
                overall=(
                    ValidationVerdict.PASS if first_fail is None
                    else first_fail.verdict
                ),
                reason=(
                    f"phase-1 synth (retrieval-coverage) slot "
                    f"aggregate: "
                    f"{'all pass' if first_fail is None else first_fail.reason}"
                ),
            ))

    return ValidationReport(
        entity_validations=tuple(entity_validations),
        slot_verdicts=tuple(slot_verdicts),
    )


def _row_has_retrieval_evidence(row: Any) -> bool:
    """Codex pass-4 Blocker 2: guard against degraded non-gap
    rows. A row PASSes retrieval-coverage only if it has at
    least one form of fetched content — non-empty direct_quote
    OR an oa_pdf_url. Human-curated rows always pass (operator
    supplied content directly).

    Returns True when the row demonstrates retrieved evidence.
    """
    if row is None:
        return False
    # Human-curated rows carry operator content by definition
    from .retrieval.frame_fetcher import ProvenanceClass
    if row.provenance_class == ProvenanceClass.HUMAN_CURATED:
        return True
    has_quote = bool(row.direct_quote and row.direct_quote.strip())
    has_oa = bool(row.oa_pdf_url and row.oa_pdf_url.strip())
    return has_quote or has_oa


def _entity_cited_in_legacy(
    entity_id: str,
    contract_entity: Any,
    legacy_report_text: str | None,
    legacy_bibliography: list[dict[str, Any]] | None,
) -> bool:
    """Deprecated at Phase 1 (pass-4 scope change).

    Three rounds of Codex audit demonstrated that a heuristic
    cross-check against the legacy generator verified output cannot
    reliably distinguish cited from paraphrased or co-located with
    cited sibling. Pass-4 narrows phase-1 semantics to retrieval
    coverage only (see _synthesize_phase1_validation). This function
    is left as a no-op stub for backwards compatibility with any
    stale imports.
    """
    return False

    doi = (contract_entity.doi or "").strip()
    anchor = (contract_entity.anchor or "").strip()
    label_name = (contract_entity.label_name or "").strip()
    url_pattern = (contract_entity.url_pattern or "").strip()
    pmid_field = contract_entity.pmid
    pmid = str(pmid_field).strip() if pmid_field else ""

    # Bibliography: DOI / PMID exact match takes precedence.
    if legacy_bibliography:
        for biblio in legacy_bibliography:
            if not isinstance(biblio, dict):
                continue
            b_doi = (biblio.get("doi") or "").strip()
            b_pmid = str(biblio.get("pmid") or "").strip()
            if doi and b_doi and doi.lower() == b_doi.lower():
                return True
            if pmid and b_pmid and pmid == b_pmid:
                return True

    # Bibliography: url_pattern + entity-specific disambiguator.
    if legacy_bibliography and url_pattern:
        for biblio in legacy_bibliography:
            if not isinstance(biblio, dict):
                continue
            b_url = (biblio.get("url") or "").strip()
            if not b_url or url_pattern not in b_url:
                continue
            # Disambiguator: bibliography entry's title or name
            # must echo the entity's label_name or anchor.
            b_title = (biblio.get("title") or "").strip()
            b_name = (biblio.get("name") or "").strip()
            haystack = f"{b_title} | {b_name}"
            if label_name and _word_bounded_search(
                label_name, haystack,
            ):
                return True
            if anchor and _word_bounded_search(anchor, haystack):
                return True

    # Report text check with tighter semantics.
    if legacy_report_text:
        rt = legacy_report_text
        # DOI: word-bounded
        if doi and _word_bounded_search(doi, rt):
            return True
        # Anchor: word-bounded (handles SURPASS-1 vs SURPASS-10,
        # Merck v. Becerra vs a paraphrase containing only
        # "Merck").
        if anchor and _word_bounded_search(anchor, rt):
            return True
        # Label_name + co-locator: co-occurrence is checked at
        # LINE granularity so a report mentioning Zepbound +
        # accessdata.fda.gov on one line and Mounjaro + a
        # different url (pdf.hres.ca) on another does NOT
        # false-pass fda_mounjaro_label.
        if label_name and _word_bounded_search(label_name, rt):
            if url_pattern:
                # Must find at least one line where BOTH
                # label_name AND url_pattern appear.
                for line in rt.splitlines():
                    if (
                        _word_bounded_search(label_name, line)
                        and url_pattern in line
                    ):
                        return True
                # No line co-located → label alone + url_pattern
                # on a different line is NOT enough; fall
                # through to False.
            elif anchor:
                # Anchor is checked at line granularity too
                # for consistency.
                for line in rt.splitlines():
                    if (
                        _word_bounded_search(label_name, line)
                        and _word_bounded_search(anchor, line)
                    ):
                        return True
            else:
                # Entity has NO url_pattern AND NO anchor:
                # label_name alone is the entity's only
                # identifier (rare; statute-only entities).
                return True

    return False
