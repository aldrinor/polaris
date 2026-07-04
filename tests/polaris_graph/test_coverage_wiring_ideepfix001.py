"""I-deepfix-001 (#1344) — DRB-II COVERAGE-LEVER WIRING gate (offline, $0).

Proves the 8 weight-and-consolidate breadth levers that were BUILT + triple-gated but sat DARK
(default-OFF, absent from the paid Gate-B slate) are now ARMED on the paid Gate-B path, that a dark
lever fails the run CLOSED pre-spend, that the operator-locked D3 analyst_synthesis stays OFF, and that
the pack_drb2 answer-boundary now excludes the T5 audit/disclosure/weighting appendix from the scored body.

§-1.3 DNA: this WIRES the existing weight-and-consolidate machinery (arm each flag at its EXISTING
default) — it asserts NO forced cap/target/thinner/canary/breadth-number. FAITHFULNESS-NEUTRAL: the
strict_verify / NLI / 4-role / provenance / span-grounding engine is NOT touched by any of this wiring.

RED on the pre-change snapshot (levers absent from the slate; assert fn + regex branch missing);
GREEN after the wiring lands.
"""

import os

import pytest

import scripts.dr_benchmark.run_gate_b as rg
import scripts.operational_readiness_preflight as orp
import scripts.dr_benchmark.pack_drb2 as pack


# The 6 pure coverage levers (O1/F1/F2/F5/R1/R2) + the 2 winner-slate levers (D1/D4).
_SIX_COVERAGE_FLAGS = (
    "PG_FACET_OUTLINE",
    "PG_ROUTE_ALL_BASKETS",
    "PG_EV_BUDGET_TRACKS_PAYLOAD",
    "PG_WORD_BUDGET_TRACKS_PAYLOAD",
    "PG_EXPERT_FACET_PLANNER",
    "PG_FACET_COMPLETENESS",
)
_D1_D4_FLAGS = ("PG_QUALIFIER_ELABORATION", "PG_ENRICHMENT_FACET_ROUTE")
_ALL_EIGHT = _SIX_COVERAGE_FLAGS + _D1_D4_FLAGS


def _gate_b_effective_env(hostile: bool = True) -> dict:
    """The Gate-B EFFECTIVE env the slate produces, computed by the SAME pure resolver the readiness
    preflight uses (``resolve_effective_config`` == a read-only replica of
    ``apply_full_capability_benchmark_slate``). ``hostile=True`` starts from an env that explicitly sets
    EVERY lever to "0" (a stray operator/.env), proving the slate FORCE-ON-pins them regardless."""
    meta = orp.load_slate_meta()
    base = {flag: "0" for flag in _ALL_EIGHT} if hostile else {}
    base["PG_SWEEP_ANALYST_SYNTHESIS"] = "1"  # hostile: operator tries to re-arm D3
    return orp.resolve_effective_config(base, meta)


# (a) the Gate-B effective-env builder yields each of the 6 coverage flags truthy ---------------------

@pytest.mark.parametrize("flag", _SIX_COVERAGE_FLAGS)
def test_six_coverage_flags_effective_truthy_on_gate_b(flag):
    eff = _gate_b_effective_env(hostile=True)
    assert orp._truthy(eff.get(flag)), (
        f"{flag} is NOT effective-truthy on the Gate-B path (a coverage lever would run DARK). "
        f"effective={eff.get(flag)!r}"
    )
    # armed by a force-pin (not merely a floor): force-ON + preflight-required + slate "1" + allowlisted.
    assert flag in rg._BENCHMARK_FORCE_ON_FLAGS
    assert flag in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1"
    assert flag in rg._WINNER_FLAG_ALLOWLIST


# (b) the D1/D4 winner-slate levers are truthy on the Gate-B path -------------------------------------

@pytest.mark.parametrize("flag", _D1_D4_FLAGS)
def test_d1_d4_levers_truthy_on_gate_b(flag):
    eff = _gate_b_effective_env(hostile=True)
    assert orp._truthy(eff.get(flag)), (
        f"{flag} (D1/D4) is NOT effective-truthy on the Gate-B path — it was armed ONLY by "
        f"run_honest_sweep_r3.main_async's apply_winner_slate_on_paid_path, which the Gate-B launcher "
        f"never calls. It must now ride the Gate-B slate. effective={eff.get(flag)!r}"
    )
    assert flag in rg._BENCHMARK_FORCE_ON_FLAGS
    assert flag in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1"


