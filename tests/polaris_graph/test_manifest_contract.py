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
# Test 1: UNIFIED_STATUS_VALUES is a closed set of exactly 10 values.
# ─────────────────────────────────────────────────────────────────

def test_manifest_contract_unified_taxonomy_defined() -> None:
    from scripts.run_honest_sweep_r3 import (
        UNIFIED_STATUS_VALUES,
        to_unified_status,
    )
    expected = frozenset({
        "success",
        "partial_thin_corpus",
        "partial_incomplete_corpus",
        "partial_rule_check_warnings",
        "abort_scope_rejected",
        "abort_no_sources",
        "abort_corpus_inadequate",
        "abort_corpus_approval_denied",
        "abort_no_verified_sections",
        "error_unexpected",
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
                    # Found a manifest write. Look backward 80 lines for
                    # the `{ ... }` construction.
                    end_line = node.lineno
                    start_line = max(1, end_line - 80)
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
    allowed_non_manifest = {"started"}
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
    # Find the first Try node directly in the body (outermost try).
    outer_try = next(
        (n for n in func.body if isinstance(n, _ast.Try)),
        None,
    )
    assert outer_try is not None, "expected outer try in run_one_query"
    # Each Try has ExceptHandler(s). Dump the handlers' source ranges.
    handler_sources = []
    for handler in outer_try.handlers:
        start = handler.lineno
        end = handler.end_lineno or start
        handler_sources.append("\n".join(source.splitlines()[start - 1:end]))
    combined = "\n".join(handler_sources)
    assert '"status": "error_unexpected"' in combined, (
        f"Outer exception handler must write manifest with "
        f"status=error_unexpected. Got handlers:\n{combined[:600]}"
    )
    assert 'manifest.json' in combined, (
        "Outer exception handler must attempt to write manifest.json"
    )


# ─────────────────────────────────────────────────────────────────
# Test 5: round-trip — unified statuses match the reader's contract
# (every class of status is recognizable by its prefix).
# ─────────────────────────────────────────────────────────────────

def test_manifest_contract_status_prefixes() -> None:
    """Every status value falls into one of four classes via its prefix.
    This is what downstream readers rely on to classify a run."""
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES
    for status in UNIFIED_STATUS_VALUES:
        assert any(
            status == "success"
            or status.startswith("partial_")
            or status.startswith("abort_")
            or status.startswith("error_")
            for _ in [1]  # dummy loop for any()
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
