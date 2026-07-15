"""feat/intake-contract — A/B contract-eval harness DRY-RUN test.

Drives scripts/ab_contract_eval.py's offline path and proves:
  (a) TREATMENT (three flags ON) diverges from BASELINE on ALL three surfaces
      (post-write adherence, intake contract, instruction-slot coverage);
  (b) BASELINE (flags OFF) is byte-identical to a no-op today — every surface None;
  (c) the harness restores the environment exactly after each arm (no flag leakage);
  (d) the PAID --live path is double-gated and REFUSES without the spend token;
  (e) no live client / network module is imported by the dry-run.

Fully offline: every surface runs regex / llm_fn=None / pure bind. No network, no LLM,
no compose, no RACE, no FACT.
"""
from __future__ import annotations

import importlib
import sys

ab = importlib.import_module("scripts.ab_contract_eval")


# ── (a)+(b) dry-run coherence: baseline inert, treatment active + divergent ───

def test_dry_run_is_coherent_ab(monkeypatch) -> None:
    # Start from a clean env so the harness controls the flags itself.
    for f in ab._TREATMENT_FLAGS:
        monkeypatch.delenv(f, raising=False)

    report = ab.run_dry_run(ab._default_tasks())
    v = report["verdict"]
    assert v["baseline_inert"] is True
    assert v["treatment_active"] is True
    assert v["coherent_ab"] is True
    assert v["n_tasks"] == 2

    for rec in report["tasks"]:
        base, treat = rec["baseline"], rec["treatment"]
        # (b) BASELINE inert — every surface None (flags OFF add nothing).
        assert base["postwrite"] is None
        assert base["intake_contract"] is None
        assert base["slot_coverage"] is None
        # (a) TREATMENT active + divergent on ALL THREE surfaces.
        assert treat["postwrite"] is not None
        assert treat["intake_contract"] is not None
        assert treat["slot_coverage"] is not None
        assert treat != base


def test_treatment_surfaces_have_expected_shape(monkeypatch) -> None:
    for f in ab._TREATMENT_FLAGS:
        monkeypatch.delenv(f, raising=False)
    rec = ab._eval_task(ab._default_tasks()[0])
    treat = rec["treatment"]
    # post-write adherence is OBSERVE-ONLY (enforced is always False).
    assert treat["postwrite"]["enforced"] is False
    # intake contract is FLOOR-only offline (no LLM enrich).
    assert treat["intake_contract"]["source"] == "floor"
    # a comparison instruction slot was extracted + bound.
    kinds = {s["kind"] for s in treat["slot_coverage"]}
    assert "comparison" in kinds


# ── (c) env is restored exactly after each arm ────────────────────────────────

def test_flag_arm_restores_environment(monkeypatch) -> None:
    import os

    monkeypatch.delenv("PG_EXTRACT_INSTRUCTION_SLOTS", raising=False)
    monkeypatch.setenv("PG_INTAKE_CONTRACT_COMPILE", "preexisting")
    with ab._flag_arm(on=True):
        assert os.environ["PG_EXTRACT_INSTRUCTION_SLOTS"] == "1"
        assert os.environ["PG_INTAKE_CONTRACT_COMPILE"] == "1"
    # After the arm: the preexisting value is restored, the absent one stays absent.
    assert os.environ.get("PG_EXTRACT_INSTRUCTION_SLOTS") is None
    assert os.environ["PG_INTAKE_CONTRACT_COMPILE"] == "preexisting"


# ── (d) the paid --live path is double-gated ──────────────────────────────────

def test_live_refuses_without_token(capsys) -> None:
    # --live but no spend token => refuse with a nonzero exit.
    rc = ab.main(["--live"])
    assert rc == 2


def test_live_refuses_with_wrong_token() -> None:
    rc = ab.main(["--live", "--i-understand-this-spends", "nope"])
    assert rc == 2


def test_dry_run_default_exits_zero(monkeypatch) -> None:
    for f in ab._TREATMENT_FLAGS:
        monkeypatch.delenv(f, raising=False)
    rc = ab.main([])  # default mode == dry-run
    assert rc == 0


