"""ITEM 6 + slate env (I-arch-007 #1264) — Gate-B containment + death-forensic slate env.

Proves:
  * PG_TRAFILATURA_SUBPROCESS is FORCE-set to "1" by the slate (not merely defaulted / floored),
    so an operator override that left libxml2 containment OFF cannot survive — the uncatchable
    in-process SIGSEGV (MODE-1) is always contained in a hard-killable subprocess.
  * the credibility-pass wall + inflight knobs are pinned as a PAIR (Codex P2-1) with the sizing
    invariant: a HEALTHY large-corpus pass (~600 members) completes within the wall.
  * the sentinel-transport-degrade (ITEM 4) and postgen-resume (ITEM 5) flags are wired ON.

FAITHFULNESS-NEUTRALITY: every assertion is over fetch-containment / advisory-pass wall / a D8-seam
transport degrade that fails CLOSED / a generation-skip that re-runs all gates. NONE of these env
values changes strict_verify / NLI / 4-role D8 / span-grounding verdicts, the fail-closed sentinel,
the 0.40 section floor, or the cited-evidence set.
"""

from __future__ import annotations

import os

import pytest

import scripts.dr_benchmark.run_gate_b as gate_b


# The credibility-pass wall/inflight pair (kept in sync with the slate + the comment's sizing math).
_WORST_HEALTHY_MEMBERS = 619       # Q72 worst-case basket-member count (consolidated plan §ITEM 1)
_HEALTHY_PER_CALL_SECONDS = 40.0   # upper bound of a HEALTHY entailment-judge call (plan §ITEM 1)
_RUN_WALL_SECONDS = 10800          # the run-level wall-clock backstop (slate PG_RUN_WALL_CLOCK_SEC)


@pytest.fixture
def slate_env(monkeypatch):
    """Apply the full-capability slate into a clean env and yield the effective os.environ.

    Hostile-operator setup: pre-seed the env with values that the OLD setdefault/floor would have
    let WIN (PG_TRAFILATURA_SUBPROCESS=0 to leave containment OFF; a tiny wall + huge inflight to
    break the pair). The force-EXACT / force-ON slate must override all of them.
    """
    monkeypatch.setenv("PG_TRAFILATURA_SUBPROCESS", "0")        # operator tried to DISABLE containment
    monkeypatch.setenv("PG_CREDIBILITY_PASS_WALL_S", "1")       # operator tried a 1s wall (would degrade)
    monkeypatch.setenv("PG_CREDIBILITY_PASS_MAX_INFLIGHT", "1")  # operator tried serial (would hang)
    monkeypatch.setenv("PG_SENTINEL_TRANSPORT_DEGRADE", "0")    # operator tried to DISABLE the degrade
    monkeypatch.setenv("PG_RESUME_REUSE_POSTGEN", "0")          # operator tried to DISABLE the resume
    # The slate syncs import-time module globals (cost cap / generator timeout / 4-role effort); those
    # setters are no-ops here beyond reading os.environ, so apply() is safe in-test.
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=False)
    yield os.environ


def test_trafilatura_subprocess_forced_on_not_defaulted(slate_env):
    """PG_TRAFILATURA_SUBPROCESS is FORCE-set to "1" — an operator =0 cannot survive the slate."""
    assert slate_env["PG_TRAFILATURA_SUBPROCESS"] == "1", (
        "MODE-1 containment gap: a stray operator PG_TRAFILATURA_SUBPROCESS=0 survived the slate; "
        "the in-process libxml2 SIGSEGV would silently kill the sweep."
    )


def test_trafilatura_subprocess_is_a_force_on_flag():
    """The flag is in the FORCE_ON set (not a setdefault / numeric floor) — structural guarantee."""
    assert "PG_TRAFILATURA_SUBPROCESS" in gate_b._BENCHMARK_FORCE_ON_FLAGS
    assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_TRAFILATURA_SUBPROCESS"] == "1"


