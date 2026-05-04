"""Slice 002 golden-test integration runner.

Mirrors `test_slice_001_goldens.py` but for the clinical retrieval slice.

Each test_*.json fixture pairs:
  - decision: a slice 001 ScopeDecision payload
  - stub_fetch_results: a deterministic list[FetchResult] returned by the
    test fetch_fn (no network)
  - expected: assertion targets (EvidencePool kind + adequacy verdict
    OR RetrievalError code)

Discovery resolution (in priority order):
  1. POLARIS_CONTROLS_PATH env var → `<path>/golden/slice_002/`
  2. Sibling directory: `<polaris-root>/../polaris-controls/golden/slice_002/`
  3. Local draft fallback: `<polaris-root>/.codex/slices/slice_002/golden_drafts/`

The third path lets slice 002 ship + run goldens before user has signed
them into polaris-controls (matching slice 001's draft-then-sign pattern).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from polaris_graph.retrieval2.clinical_retriever import (
    FetchResult,
    process_retrieval,
)
from polaris_graph.retrieval2.evidence_pool import EvidencePool, RetrievalError
from polaris_graph.scope.scope_decision import ScopeDecision


_POLARIS_ROOT = Path(__file__).resolve().parents[3]


def _find_slice_002_golden_dir() -> Path | None:
    """Resolve slice 002 golden directory; return None if no source available."""
    env_path = os.environ.get("POLARIS_CONTROLS_PATH")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if (candidate / "golden" / "slice_002").is_dir():
            return candidate / "golden" / "slice_002"

    sibling = _POLARIS_ROOT.parent / "polaris-controls" / "golden" / "slice_002"
    if sibling.is_dir():
        return sibling

    draft = _POLARIS_ROOT / ".codex" / "slices" / "slice_002" / "golden_drafts"
    if draft.is_dir():
        return draft

    return None


def _slice_002_test_files() -> list[Path]:
    pc_dir = _find_slice_002_golden_dir()
    if pc_dir is None:
        return []
    return sorted(pc_dir.glob("test_*.json"))


# ---------------------------------------------------------------------------
# Discovery diagnostics
# ---------------------------------------------------------------------------

def test_slice_002_golden_dir_resolvable():
    pc_dir = _find_slice_002_golden_dir()
    if pc_dir is None:
        pytest.skip(
            "slice 002 golden directory not found in any of: "
            "POLARIS_CONTROLS_PATH, sibling polaris-controls, "
            ".codex/slices/slice_002/golden_drafts"
        )
    assert pc_dir.is_dir()


def test_at_least_5_slice_002_golden_files_exist():
    files = _slice_002_test_files()
    if not files:
        pytest.skip("slice 002 goldens not available")
    assert len(files) >= 5, f"expected at least 5 slice 002 goldens, found {len(files)}"


# ---------------------------------------------------------------------------
# Per-golden execution
# ---------------------------------------------------------------------------

def _golden_id(path: Path) -> str:
    return path.stem


def _build_stub_fetcher(stub_results: list[dict]):
    """Return a fetch_fn that returns the same FetchResult list for every query.

    Tracks call count so 'expect_no_fetch_calls' assertions can verify
    that an out-of-scope decision short-circuits before the fetcher fires.
    """
    state = {"calls": 0}

    def fetcher(_query: str) -> list[FetchResult]:
        state["calls"] += 1
        return [
            FetchResult(
                url=item["url"],
                title=item.get("title", "untitled"),
                snippet=item.get("snippet", ""),
            )
            for item in stub_results
        ]

    return fetcher, state


@pytest.mark.parametrize(
    "golden_path",
    _slice_002_test_files()
    or [
        pytest.param(
            None,
            marks=pytest.mark.skip(reason="slice 002 goldens not available"),
        )
    ],
    ids=lambda p: _golden_id(p) if p else "skipped",
)
def test_slice_002_golden(golden_path: Path | None):
    if golden_path is None:
        pytest.skip("no slice 002 goldens")

    spec = json.loads(golden_path.read_text(encoding="utf-8"))

    decision_payload = spec["decision"]
    stub_results = spec.get("stub_fetch_results", [])
    expected = spec["expected"]

    decision = ScopeDecision.model_validate(decision_payload)
    fetcher, state = _build_stub_fetcher(stub_results)

    result = process_retrieval(decision, fetch_fn=fetcher)

    expected_kind = expected["kind"]
    if expected_kind == "RetrievalError":
        assert isinstance(result, RetrievalError), (
            f"{golden_path.name}: expected RetrievalError, got {type(result).__name__}"
        )
        if "code" in expected:
            assert result.code == expected["code"], (
                f"{golden_path.name}: code {result.code!r} != {expected['code']!r}"
            )
        if expected.get("expect_no_fetch_calls"):
            assert state["calls"] == 0, (
                f"{golden_path.name}: fetch_fn was called {state['calls']} time(s); "
                f"out-of-scope decision must short-circuit before any fetch"
            )

    elif expected_kind == "EvidencePool":
        assert isinstance(result, EvidencePool), (
            f"{golden_path.name}: expected EvidencePool, got {type(result).__name__}"
        )
        assert result.adequacy.is_adequate == expected["adequacy_is_adequate"], (
            f"{golden_path.name}: adequacy {result.adequacy.is_adequate} != "
            f"{expected['adequacy_is_adequate']}; "
            f"failure_reason={result.adequacy.failure_reason!r}"
        )
        if "min_sources" in expected:
            assert len(result.sources) >= expected["min_sources"], (
                f"{golden_path.name}: expected >={expected['min_sources']} sources, "
                f"got {len(result.sources)}"
            )
        if "expected_source_count" in expected:
            assert len(result.sources) == expected["expected_source_count"], (
                f"{golden_path.name}: expected exactly "
                f"{expected['expected_source_count']} sources, got {len(result.sources)}"
            )
        if "expected_failure_reason_substring" in expected:
            assert result.adequacy.failure_reason is not None, (
                f"{golden_path.name}: expected failure_reason, got None"
            )
            assert (
                expected["expected_failure_reason_substring"]
                in result.adequacy.failure_reason
            ), (
                f"{golden_path.name}: failure_reason "
                f"{result.adequacy.failure_reason!r} does not contain "
                f"{expected['expected_failure_reason_substring']!r}"
            )

    else:
        pytest.fail(f"{golden_path.name}: unknown expected.kind {expected_kind!r}")


def test_all_5_slice_002_goldens_pass_summary():
    """Aggregate gate. PASSES iff all goldens pass.

    Useful as a single CI signal for slice 002 status.
    """
    files = _slice_002_test_files()
    if not files:
        pytest.skip("slice 002 goldens not available")

    failures: list[str] = []
    for path in files:
        spec = json.loads(path.read_text(encoding="utf-8"))
        decision = ScopeDecision.model_validate(spec["decision"])
        stub_results = spec.get("stub_fetch_results", [])
        fetcher, _state = _build_stub_fetcher(stub_results)
        result = process_retrieval(decision, fetch_fn=fetcher)
        expected = spec["expected"]
        kind = expected["kind"]
        if kind == "RetrievalError" and not isinstance(result, RetrievalError):
            failures.append(f"{path.name}: not a RetrievalError")
        elif kind == "EvidencePool":
            if not isinstance(result, EvidencePool):
                failures.append(f"{path.name}: not an EvidencePool")
            elif result.adequacy.is_adequate != expected["adequacy_is_adequate"]:
                failures.append(
                    f"{path.name}: adequacy {result.adequacy.is_adequate} != "
                    f"{expected['adequacy_is_adequate']}"
                )
    assert not failures, "Slice 002 golden failures:\n  " + "\n  ".join(failures)