# ── (e) no live client / network module imported by the dry-run ───────────────

def test_dry_run_imports_no_live_client(monkeypatch) -> None:
    for f in ab._TREATMENT_FLAGS:
        monkeypatch.delenv(f, raising=False)
    ab.run_dry_run(ab._default_tasks())
    forbidden = ("deepresearch_bench_race", "utils.scrape", "utils.validate")
    for name in list(sys.modules):
        assert not any(f in name for f in forbidden), f"live module leaked: {name}"


# ═════════════════════════════════════════════════════════════════════════════
# LIVE PATH — fully MOCKED. No compose, no RACE, no FACT, no network, no paid call.
# The paid seam (ab.LiveRunner) is NEVER constructed here; a recorder is injected.
# ═════════════════════════════════════════════════════════════════════════════

from pathlib import Path  # noqa: E402


# ── (b1) the flag-set assembly is correct + arms differ ONLY by the 3 flags ───

def test_arm_flag_env_baseline_vs_treatment() -> None:
    base = ab._arm_flag_env(treatment=False, web_search=False)
    treat = ab._arm_flag_env(treatment=True, web_search=False)
    # The three contract flags are the ONLY difference.
    for f in ab._TREATMENT_FLAGS:
        assert base[f] == "0"
        assert treat[f] == "1"
    # Everything else is byte-identical across arms (no confound).
    shared = {k: v for k, v in base.items() if k not in ab._TREATMENT_FLAGS}
    assert shared == {k: v for k, v in treat.items() if k not in ab._TREATMENT_FLAGS}
    # Champion model-lock + pinned confounds + web-search control.
    assert base["PG_OUTLINE_AGENT"] == "1"
    assert base["PG_SYNTHESIS_QUANT_DIRECTIVE"] == "0"
    assert base["PG_OUTLINE_WEB_SEARCH"] == "0"


def test_arm_flag_env_live_web_toggles_web_search_on_both_arms() -> None:
    for treatment in (False, True):
        assert ab._arm_flag_env(treatment=treatment, web_search=True)["PG_OUTLINE_WEB_SEARCH"] == "1"
        assert ab._arm_flag_env(treatment=treatment, web_search=False)["PG_OUTLINE_WEB_SEARCH"] == "0"


# ── (b2) score parsers ────────────────────────────────────────────────────────

def test_parse_race_result(tmp_path) -> None:
    p = tmp_path / "race_result.txt"
    p.write_text("Comprehensiveness: 0.4110\nInsight: 0.4051\n"
                 "Instruction Following: 0.4621\nReadability: 0.4172\n"
                 "Overall Score: 0.4218\n")
    r = ab._parse_race_result(p)
    assert r == {"comprehensiveness": 0.4110, "insight": 0.4051,
                 "instruction_following": 0.4621, "readability": 0.4172, "overall": 0.4218}


def test_parse_fact_result(tmp_path) -> None:
    p = tmp_path / "fact_result.txt"
    p.write_text("total_citations: 44.0\ntotal_valid_citations: 22.0\nvalid_rate: 0.5\n")
    r = ab._parse_fact_result(p)
    assert r == {"valid_rate": 0.5, "total_valid_citations": 22.0, "total_citations": 44.0}


# ── a recorder standing in for the PAID LiveRunner ────────────────────────────