def test_credibility_pass_wall_and_inflight_pinned_as_a_pair(slate_env):
    """Wall + inflight are BOTH force-set to the slate pair (Codex P2-1), overriding a hostile env."""
    wall = float(slate_env["PG_CREDIBILITY_PASS_WALL_S"])
    inflight = int(slate_env["PG_CREDIBILITY_PASS_MAX_INFLIGHT"])
    # The slate's chosen pair (kept in sync with the slate dict + its sizing comment). I-arch-007 #1264
    # PREFLIGHT RE-SIZE: the wall is RAISED 1800 -> 3000 for generous headroom over the longest healthy
    # large-corpus pass (~1548s worst-case) so a slow-but-HEALTHY pass completes-and-WEIGHTS; still far
    # under the run-wall (10800s) so it never starves generation.
    assert wall == 3000.0
    assert inflight == 16
    # Both are force-EXACT (the int-FLOOR path would mishandle the FLOAT wall + break the pair).
    assert "PG_CREDIBILITY_PASS_WALL_S" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
    assert "PG_CREDIBILITY_PASS_MAX_INFLIGHT" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS


def test_credibility_pair_sizing_invariant_holds(slate_env):
    """The chosen (wall, inflight) lets a HEALTHY ~600-member pass COMPLETE within the wall.

    Sizing reality (consolidated plan §ITEM 1): the pass is SERIAL-equivalent per worker, so a worst-
    case healthy pass of N members at per_call seconds across `inflight` workers takes ~N*per_call/inflight.
    The wall must clear that, AND stay safely under the run-wall so it never starves Stage-2 generation.
    """
    wall = float(slate_env["PG_CREDIBILITY_PASS_WALL_S"])
    inflight = int(slate_env["PG_CREDIBILITY_PASS_MAX_INFLIGHT"])
    worst_healthy_seconds = _WORST_HEALTHY_MEMBERS * _HEALTHY_PER_CALL_SECONDS / inflight
    assert worst_healthy_seconds <= wall, (
        f"sizing broken: a healthy {_WORST_HEALTHY_MEMBERS}-member pass needs ~{worst_healthy_seconds:.0f}s "
        f"at inflight={inflight} but the wall is only {wall:.0f}s — the WEIGHT half would ship unscored."
    )
    assert wall < _RUN_WALL_SECONDS, (
        f"the credibility-pass wall {wall:.0f}s must stay under the run-wall {_RUN_WALL_SECONDS}s so it "
        "can never starve Stage-2 generation."
    )


def test_per_call_total_deadline_walls_force_set(slate_env):
    """I-arch-007 #1264 PREFLIGHT RE-GO: the two per-call total-deadline walls (the residual
    trickle-hang fix) are FORCE-set to "300" — a hostile operator value cannot leave a verifier
    POST site unbounded. 300s clears the longest HEALTHY verifier call (~6-40s) with wide margin,
    so the OFF-path call is byte-identical; only a trickle-hang trips the wall (transport-only,
    faithfulness-neutral: the fail-closed sentinel on exhaustion is the SAME verdict the caller
    already handles)."""
    assert slate_env["PG_CREDIBILITY_JUDGE_TOTAL_S"] == "300"
    assert slate_env["PG_ROLE_TRANSPORT_TOTAL_S"] == "300"
    # Force-EXACT (wall-seconds, not capability floors) — the int-FLOOR max() is meaningless here.
    assert "PG_CREDIBILITY_JUDGE_TOTAL_S" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
    assert "PG_ROLE_TRANSPORT_TOTAL_S" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
    # The wall comfortably exceeds the longest healthy verifier call (so a healthy call never trips it),
    # and stays under the per-section / run-wall hierarchy so it can never starve generation.
    assert float(slate_env["PG_CREDIBILITY_JUDGE_TOTAL_S"]) > _HEALTHY_PER_CALL_SECONDS
    assert float(slate_env["PG_ROLE_TRANSPORT_TOTAL_S"]) > _HEALTHY_PER_CALL_SECONDS
    assert float(slate_env["PG_CREDIBILITY_JUDGE_TOTAL_S"]) < _RUN_WALL_SECONDS
    assert float(slate_env["PG_ROLE_TRANSPORT_TOTAL_S"]) < _RUN_WALL_SECONDS