# (c) the pre-spend assert RAISES when any one coverage flag is forced off (fail-closed proof) --------

def test_prespend_assert_passes_when_all_armed(monkeypatch):
    for flag in _ALL_EIGHT:
        monkeypatch.setenv(flag, "1")
    monkeypatch.setenv("PG_WINNER_SLATE_PRESPEND_ASSERT", "1")
    rg.assert_coverage_levers_armed()  # must NOT raise


@pytest.mark.parametrize("dark_flag", _ALL_EIGHT)
def test_prespend_assert_raises_when_one_lever_dark(monkeypatch, dark_flag):
    for flag in _ALL_EIGHT:
        monkeypatch.setenv(flag, "1")
    monkeypatch.setenv("PG_WINNER_SLATE_PRESPEND_ASSERT", "1")
    monkeypatch.setenv(dark_flag, "0")  # a single dark lever
    with pytest.raises(RuntimeError, match=r"COVERAGE-LEVER-DARK"):
        rg.assert_coverage_levers_armed()


def test_prespend_assert_covers_all_eight_levers():
    covered = {flag for flag, _why in rg._COVERAGE_LEVER_FLAGS}
    assert covered == set(_ALL_EIGHT), covered


# (d) D3 / analyst_synthesis remain OFF (REQUIRED_OFF assert still fires) -----------------------------

def test_d3_analyst_synthesis_stays_off_and_required_off():
    # not armed as a coverage lever, and effective "0" even when the operator tries to re-arm it.
    assert "PG_SWEEP_ANALYST_SYNTHESIS" not in rg._BENCHMARK_FORCE_ON_FLAGS
    assert "PG_SWEEP_ANALYST_SYNTHESIS" not in {f for f, _ in rg._COVERAGE_LEVER_FLAGS}
    assert "PG_SWEEP_ANALYST_SYNTHESIS" in rg._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
    eff = _gate_b_effective_env(hostile=True)
    assert not orp._truthy(eff.get("PG_SWEEP_ANALYST_SYNTHESIS")), (
        f"D3 analyst_synthesis must be force-OFF; effective={eff.get('PG_SWEEP_ANALYST_SYNTHESIS')!r}"
    )


def test_required_off_loop_rejects_a_re_armed_d3(monkeypatch):
    """Replicate the run_gate_b preflight REQUIRED_OFF loop: a truthy D3 fails CLOSED."""
    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    tripped = [
        flag for flag in rg._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
        if os.getenv(flag, "1").strip() in ("1", "true", "True")
    ]
    assert "PG_SWEEP_ANALYST_SYNTHESIS" in tripped


# (e) pack_drb2 boundary now includes the Appendix header --------------------------------------------

def test_pack_drb2_boundary_matches_audit_appendix_header():
    # the exact header the render emits (run_honest_sweep_r3._AUDIT_MACHINERY_APPENDIX_BOUNDARY).
    header = "## Appendix: audit, disclosure, and weighting (not scored as report claims)"
    assert pack._APPENDIX_BOUNDARY_RE.match(header), (
        "the T5 audit-machinery appendix header is NOT recognized as an answer-body boundary — the "
        "audit-counts block would dilute the scored answer / risk scorer truncation of real body content"
    )
    # the original three boundaries still match (no regression).
    for legacy in ("## Bibliography", "## References", "## Evidence-support disclosure"):
        assert pack._APPENDIX_BOUNDARY_RE.match(legacy), legacy


def test_pack_drb2_answer_body_excludes_the_audit_appendix():
    body = (
        "# Report\n\n## Findings\nA real on-topic claim [1].\n\n"
        "## Appendix: audit, disclosure, and weighting (not scored as report claims)\n\n"
        "- Corroboration basis: `basket`\n"
    )
    scored = pack.answer_body(body)
    assert "real on-topic claim" in scored
    assert "Corroboration basis" not in scored, "the audit appendix leaked into the scored answer body"
