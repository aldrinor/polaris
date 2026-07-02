"""I-deepfix-001 (#1344) wallclock_guard — offline RED->GREEN tests.

The run-level wall-clock timeout handler used to UNCONDITIONALLY stamp an ``error_unexpected`` manifest,
guillotining a run whose ``report.md`` had ALREADY rendered (a real clinical back-half measured 10992s,
over the old 10800 wall). ``timeout_should_preserve_rendered_report`` preserves the truthful terminal
manifest when a non-empty report.md exists, and the run-wall cap is raised 10800 -> 14400.

Outer-orchestration bookkeeping only — the FROZEN faithfulness engine (strict_verify / NLI / 4-role D8 /
provenance / span-grounding) is never referenced. Offline: no GPU, no network, no paid LLM.
"""
from __future__ import annotations

import json

from scripts.run_honest_sweep_r3 import (
    finalize_run_artifact,
    finalize_timeout_run_and_maybe_write_error_manifest,
    timeout_should_preserve_rendered_report,
)


def test_preserves_rendered_report_and_recovers_status(tmp_path):
    """A non-empty report.md + an on-disk success manifest => preserve (return True) and RECOVER
    the truthful status into the timeout summary (RED pre-fix: the helper did not exist)."""
    (tmp_path / "report.md").write_text("# Real rendered report\n\nbody", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"status": "released_with_disclosed_gaps", "release_allowed": True}),
        encoding="utf-8",
    )
    summary = {"status": "error_unexpected", "error": "wall hang"}
    assert timeout_should_preserve_rendered_report(tmp_path, summary) is True
    assert summary["status"] == "released_with_disclosed_gaps"
    assert summary["manifest"]["release_allowed"] is True


def test_writes_error_manifest_when_no_report(tmp_path):
    """No report.md => return False so the caller writes the labeled timeout manifest (a real hang
    is never silent). The summary is left untouched."""
    summary = {"status": "error_unexpected", "error": "wall hang"}
    assert timeout_should_preserve_rendered_report(tmp_path, summary) is False
    assert summary["status"] == "error_unexpected"
    assert "manifest" not in summary


def test_empty_report_is_not_counted_as_rendered(tmp_path):
    """A zero-byte report.md does NOT count as rendered => return False (write the timeout manifest)."""
    (tmp_path / "report.md").write_text("", encoding="utf-8")
    summary = {"status": "error_unexpected"}
    assert timeout_should_preserve_rendered_report(tmp_path, summary) is False


def test_preserves_report_even_when_manifest_missing(tmp_path):
    """A non-empty report.md with NO manifest.json => still preserve (return True); status is left
    as-is (nothing to recover) and it never raises."""
    (tmp_path / "report.md").write_text("# Rendered\n\nbody", encoding="utf-8")
    summary = {"status": "error_unexpected"}
    assert timeout_should_preserve_rendered_report(tmp_path, summary) is True
    assert summary["status"] == "error_unexpected"  # no manifest -> unchanged


def test_genuine_hang_no_prior_report_still_writes_error_manifest(tmp_path):
    """ORDERING GUARD (Codex P1). A genuine hang with NO prior report.md: finalize_run_artifact
    writes a NON-EMPTY timeout backstop report.md, but because the PRESERVE decision is captured
    BEFORE the finalizer runs, that backstop must NOT suppress the labeled error manifest.

    RED with the buggy finalize-THEN-decide order (the helper sees the finalizer's own backstop
    report.md -> preserves -> no error manifest). GREEN once the decision is computed pre-finalizer:
    the error/timeout manifest IS still written so a real hang is never silently mislabeled."""
    q = {"slug": "drb_x", "domain": "clinical", "question": "does it hang?"}
    summary = {"status": "error_unexpected", "error": "run-level wall-clock exceeded (hang)"}
    preserved = finalize_timeout_run_and_maybe_write_error_manifest(
        tmp_path, summary, q, wall_clock_seconds=14400,
    )
    # The finalizer's backstop report.md was written (the run is never silent)...
    assert (tmp_path / "report.md").is_file()
    assert (tmp_path / "report.md").stat().st_size > 0
    # ...but a genuine no-prior-report hang MUST still be labeled with the error manifest.
    assert preserved is False
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file(), "genuine hang must write the labeled timeout error manifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "error_unexpected"
    assert manifest["run_wall_clock_timeout"] is True
    assert manifest["release_allowed"] is False
    assert summary["manifest"]["status"] == "error_unexpected"