def test_dormant_caps_forced_off(slate_env):
    """I-arch-007 #1264 DORMANT-CAP CLEANUP (operator: ZERO cap; §-1.3 BANNED number-forcing bolt-ons).

    Both caps are pinned EXACTLY OFF ("0") so a stray operator/.env value can never silently re-enable
    a CAP that fights the WEIGHT-AND-CONSOLIDATE architecture:
      * PG_CAPPED_FINDING_DEDUP=0 removes the re-cap-to-max_ev (the consolidated keep-all floor pool flows
        to composition bounded only by the per-section token budget + the UNCHANGED faithfulness gate).
        Verified the ONLY consumer is the two run_honest_sweep_r3 re-cap sites (both `and _capped_dedup`-
        gated), so 0 makes `and _capped_dedup` short-circuit and skips BOTH re-cap calls.
      * PG_SPAN_PER_SOURCE_CITE_CAP=0 is the fact_dedup no-op default made EXPLICIT (0 == OFF, byte-
        identical sections — fact_dedup `_read_span_cite_cap`).
    Both faithfulness-neutral (a cap only ever DROPPED an already-verified citation / consolidated row)."""
    assert slate_env["PG_CAPPED_FINDING_DEDUP"] == "0"
    assert slate_env["PG_SPAN_PER_SOURCE_CITE_CAP"] == "0"
    # Force-EXACT to "0" (NOT force-ON, NOT preflight-required — a required-truthy flag set to 0 would
    # fail the preflight). The flag is GONE from both enforcement sets that demand truthiness.
    assert "PG_CAPPED_FINDING_DEDUP" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
    assert "PG_SPAN_PER_SOURCE_CITE_CAP" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
    assert "PG_CAPPED_FINDING_DEDUP" not in gate_b._BENCHMARK_FORCE_ON_FLAGS
    assert "PG_CAPPED_FINDING_DEDUP" not in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert "PG_SPAN_PER_SOURCE_CITE_CAP" not in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


def test_capped_dedup_zero_survives_hostile_operator_one(monkeypatch):
    """A hostile operator PG_CAPPED_FINDING_DEDUP=1 (trying to RESTORE the cap) cannot survive the
    force-EXACT slate — the slate pins it back to "0" (ZERO cap, unconditional)."""
    monkeypatch.setenv("PG_CAPPED_FINDING_DEDUP", "1")          # operator tries to RE-ENABLE the cap
    monkeypatch.setenv("PG_SPAN_PER_SOURCE_CITE_CAP", "5")      # operator tries to set a per-source cap
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=False)
    assert os.environ["PG_CAPPED_FINDING_DEDUP"] == "0"
    assert os.environ["PG_SPAN_PER_SOURCE_CITE_CAP"] == "0"


def test_sentinel_on_and_resume_intentionally_off(slate_env):
    """ITEM 4 (sentinel transport degrade) is force-ON; ITEM 5 (PG_RESUME_REUSE_POSTGEN) is
    INTENTIONALLY default-OFF — deferred while the ITEM 5a generator-side cached-draft hook is absent
    (Codex build-gate iter-1 P1: force-on would hard-fail every --resume instead of regenerating from
    corpus_snapshot). So a hostile operator =0 SURVIVES for resume (correct: reuse path stays inert)."""
    assert slate_env["PG_SENTINEL_TRANSPORT_DEGRADE"] == "1"
    assert slate_env["PG_RESUME_REUSE_POSTGEN"] == "0"
    assert "PG_SENTINEL_TRANSPORT_DEGRADE" in gate_b._BENCHMARK_FORCE_ON_FLAGS
    assert "PG_RESUME_REUSE_POSTGEN" not in gate_b._BENCHMARK_FORCE_ON_FLAGS


def test_run_gate_b_query_forces_trafilatura_subprocess_inline(monkeypatch):
    """The per-query path (run_gate_b_query) also FORCE-sets containment ON (not setdefault).

    Belt-and-braces: even on a direct run_gate_b_query call that did not go through the slate, an
    operator PG_TRAFILATURA_SUBPROCESS=0 must not survive. We assert the SOURCE forces it (string
    check on the function body) so a regression back to setdefault is caught without a live run.
    """
    import inspect

    src = inspect.getsource(gate_b.run_gate_b_query)
    assert 'os.environ["PG_TRAFILATURA_SUBPROCESS"] = "1"' in src, (
        "run_gate_b_query must FORCE PG_TRAFILATURA_SUBPROCESS=1 (not setdefault) so the in-process "
        "libxml2 SIGSEGV containment cannot be disabled by a stray operator override."
    )
    assert 'os.environ.setdefault("PG_TRAFILATURA_SUBPROCESS"' not in src, (
        "regression: run_gate_b_query reverted to setdefault for PG_TRAFILATURA_SUBPROCESS — an "
        "operator =0 could leave libxml2 containment OFF."
    )
