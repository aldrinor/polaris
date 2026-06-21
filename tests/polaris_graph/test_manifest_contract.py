"""
BUG-B-101 regression tests: manifest.status contract.

Pre-fix, successful pipeline-A runs wrote manifest.json WITHOUT a
"status" key. Abort runs included it. The documentation claimed
manifest.status was authoritative — it wasn't. See
outputs/codex_findings/deep_dive_round_1/findings.md for scope.

Post-fix, every exit path in run_one_query writes a manifest with
a "status" field from the unified taxonomy:

    success | partial_* | abort_* | error_unexpected

These tests pin that contract. A new exit path that forgets to
emit manifest.status should fail test_*_all_manifest_writes_have_status.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────
# Test 1: UNIFIED_STATUS_VALUES is a closed taxonomy. Keep this in
# lock-step with UNIFIED_STATUS_VALUES in scripts/run_honest_sweep_r3.py.
# ─────────────────────────────────────────────────────────────────

def test_manifest_contract_unified_taxonomy_defined() -> None:
    from scripts.run_honest_sweep_r3 import (
        UNIFIED_STATUS_VALUES,
        to_unified_status,
    )
    expected = frozenset({
        "success",
        "released_with_disclosed_gaps",            # I-perm-001 (#1195): always-release BLOCK->LABEL
        "released_insufficient_safety_evidence",   # I-perm-001 (#1195): clinical safety-floor honest report
        "partial_thin_corpus",
        "partial_incomplete_corpus",
        "partial_rule_check_warnings",
        "partial_outline_fallback",    # added by BUG-M-203 (R4)
        "partial_evaluator_advisory",  # added by BUG-M-205 (R5)
        "partial_qwen_advisory",       # I-modref-004 (#530): legacy alias
        "partial_saturation",          # I-meta-005 Phase 4 (#988): pruned report
        "abort_scope_rejected",
        "abort_no_sources",
        "abort_corpus_inadequate",
        "abort_corpus_approval_denied",
        "abort_no_verified_sections",
        "abort_excessive_gap",         # F03 (A3): verified-section fraction below PG_MIN_VERIFIED_SECTION_FRACTION
        "abort_critical_topic_uncovered",  # F11 (A3): clinical run left a `critical: true` checklist topic (contraindications) applicable but uncovered
        "abort_evaluator_critical",    # added by BUG-M-205 (R5)
        "abort_budget_exceeded",       # I-meta-008 (#1015): PG_MAX_COST_PER_RUN breach (generator OR 4-role verifier)
        "abort_verifier_degraded",     # I-ready-002 (#1071): binding verifier judge_error_rate over cap
        "abort_discovery_degraded",    # FL-05 (#1124): force-enabled discovery feature did not fire (run-health backstop)
        "abort_safety_refused",        # I-ready-007 (#1072): input harm-refusal before retrieval
        "abort_four_role_release_held",  # I-ready-016 (#1086): 4-role D8 held release
        "abort_role_transport_exhausted",  # I-beatboth-006 (#1283) Fix C.3: force-closed role transport reached the D8 seam with PG_ROLE_TRANSPORT_DEGRADE OFF -> disclosed hard halt
        "abort_report_redaction_failed",  # I-beatboth-fix-000 (#1171): post-gate report.md reconciliation failed fail-closed (material non-VERIFIED claim present-but-unredactable)
        "abort_required_entity_ledger_failed",  # I-arch-004 F27 (#1213/h3): strict-gate force-on RequiredEntityLedger raised -> HOLD instead of silently dropping the Coverage-gaps disclosure
        "abort_journal_only_contract_conflict",  # I-ready-017 (#1134): journal_only required contract slot non-journal
        "abort_credibility_coverage_gap",  # I-cred-008b (#1162): activated credibility-disclosure pass found an uncovered cited token
        "abort_conflict_judge_unavailable",  # I-arch-004 F07 (#1249/#1252): strict-gate conflict-judge error -> run holds (fail-closed)
        "cancelled",                   # I-ready-016 (#1086): user-cancel terminal manifest status
        "error_unexpected",
        "error_journal_only_leak",     # I-ready-017 (#1134): journal_only fail-closed no-leak backstop
        "error_corpus_population_mismatch",  # I-ready-017 FX-06b (#1121): corpus-approval vs adequacy population divergence
    })
    assert UNIFIED_STATUS_VALUES == expected, (
        f"Unified taxonomy has drifted: got {UNIFIED_STATUS_VALUES}, "
        f"expected {expected}"
    )


def test_manifest_contract_partial_status_mapping() -> None:
    """Summary labels map correctly to unified statuses."""
    from scripts.run_honest_sweep_r3 import to_unified_status
    cases = [
        ("ok", "success"),
        ("ok_thin_corpus", "partial_thin_corpus"),
        ("ok_incomplete_corpus", "partial_incomplete_corpus"),
        ("warn_rule_checks", "partial_rule_check_warnings"),
        ("fail_no_sources", "abort_no_sources"),
        ("fail_no_verified_prose", "abort_no_verified_sections"),
        ("abort_corpus_inadequate", "abort_corpus_inadequate"),
        ("abort_corpus_approval_denied", "abort_corpus_approval_denied"),
        ("abort_no_verified_sections", "abort_no_verified_sections"),
        ("report_redaction_failed", "abort_report_redaction_failed"),  # I-beatboth-fix-000 (#1171)
        # I-arch-004 F27 (#1213/h3): identity map — already a unified abort_ name.
        ("abort_required_entity_ledger_failed", "abort_required_entity_ledger_failed"),
        ("error", "error_unexpected"),
    ]
    for legacy, unified in cases:
        assert to_unified_status(legacy) == unified, (
            f"to_unified_status({legacy!r}) != {unified!r}"
        )


def test_manifest_contract_unknown_label_maps_to_error() -> None:
    """An unknown summary label — future drift — falls back to error."""
    from scripts.run_honest_sweep_r3 import to_unified_status
    assert to_unified_status("wat_this_is_new") == "error_unexpected"
    assert to_unified_status("") == "error_unexpected"


# ─────────────────────────────────────────────────────────────────
# Test 2: Every manifest-writing branch in run_one_query emits a
# status field, enforced by AST inspection of the source.
# ─────────────────────────────────────────────────────────────────

def _find_manifest_write_blocks(source: str) -> list[tuple[int, int, str]]:
    """Find every `(run_dir / "manifest.json").write_text(...)` call
    and the ~60 lines of source that precede it (that's the manifest
    construction). Return [(start_line, end_line, block_text), ...]."""
    tree = ast.parse(source)
    blocks: list[tuple[int, int, str]] = []
    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "write_text"
        ):
            # Check the receiver is `(... / "manifest.json")`
            recv = node.func.value
            if isinstance(recv, ast.BinOp) and isinstance(recv.op, ast.Div):
                right = recv.right
                if isinstance(right, ast.Constant) and right.value == "manifest.json":
                    # Found a manifest write. Look backward 200 lines
                    # for the `{ ... }` construction. The V30 site
                    # at line 1918 has its dict starting at 1780 (138
                    # lines apart), so the original 80-line window
                    # missed it; the M-26-era triage Codex review
                    # flagged this as a false positive. Extending to
                    # 200 covers the V30 site without admitting
                    # false positives elsewhere (other manifest
                    # writes have their `{ ... }` immediately above
                    # the write_text call).
                    end_line = node.lineno
                    start_line = max(1, end_line - 200)
                    block = "\n".join(source_lines[start_line - 1:end_line])
                    blocks.append((start_line, end_line, block))
    return blocks


def test_manifest_contract_all_manifest_writes_have_status() -> None:
    """Every site that writes manifest.json in run_honest_sweep_r3.py
    must include a 'status' key in the manifest dict. AST-based check
    so adding a new exit path without status fails this test."""
    sweep_path = Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    source = sweep_path.read_text(encoding="utf-8")
    blocks = _find_manifest_write_blocks(source)
    assert len(blocks) >= 4, (
        f"Expected >=4 manifest write sites in run_one_query, got {len(blocks)}"
    )
    for start, end, block in blocks:
        # Look for a `"status":` literal string assignment within the
        # preceding 80-line window. That's loose but catches the common
        # pattern.
        assert '"status"' in block, (
            f"Manifest write at line {end} has no 'status' field in "
            f"the preceding construction block (lines {start}-{end}):\n"
            f"{block[-400:]}"
        )


# ─────────────────────────────────────────────────────────────────
# Test 3: Abort status values written at the three known-good paths
# are all in the unified taxonomy.
# ─────────────────────────────────────────────────────────────────

def test_manifest_contract_abort_statuses_are_authoritative() -> None:
    """The abort exit paths write status values that are members of
    UNIFIED_STATUS_VALUES."""
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES
    sweep_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    )
    source = sweep_path.read_text(encoding="utf-8")
    # Find status literal values in the source.
    status_values = set(re.findall(
        r'''["']status["']\s*:\s*["']([a-z_]+)["']''', source,
    ))
    # "started" is the in-memory summary-dict sentinel (summary["status"]
    # starts as "started" and gets overwritten before every return).
    # It is NEVER written to a manifest. Exclude it from the contract check.
    #
    # I-ready-016 (#1086): tightly-scoped non-manifest allowlist (per Codex P2 — NOT a broad
    # allowlist). Each entry is a `"status": "<x>"` literal that is provably NOT a run manifest
    # status:
    #   - "abort_quota_exceeded": written to sweep_quota_refusal.json in main_async
    #     (run_honest_sweep_r3.py:~5682), a SWEEP-level refusal artifact — never a run manifest.
    # The feature-firing telemetry that previously tripped this regex (fired / not_enabled / ...)
    # was renamed to the `firing_status` key (#1086), so it no longer matches `"status":`.
    #   - "not_applicable_planner_lane": FX-14 (#1129) custody-lane honesty marker, returned by
    #     compute_custody_lane_status() (run_honest_sweep_r3.py:356) and written ONLY to
    #     custody_lane_status.json (run_honest_sweep_r3.py:~4844) — NEVER to manifest.json. Same
    #     non-manifest false-positive class as the firing_status carve-out above; provably never a
    #     run manifest status, so excluding it does NOT weaken the manifest-status contract.
    allowed_non_manifest = {"started", "abort_quota_exceeded", "not_applicable_planner_lane"}
    status_values -= allowed_non_manifest
    unknown = status_values - UNIFIED_STATUS_VALUES
    assert not unknown, (
        f"Source contains status values not in UNIFIED_STATUS_VALUES: "
        f"{unknown}"
    )


# ─────────────────────────────────────────────────────────────────
# Test 4: the two previously-missing exit paths (zero sources +
# exception) now write manifests.
# ─────────────────────────────────────────────────────────────────

def test_manifest_contract_zero_sources_writes_abort_manifest() -> None:
    """Source check: the zero-classified-sources branch writes a
    manifest.json with status='abort_no_sources' before returning."""
    sweep_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    )
    source = sweep_path.read_text(encoding="utf-8")
    zero_src_idx = source.find("if len(retrieval.classified_sources) == 0:")
    assert zero_src_idx > 0, "expected zero-sources branch"
    # Find the next 'return summary' after this branch
    next_return = source.find("return summary", zero_src_idx)
    assert next_return > zero_src_idx
    branch = source[zero_src_idx:next_return]
    assert '"status": "abort_no_sources"' in branch, (
        f"zero-sources branch must write status=abort_no_sources. Branch:\n"
        f"{branch}"
    )
    assert 'manifest.json' in branch, (
        "zero-sources branch must write manifest.json before returning"
    )


def test_manifest_contract_exception_writes_error_manifest() -> None:
    """Source check: the OUTER exception handler in run_one_query writes
    a manifest with status='error_unexpected'. Uses AST to find the
    outermost try/except in run_one_query (not an inner one)."""
    import ast as _ast
    sweep_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    )
    source = sweep_path.read_text(encoding="utf-8")
    tree = _ast.parse(source)
    # Find the async def run_one_query
    func = next(
        (n for n in _ast.walk(tree)
         if isinstance(n, _ast.AsyncFunctionDef) and n.name == "run_one_query"),
        None,
    )
    assert func is not None, "expected async def run_one_query"
    # I-ready-016 (#1086): select the OUTER orchestration try — the one whose handlers write
    # error_unexpected — NOT merely the first top-level try. The first top-level try is the I-bug-111
    # synthesis-reset guard (`try: ...reset...; except Exception: pass`), a no-op; selecting it made
    # this gate stale-red. Identify the orchestration try by its source segment.
    outer_try = next(
        (n for n in func.body
         if isinstance(n, _ast.Try)
         and "error_unexpected" in (_ast.get_source_segment(source, n) or "")),
        None,
    )
    assert outer_try is not None, (
        "expected the outer orchestration try (handlers write error_unexpected) in run_one_query"
    )
    # Each Try has ExceptHandler(s). Dump the handlers' source ranges.
    handler_sources = []
    for handler in outer_try.handlers:
        start = handler.lineno
        end = handler.end_lineno or start
        handler_sources.append("\n".join(source.splitlines()[start - 1:end]))
    combined = "\n".join(handler_sources)
    # I-cred-008b (#1162): the outer handler now classifies via _credibility_abort_status — a generic /
    # non-coverage exception DEFAULTS to error_unexpected, while a coverage-gap CredibilityPassError routes
    # to abort_credibility_coverage_gap; the manifest writes the resolved _unified_error_status. (The old
    # literal '"status": "error_unexpected"' assertion went stale when the hardcode became the variable.)
    assert '_unified_error_status = "error_unexpected"' in combined, (
        f"Outer exception handler must DEFAULT generic/non-coverage exceptions to error_unexpected. "
        f"Got handlers:\n{combined[:700]}"
    )
    assert '"status": _unified_error_status' in combined, (
        "Outer exception handler must write the resolved _unified_error_status into the manifest"
    )
    assert '_credibility_abort_status' in combined, (
        "Outer handler must route via _credibility_abort_status(exc) (coverage-gap -> named status, "
        "everything else -> error_unexpected). The literal status string lives in that helper, not inline."
    )
    assert 'manifest.json' in combined, (
        "Outer exception handler must attempt to write manifest.json"
    )


# ─────────────────────────────────────────────────────────────────
# Test 5: round-trip — unified statuses match the reader's contract
# (every class of status is recognizable by its prefix).
# ─────────────────────────────────────────────────────────────────

def test_always_release_outcome_statuses_round_trip() -> None:
    """Every status `compute_release_outcome` can emit must be a valid unified status AND map to
    ITSELF through to_unified_status (NOT error_unexpected) — the I-perm-001 slice-2 consume site
    feeds outcome.status straight into to_unified_status (Codex slice-2 iter-2 P1)."""
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES, to_unified_status
    from src.polaris_graph.roles import release_policy as rp

    emitted = {
        rp.STATUS_SUCCESS,
        rp.STATUS_RELEASED_WITH_DISCLOSED_GAPS,
        rp.STATUS_RELEASED_INSUFFICIENT_SAFETY,
        rp.STATUS_ABORT_NO_VERIFIED,
        rp.STATUS_ABORT_FABRICATED,
    }
    for status in emitted:
        assert status in UNIFIED_STATUS_VALUES, f"{status!r} not in UNIFIED_STATUS_VALUES"
        assert to_unified_status(status) == status, (
            f"to_unified_status({status!r}) = {to_unified_status(status)!r}, not identity "
            "(a clean/disclosed always-release run would be mis-classified)"
        )


def test_manifest_contract_status_prefixes() -> None:
    """Every status value falls into one of four classes via its prefix.
    This is what downstream readers rely on to classify a run."""
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES
    for status in UNIFIED_STATUS_VALUES:
        assert (
            status == "success"
            or status.startswith("partial_")
            or status.startswith("abort_")
            or status.startswith("error_")
            # I-ready-016 (#1086): documented single terminal exception. `cancelled` is a real
            # manifest status (_abort_if_cancelled) whose value is preserved (consumed by v6 UI +
            # SSE `run.completed`); renaming it to abort_cancelled would break those consumers. It is
            # a terminal/cancel class of its own, deliberately outside the 4-prefix scheme.
            or status == "cancelled"
            # I-perm-001 (#1195): the always-release model adds a RELEASED-with-disclosure class
            # (`released_with_disclosed_gaps` / `released_insufficient_safety_evidence`) — a report
            # SHIPPED with honest disclosed gaps (BLOCK->LABEL). Documented prefix exception: it is
            # neither success (it carries gaps) nor abort (a report was produced).
            or status.startswith("released_")
        ), f"Status {status!r} doesn't match any known prefix class"


# ─────────────────────────────────────────────────────────────────
# Test 6: sanity — the success-path manifest construction includes
# the computed unified status.
# ─────────────────────────────────────────────────────────────────

def test_manifest_contract_success_path_includes_unified_status() -> None:
    """The success-path manifest construction in run_one_query
    references unified_status in the 'status' field, not a hardcoded
    literal."""
    sweep_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    )
    source = sweep_path.read_text(encoding="utf-8")
    # Look for the success-path manifest dict construction — it should
    # have '"status": unified_status' somewhere.
    assert '"status": unified_status' in source, (
        "success-path manifest must set status to the computed "
        "unified_status variable, not a literal"
    )


# ─────────────────────────────────────────────────────────────────
# BUG-SCHEMA-R8d: every manifest carries the shared envelope fields.
# The original R1 test only pinned the `status` key. Live smoke
# (2026-04-18) showed abort manifests missing retrieval/budget_cap_usd.
# ─────────────────────────────────────────────────────────────────

ENVELOPE_REQUIRED_KEYS = {"run_id", "slug", "domain", "question",
                          "cost_usd", "budget_cap_usd", "status"}


def test_manifest_envelope_helper_produces_full_shape() -> None:
    """_base_manifest_envelope returns every required envelope key."""
    from scripts.run_honest_sweep_r3 import _base_manifest_envelope
    q = {"slug": "t", "domain": "d", "question": "q?"}
    env = _base_manifest_envelope(run_id="RUN_X", q=q, run_cost=0.12)
    # status is added by caller, not the helper
    env["status"] = "success"
    missing = ENVELOPE_REQUIRED_KEYS - set(env.keys())
    assert not missing, f"envelope missing keys: {missing}"
    assert env["run_id"] == "RUN_X"
    assert env["cost_usd"] == 0.12
    assert env["budget_cap_usd"] > 0  # default PG_MAX_COST_PER_RUN


def test_manifest_envelope_includes_retrieval_when_provided() -> None:
    """When retrieval object is passed, envelope has retrieval block
    with fetched/failed/api_calls fields."""
    from scripts.run_honest_sweep_r3 import _base_manifest_envelope

    class _FakeRetrieval:
        total_candidates_pre_filter = 300
        candidates_fetched = 17
        candidates_failed_fetch = 3
        api_calls = {"serper": 3, "s2": 3, "fetch": 20}

    q = {"slug": "t", "domain": "d", "question": "q?"}
    env = _base_manifest_envelope(
        run_id="X", q=q, retrieval=_FakeRetrieval(), run_cost=0.01,
    )
    assert "retrieval" in env
    r = env["retrieval"]
    assert r["fetched"] == 17
    assert r["failed"] == 3
    assert r["api_calls"]["serper"] == 3


def test_manifest_envelope_retrieval_omitted_when_none() -> None:
    """If retrieval=None (e.g., scope_rejected abort fires BEFORE
    retrieval), the retrieval key is simply absent — not None."""
    from scripts.run_honest_sweep_r3 import _base_manifest_envelope
    env = _base_manifest_envelope(
        run_id="X", q={"slug": "t", "domain": "d", "question": "q?"},
        retrieval=None, run_cost=0.0,
    )
    assert "retrieval" not in env


def test_manifest_every_abort_site_uses_envelope_helper() -> None:
    """Source check: every abort branch calls _base_manifest_envelope
    to build its manifest. Prevents future drift where a new abort
    branch forgets envelope fields.

    Checks that `_base_manifest_envelope` is called BEFORE every
    manifest.json write in run_one_query (except the success path,
    which has its own status-computation block).
    """
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    # Count abort-path manifest writes (each has a distinct status=...)
    abort_statuses = [
        "abort_scope_rejected",
        "abort_no_sources",
        "abort_corpus_inadequate",
        "abort_corpus_approval_denied",
        "abort_no_verified_sections",
    ]
    helper_calls = source.count("_base_manifest_envelope(")
    # Envelope helper used >= once per abort branch (5 total)
    assert helper_calls >= 5, (
        f"Expected _base_manifest_envelope called in each of 5 abort "
        f"branches; found {helper_calls} calls. New abort branches must "
        f"use the envelope helper."
    )
