"""F25 + F03 (A3) regression for the Gate-B ``--all`` loop.

F25: per-query EXCEPTION isolation. Pre-fix ``asyncio.run(run_gate_b_query)`` had no
try/except, so one escaped exception aborted ALL remaining cert questions — the
5-Q ``--all`` run could not complete. Post-fix a crashed query is logged, written
as a durable failed-manifest record under out_root, counted as a failure (rc!=0),
and the sweep CONTINUES (``PG_ABORT_ON_QUERY_ERROR=1`` re-raises after recording).

F03 part 2: a non-``success`` per-query status now makes the run FAIL (rc!=0) unless
``PG_GATE_B_ALLOW_PARTIAL=1`` — pre-fix ANY ``partial*`` status returned rc=0, so a
mostly-gap-stubbed clinical report (and the new ``abort_excessive_gap`` from F03
part 1) shipped GREEN.

NO network, NO spend: ``run_gate_b_query`` is monkeypatched per case.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.dr_benchmark import run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    LOCKED_BENCHMARK_SLUGS,
    abort_query_error_propagates,
    gate_b_allow_partial,
    main,
    query_status_ok,
)


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# ── pure predicate: query_status_ok (F03 part 2) ─────────────────────────────

def test_query_status_ok_success_always_passes() -> None:
    assert query_status_ok("success", allow_partial=False) is True
    assert query_status_ok("success", allow_partial=True) is True


def test_query_status_ok_partial_fails_by_default() -> None:
    """The F03 part-2 flip: partial* is a FAILURE unless explicitly allowed."""
    assert query_status_ok("partial_saturation", allow_partial=False) is False
    assert query_status_ok("partial_thin_corpus", allow_partial=False) is False


def test_query_status_ok_partial_passes_only_when_allowed() -> None:
    assert query_status_ok("partial_saturation", allow_partial=True) is True


def test_query_status_ok_abort_and_error_always_fail() -> None:
    for status in (
        "abort_excessive_gap",
        "abort_no_verified_sections",
        "abort_corpus_inadequate",
        "error_unexpected",
        "error_query_crashed",
        "<no-status>",
    ):
        assert query_status_ok(status, allow_partial=False) is False
        assert query_status_ok(status, allow_partial=True) is False


def test_allow_partial_reader_default_false(monkeypatch) -> None:
    monkeypatch.delenv("PG_GATE_B_ALLOW_PARTIAL", raising=False)
    assert gate_b_allow_partial() is False
    monkeypatch.setenv("PG_GATE_B_ALLOW_PARTIAL", "1")
    assert gate_b_allow_partial() is True


def test_abort_on_error_reader_default_false(monkeypatch) -> None:
    monkeypatch.delenv("PG_ABORT_ON_QUERY_ERROR", raising=False)
    assert abort_query_error_propagates() is False
    monkeypatch.setenv("PG_ABORT_ON_QUERY_ERROR", "1")
    assert abort_query_error_propagates() is True


# ── F03 part 1 ACTIVATION: the slate must turn the floor ON for the cert run ──

def test_slate_activates_min_verified_section_fraction() -> None:
    """F03 part 1 is DORMANT (default 0.0 inert) unless the Gate-B slate sets it.
    The slate MUST force the coverage-honesty floor to an active float in (0,1] —
    otherwise a mostly-gap clinical report ships GREEN on the canonical --all run
    (the 'built-it-then-left-it-off' failure)."""
    slate = run_gate_b._FULL_CAPABILITY_BENCHMARK_SLATE
    assert "PG_MIN_VERIFIED_SECTION_FRACTION" in slate
    val = float(slate["PG_MIN_VERIFIED_SECTION_FRACTION"])
    assert 0.0 < val <= 1.0
    # FLOAT => must ride the force-EXACT path, NOT the int FLOOR loop (which would
    # coerce 0.4 -> 0 and silently disable the gate, the PG_RELEVANCE_FLOOR gotcha).
    assert "PG_MIN_VERIFIED_SECTION_FRACTION" in run_gate_b._BENCHMARK_FORCE_EXACT_FLAGS


def test_apply_slate_sets_active_floor(monkeypatch) -> None:
    """Applying the slate makes the live env carry an active floor even when the
    operator/.env left it at 0 (a stray =0 must NOT survive the force-exact)."""
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0")
    run_gate_b.apply_full_capability_benchmark_slate()
    assert float(os.environ["PG_MIN_VERIFIED_SECTION_FRACTION"]) > 0.0


def test_preflight_fails_when_floor_disabled(monkeypatch) -> None:
    """preflight_full_capability fails closed if the floor is 0/absent — the cert
    run cannot proceed with the coverage-honesty gate disabled. The F03 check runs
    FIRST in preflight (fail-fast on a faithfulness gate), so a 0 floor is caught
    regardless of the other slate flags."""
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0")
    with pytest.raises(RuntimeError, match="PG_MIN_VERIFIED_SECTION_FRACTION"):
        run_gate_b.preflight_full_capability()


def test_preflight_passes_floor_when_active(monkeypatch) -> None:
    """A valid active floor passes the F03 check (preflight then proceeds to the
    OTHER floors — which may fail in a bare test env; we only assert the F03 check
    itself does not reject an active floor)."""
    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0.4")
    try:
        run_gate_b.preflight_full_capability()
    except RuntimeError as exc:
        # If preflight raises, it must NOT be on the F03 floor (some other slate
        # floor unset in the bare test env is fine — that's a different check).
        assert "PG_MIN_VERIFIED_SECTION_FRACTION" not in str(exc)


# ── F03 part 2: loop-level rc on a partial status ────────────────────────────

def test_partial_status_makes_run_fail_by_default(monkeypatch, tmp_path) -> None:
    async def _partial(q, out_root, **kwargs):
        return {"status": "partial_saturation", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _partial)
    monkeypatch.delenv("PG_GATE_B_ALLOW_PARTIAL", raising=False)
    rc = main(["--only", "drb_72_ai_labor", "--out-root", str(tmp_path)])
    assert rc == 1  # pre-fix this was 0


def test_partial_status_allowed_with_flag(monkeypatch, tmp_path) -> None:
    async def _partial(q, out_root, **kwargs):
        return {"status": "partial_saturation", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _partial)
    monkeypatch.setenv("PG_GATE_B_ALLOW_PARTIAL", "1")
    rc = main(["--only", "drb_72_ai_labor", "--out-root", str(tmp_path)])
    assert rc == 0  # operator opted into partials


def test_excessive_gap_status_fails_run(monkeypatch, tmp_path) -> None:
    """F03 wired end-to-end: abort_excessive_gap (NOT a partial) fails Gate-B even
    with PG_GATE_B_ALLOW_PARTIAL=1 (it is not a partial)."""
    async def _gap(q, out_root, **kwargs):
        return {"status": "abort_excessive_gap", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _gap)
    monkeypatch.setenv("PG_GATE_B_ALLOW_PARTIAL", "1")
    rc = main(["--only", "drb_72_ai_labor", "--out-root", str(tmp_path)])
    assert rc == 1


# ── F25: per-query exception isolation ───────────────────────────────────────

def test_q1_crash_does_not_abort_remaining_questions(monkeypatch, tmp_path) -> None:
    """Inject a fault in the FIRST question; every later cert question MUST still
    run, and the overall rc reflects the failure (not a silent green)."""
    seen = []

    async def _faulty_first(q, out_root, **kwargs):
        seen.append(q["slug"])
        if q["slug"] == LOCKED_BENCHMARK_SLUGS[0]:
            raise RuntimeError("simulated transport blowup in Q1")
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _faulty_first)
    monkeypatch.delenv("PG_ABORT_ON_QUERY_ERROR", raising=False)

    rc = main(["--all", "--out-root", str(tmp_path)])

    # Every question was attempted despite Q1 crashing.
    assert seen == list(LOCKED_BENCHMARK_SLUGS)
    # The crash counts as a failure — NOT a silent rc=0.
    assert rc == 1
    # A durable crash SIDECAR was written for the crashed question (never collides
    # with run_one_query's manifest.json).
    crashed_slug = LOCKED_BENCHMARK_SLUGS[0]
    sidecars = list(Path(tmp_path).rglob(f"**/{crashed_slug}/gate_b_query_crash.json"))
    assert sidecars, "no crash sidecar written for the crashed query"
    record = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert record["status"] == "error_query_crashed"
    assert "simulated transport blowup" in record["error"]
    # And (since run_one_query never wrote a manifest for this raised-before-result
    # case) a manifest.json mirror exists too.
    manifests = list(Path(tmp_path).rglob(f"**/{crashed_slug}/manifest.json"))
    assert manifests, "no failed-manifest mirror written for the crashed query"


def test_crash_does_not_clobber_existing_manifest(monkeypatch, tmp_path) -> None:
    """Codex P2: if run_one_query already wrote a (richer) manifest before an
    exception escaped, the outer crash handler must PRESERVE it — only the sidecar
    is new, manifest.json is left untouched."""
    crashed_slug = LOCKED_BENCHMARK_SLUGS[0]
    crashed_domain = {}

    async def _faulty_after_manifest(q, out_root, **kwargs):
        if q["slug"] == crashed_slug:
            crashed_domain["d"] = q["domain"]
            # Simulate run_one_query having written a rich error manifest, THEN raising.
            d = Path(out_root) / q["domain"] / q["slug"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "manifest.json").write_text(
                json.dumps({"status": "error_unexpected", "rich": True}),
                encoding="utf-8",
            )
            raise RuntimeError("escaped after manifest write")
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _faulty_after_manifest)
    monkeypatch.delenv("PG_ABORT_ON_QUERY_ERROR", raising=False)
    rc = main(["--all", "--out-root", str(tmp_path)])
    assert rc == 1
    d = Path(tmp_path) / crashed_domain["d"] / crashed_slug
    # The richer manifest is PRESERVED (not overwritten by the thinner crash record).
    preserved = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    assert preserved.get("rich") is True
    assert preserved["status"] == "error_unexpected"
    # The crash sidecar still exists with the outer record.
    sidecar = json.loads((d / "gate_b_query_crash.json").read_text(encoding="utf-8"))
    assert sidecar["status"] == "error_query_crashed"


def test_incremental_sweep_summary_persisted(monkeypatch, tmp_path) -> None:
    """A sweep_summary.json roster is written under out_root after the run, so a
    sweep killed mid-run leaves a durable record of what ran."""
    async def _ok(q, out_root, **kwargs):
        return {"status": "success", "slug": q["slug"], "cost_usd": 0.0}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _ok)
    rc = main(["--all", "--out-root", str(tmp_path)])
    assert rc == 0
    summary_path = Path(tmp_path) / "sweep_summary.json"
    assert summary_path.exists()
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["completed"] == len(LOCKED_BENCHMARK_SLUGS)
    assert data["overall_rc"] == 0
    assert len(data["queries"]) == len(LOCKED_BENCHMARK_SLUGS)
    assert all(row["ok"] for row in data["queries"])


def test_abort_on_query_error_reraises(monkeypatch, tmp_path) -> None:
    """With PG_ABORT_ON_QUERY_ERROR=1 the sweep STOPS on the first crash, but only
    AFTER writing the failed-manifest + sweep_summary (no silent loss)."""
    seen = []

    async def _faulty_first(q, out_root, **kwargs):
        seen.append(q["slug"])
        raise RuntimeError("boom")

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _faulty_first)
    monkeypatch.setenv("PG_ABORT_ON_QUERY_ERROR", "1")

    with pytest.raises(RuntimeError):
        main(["--all", "--out-root", str(tmp_path)])

    # Stopped after the first question.
    assert seen == [LOCKED_BENCHMARK_SLUGS[0]]
    # The record was still durably written before re-raising.
    assert (Path(tmp_path) / "sweep_summary.json").exists()
