"""LANE-SWEEP (B11 + B20 + B15-B19 + B12/B13 run-side glue) — the ALWAYS-EMIT invariant.

I-arch-005 #1257, Phase-2/3, Codex iter-2. Operator-locked 2026-06-14 ("nothing shall hold
the report").

WHAT THIS PROVES (the acceptance contract — Codex iter-2 P1-2 table-driven injection)
-------------------------------------------------------------------------------------
For EVERY terminal status a runner can emit + an INJECTED REAL HANG that flows through the
ACTUAL ``run_one_query`` path (so its inner B11 ``finally`` fires) + each judge-exception
class (credibility / conflict / entailment), the run produces EXACTLY ONE non-empty human
artifact whose terminal status is in the shared status schema, no class-A path yields
silence-or-hold, and a faithfulness failure QUARANTINES the offending claim (never relaxes
span / provenance / the verdict). The two mechanical halves:

  HALF A — NEVER SILENCE: B11 (the Universal Artifact Finalizer) + B20 (the run-level
           wall-clock that catches a HANG the function-level `finally` cannot reach, AND —
           Codex iter-2 P1-1 — labels a wall-clock-cancelled run TIMEOUT deterministically).
  HALF B — VERIFY = LABEL NEVER HOLD: B15-B19 convert each post-success judge/infra HOLD
           into a disclosed LABEL; B12/B13 route the per-source/per-pair unscored labels.

P1-1 PROOF (the discriminating test): ``test_b20_real_path_hang_emits_timeout_artifact``
drives a REAL ``run_one_query`` (scope gate runs for real offline; retrieval/adequacy/approval
are stubbed to REACH an awaited stage; the awaited generator is replaced by a hang). When the
call-site ``asyncio.wait_for`` times out it CANCELS run_one_query, whose OWN inner ``finally``
runs during the CancelledError unwind and — because the wall-clock deadline ContextVar is set —
emits a TIMEOUT-labeled artifact. This is the exact race Codex flagged: pre-fix the inner
finally wrote a *degraded* artifact and the call-site timeout finalizer NO-OP'd on it.

NON-NEGOTIABLE: the faithfulness engine is NEVER mocked here. The B16 quarantine test calls the
REAL report_redactor and asserts the unverified claim's text is REMOVED from the shipped body —
a status flip that left the claim asserted as fact would be a relaxation and FAILS. The
gate-stubs in the real-path tests stub only the corpus-adequacy/approval ROUTING needed to reach
the awaited stage under test (a unit test of cancel-/judge-exception LABELING, not an integration
test of retrieval); strict_verify / span / provenance are never relaxed.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

import scripts.run_honest_sweep_r3 as sweep
from scripts.run_honest_sweep_r3 import (
    UNIFIED_STATUS_VALUES,
    artifact_kind_for_status,
    b18_b19_disposition,
    build_finalizer_artifact_body,
    finalize_run_artifact,
    render_reliability_header_md,
    run_wall_clock_cancellation_active,
    run_wall_clock_seconds,
    to_unified_status,
    _B18_B19_CONVERTIBLE_HOLDS,
    _collect_judge_unscored_labels,
)


# Class-A terminal statuses (the unified taxonomy) the runner can emit. The finalizer must
# produce a non-empty artifact for EVERY one of them. We drive the DECLARED taxonomy directly
# (no pipeline run) so this is exhaustive over the status schema, not a sample.
_ALL_TERMINAL_STATUSES = sorted(UNIFIED_STATUS_VALUES)


# ─────────────────────────────────────────────────────────────────────────────
# B11 — Universal Artifact Finalizer: one non-empty artifact on EVERY exit.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", _ALL_TERMINAL_STATUSES)
def test_b11_finalizer_emits_artifact_for_every_terminal_status(tmp_path, status):
    """For EVERY terminal status, a run that wrote a manifest-ONLY (the TRUE-SILENCE class)
    gets a non-empty report.md from the finalizer, and the status stays in the shared schema."""
    run_dir = tmp_path / "clinical" / "slug"
    run_dir.mkdir(parents=True)
    # Simulate a manifest-only exit (an except path / pre-success abort that did NOT write
    # report.md). This is exactly the silence class B11 closes.
    summary = {"status": status, "error": f"injected for {status}"}
    q = {"slug": "slug", "domain": "clinical", "question": "What is the efficacy of drug X?"}
    (run_dir / "manifest.json").write_text(
        json.dumps({"status": status}) + "\n", encoding="utf-8"
    )

    kind = finalize_run_artifact(run_dir, summary, q)

    report = run_dir / "report.md"
    # (1) manifest exists
    assert (run_dir / "manifest.json").is_file()
    # (2) status is in the shared schema (unified)
    assert to_unified_status(status) in UNIFIED_STATUS_VALUES
    assert status in UNIFIED_STATUS_VALUES  # we drove the unified set directly
    # (3) a NON-EMPTY human artifact exists
    assert report.is_file()
    assert report.stat().st_size > 0
    body = report.read_text(encoding="utf-8")
    assert body.strip()
    assert "Pipeline verdict" in body
    assert status in body  # the artifact is self-documenting about the terminal status
    # (4) no silence: the finalizer reported it wrote an artifact (a kind), not a no-op
    assert kind is not None


def test_b11_finalizer_never_overwrites_a_real_report(tmp_path):
    """The success path (and abort paths that wrote their own verdict body) must be untouched."""
    run_dir = tmp_path / "clinical" / "slug"
    run_dir.mkdir(parents=True)
    real = "# Research report: Q?\n\n## Findings\n\nReal verified prose with [#ev:e1:0-10].\n"
    (run_dir / "report.md").write_text(real, encoding="utf-8")
    summary = {"status": "success"}
    q = {"slug": "slug", "domain": "clinical", "question": "Q?"}

    kind = finalize_run_artifact(run_dir, summary, q)

    assert kind is None  # no-op
    assert (run_dir / "report.md").read_text(encoding="utf-8") == real  # byte-identical


def test_b11_finalizer_never_overwrites_real_report_even_under_timeout(tmp_path):
    """Codex iter-2 P1-1 FAITHFULNESS GUARD: the post-report-write HANG. The success path writes
    report.md, then the run continues into the 4-role seam (the known xhigh-reasoning stall). If
    the wall-clock fires THERE, report.md on disk is a REAL verified report. The timeout finalizer
    MUST NOT overwrite it with a timeout stub (that would destroy a real deliverable). The no-op
    guard protects the real report EVEN with timed_out=True."""
    run_dir = tmp_path / "clinical" / "slug"
    run_dir.mkdir(parents=True)
    real = "# Research report: Q?\n\n## Findings\n\nReal verified prose with [#ev:e1:0-10].\n"
    (run_dir / "report.md").write_text(real, encoding="utf-8")
    summary = {"status": "started"}
    q = {"slug": "slug", "domain": "clinical", "question": "Q?"}

    kind = finalize_run_artifact(run_dir, summary, q, timed_out=True, wall_clock_seconds=3600.0)

    assert kind is None  # no-op even under the timeout flag
    assert (run_dir / "report.md").read_text(encoding="utf-8") == real  # the real report survives


def test_b11_finalizer_replaces_an_empty_report(tmp_path):
    """An EMPTY report.md (0 bytes) is not a real artifact — the finalizer must replace it
    (else a zero-byte report.md is silence dressed as an artifact)."""
    run_dir = tmp_path / "d" / "s"
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text("", encoding="utf-8")
    summary = {"status": "error_unexpected", "error": "boom"}
    q = {"slug": "s", "domain": "d", "question": "Q?"}

    kind = finalize_run_artifact(run_dir, summary, q)

    assert kind is not None
    assert (run_dir / "report.md").stat().st_size > 0


def test_b11_finalizer_never_raises_on_bad_inputs():
    """The finalizer runs inside a `finally`; it must NEVER raise, even on None run_dir / q."""
    assert finalize_run_artifact(None, {"status": "x"}, {}) is None
    assert finalize_run_artifact(None, {}, None) is None  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# B20 — run-level wall-clock helpers.
# ─────────────────────────────────────────────────────────────────────────────
def test_b20_wall_clock_env_override(monkeypatch):
    """LAW VI: the wall-clock is env-overridable; a bad/empty/negative value falls back to
    the generous default (never silently disables the guard)."""
    monkeypatch.delenv("PG_RUN_WALL_CLOCK_SEC", raising=False)
    assert run_wall_clock_seconds() == sweep._RUN_WALL_CLOCK_DEFAULT_SEC
    monkeypatch.setenv("PG_RUN_WALL_CLOCK_SEC", "120")
    assert run_wall_clock_seconds() == 120.0
    monkeypatch.setenv("PG_RUN_WALL_CLOCK_SEC", "-5")
    assert run_wall_clock_seconds() == sweep._RUN_WALL_CLOCK_DEFAULT_SEC
    monkeypatch.setenv("PG_RUN_WALL_CLOCK_SEC", "not-a-number")
    assert run_wall_clock_seconds() == sweep._RUN_WALL_CLOCK_DEFAULT_SEC


def test_b20_cancellation_detector_false_when_no_deadline():
    """Codex iter-2 P1-1: outside a wall-clock window (no deadline ContextVar set), the detector
    must return False so the inner finalizer never mislabels a normal exit as a timeout."""
    # No deadline set in this (sync) context -> never a wall-clock cancellation.
    assert run_wall_clock_cancellation_active() is False


@pytest.mark.asyncio
async def test_b20_cancellation_detector_false_when_deadline_not_elapsed():
    """The detector is two ANDed signals: a pending cancel AND an elapsed deadline. With the
    deadline far in the future, it returns False even if the task were cancelled (the deadline
    AND makes the classification specific to a wall-clock timeout, not any cancel)."""
    token = sweep._RUN_WALL_CLOCK_DEADLINE_CTX.set(time.monotonic() + 10_000.0)
    try:
        assert run_wall_clock_cancellation_active() is False
    finally:
        sweep._RUN_WALL_CLOCK_DEADLINE_CTX.reset(token)


# ─────────────────────────────────────────────────────────────────────────────
# Real-path injection harness: stub only the corpus gates needed to REACH an awaited
# stage of the ACTUAL run_one_query (so its inner B11 `finally` fires). The faithfulness
# engine (strict_verify / span / provenance) is NEVER touched.
# ─────────────────────────────────────────────────────────────────────────────
_QUESTION = "What is the efficacy of drug X for type 2 diabetes in adults?"


def _fake_retrieval(*_a, **_k):
    """A SYNC stub matching run_live_retrieval's real return type with enough T1 sources/rows to
    pass the (stubbed) adequacy gate. run_live_retrieval is SYNC, so this is a `def`, not async."""
    from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
    from src.polaris_graph.retrieval.live_retriever import LiveRetrievalResult

    sources = [
        CorpusSource(url=f"https://pmc/{i}", tier="T1", title=f"T{i}", domain="pmc",
                     tier_confidence=0.9, tier_rule="", tier_reasons=[])
        for i in range(8)
    ]
    rows = [
        {"evidence_id": f"e{i}", "url": f"https://pmc/{i}", "text": f"Finding {i}.",
         "tier": "T1", "title": f"T{i}"}
        for i in range(8)
    ]
    return LiveRetrievalResult(
        classified_sources=sources, evidence_rows=rows,
        total_candidates_pre_filter=8, candidates_kept_by_scope=8,
        candidates_kept_by_offtopic=8, candidates_fetched=8, candidates_failed_fetch=0,
        candidates_total=8, candidates_processed=8,
    )


def _fake_adequacy_proceed(*_a, **_k):
    """A SYNC stub returning a real CorpusAdequacyReport(decision='proceed') — the corpus-adequacy
    ROUTING only (so the run reaches the stage under test). Faithfulness gates are downstream."""
    from src.polaris_graph.nodes.corpus_adequacy_gate import (
        AdequacyFinding,
        AdequacyThresholds,
        CorpusAdequacyReport,
    )
    thresholds = AdequacyThresholds(
        min_total_sources=1, min_t1_count=1, min_t1_plus_t2=1, min_t1_plus_t2_plus_t3=1,
        min_t3_plus_t4_plus_t6=0, min_evidence_rows=1, max_t5_plus_t6_fraction=1.0,
        max_t7_fraction=1.0, abort_if_below_fraction=0.0,
    )
    findings = [AdequacyFinding(
        name="total_sources", ok=True, observed=8, threshold=1, severity="critical",
    )]
    return CorpusAdequacyReport(
        decision="proceed", findings=findings, total_sources=8,
        tier_counts={"T1": 8}, evidence_rows=8, notes=[], thresholds=thresholds,
    )


def _install_real_path_gate_stubs(monkeypatch):
    """Stub run_live_retrieval (sync) + assess_corpus_adequacy (proceed) so the REAL run_one_query
    reaches its awaited generation stage offline. PG_AUTHORIZED_SWEEP_APPROVAL clears the structured
    corpus-approval gate (the T1-only mix is a material deviation; a real env override approves it —
    the exact sanctioned path, never a rubber-stamp). All faithfulness gates remain real."""
    monkeypatch.setattr(sweep, "run_live_retrieval", _fake_retrieval)
    monkeypatch.setattr(sweep, "assess_corpus_adequacy", _fake_adequacy_proceed)
    monkeypatch.setenv("PG_AUTHORIZED_SWEEP_APPROVAL", "1")
    # Keep the run deterministic + offline-safe: no STORM/agentic/auto-induction LLM lanes.
    for _flag in ("PG_USE_STORM_EXPANSION", "PG_USE_AGENTIC_SEARCH", "PG_USE_AUTO_INDUCTION",
                  "PG_USE_LLM_SCOPE", "PG_USE_SAFETY_REFUSAL"):
        monkeypatch.setenv(_flag, "0")


async def _drive_run_one_query_with_walltimeout(tmp_path, slug):
    """Replicate the EXACT main_async B20 call-site: set the deadline ContextVar, wrap
    run_one_query in asyncio.wait_for(timeout=wall), and on TimeoutError run BOTH the call-site
    finalizer (timed_out=True) AND the call-site timeout manifest write. Returns (run_dir,
    timed_out). The generator is a hang, so wait_for cancels run_one_query inside its body."""
    out_root = tmp_path
    q = {"slug": slug, "domain": "clinical", "question": _QUESTION}
    wall = run_wall_clock_seconds()  # tiny (the caller sets PG_RUN_WALL_CLOCK_SEC)
    token = sweep._RUN_WALL_CLOCK_DEADLINE_CTX.set(time.monotonic() + wall)
    timed_out = False
    run_dir = out_root / "clinical" / slug
    try:
        try:
            await asyncio.wait_for(
                sweep.run_one_query(q, out_root, resume=False), timeout=wall,
            )
        except (asyncio.TimeoutError, TimeoutError):
            timed_out = True
            # Call-site handler (mirrors main_async): finalizer no-ops if the inner finally
            # already wrote the timeout artifact; the manifest write still records the timeout.
            timeout_summary = {
                "slug": slug, "domain": "clinical", "question": _QUESTION,
                "status": "error_unexpected", "error": "wall-clock exceeded (hang)",
            }
            finalize_run_artifact(run_dir, timeout_summary, q, timed_out=True, wall_clock_seconds=wall)
            manifest = {
                "status": "error_unexpected", "release_allowed": False,
                "run_wall_clock_timeout": True, "run_wall_clock_seconds": wall,
            }
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
            )
    finally:
        sweep._RUN_WALL_CLOCK_DEADLINE_CTX.reset(token)
    return run_dir, timed_out


@pytest.mark.asyncio
async def test_b20_real_path_hang_emits_timeout_artifact(tmp_path, monkeypatch):
    """Codex iter-2 P1-1 — THE discriminating proof. An INJECTED REAL HANG flows through the
    ACTUAL run_one_query path: scope gate runs for real offline; retrieval/adequacy/approval are
    stubbed to REACH the awaited generator, which is replaced by a hang. asyncio.wait_for times
    out and CANCELS run_one_query, so run_one_query's OWN inner `finally` (the B11 finalizer)
    fires during the CancelledError unwind. With the wall-clock deadline ContextVar set, that
    inner finally now emits a TIMEOUT-labeled artifact deterministically (pre-fix it wrote a
    *degraded* artifact and the call-site timeout finalizer NO-OP'd on it -> mislabel)."""
    _install_real_path_gate_stubs(monkeypatch)
    monkeypatch.setenv("PG_RUN_WALL_CLOCK_SEC", "0.4")

    async def _hang_generation(*_a, **_k):
        await asyncio.sleep(30.0)  # far past the 0.4s wall-clock

    monkeypatch.setattr(sweep, "generate_multi_section_report", _hang_generation)

    run_dir, timed_out = await _drive_run_one_query_with_walltimeout(tmp_path, "hang")

    assert timed_out, "the real-path hang WAS caught by the run-level wall-clock"
    # (1) a NON-EMPTY human artifact exists
    report = run_dir / "report.md"
    assert report.is_file() and report.stat().st_size > 0
    body = report.read_text(encoding="utf-8")
    # (2) it is TIMEOUT-labeled (the P1-1 fix — written by the INNER finally during the cancel
    # unwind, NOT a degraded body)
    assert ("timed out" in body.lower() or "timeout" in body.lower())
    assert "wall-clock" in body.lower()
    assert artifact_kind_for_status("error_unexpected", timed_out=True) == sweep._ARTIFACT_KIND_TIMEOUT
    # the degraded wording must NOT be the artifact kind (proves the inner finally did not win
    # with timed_out=False)
    assert "**Artifact kind:** timeout" in body
    # (3) manifest exists and records the wall-clock timeout (call-site write)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] in UNIFIED_STATUS_VALUES
    assert manifest.get("run_wall_clock_timeout") is True


def test_b20_callsite_wraps_run_one_query_in_wait_for_and_sets_deadline():
    """Source check: the call site wraps run_one_query in asyncio.wait_for, sets the wall-clock
    DEADLINE ContextVar before it (so the inner finally can detect the cancellation — P1-1), and
    handles the timeout by emitting the finalizer artifact (B20). A `finally` inside run_one_query
    cannot reach a hang, so this MUST live at the call site."""
    import inspect

    src = inspect.getsource(sweep.main_async)
    assert "asyncio.wait_for(" in src
    assert "run_one_query(" in src
    assert "TimeoutError" in src
    assert "finalize_run_artifact(" in src
    assert "timed_out=True" in src
    # P1-1: the deadline ContextVar is set at the call site before wait_for.
    assert "_RUN_WALL_CLOCK_DEADLINE_CTX.set(" in src


# ─────────────────────────────────────────────────────────────────────────────
# P1-2 — the three JUDGE-EXCEPTION CLASSES, each injected through the REAL run_one_query
# path. For each: a non-empty artifact exists, the terminal status is in the shared schema,
# and the run is NOT silent-or-held (it ships a labeled verdict artifact).
# ─────────────────────────────────────────────────────────────────────────────
async def _drive_run_one_query(tmp_path, slug):
    """Drive the REAL run_one_query to completion (no wall-clock); return its summary."""
    out_root = tmp_path
    q = {"slug": slug, "domain": "clinical", "question": _QUESTION}
    return await sweep.run_one_query(q, out_root, resume=False), out_root / "clinical" / slug


def _assert_labeled_not_silent(run_dir, summary, *, allowed_statuses):
    """Shared P1-2 assertions: (1) manifest exists, (2) status in shared schema AND in the
    expected set for this judge-exception class, (3) a NON-EMPTY human artifact exists, (4) the
    run is NOT silent (an artifact + a manifest) and NOT a fabricated finding (the verdict body
    asserts no claim)."""
    status = summary.get("status")
    unified = to_unified_status(status) if status not in UNIFIED_STATUS_VALUES else status
    assert (run_dir / "manifest.json").is_file()
    assert unified in UNIFIED_STATUS_VALUES
    assert status in allowed_statuses, f"got {status!r}, expected one of {allowed_statuses}"
    report = run_dir / "report.md"
    assert report.is_file() and report.stat().st_size > 0
    assert report.read_text(encoding="utf-8").strip()


@pytest.mark.asyncio
async def test_p1_2_credibility_judge_exception_labels_not_silent(tmp_path, monkeypatch):
    """JUDGE-EXCEPTION CLASS 1 (credibility): a credibility-disclosure COVERAGE-GAP
    CredibilityPassError raised mid-run routes to abort_credibility_coverage_gap — a non-empty
    disclosed-gaps artifact, never silence. The faithfulness engine is untouched (the coverage
    gap is a fail-LOUD disclosure that a cited token's source was never scored)."""
    _install_real_path_gate_stubs(monkeypatch)

    async def _gen_raises_credibility(*_a, **_k):
        from src.polaris_graph.synthesis.credibility_pass import CredibilityPassError
        raise CredibilityPassError(
            "abort_credibility_coverage_gap: cited token e1 has no credibility/origin coverage"
        )

    monkeypatch.setattr(sweep, "generate_multi_section_report", _gen_raises_credibility)
    summary, run_dir = await _drive_run_one_query(tmp_path, "cred")
    _assert_labeled_not_silent(
        run_dir, summary, allowed_statuses={"abort_credibility_coverage_gap"},
    )


@pytest.mark.asyncio
async def test_p1_2_conflict_judge_exception_labels_not_silent(tmp_path, monkeypatch):
    """JUDGE-EXCEPTION CLASS 2 (conflict): the cross-document NLI conflict judge erroring under
    the strict-gate slate FAILS CLOSED to abort_conflict_judge_unavailable — a non-empty verdict
    artifact, NEVER a silent fail-open ('neutral', 0.0) that could drop a real contradiction. No
    conflict is fabricated; the artifact says 'could not adjudicate'."""
    _install_real_path_gate_stubs(monkeypatch)
    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", "1")
    monkeypatch.setenv("PG_BENCHMARK_STRICT_GATES", "1")  # strict -> fail closed (HOLD), not label+ship
    monkeypatch.setenv("PG_ALWAYS_RELEASE", "0")

    import src.polaris_graph.retrieval.semantic_conflict_detector as scd

    def _raise_conflict(*_a, **_k):
        raise scd.ConflictJudgeUnavailableError("judge transport 400 on same-subject pair (e1,e2)")

    monkeypatch.setattr(scd, "detect_semantic_conflicts_for_rows", _raise_conflict)
    summary, run_dir = await _drive_run_one_query(tmp_path, "conf")
    _assert_labeled_not_silent(
        run_dir, summary, allowed_statuses={"abort_conflict_judge_unavailable"},
    )
    # the verdict artifact discloses the judge could not decide (no fabricated conflict)
    body = (run_dir / "report.md").read_text(encoding="utf-8").lower()
    assert "could not adjudicate" in body or "could not decide" in body


@pytest.mark.asyncio
async def test_p1_2_entailment_judge_exception_labels_not_silent(tmp_path, monkeypatch):
    """JUDGE-EXCEPTION CLASS 3 (entailment): the binding entailment verifier erroring on too many
    sentences (judge_error_rate over cap) routes to abort_verifier_degraded — a non-empty artifact,
    never a silent ship. Each errored sentence already FAILED CLOSED (its claim was dropped at
    strict_verify), so faithfulness is untouched; this is the run-level degraded-verifier guard.

    Injection: a real MultiSectionResult with one verified section, plus the run-scoped entailment
    telemetry mutated to report calls+errors (simulating the judge erroring during generation), with
    PG_MAX_JUDGE_ERROR_RATE=0.0. PG_ALWAYS_RELEASE=0 -> the legacy abort (the always-release variant
    is the released_with_disclosed_gaps LABEL, covered by test_b15_*)."""
    _install_real_path_gate_stubs(monkeypatch)
    monkeypatch.setenv("PG_MAX_JUDGE_ERROR_RATE", "0.0")
    monkeypatch.setenv("PG_ALWAYS_RELEASE", "0")

    import src.polaris_graph.llm.entailment_judge as ej
    from src.polaris_graph.generator.multi_section_generator import (
        MultiSectionResult,
        SectionResult,
    )

    async def _gen_with_judge_errors(*_a, **_k):
        tel = ej._RUN_JUDGE_TELEMETRY.get()  # the SAME dict run_one_query started this run
        if tel is not None:
            tel["calls"] = tel.get("calls", 0) + 4
            tel["judge_error"] = tel.get("judge_error", 0) + 4
        section = SectionResult(
            title="Efficacy", focus="efficacy", ev_ids_assigned=["e0"], raw_draft="x",
            rewritten_draft="The drug works [#ev:e0:0-3].",
            verified_text="The drug works [#ev:e0:0-3].", biblio_slice={},
            sentences_verified=1, sentences_dropped=0, regen_attempted=False,
            dropped_due_to_failure=False,
        )
        return MultiSectionResult(
            sections=[section], outline=[], bibliography={}, total_words=3,
            total_sentences_verified=1, total_sentences_dropped=0,
            total_input_tokens=0, total_output_tokens=0,
        )

    monkeypatch.setattr(sweep, "generate_multi_section_report", _gen_with_judge_errors)
    summary, run_dir = await _drive_run_one_query(tmp_path, "ent")
    _assert_labeled_not_silent(
        run_dir, summary, allowed_statuses={"abort_verifier_degraded"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# B15 D8-BYPASS REGRESSION (Codex iter-3 P0) — the binding 4-role D8 gate must STAY binding
# under always-release: a verifier-reliability (judge_error_degraded) META-degradation may LABEL
# but MUST NOT short-circuit a FINDINGS report PAST D8. These tests drive the REAL run_one_query
# WITH a 4-role transport injected (so the binding D8 seam runs) and control ONLY the D8 release
# VERDICT (the faithfulness engine's per-claim CHECK / span / provenance are never relaxed — the
# real report_redactor decides what survives a non-VERIFIED verdict).
# ─────────────────────────────────────────────────────────────────────────────
_FINDINGS_TOKEN = "The drug reduced HbA1c by 1.5 percent"


def _gen_findings_with_judge_errors(*_a, **_k):
    """A generator stub that (1) trips the binding-verifier judge_error_degraded guard (mutates the
    run-scoped entailment telemetry to calls=errors) AND (2) emits a real MultiSectionResult whose
    verified prose carries a DISTINCTIVE findings token, so report.md is a FINDINGS body BEFORE D8
    runs. The async signature matches generate_multi_section_report."""
    import src.polaris_graph.llm.entailment_judge as ej
    from src.polaris_graph.generator.multi_section_generator import (
        MultiSectionResult,
        SectionResult,
    )

    async def _gen(*_aa, **_kk):
        tel = ej._RUN_JUDGE_TELEMETRY.get()
        if tel is not None:
            tel["calls"] = tel.get("calls", 0) + 4
            tel["judge_error"] = tel.get("judge_error", 0) + 4
        section = SectionResult(
            title="Efficacy", focus="efficacy", ev_ids_assigned=["e0"], raw_draft="x",
            rewritten_draft=f"{_FINDINGS_TOKEN} [#ev:e0:0-3].",
            verified_text=f"{_FINDINGS_TOKEN} [#ev:e0:0-3].", biblio_slice={},
            sentences_verified=1, sentences_dropped=0, regen_attempted=False,
            dropped_due_to_failure=False,
        )
        return MultiSectionResult(
            sections=[section], outline=[], bibliography={}, total_words=6,
            total_sentences_verified=1, total_sentences_dropped=0,
            total_input_tokens=0, total_output_tokens=0,
        )

    return _gen


def _make_d8_result(*, release_allowed, final_verdicts, status):
    """Build a deterministic FourRoleEvaluationResult + matching always-release ReleaseOutcome so
    a fake run_four_role_seam can drive the runner's post-D8 path without the real verifier LLMs.
    This controls the D8 VERDICT only — the runner's binding control flow (and the REAL
    report_redactor) is exercised for real."""
    from pathlib import Path as _Path

    from src.polaris_graph.roles.release_policy import ReleaseOutcome
    from src.polaris_graph.roles.sweep_integration import FourRoleEvaluationResult

    outcome = ReleaseOutcome(
        released=release_allowed,
        hard_block=not release_allowed,
        normal_release_blocked=not release_allowed,
        status=status,
        disclosed_gaps=[],
        hard_block_reasons=([] if release_allowed else ["d8_test_hard_block"]),
        release_quality_score=(1.0 if release_allowed else 0.0),
        safety_floor="ok",
    )
    return FourRoleEvaluationResult(
        release_allowed=release_allowed,
        held_reasons=([] if release_allowed else ["d8_test_hold"]),
        gaps=[],
        final_verdicts=final_verdicts,
        records=[],
        coverage_fraction=(1.0 if release_allowed else 0.0),
        fabricated_occurrence_latched=False,
        needs_rewrite=[],
        kg_path=_Path("verified_claim_graph_campaign.db"),
        release_outcome=outcome,
    )


async def _drive_run_one_query_with_d8(tmp_path, slug, *, fake_seam):
    """Drive the REAL run_one_query with PG_FOUR_ROLE_MODE on + a (sentinel) transport + inputs
    injected, so the binding 4-role D8 seam branch runs. `run_four_role_seam` is replaced by
    `fake_seam` (deterministic D8 verdict). Returns (summary, run_dir)."""
    import src.polaris_graph.roles.sweep_integration as si

    # Patch the seam symbol the runner imports from sweep_integration (local import resolves here).
    import unittest.mock as _mock  # test-only injection; NOT src production code
    with _mock.patch.object(si, "run_four_role_seam", fake_seam):
        out_root = tmp_path
        q = {"slug": slug, "domain": "clinical", "question": _QUESTION}
        summary = await sweep.run_one_query(
            q, out_root, resume=False,
            four_role_transport=object(),  # non-None -> the seam branch fires; fake_seam ignores it
            four_role_inputs={"sentinel": True},  # non-None -> not fail-closed
        )
    return summary, out_root / "clinical" / slug


@pytest.mark.asyncio
async def test_b15_d8_hold_under_always_release_withholds_findings_body(tmp_path, monkeypatch):
    """THE Codex iter-3 P0 PROOF (D8 stays binding). Under always-release, a judge_error_degraded
    verifier META-degradation NO LONGER short-circuits past D8 — the run flows THROUGH the binding
    4-role D8 gate. When D8 returns a NON-VERIFIED verdict, the findings body MUST be withheld and a
    NON-findings disclosure shipped (never a findings report.md that skipped D8).

    Faithfulness-critical: we control only the D8 VERDICT (non-VERIFIED) + omit the audit map, so
    the runner's always-release audit-map-missing path WITHHOLDS the leaking findings body via the
    REAL build_finalizer_artifact_body. We assert the distinctive findings token is GONE and the
    shipped artifact is the non-findings disclosure."""
    _install_real_path_gate_stubs(monkeypatch)
    monkeypatch.setenv("PG_ALWAYS_RELEASE", "1")
    monkeypatch.setenv("PG_FOUR_ROLE_MODE", "1")
    monkeypatch.setenv("PG_MAX_JUDGE_ERROR_RATE", "0.0")  # trip judge_error_degraded
    monkeypatch.setattr(
        sweep, "generate_multi_section_report", _gen_findings_with_judge_errors()
    )

    def _fake_seam_hold(*_a, **_k):
        # D8 returns a NON-VERIFIED verdict for a claim and writes NO four_role_claim_audit.json,
        # so the always-release path cannot surgically quarantine -> it WITHHOLDS the findings body.
        return _make_d8_result(
            release_allowed=False,
            final_verdicts={"c1": "UNSUPPORTED"},
            status="four_role_held",
        )

    summary, run_dir = await _drive_run_one_query_with_d8(
        tmp_path, "d8hold", fake_seam=_fake_seam_hold
    )

    # (1) the run reached D8 (the seam ran) — proven by the four_role_evaluation manifest block.
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "four_role_evaluation" in manifest, "the binding 4-role D8 seam did NOT run"
    # (2) a NON-EMPTY artifact exists; the FINDINGS body was WITHHELD (token gone), replaced by the
    # non-findings disclosure (Pipeline verdict / Artifact kind). This is the anti-D8-bypass proof.
    report = run_dir / "report.md"
    assert report.is_file() and report.stat().st_size > 0
    body = report.read_text(encoding="utf-8")
    assert _FINDINGS_TOKEN not in body, (
        "the findings body SHIPPED despite a D8 non-VERIFIED verdict — D8 was BYPASSED "
        "(faithfulness relaxation)"
    )
    assert "## Pipeline verdict" in body  # the non-findings disclosure
    assert "**Artifact kind:**" in body
    # (3) the unredacted findings body is preserved for the curator (never silently destroyed).
    assert (run_dir / "report_unredacted.md").is_file()
    # (4) status is in the shared schema + the audit trail shows the findings were withheld.
    assert summary["status"] in UNIFIED_STATUS_VALUES
    assert any(
        "audit_map_missing" in g or "withheld" in g
        for g in manifest.get("disclosed_gaps", [])
    )


@pytest.mark.asyncio
async def test_b15_d8_release_under_always_release_ships_findings_with_label(tmp_path, monkeypatch):
    """MIRROR proof: when the binding D8 gate RELEASES, the always-release verifier-degraded run
    ships the FINDINGS body WITH the verifier_degraded reliability LABEL disclosed (always-release
    AND faithfulness both satisfied). The label rides on the manifest disclosed_gaps; the findings
    token survives because D8 passed."""
    _install_real_path_gate_stubs(monkeypatch)
    monkeypatch.setenv("PG_ALWAYS_RELEASE", "1")
    monkeypatch.setenv("PG_FOUR_ROLE_MODE", "1")
    monkeypatch.setenv("PG_MAX_JUDGE_ERROR_RATE", "0.0")  # trip judge_error_degraded
    monkeypatch.setattr(
        sweep, "generate_multi_section_report", _gen_findings_with_judge_errors()
    )

    def _fake_seam_release(*_a, **_k):
        # D8 RELEASES (all VERIFIED) -> the findings body ships; the verifier-degraded LABEL is
        # disclosed on the manifest (NOT a status flip — D8 owns the headline).
        return _make_d8_result(
            release_allowed=True,
            final_verdicts={},
            status="four_role_released",
        )

    summary, run_dir = await _drive_run_one_query_with_d8(
        tmp_path, "d8rel", fake_seam=_fake_seam_release
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    # (1) the run reached D8 and D8 released.
    assert "four_role_evaluation" in manifest
    assert manifest.get("release_allowed") is True
    # (2) the FINDINGS body ships (D8 passed) ...
    body = (run_dir / "report.md").read_text(encoding="utf-8")
    assert _FINDINGS_TOKEN in body, "D8 released but the findings body did not ship"
    # (3) ... WITH the verifier-degraded reliability LABEL disclosed (auditable, never silent).
    assert "verifier_degraded_disclosed_gap" in manifest
    assert any("verifier_degraded" in g for g in manifest.get("disclosed_gaps", []))


@pytest.mark.asyncio
async def test_b15_off_branch_with_d8_transport_stays_abort_not_overwritten(tmp_path, monkeypatch):
    """REGRESSION GUARD (advisor point 1). With always-release OFF, the judge_error_degraded guard
    is a TERMINAL abort that fires BEFORE D8 — a degraded run must NOT be flowed into D8 and
    overwritten back to success. Inject a D8 transport that WOULD release; assert the run is still
    `abort_verifier_degraded`, release blocked, and the D8 seam NEVER ran (no four_role_evaluation)."""
    _install_real_path_gate_stubs(monkeypatch)
    monkeypatch.setenv("PG_ALWAYS_RELEASE", "0")  # OFF -> the abort branch is terminal
    monkeypatch.setenv("PG_FOUR_ROLE_MODE", "1")
    monkeypatch.setenv("PG_MAX_JUDGE_ERROR_RATE", "0.0")  # trip judge_error_degraded
    monkeypatch.setattr(
        sweep, "generate_multi_section_report", _gen_findings_with_judge_errors()
    )

    _seam_ran = {"called": False}

    def _fake_seam_would_release(*_a, **_k):
        _seam_ran["called"] = True  # if this fires, the abort branch did NOT short-circuit (BAD)
        return _make_d8_result(
            release_allowed=True, final_verdicts={}, status="four_role_released",
        )

    summary, run_dir = await _drive_run_one_query_with_d8(
        tmp_path, "d8off", fake_seam=_fake_seam_would_release
    )

    # the terminal abort fired BEFORE D8 -> the seam never ran, the run was NOT overwritten to success
    assert summary["status"] == "abort_verifier_degraded", (
        f"got {summary['status']!r}: the OFF abort branch was overwritten by the D8 status path (#1071 regression)"
    )
    assert not _seam_ran["called"], "the D8 seam ran AFTER a terminal abort_verifier_degraded — short-circuit lost"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("release_allowed") is False
    assert "four_role_evaluation" not in manifest  # D8 never ran
    # a non-empty artifact still exists (never silent).
    assert (run_dir / "report.md").is_file() and (run_dir / "report.md").stat().st_size > 0


# ─────────────────────────────────────────────────────────────────────────────
# B11 artifact-kind taxonomy — every status maps to a named, non-degraded-by-accident kind.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", _ALL_TERMINAL_STATUSES)
def test_artifact_kind_is_named_for_every_status(status):
    kind = artifact_kind_for_status(status)
    assert kind in {
        sweep._ARTIFACT_KIND_REFUSAL,
        sweep._ARTIFACT_KIND_INSUFFICIENT,
        sweep._ARTIFACT_KIND_DEGRADED,
        sweep._ARTIFACT_KIND_DISCLOSED_GAPS,
    }
    # the body must be non-empty + carry the kind label
    body = build_finalizer_artifact_body(
        research_question="Q?", status=status, error=None
    )
    assert kind in body
    assert "Pipeline verdict" in body


def test_success_status_is_not_a_silence_artifact():
    """`success` should never need a backstop body (report.md exists) — but if it somehow
    reaches the finalizer with no report.md, the body is still non-empty (never silent)."""
    body = build_finalizer_artifact_body(research_question="Q?", status="success", error=None)
    assert body.strip()


# ─────────────────────────────────────────────────────────────────────────────
# B15-B19 — post-success HOLD -> disclosed LABEL (release status), faithfulness untouched.
# These assert the FINAL STATUS is a released value, not merely that a file exists.
# ─────────────────────────────────────────────────────────────────────────────
# ── B18/B19 — BEHAVIORAL disposition (the pure helper), every convertible status + ON/OFF ──
@pytest.mark.parametrize("status", sorted(_B18_B19_CONVERTIBLE_HOLDS))
def test_b18_b19_convertible_hold_releases_under_always_release_on(status):
    """ON: every convertible META HOLD becomes released_with_disclosed_gaps + a disclosure."""
    new_status, disclosure = b18_b19_disposition(status, always_release=True)
    assert new_status == "released_with_disclosed_gaps"  # released, NOT a hold (acceptance 4)
    assert disclosure  # a non-empty disclosed-gap label
    assert new_status in UNIFIED_STATUS_VALUES


@pytest.mark.parametrize("status", sorted(_B18_B19_CONVERTIBLE_HOLDS))
def test_b18_b19_off_is_byte_identical_legacy_abort(status):
    """OFF: the helper returns the status UNCHANGED (clinical runs untouched, no disclosure)."""
    new_status, disclosure = b18_b19_disposition(status, always_release=False)
    assert new_status == status  # legacy abort byte-identical
    assert disclosure is None


def test_b18_b19_binding_d8_hold_is_never_converted():
    """FAITHFULNESS: the binding 4-role D8 hold must NEVER be converted, even ON. A real
    fabrication / coverage hold always wins over the always-release reframe."""
    for d8_hold in ("abort_four_role_release_held", "four_role_held"):
        assert d8_hold not in _B18_B19_CONVERTIBLE_HOLDS
        new_status, disclosure = b18_b19_disposition(d8_hold, always_release=True)
        assert new_status == d8_hold  # untouched
        assert disclosure is None


def test_b18_b19_non_hold_statuses_pass_through():
    """A normal success / partial status is not a convertible hold — unchanged either way."""
    for status in ("success", "partial_thin_corpus", "abort_no_verified_sections"):
        assert b18_b19_disposition(status, always_release=True)[0] == status
        assert b18_b19_disposition(status, always_release=False)[0] == status


def test_b15_b18_b19_released_status_is_in_shared_schema():
    """The released terminal the flips use must be a real shared-schema value (so B23 parity +
    the v6 actor accept it)."""
    assert "released_with_disclosed_gaps" in UNIFIED_STATUS_VALUES
    assert to_unified_status("released_with_disclosed_gaps") == "released_with_disclosed_gaps"


def test_b18_b19_conversion_is_reachable_no_intervening_return():
    """REACHABILITY (the dead-code guard a constant-grep cannot give): for EVERY convertible
    status, its set-site in run_one_query must precede the b18_b19_disposition call AND no
    `return summary` may lie between them — else the flip is dead code and the run still HOLDS
    while all other tests pass. This is the failure mode source-presence checks miss."""
    import inspect
    import re

    src = inspect.getsource(sweep.run_one_query)
    conv_idx = src.find("b18_b19_disposition(")
    assert conv_idx > 0, "the B18/B19 conversion call must exist in run_one_query"

    # The set-sites for each convertible status (literal assignment or the ledger-hold helper).
    set_markers = {
        "abort_evaluator_critical": 'summary_status = "abort_evaluator_critical"',
        "abort_discovery_degraded": 'summary_status = "abort_discovery_degraded"',
        "abort_required_entity_ledger_failed": "_apply_required_entity_ledger_hold(",
    }
    return_summary_re = re.compile(r"\n\s*return summary\s*\n")
    for status, marker in set_markers.items():
        set_idx = src.find(marker)
        assert set_idx > 0, f"set-site for {status} not found"
        assert set_idx < conv_idx, f"{status} is set AFTER the conversion — unreachable flip"
        # No `return summary` between the LAST set-site and the conversion (the FL-05 / quantified
        # backstop is the last writer of discovery_degraded; use the last occurrence to be safe).
        last_set_idx = src.rfind(marker, 0, conv_idx)
        span = src[last_set_idx:conv_idx]
        assert not return_summary_re.search(span), (
            f"a `return summary` lies between {status}'s set-site and the conversion — "
            "the HOLD->LABEL flip is DEAD CODE and the run would still hold"
        )


def test_b15_verifier_degraded_does_not_bypass_d8_in_source():
    """Codex iter-3 P0 SOURCE GUARD: the B15 always-release branch (a verifier-reliability
    META-degradation) must NOT short-circuit a findings report PAST the binding 4-role D8 gate.

    Pre-fix it set status=released_with_disclosed_gaps AND `return summary` BEFORE the D8 seam —
    shipping a findings report.md that never passed D8 (a D8-bypass = faithfulness relaxation).
    The fix: the always-release branch sets only a LABEL and FALLS THROUGH to D8; ONLY the OFF
    (abort) branch is terminal. We assert structurally:

      (1) the pre-D8 `return summary` for the always-release case is GONE — there is NO
          `return summary` between the always-release LABEL-set and the binding D8 seam call
          (`run_four_role_seam`), so the run provably reaches D8.
      (2) the OFF branch keeps the legacy terminal abort (status + its own `return summary`).
      (3) the disclosed-gap LABEL is surfaced AFTER D8 (manifest["disclosed_gaps"]), never as a
          pre-D8 terminal status flip."""
    import inspect
    import re

    src = inspect.getsource(sweep.run_one_query)
    assert "_b15_always_release()" in src
    return_summary_re = re.compile(r"\n\s*return summary\s*\n")

    # Locate the B15 block, its always-release `if` branch, the matching `else:`, and the binding
    # D8 seam call. The always-release branch (if .. else) and the D8 seam appear in this order.
    b15_idx = src.find('if verif_details.get("judge_error_degraded"):')
    assert b15_idx > 0, "the B15 judge_error_degraded block must exist"
    if_idx = src.find("if _b15_always_release():", b15_idx)
    assert if_idx > 0, "the B15 always-release if-branch must exist"
    else_idx = src.find("\n            else:", if_idx)
    assert else_idx > if_idx, "the B15 OFF (abort) else-branch must exist"
    seam_idx = src.find("run_four_role_seam,", else_idx)
    assert seam_idx > else_idx, "the binding 4-role D8 seam must come AFTER the B15 block"

    # (1) THE D8-BYPASS GUARD: the always-release `if` branch (between `if .. :` and `else:`) sets
    # the LABEL and has NO `return summary` — it FALLS THROUGH to the binding D8 seam. A pre-D8
    # `return summary` here is exactly the Codex iter-3 P0 (a findings report shipped skipping D8).
    always_release_branch = src[if_idx:else_idx]
    assert 'summary["verifier_degraded_disclosed_gap"] = (' in always_release_branch, (
        "the B15 always-release branch must set the disclosed-gap LABEL"
    )
    assert not return_summary_re.search(always_release_branch), (
        "the B15 always-release branch contains a `return summary` — it would BYPASS the binding "
        "4-role D8 gate (faithfulness relaxation). It MUST fall through to D8."
    )
    # the always-release branch must NOT set a terminal released_with_disclosed_gaps status pre-D8.
    assert 'summary["status"] = "released_with_disclosed_gaps"' not in always_release_branch

    # (2) OFF branch stays TERMINAL: the `else:` block sets the legacy abort status AND keeps its
    # own `return summary` BEFORE the D8 seam (so a degraded run is never overwritten to success by
    # the D8 status path — #1071). This is the regression guard advisor flagged.
    off_branch = src[else_idx:seam_idx]
    assert 'summary["status"] = "abort_verifier_degraded"' in off_branch  # legacy byte-identical
    assert return_summary_re.search(off_branch), (
        "the OFF (abort) branch must keep its terminal `return summary` so a degraded run is NOT "
        "later overwritten back to success by the D8 status path (#1071)"
    )
    # (3) the disclosed-gap LABEL is surfaced into the manifest AFTER D8 (not a pre-D8 status flip).
    assert 'manifest["verifier_degraded_disclosed_gap"] = _b15_verifier_gap' in src
    # The B18/B19 consolidated flip is gated on always-release too.
    assert "_b18_always_release()" in src


# ─────────────────────────────────────────────────────────────────────────────
# B16/B17 — report_redaction_failed: QUARANTINE the unpinnable claim, ship the rest.
# FAITHFULNESS-CRITICAL: uses the REAL report_redactor (never mocked).
# ─────────────────────────────────────────────────────────────────────────────
def test_b16_quarantine_removes_unpinnable_claim_from_shipped_body():
    """The discriminating faithfulness assertion. When annotate cannot TIER-1-pin a non-VERIFIED
    claim (an under-split straddle), the fallback to reconcile must QUARANTINE (remove) the
    claim's text from the shipped body. A status flip that left the claim asserted as fact would
    be a faithfulness RELAXATION — so we assert the claim text is GONE, not merely 'a file exists'."""
    from src.polaris_graph.roles.report_redactor import (
        ReportRedactionError,
        annotate_report_against_verdicts,
        reconcile_report_against_verdicts,
    )

    # An UNSUPPORTED claim straddling two sentences on one under-split line: annotate (TIER-1
    # per-line label) cannot pin it, but reconcile (TIER-2 minimal-containing-unit) can.
    report = (
        "The drug reduced HbA1c by 1.5 percent in adults "
        "The penalty is 27874 dollars per violation"
    )
    final_verdicts = {"c1": "UNSUPPORTED"}
    audit_map = {
        "c1": {"sentence": "The penalty is 27874 dollars per violation", "severity": "S1"}
    }
    markers = {"c1": "[confidence: low]"}

    # 1) annotate RAISES (cannot pin) — this is exactly the case our fallback handles.
    with pytest.raises(ReportRedactionError):
        annotate_report_against_verdicts(report, final_verdicts, audit_map, markers)

    # 2) the fallback (reconcile) QUARANTINES the claim and ships the rest.
    result = reconcile_report_against_verdicts(report, final_verdicts, audit_map)
    assert result.redacted_count == 1
    # FAITHFULNESS: the unverified claim's distinctive token is GONE from the shipped body.
    assert "27874" not in result.report_text
    # the gap language replaced it (a disclosure, not silence)
    assert "did not survive" in result.report_text.lower()


def test_b16_fallback_chain_present_in_source():
    """Source check: the always-release annotate-except handler falls back to reconcile
    (quarantine + ship the rest), and on the absolute residue withholds the leaking body."""
    import inspect

    src = inspect.getsource(sweep.run_one_query)
    annot_idx = src.find("except ReportRedactionError as _annot_exc:")
    assert annot_idx > 0
    handler = src[annot_idx:annot_idx + 4000]
    # the fallback to reconcile (quarantine)
    assert "reconcile_report_against_verdicts(" in handler
    # ships released, not held, once quarantined
    assert "released_with_disclosed_gaps" in handler
    # absolute residue: withhold the leaking body + keep an unredacted curator sidecar
    assert "report_unredacted.md" in handler


def test_b16_audit_map_missing_withholds_leaking_body_under_always_release():
    """Source check: a missing audit_map (cannot locate claims to quarantine) under
    always-release WITHHOLDS the leaking findings body (replaces it) rather than HOLDing with
    the leak on disk; OFF stays the legacy fail-closed report_redaction_failed."""
    import inspect

    src = inspect.getsource(sweep.run_one_query)
    assert "report_redaction_audit_map_missing" in src
    assert 'summary_status = "report_redaction_failed"' in src  # OFF legacy branch preserved


# ─────────────────────────────────────────────────────────────────────────────
# SECTION-lane cross-wire (Codex iter-2 fold-in): reliability_header -> report.md ARTIFACT,
# budget_tail_drops -> manifest. Both DEFENSIVE (absent at base 8002392e => byte-identical).
# ─────────────────────────────────────────────────────────────────────────────
def test_section_fields_absent_at_base_so_wiring_is_inert():
    """The cross-wire reads MultiSectionResult.reliability_header / .budget_tail_drops via
    getattr — neither field exists at this base, so the wiring is INERT (byte-identical) until
    the SECTION lane integrates. Pin that they are NOT yet on the dataclass (the inert proof)."""
    import dataclasses

    from src.polaris_graph.generator.multi_section_generator import MultiSectionResult

    field_names = {f.name for f in dataclasses.fields(MultiSectionResult)}
    assert "reliability_header" not in field_names
    assert "budget_tail_drops" not in field_names


def test_reliability_header_render_empty_when_absent():
    """DEFENSIVE: None / non-dict / empty -> "" (no prepend) so a base run's report.md is
    byte-identical. getattr(multi, 'reliability_header', None) yields None at base -> "" here."""
    assert render_reliability_header_md(None) == ""
    assert render_reliability_header_md({}) == ""
    assert render_reliability_header_md("not-a-dict") == ""  # type: ignore[arg-type]


def test_reliability_header_render_when_present():
    """When the SECTION lane attaches the dict, the header renders the corroboration COUNTS into
    a markdown block (a disclosure SIGNAL, never an asserted finding)."""
    header = {
        "claims_total": 10, "claims_with_verified_support": 9,
        "claims_multi_source_corroborated": 6, "claims_single_origin": 3,
        "claims_contested": 1, "corroboration_basis": "verified_support_origin_count",
    }
    md = render_reliability_header_md(header)
    assert md.startswith("## Reliability header")
    assert "Multi-source corroborated" in md
    assert "10" in md and "6" in md and "verified_support_origin_count" in md


def test_reliability_header_prepended_to_artifact_not_evaluated_text():
    """FAITHFULNESS-CRITICAL source check: the reliability header is prepended to the report.md
    ARTIFACT bytes, NEVER spliced into `final_report` (the evaluator/PT11 + judge text). A counts
    block reaching the uncited-numeric gate could abort a clean run — so it must stay out of the
    evaluated text. Verify the prepend is at the report.md write, and `final_report` is the
    unmodified text fed to run_external_evaluation / judge_report."""
    import inspect

    src = inspect.getsource(sweep.run_one_query)
    # the render is read defensively via getattr (absent at base) and prepended at the write
    assert 'render_reliability_header_md(' in src
    assert 'getattr(multi, "reliability_header", None)' in src
    # T5 (#1344): the reliability/audit MACHINERY is composed into the report.md ARTIFACT via
    # compose_report_with_reliability (a trailing typed appendix by default), NOT a bare
    # `_reliability_md + final_report` prepend — but it is STILL only in the report.md bytes, never
    # spliced into the evaluated `final_report` (asserted below).
    assert 'compose_report_with_reliability(final_report, _reliability_md)' in src
    # `final_report` (NOT the prepended bytes) is what the evaluator + judge read — verify the
    # render var name never enters those call args.
    assert "report_text=final_report" in src  # evaluator + judge both read final_report
    assert "report_text=_reliability_md" not in src


def test_budget_tail_drops_wired_defensively_into_manifest():
    """Source check: budget_tail_drops is read via getattr (absent at base -> key omitted ->
    byte-identical manifest) and added only when a non-empty list is present."""
    import inspect

    src = inspect.getsource(sweep.run_one_query)
    assert 'getattr(multi, "budget_tail_drops", None)' in src
    assert 'manifest["budget_tail_drops"]' in src


# ─────────────────────────────────────────────────────────────────────────────
# B12/B13 run-side glue — defensively consume the JUDGES-lane unscored labels.
# ─────────────────────────────────────────────────────────────────────────────
class _Carrier:
    """A minimal stand-in for a generator-result / retrieval object carrying the JUDGES-lane
    per-source / per-pair unscored label fields (which do NOT exist at this base)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_b12_b13_glue_absent_markers_yield_empty(monkeypatch):
    """At THIS base the JUDGES lane is not integrated, so the markers are absent — the glue
    must tolerate that and return empty lists (no crash, no false disclosure)."""
    out = _collect_judge_unscored_labels(_Carrier(), _Carrier())
    assert out == {"credibility_unscored": [], "conflict_unscored": []}
    # also tolerant of None carriers
    out2 = _collect_judge_unscored_labels(None, None)
    assert out2 == {"credibility_unscored": [], "conflict_unscored": []}


def test_b12_glue_collects_credibility_unscored_from_attribute():
    """When the JUDGES lane attaches `credibility_unscored` (per-source), the glue routes it."""
    multi = _Carrier(credibility_unscored=["src_a", "src_b"])
    out = _collect_judge_unscored_labels(multi, None)
    assert out["credibility_unscored"] == ["src_a", "src_b"]
    assert out["conflict_unscored"] == []


def test_b13_glue_collects_conflict_unscored_from_dict_carrier():
    """The glue also detects the marker as a dict KEY (the lane may attach to a dict bundle)."""
    retrieval = {"conflict_unscored": [{"pair": ["e1", "e2"]}]}
    out = _collect_judge_unscored_labels(None, retrieval)
    assert len(out["conflict_unscored"]) == 1
    assert out["credibility_unscored"] == []


def test_b12_b13_glue_wraps_scalar_into_list():
    """A scalar marker is normalized to a single-element list (robust to the lane's exact shape)."""
    multi = _Carrier(credibility_unscored="only_one")
    out = _collect_judge_unscored_labels(multi, None)
    assert out["credibility_unscored"] == ["only_one"]


def test_b12_b13_run_side_glue_present_in_source():
    """Source check: run_one_query consumes the unscored labels into the disclosed-gaps section
    (extends the B5/B7 disclosed-gap surfacing, does not duplicate it)."""
    import inspect

    src = inspect.getsource(sweep.run_one_query)
    assert "_collect_judge_unscored_labels(" in src
    assert '"credibility_unscored"' in src
    assert '"conflict_unscored"' in src
    assert "disclosed_gaps" in src


# ─────────────────────────────────────────────────────────────────────────────
# Cross-cutting: NO class-A path yields silence; faithfulness engine never mocked.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", _ALL_TERMINAL_STATUSES)
def test_no_class_a_status_yields_silence(tmp_path, status):
    """Exhaustive: for EVERY terminal status, the finalizer leaves a non-empty artifact when no
    report.md exists — there is no class-A status that produces silence."""
    run_dir = tmp_path / "d" / "s"
    run_dir.mkdir(parents=True)
    summary = {"status": status, "error": "x"}
    q = {"slug": "s", "domain": "d", "question": "Q?"}
    finalize_run_artifact(run_dir, summary, q)
    report = run_dir / "report.md"
    assert report.is_file()
    assert report.read_text(encoding="utf-8").strip()


def test_finalizer_is_wired_into_the_run_finally():
    """Source check: B11 is called from the run body's `finally` (the one choke point every
    non-hang exit passes through), and the call passes the wall-clock cancellation flag (P1-1)."""
    import inspect

    src = inspect.getsource(sweep.run_one_query)
    fin_idx = src.rfind("finally:")
    assert fin_idx > 0
    finally_block = src[fin_idx:]
    # The call is now multi-line (it passes timed_out=run_wall_clock_cancellation_active()).
    assert "finalize_run_artifact(" in finally_block
    assert "run_dir, summary, q," in finally_block
    assert "run_wall_clock_cancellation_active()" in finally_block
