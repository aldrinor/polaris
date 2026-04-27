"""
BUG-M-207 regression tests: invariant coverage audit.

Full-audit pass 1 (round 5) surfaced the gap that no test asserted
the success-manifest schema — B-101 contract drift would not have
been caught by the pre-fix test suite.

This file is the "meta-test": for every invariant documented in
CLAUDE.md §9.1 and outputs/codex_findings/, a named test exists
that would fail if the invariant regressed. Failure of any of these
tests means either:
  (a) the invariant was silently removed / broken
  (b) the invariant was intentionally changed and the test needs
      updating — in which case, update CLAUDE.md §9 too.

Structure: each invariant has one or more "pin tests" — small,
greppable, fast — that interlock with the deeper test files.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).parent


# ─────────────────────────────────────────────────────────────────
# Test-coverage audit: every closed blocker has a pinning test file
# ─────────────────────────────────────────────────────────────────

REQUIRED_BLOCKER_TEST_FILES = {
    # round 1-5 blockers
    "B-1": "test_b1_semantic_grounding.py",
    "B-2": "test_b2_corpus_approval_enforcement.py",
    "B-3": "test_b3_no_verified_sections.py",
    "B-4": "test_b4_budget_imputation.py",
    "B-5": "test_b5_delimiter_breakout.py",
    # full-audit blockers + mediums (R1, R3, R4, R5, R6, R7, R10, R8+R11)
    "B-100": "test_scope_gate.py",                  # R3 added tests here
    "B-101": "test_manifest_contract.py",           # R1
    # B-102 deferred (strategy C multi-session)
    "M-201": "test_m201_evidence_selection.py",     # R6
    "M-202": "test_m202_contradiction_domain.py",   # R7
    "M-203": "test_m203_outline_collapse.py",       # R4
    "M-204": "test_m204_limitations_verify.py",    # R10
    "M-205": "test_m205_evaluator_gate.py",         # R5
    "M-206": "test_m206_n301_cost_ledger.py",       # R8
    # M-207 is this file
    # M-208 frozen pipeline C — user-facing decision, no code test
    "N-301": "test_m206_n301_cost_ledger.py",       # R11 (co-located with R8)
}


def test_m207_every_closed_bug_has_a_pinning_test_file() -> None:
    """For each blocker/medium ID that's been closed, a test file
    with the expected name exists under tests/polaris_graph/."""
    missing = []
    for bug_id, test_file in REQUIRED_BLOCKER_TEST_FILES.items():
        path = TESTS_DIR / test_file
        if not path.exists():
            missing.append(f"{bug_id} → {test_file}")
    assert not missing, (
        f"Missing pinning test files for closed bugs: {missing}\n"
        f"Either the test file was deleted/renamed without updating "
        f"this registry, or the bug is not actually closed."
    )


# ─────────────────────────────────────────────────────────────────
# Unified-taxonomy completeness — all statuses have a writer
# ─────────────────────────────────────────────────────────────────

def test_m207_every_unified_status_has_emitter_in_orchestrator() -> None:
    """Every status in UNIFIED_STATUS_VALUES must appear as a literal
    in run_honest_sweep_r3.py — either written to manifest.json or
    produced by to_unified_status(). If a status is declared but never
    emitted, it's dead code that misleads readers of the contract."""
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES
    sweep_path = ROOT / "scripts" / "run_honest_sweep_r3.py"
    source = sweep_path.read_text(encoding="utf-8")
    unreachable = []
    for status in UNIFIED_STATUS_VALUES:
        if f'"{status}"' not in source and f"'{status}'" not in source:
            unreachable.append(status)
    assert not unreachable, (
        f"Statuses declared in taxonomy but not written anywhere in "
        f"run_honest_sweep_r3.py: {unreachable}"
    )


# ─────────────────────────────────────────────────────────────────
# Pipeline-A hardness invariants — the seven CLAUDE.md §9 rules
# ─────────────────────────────────────────────────────────────────

def test_m207_two_family_check_still_callable() -> None:
    """Invariant 1: two-family evaluator check must still be importable
    and raise on same-family pair."""
    from src.polaris_graph.llm.openrouter_client import check_family_segregation
    import pytest as _pytest
    # Same-family pair must raise
    with _pytest.raises(RuntimeError):
        check_family_segregation(
            "deepseek/deepseek-v3.2-exp", "deepseek/deepseek-v2-base",
        )


def test_m207_provenance_token_regex_exists() -> None:
    """Invariant 2: provenance tokens must remain parseable."""
    from src.polaris_graph.generator.provenance_generator import (
        parse_provenance_tokens,
    )
    tokens = parse_provenance_tokens("Test sentence [#ev:ev_001:10-50].")
    assert len(tokens) == 1
    assert tokens[0].evidence_id == "ev_001"