def test_prior_rendered_report_is_preserved_no_error_manifest(tmp_path):
    """A real report.md + a truthful terminal manifest already on disk when the wall fires =>
    PRESERVE. The error manifest is NOT written; the truthful manifest survives unclobbered and the
    timeout summary recovers its status."""
    (tmp_path / "report.md").write_text("# Real rendered report\n\nbody", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"status": "released_with_disclosed_gaps", "release_allowed": True}),
        encoding="utf-8",
    )
    q = {"slug": "drb_y", "domain": "clinical", "question": "already rendered?"}
    summary = {"status": "error_unexpected", "error": "wall hang after render"}
    preserved = finalize_timeout_run_and_maybe_write_error_manifest(
        tmp_path, summary, q, wall_clock_seconds=14400,
    )
    assert preserved is True
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    # The truthful terminal manifest is intact — NOT clobbered by an error_unexpected stamp.
    assert manifest["status"] == "released_with_disclosed_gaps"
    assert manifest["release_allowed"] is True
    assert "run_wall_clock_timeout" not in manifest
    # The timeout summary recovered the truthful status.
    assert summary["status"] == "released_with_disclosed_gaps"


def test_inner_finalizer_backstop_then_outer_helper_still_writes_error_manifest(tmp_path):
    """ORDERING GUARD — the REAL production sequence (Codex iter-2 P1). run_one_query's inner
    ``finally`` runs finalize_run_artifact BEFORE the outer wall-clock handler calls
    finalize_timeout_run_and_maybe_write_error_manifest. On a genuine no-prior-report hang the
    INNER finalizer writes a NON-EMPTY TIMEOUT backstop report.md FIRST; the outer handler's
    preserve check must NOT mistake that backstop for a genuine render (doing so suppresses the
    labeled error manifest -> a real hang is mislabeled "already rendered").

    RED with the report.md-size-ONLY preserve check (it sees the inner backstop as "already
    rendered" -> preserves -> no error manifest -> the manifest.json read below raises).
    GREEN once the preserve check tells the finalizer's backstop apart from a genuine render:
    the labeled error/timeout manifest IS still written for the real hang."""
    q = {"slug": "drb_hang", "domain": "clinical", "question": "does it hang before any render?"}
    # 1) INNER finalizer (run_one_query's `finally`) on a genuine hang: no real report.md existed,
    #    so it writes a NON-EMPTY TIMEOUT backstop. status is still non-terminal ("started").
    inner_kind = finalize_run_artifact(
        tmp_path, {"status": "started"}, q, timed_out=True, wall_clock_seconds=14400,
    )
    assert inner_kind == "timeout", inner_kind  # the inner finalizer wrote a TIMEOUT backstop
    assert (tmp_path / "report.md").is_file()
    assert (tmp_path / "report.md").stat().st_size > 0
    # 2) OUTER wall-clock handler runs AFTER the TimeoutError propagates (the real ordering).
    outer_summary = {"status": "error_unexpected", "error": "run-level wall-clock exceeded (hang)"}
    preserved = finalize_timeout_run_and_maybe_write_error_manifest(
        tmp_path, outer_summary, q, wall_clock_seconds=14400,
    )
    # The inner finalizer's OWN backstop must NOT be mistaken for a genuine render.
    assert preserved is False
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file(), "a genuine hang must still write the labeled timeout manifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "error_unexpected"
    assert manifest["run_wall_clock_timeout"] is True
    assert manifest["release_allowed"] is False
    assert outer_summary["manifest"]["status"] == "error_unexpected"


def test_real_rendered_report_survives_inner_finalizer_noop_and_is_preserved(tmp_path):
    """The companion INVARIANT: a GENUINELY-rendered report.md (the documented post-report 4-role
    seam hang) is still PRESERVED. A real render carries NO finalizer verdict marker, so the inner
    finalizer NO-OPs on it (no marker written) and the outer handler preserves the truthful terminal
    manifest — the fix must not clobber a real deliverable."""
    (tmp_path / "report.md").write_text(
        "# Research report: q\n\n## Key findings\n\nReal verified prose with [#ev:e1:0-10].",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"status": "released_with_disclosed_gaps", "release_allowed": True}),
        encoding="utf-8",
    )
    q = {"slug": "drb_post_report", "domain": "clinical", "question": "rendered then hung?"}
    # The inner finalizer must NO-OP on the real report (never overwrite it, never mark it).
    assert finalize_run_artifact(tmp_path, {"status": "started"}, q, timed_out=True) is None
    outer_summary = {"status": "error_unexpected", "error": "wall hang after render"}
    preserved = finalize_timeout_run_and_maybe_write_error_manifest(
        tmp_path, outer_summary, q, wall_clock_seconds=14400,
    )
    assert preserved is True
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "released_with_disclosed_gaps"
    assert manifest["release_allowed"] is True
    assert "run_wall_clock_timeout" not in manifest
    assert outer_summary["status"] == "released_with_disclosed_gaps"


def test_run_wall_raised_to_14400():
    """The run-wall cap is raised 10800 -> 14400 in both the slate and the extra-env floor
    (RED pre-fix: both were 10800)."""
    from scripts.dr_benchmark.run_gate_b import (
        _BENCHMARK_EXTRA_ENV_FLOORS,
        _FULL_CAPABILITY_BENCHMARK_SLATE,
    )
    assert _FULL_CAPABILITY_BENCHMARK_SLATE["PG_RUN_WALL_CLOCK_SEC"] == "14400"
    assert _BENCHMARK_EXTRA_ENV_FLOORS["PG_RUN_WALL_CLOCK_SEC"] == 14400
