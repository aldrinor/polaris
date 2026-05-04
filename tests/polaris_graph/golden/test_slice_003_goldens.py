"""Slice 003 golden-test integration runner.

Mirrors slice 001 + 002 golden runners. Each test_*.json fixture pairs:
  - pool_full_text + scope_class: builds an EvidencePool fixture
  - stub_completion_text: deterministic generator output (with {{TOKEN}}
    placeholder substituted at runtime to a valid provenance token)
  - expected: VerifiedReport vs GenerationError + verdict assertions

Discovery resolution (mirrors slice 002):
  1. POLARIS_CONTROLS_PATH env var → `<path>/golden/slice_003/`
  2. Sibling polaris-controls/golden/slice_003/
  3. Local .codex/slices/slice_003/golden_drafts/ fallback
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polaris_graph.generator2.generator import process_generation
from polaris_graph.generator2.verified_report import (
    GenerationError,
    VerifiedReport,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


_POLARIS_ROOT = Path(__file__).resolve().parents[3]


def _find_slice_003_golden_dir() -> Path | None:
    env_path = os.environ.get("POLARIS_CONTROLS_PATH")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if (candidate / "golden" / "slice_003").is_dir():
            return candidate / "golden" / "slice_003"

    sibling = _POLARIS_ROOT.parent / "polaris-controls" / "golden" / "slice_003"
    if sibling.is_dir():
        return sibling

    draft = _POLARIS_ROOT / ".codex" / "slices" / "slice_003" / "golden_drafts"
    if draft.is_dir():
        return draft

    return None


def _slice_003_test_files() -> list[Path]:
    pc_dir = _find_slice_003_golden_dir()
    if pc_dir is None:
        return []
    return sorted(pc_dir.glob("test_*.json"))


# ---------------------------------------------------------------------------
# Discovery diagnostics
# ---------------------------------------------------------------------------

def test_slice_003_golden_dir_resolvable():
    pc_dir = _find_slice_003_golden_dir()
    if pc_dir is None:
        pytest.skip("slice 003 goldens not available")
    assert pc_dir.is_dir()


def test_at_least_5_slice_003_golden_files_exist():
    files = _slice_003_test_files()
    if not files:
        pytest.skip("slice 003 goldens not available")
    assert len(files) >= 5


# ---------------------------------------------------------------------------
# Pool builder + stub completion
# ---------------------------------------------------------------------------

def _build_pool(spec: dict) -> EvidencePool:
    if spec.get("pool_inadequate"):
        return EvidencePool(
            decision_id="dec-1",
            sources=[],
            adequacy=AdequacyVerdict(
                is_adequate=False,
                sources_per_tier={
                    SourceTier.T1: 0,
                    SourceTier.T2: 0,
                    SourceTier.T3: 0,
                },
                min_required_per_tier={
                    SourceTier.T1: 2,
                    SourceTier.T2: 4,
                    SourceTier.T3: 2,
                },
                failure_reason="not enough sources",
            ),
            retrieval_started_at_utc=datetime.now(timezone.utc),
            retrieval_finished_at_utc=datetime.now(timezone.utc),
            latency_ms=0,
            cost_usd=0.0,
        )

    full_text = spec["pool_full_text"]
    return EvidencePool(
        decision_id="dec-1",
        sources=[
            Source(
                url="https://www.cochrane.org/CD001",
                domain="cochrane.org",
                tier=SourceTier.T1,
                title="Test source",
                snippet=full_text[:200],
                full_text=full_text,
                full_text_available=True,
                source_id="src-1",
            )
        ],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 1, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={
                SourceTier.T1: 0,
                SourceTier.T2: 0,
                SourceTier.T3: 0,
            },
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _build_stub_completion(spec: dict, pool: EvidencePool):
    state = {"calls": 0}
    template = spec["stub_completion_text"]
    if pool.sources:
        full_text_len = len(pool.sources[0].full_text or "")
        token = f"[#ev:src-1:0-{full_text_len}]"
        text = template.replace("{{TOKEN}}", token)
    else:
        text = template

    def fn(prompt, section_plan, pool):
        state["calls"] += 1
        return text

    return fn, state


# ---------------------------------------------------------------------------
# Per-golden execution
# ---------------------------------------------------------------------------

def _golden_id(path: Path) -> str:
    return path.stem


@pytest.mark.parametrize(
    "golden_path",
    _slice_003_test_files()
    or [
        pytest.param(
            None,
            marks=pytest.mark.skip(reason="slice 003 goldens not available"),
        )
    ],
    ids=lambda p: _golden_id(p) if p else "skipped",
)
def test_slice_003_golden(golden_path: Path | None):
    if golden_path is None:
        pytest.skip("no slice 003 goldens")

    spec = json.loads(golden_path.read_text(encoding="utf-8"))
    pool = _build_pool(spec)
    fn, state = _build_stub_completion(spec, pool)

    result = process_generation(
        pool,
        completion_fn=fn,
        scope_class=spec.get("scope_class"),
    )

    expected = spec["expected"]
    kind = expected["kind"]

    if kind == "GenerationError":
        assert isinstance(result, GenerationError), (
            f"{golden_path.name}: expected GenerationError, got {type(result).__name__}"
        )
        if "code" in expected:
            assert result.code == expected["code"]
        if expected.get("expect_no_completion_calls"):
            assert state["calls"] == 0, (
                f"{golden_path.name}: completion_fn called {state['calls']} time(s); "
                f"inadequate pool must short-circuit before any completion"
            )
    elif kind == "VerifiedReport":
        assert isinstance(result, VerifiedReport), (
            f"{golden_path.name}: expected VerifiedReport, got {type(result).__name__}"
        )
        assert result.pipeline_verdict == expected["pipeline_verdict"], (
            f"{golden_path.name}: verdict {result.pipeline_verdict!r} != "
            f"{expected['pipeline_verdict']!r}"
        )
        if "min_kept_sections" in expected:
            kept = [s for s in result.sections if s.section_status != "dropped"]
            assert len(kept) >= expected["min_kept_sections"], (
                f"{golden_path.name}: kept {len(kept)} sections, "
                f"expected >={expected['min_kept_sections']}"
            )
        if expected.get("all_sections_dropped"):
            assert all(
                s.section_status == "dropped" for s in result.sections
            ), f"{golden_path.name}: not all sections dropped"
    else:
        pytest.fail(f"{golden_path.name}: unknown expected.kind {kind!r}")


def test_all_5_slice_003_goldens_pass_summary():
    files = _slice_003_test_files()
    if not files:
        pytest.skip("slice 003 goldens not available")

    failures: list[str] = []
    for path in files:
        spec = json.loads(path.read_text(encoding="utf-8"))
        pool = _build_pool(spec)
        fn, _state = _build_stub_completion(spec, pool)
        result = process_generation(
            pool, completion_fn=fn, scope_class=spec.get("scope_class")
        )
        expected = spec["expected"]
        kind = expected["kind"]
        if kind == "GenerationError" and not isinstance(result, GenerationError):
            failures.append(f"{path.name}: not a GenerationError")
        elif kind == "VerifiedReport":
            if not isinstance(result, VerifiedReport):
                failures.append(f"{path.name}: not a VerifiedReport")
            elif result.pipeline_verdict != expected["pipeline_verdict"]:
                failures.append(
                    f"{path.name}: verdict {result.pipeline_verdict} != {expected['pipeline_verdict']}"
                )
    assert not failures, "Slice 003 golden failures:\n  " + "\n  ".join(failures)
