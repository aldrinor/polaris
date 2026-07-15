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