class _MockRunner:
    """Records the call sequence + the treatment flag, and returns canned scores that
    DIFFER between arms so delta math is verifiable. Spends nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def compose(self, task, *, treatment, arm_out_dir):
        self.calls.append(("compose", treatment))
        return Path(arm_out_dir) / "report.md"

    def bridge(self, *, report_md, task, target_name):
        self.calls.append(("bridge", target_name))
        return Path("raw") / f"{target_name}.jsonl"

    def race(self, *, target_name, task):
        self.calls.append(("race", target_name))
        t = target_name.endswith("treatment")
        return {"overall": 0.44 if t else 0.40,
                "comprehensiveness": 0.42 if t else 0.41,
                "insight": 0.41 if t else 0.40,
                "instruction_following": 0.47 if t else 0.46,
                "readability": 0.42 if t else 0.42}

    def fact(self, *, target_name, task):
        self.calls.append(("fact", target_name))
        t = target_name.endswith("treatment")
        return {"valid_rate": 0.90 if t else 0.80,
                "total_valid_citations": 27.0 if t else 24.0,
                "total_citations": 30.0}


# ── (b3) orchestrator: correct order, correct flag-arms, correct deltas ───────

def test_run_live_ab_order_flags_and_deltas(tmp_path) -> None:
    task = {"id": 72, "prompt": "p", "language": "en"}
    mock = _MockRunner()
    result = ab.run_live_ab([task], mock, workdir=tmp_path)

    # Per arm, the four stages fire in order compose→bridge→RACE→FACT; baseline arm
    # (treatment=False) runs before the treatment arm (treatment=True).
    methods = [c[0] for c in mock.calls]
    assert methods == ["compose", "bridge", "race", "fact"] * 2
    compose_treatment_flags = [c[1] for c in mock.calls if c[0] == "compose"]
    assert compose_treatment_flags == [False, True]
    # The bridge/RACE/FACT targets are distinct per arm.
    assert ("bridge", "abctr_task72_baseline") in mock.calls
    assert ("bridge", "abctr_task72_treatment") in mock.calls

    # Deltas = treatment − baseline, computed from the canned scores.
    d = result["tasks"][0]["delta"]
    assert d["race"]["overall"] == 0.04
    assert d["fact"]["valid_rate"] == 0.1
    assert d["race"]["readability"] == 0.0

    agg = result["aggregate"]
    assert agg["n_tasks"] == 1
    assert agg["race"]["overall"] == {"baseline": 0.40, "treatment": 0.44, "delta": 0.04}
    assert agg["fact"]["valid_rate"]["delta"] == 0.1


# ── (b4) gated entry with an injected mock: refuses/needs both gates, spends 0 ──

def _both_gates_args(tmp_path):
    return ab._parse_args([
        "--live", "--i-understand-this-spends", ab._SPEND_TOKEN,
        "--live-workdir", str(tmp_path / "wd"),
    ])


def test_run_live_with_injected_runner_runs_full_ab(tmp_path, monkeypatch, capsys) -> None:
    # No API key present — proves the INJECTED-runner path never reaches the paid seam.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Guard: LiveRunner (the paid seam) must NOT be constructed on the injected path.
    monkeypatch.setattr(ab, "LiveRunner",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("paid seam built")))
    mock = _MockRunner()
    rc = ab.run_live(_both_gates_args(tmp_path), runner=mock)
    assert rc == 0
    # compose→bridge→race→fact for the single default task (72), both arms.
    assert [c[0] for c in mock.calls] == ["compose", "bridge", "race", "fact"] * 2
    # The MANDATORY cost warning printed (before results).
    err = capsys.readouterr().err
    assert "PAID LIVE A/B" in err and "SPENDS REAL MONEY" in err


def test_run_live_double_gate_still_enforced_even_with_runner(tmp_path) -> None:
    # --live but NO token: refuse (rc 2) even if a runner is injected — the gate is first.
    args = ab._parse_args(["--live", "--live-workdir", str(tmp_path / "wd")])
    assert ab.run_live(args, runner=_MockRunner()) == 2


def test_live_orchestration_imports_no_live_client(tmp_path) -> None:
    # Driving the whole mocked live orchestration imports NO benchmark live module.
    ab.run_live_ab([{"id": 72, "prompt": "p", "language": "en"}], _MockRunner(), workdir=tmp_path)
    forbidden = ("deepresearch_bench_race", "utils.scrape", "utils.validate", "utils.extract")
    for name in list(sys.modules):
        assert not any(f in name for f in forbidden), f"live module leaked: {name}"