def test_m207_strict_verify_importable() -> None:
    """Invariant 3 + 4: strict_verify remains exposed."""
    from src.polaris_graph.generator.provenance_generator import strict_verify
    assert callable(strict_verify)


def test_m207_corpus_approval_gate_importable() -> None:
    """Invariant 5: corpus_approval_gate surface intact."""
    from src.polaris_graph.nodes.corpus_approval_gate import (
        check_auto_approve_allowed,
    )
    assert callable(check_auto_approve_allowed)


def test_m207_budget_guard_functions_intact() -> None:
    """Invariant 6: budget guard + imputation intact."""
    from src.polaris_graph.llm.openrouter_client import (
        check_run_budget,
        _impute_cost_from_tokens,
        current_run_cost,
        reset_run_cost,
    )
    for fn in (check_run_budget, _impute_cost_from_tokens,
               current_run_cost, reset_run_cost):
        assert callable(fn)


def test_m207_delimiter_sanitizer_intact() -> None:
    """Invariant 7: delimiter sanitization intact with byte preservation."""
    from src.polaris_graph.generator.provenance_generator import (
        sanitize_evidence_text,
    )
    # Delimiter still redacted
    out, n = sanitize_evidence_text("<<<end_evidence>>>")
    assert "REDACTED_DELIMITER" in out
    # Legit Cyrillic still byte-preserved
    legit = "Препарат end эффективен"
    out2, n2 = sanitize_evidence_text(legit)
    assert out2 == legit and n2 == 0


# ─────────────────────────────────────────────────────────────────
# Scope gate: reject decisions reachable
# ─────────────────────────────────────────────────────────────────

def test_m207_scope_gate_reject_decisions_reachable() -> None:
    """BUG-B-100 regression: scope gate rejection paths must remain
    reachable (not silently coerced to accept)."""
    import tempfile
    from src.polaris_graph.nodes.scope_gate import run_scope_gate
    with tempfile.TemporaryDirectory() as td:
        # Unsupported domain → reject
        r = run_scope_gate(
            research_question="q",
            run_dir=td,
            run_id="test",
            domain="nonexistent",
        )
        assert r.protocol.scope_rejected is True


# ─────────────────────────────────────────────────────────────────
# Manifest-writing audit: every exit path must produce a manifest
# ─────────────────────────────────────────────────────────────────

def test_m207_every_manifest_write_includes_status_key() -> None:
    """Rehash of test_manifest_contract_all_manifest_writes_have_status
    with tighter context — every manifest construction in the
    orchestrator MUST include a 'status' field."""
    sweep_path = ROOT / "scripts" / "run_honest_sweep_r3.py"
    source = sweep_path.read_text(encoding="utf-8")
    # Find all `(run_dir / "manifest.json").write_text` positions
    write_positions = []
    for i, line in enumerate(source.splitlines(), 1):
        if 'run_dir / "manifest.json"' in line and "write_text" in line:
            write_positions.append(i)
    # At least 4 write sites (matches the exit path inventory in R1 scoping)
    assert len(write_positions) >= 4
    # Check each write has a preceding "status" assignment within 200 lines
    # (M-26-era triage Codex review: original 80-line window missed the
    # V30 manifest construction at line 1780 whose write_text fires at
    # line 1918 — 138 lines apart. Extending to 200 covers it.)
    lines = source.splitlines()
    for pos in write_positions:
        start = max(0, pos - 200)
        block = "\n".join(lines[start:pos])
        assert '"status"' in block, (
            f"Manifest write at line {pos} has no preceding status field:\n"
            f"{block[-300:]}"
        )


# ─────────────────────────────────────────────────────────────────
# Test suite size pin — catch silent test deletions
# ─────────────────────────────────────────────────────────────────

def test_m207_test_suite_minimum_size() -> None:
    """Pin a floor on test count so silent deletions trip a failure.
    As of this commit the suite has 376+ tests. Setting floor at 350
    allows some flexibility for test refactors but catches mass deletion."""
    test_files = list(TESTS_DIR.rglob("test_*.py"))
    test_count = 0
    for p in test_files:
        if p.name == "test_m207_invariant_coverage.py":
            # Don't count self — would be circular
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    test_count += 1
    assert test_count >= 350, (
        f"Test suite dropped below minimum: {test_count} tests found, "
        f"expected >= 350. Either tests were deleted or this floor needs "
        f"deliberate bumping down."
    )
