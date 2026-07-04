"""I-meta-007a smoke — benchmark-stack activation.

Proves the Gate-B benchmark entry now turns on BOTH the 4-role seam AND the
verifiable calculator, enforces 4-distinct-family + self-host-endpoint preflight
(live path only), and that the legacy single-judge is SKIPPED when the 4-role
seam runs (no double-judge with conflicting models). SPEND-FREE — no LLM, no net.
"""
from __future__ import annotations

import asyncio
import os

import pytest

import src.polaris_graph.llm.openrouter_client as orc
from scripts.dr_benchmark import run_gate_b as g


def _clear_flags():
    os.environ.pop("PG_FOUR_ROLE_MODE", None)
    os.environ.pop("PG_ENABLE_QUANTIFIED_ANALYSIS", None)
    # I-cap-002 feature 2/4 (#1060): advisory analytical-depth annotation activation flag.
    os.environ.pop("PG_DEPTH_ANNOTATION_IN_BENCHMARK", None)
    # I-cap-002 feature 3/4 (#1060): agentic URL-discovery activation flag.
    os.environ.pop("PG_AGENTIC_SEARCH_IN_BENCHMARK", None)
    # I-cap-002 feature 4/4 (#1060): NLI entailment annotation activation flag.
    os.environ.pop("PG_NLI_IN_BENCHMARK", None)
    # I-cap-005 (#1068): clear the full-capability slate too, so the test proves run_gate_b_query SETS
    # them (rather than a leaked value from another test passing the assertion).
    for _k in (
        "PG_STORM_ENABLED_IN_BENCHMARK", "PG_ENABLE_TOOL_TRACKER", "PG_SWEEP_EVIDENCE_DEEPENER",
        "PG_SWEEP_FETCH_CAP", "PG_SWEEP_MAX_SERPER", "PG_SWEEP_MAX_S2", "PG_MAX_COST_PER_RUN",
    ):
        os.environ.pop(_k, None)


def test_families_are_four_distinct_lineages():
    # I-beatboth-008 (#1285) re-premise: all-GLM-5.2 — the generator AND the mirror are now BOTH
    # z-ai/glm-5.2 (the operator-signed family_policy.allowed_collisions pair [[generator, mirror]]
    # in the lock). The 4 roles are still ENUMERATED, but the active families are {z-ai (gen+mirror),
    # minimax (sentinel), moonshotai (judge)} = 3 distinct lineages — the gen+mirror collision is the ONE
    # permitted pair. The two-family invariant for every OTHER role is asserted by the negative
    # collision test below.
    fams = g.assert_four_role_families_distinct()
    assert set(fams) == {"generator", "mirror", "sentinel", "judge"}
    assert fams["generator"] == fams["mirror"]        # the allowed_collisions z-ai pair
    assert len(set(fams.values())) == 3               # gen+mirror share z-ai; sentinel+judge distinct


def test_unlisted_same_family_collision_raises(monkeypatch):
    """I-beatboth-008 (#1285) BINDING NEGATIVE case: the all-GLM-5.2 allowed_collisions relaxation
    is scoped to ONLY the [[generator, mirror]] pair. An UNLISTED same-family collision MUST still
    FAIL LOUD — the two-family invariant is preserved for every other role. PG_JUDGE_MODEL into the
    z-ai lineage puts a THIRD role (Judge) into the generator+mirror family; the (generator, judge)
    pair is NOT in allowed_collisions, so the family check must RAISE. monkeypatch auto-reverts the
    env so it does not leak into later tests in this file (which has no env-isolation fixture).

    I-judge-kimi (2026-06-29): the benchmark Judge now resolves via PG_BENCHMARK_JUDGE_MODEL (the
    decouple from the lock's PG_JUDGE_MODEL — gate P1-1), so the collision is forced through THAT env."""
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
    monkeypatch.setenv("PG_BENCHMARK_JUDGE_MODEL", "z-ai/glm-5.1")
    with pytest.raises((RuntimeError, ValueError), match="(?i)judge|lane|collision"):
        g.assert_four_role_families_distinct()


def test_preflight_fails_loud_when_endpoint_unset(monkeypatch):
    # live preflight must FAIL before the sweep when a self-host URL is missing.
    for role in ("MIRROR", "SENTINEL", "JUDGE"):
        monkeypatch.delenv(f"PG_{role}_BASE_URL", raising=False)
    with pytest.raises((RuntimeError, ValueError)):
        g.preflight_self_host_roles()


def test_gate_b_query_sets_both_flags_and_skips_preflight_on_injected_transport(monkeypatch, tmp_path):
    # With an injected (fake) transport, run_gate_b_query must set BOTH flags and
    # SKIP the live preflight (offline-safe). Capture the env at run_one_query time.
    # I-cap-005: the slate calls set_max_cost_per_run() which mutates the openrouter_client global;
    # register it with monkeypatch so it is RESTORED after this test (no leak into budget-cap tests).
    monkeypatch.setattr(orc, "PG_MAX_COST_PER_RUN", orc.PG_MAX_COST_PER_RUN)
    _clear_flags()
    captured = {}

    async def fake_run_one_query(q, out_root, **kwargs):
        captured["PG_FOUR_ROLE_MODE"] = os.environ.get("PG_FOUR_ROLE_MODE")
        captured["PG_ENABLE_QUANTIFIED_ANALYSIS"] = os.environ.get("PG_ENABLE_QUANTIFIED_ANALYSIS")
        # I-cap-002 feature 2/4 (#1060): advisory depth annotation must be ON for the benchmark.
        captured["PG_DEPTH_ANNOTATION_IN_BENCHMARK"] = os.environ.get(
            "PG_DEPTH_ANNOTATION_IN_BENCHMARK"
        )
        # I-cap-002 feature 3/4 (#1060): agentic URL-discovery must be ON for the benchmark.
        captured["PG_AGENTIC_SEARCH_IN_BENCHMARK"] = os.environ.get(
            "PG_AGENTIC_SEARCH_IN_BENCHMARK"
        )
        # I-cap-002 feature 4/4 (#1060): NLI entailment annotation must be ON for the benchmark.
        captured["PG_NLI_IN_BENCHMARK"] = os.environ.get("PG_NLI_IN_BENCHMARK")
        # I-cap-005 (#1068) KEYSTONE: STORM + tracker + deepener + the REAL retrieval caps must be set
        # by run_gate_b_query (the prior ~40-URL throttle was a missing/wrong-named slate).
        captured["PG_STORM_ENABLED_IN_BENCHMARK"] = os.environ.get("PG_STORM_ENABLED_IN_BENCHMARK")
        captured["PG_ENABLE_TOOL_TRACKER"] = os.environ.get("PG_ENABLE_TOOL_TRACKER")
        captured["PG_SWEEP_EVIDENCE_DEEPENER"] = os.environ.get("PG_SWEEP_EVIDENCE_DEEPENER")
        captured["PG_SWEEP_FETCH_CAP"] = os.environ.get("PG_SWEEP_FETCH_CAP")
        captured["PG_SWEEP_MAX_SERPER"] = os.environ.get("PG_SWEEP_MAX_SERPER")
        captured["PG_SWEEP_MAX_S2"] = os.environ.get("PG_SWEEP_MAX_S2")
        captured["transport"] = kwargs.get("four_role_transport")
        return {"status": "ok"}

    import scripts.run_honest_sweep_r3 as sweep
    monkeypatch.setattr(sweep, "run_one_query", fake_run_one_query)

    sentinel_transport = object()  # stand-in fake transport (preflight must be skipped)
    # I-deepfix-001 (#1344): now that the winners-only preflight PASSES (the killed losers are correctly
    # off), run_gate_b_query advances into the B20 run-wall-clock wrapper, which does out_root/domain/slug
    # + mkdir BEFORE calling run_one_query — so out_root must be a real Path (the prior str "." pre-dated
    # that wrapper and only worked because the run aborted at the gate). Use tmp_path so the mkdir is a
    # throwaway, never the repo.
    out = asyncio.run(
        g.run_gate_b_query({"question": "q", "slug": "s", "domain": "d"},
                           out_root=tmp_path, transport=sentinel_transport)
    )
    assert out == {"status": "ok"}
    assert captured["PG_FOUR_ROLE_MODE"] == "1"
    assert captured["PG_ENABLE_QUANTIFIED_ANALYSIS"] == "1"   # calculator ON for benchmark
    assert captured["PG_DEPTH_ANNOTATION_IN_BENCHMARK"] == "1"  # advisory depth ON for benchmark
    # I-deepfix-001 (#1344) WINNERS-ONLY PURITY: agentic URL-discovery is STORM's twin LOSER — KILLED.
    # run_gate_b_query force-sets it OFF (was "1"); the slate force-EXACTs it "0"; the NO-LOSER gate fails
    # closed if re-armed (STALE-ASSERTION updated to the winners-only reality).
    assert captured["PG_AGENTIC_SEARCH_IN_BENCHMARK"] == "0"    # agentic URL-discovery KILLED loser (force-off)
    assert captured["PG_NLI_IN_BENCHMARK"] == "1"              # NLI entailment annotation ON for benchmark
    # I-cap-005 (#1068) KEYSTONE assertions: full-capability slate applied + preflight passed.
    # I-deepfix-001 (#1344) PURITY: STORM core is a KILLED loser — the slate force-EXACTs it to "0" and
    # the NO-LOSER preflight gate fails closed if it is re-armed.
    assert captured["PG_STORM_ENABLED_IN_BENCHMARK"] == "0"    # STORM KILLED loser (slate force-exact "0")
    assert captured["PG_ENABLE_TOOL_TRACKER"] == "1"           # tracker ON so feature firing is provable
    # R1_deepener_enable (operator-authorized reversal, AskUserQuestion 2026-07-04): the citation-snowball
    # deepener is NO LONGER a killed loser — it is the recall lever, setdefault-ON (widen-only, LAW VI
    # operator-override-wins). run_gate_b_query -> apply_full_capability_benchmark_slate setdefaults it to
    # "1" here (the STORM/F2 unlock is deepener-scoped; every other loser stays killed). Every URL the
    # deepener discovers still re-passes the UNCHANGED fetch->tier->strict_verify chokepoint.
    assert captured["PG_SWEEP_EVIDENCE_DEEPENER"] == "1"       # recall lever, setdefault-ON (was force-exact "0")
    assert int(captured["PG_SWEEP_FETCH_CAP"]) >= 500          # the REAL fetch knob, above the floor
    assert int(captured["PG_SWEEP_MAX_SERPER"]) >= 50          # not the dead PG_LIVE_* name
    assert int(captured["PG_SWEEP_MAX_S2"]) >= 50
    assert captured["transport"] is sentinel_transport        # injected fake used, no preflight
    _clear_flags()


def test_run_gate_b_import_order_raises_module_constants():
    # I-cap-005 Codex iter-2 P1-2 regression (no network): in a FRESH subprocess, simulate main()'s order
    # — set conservative .env-like values, import run_gate_b, apply the slate, THEN import the
    # import-time-constant modules — and assert the constants were RAISED to full capability. This proves
    # the slate-before-load_locked_questions ordering is correct; a reorder would make this fail.
    import subprocess
    import sys

    script = (
        "import os\n"
        "for k in list(os.environ):\n"
        "    if k.startswith('PG_'): del os.environ[k]\n"
        "os.environ['PG_MOST_MAX_EVIDENCE']='300'\n"          # .env-like low (below slate 800)
        "os.environ['PG_AGENTIC_WEB_PER_ROUND']='6'\n"        # .env-like low (below slate 10)
        "from scripts.dr_benchmark.run_gate_b import (apply_full_capability_benchmark_slate as a,"
        " preflight_import_time_constants as p)\n"
        "a()\n"                                                # slate BEFORE the import-time-const modules
        "import importlib\n"
        "lr=importlib.import_module('src.polaris_graph.retrieval.live_retriever')\n"
        "st=importlib.import_module('src.polaris_graph.state')\n"
        "assert lr.DEFAULT_CONTENT_MAX_CHARS>=50000, lr.DEFAULT_CONTENT_MAX_CHARS\n"
        "assert lr.DEFAULT_HTTP_TIMEOUT>=30, lr.DEFAULT_HTTP_TIMEOUT\n"
        "assert st.PG_AGENTIC_WEB_PER_ROUND>=10, st.PG_AGENTIC_WEB_PER_ROUND\n"
        "p()\n"                                                # full assertion passes
        "print('IMPORT_ORDER_OK')\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert "IMPORT_ORDER_OK" in proc.stdout, f"stdout={proc.stdout!r} stderr={proc.stderr[-800:]!r}"


def test_preflight_full_capability_fails_closed_on_silent_throttle(monkeypatch):
    # I-cap-005 (#1068): a deliberate throttle below the full-capability floor MUST be caught (the
    # operator no-downgrade directive) — preflight_full_capability raises rather than letting a
    # ~40-URL run reach a paid endpoint silently.
    # I-cap-005: register the cost-cap global for restoration (the slate's set_max_cost_per_run mutates
    # it) so this test does not leak the cap into later budget tests in the same process.
    monkeypatch.setattr(orc, "PG_MAX_COST_PER_RUN", orc.PG_MAX_COST_PER_RUN)
    # I-deepfix-001 (#1344): apply_full_capability_benchmark_slate + the entry-scoped flag-forces mutate
    # os.environ DIRECTLY (and rebind _sweep_integration._CLAIM_WORKERS). Snapshot + restore the whole env
    # so the winners-only baseline (mineru25, the claim-workers value, etc.) cannot leak into sibling
    # dr_benchmark tests in the same process.
    env_snapshot = dict(os.environ)
    try:
        g.apply_full_capability_benchmark_slate()
        # Mirror the entry-scoped flag-forces run_gate_b_query applies before preflight. I-deepfix-001
        # PURITY: PG_AGENTIC_SEARCH_IN_BENCHMARK is NO LONGER set ON — it is a KILLED loser; re-arming it
        # would trip the NO-LOSER gate FIRST and the test would no longer isolate the throttle floor
        # (STALE-BASELINE). The slate already force-EXACTs it "0".
        for f in ("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "PG_NLI_IN_BENCHMARK",
                  # I-ready-016b (#1097): the 3 readiness faithfulness flags are now preflight-required.
                  "PG_USE_SAFETY_REFUSAL", "PG_SWEEP_NLI_CONFLICT", "PG_SWEEP_TABLE_CELL_VERIFY"):
            monkeypatch.setenv(f, "1")
        # offline=True: no-GPU / no-spend unit test — skip ONLY the WINNER-FIRES GPU host-capability probes
        # (W4/W5). The capacity-FLOOR checks (what this test protects) are gated by smoke_scale, NOT offline,
        # so they stay active and the throttle below still fires for the right reason.
        g.preflight_full_capability(offline=True)             # clean winners-only slate -> passes
        monkeypatch.setenv("PG_SWEEP_FETCH_CAP", "40")        # the exact prior-bug throttle value
        with pytest.raises(RuntimeError, match="(?i)throttl|floor"):
            g.preflight_full_capability(offline=True)
    finally:
        # I-deepfix-001 (#1344) Codex P1: undo monkeypatch FIRST — it recorded POST-slate env values, and
        # pytest's monkeypatch teardown runs AFTER this finally; without undo() it would re-inject those
        # slate values into the process, defeating the snapshot restore. The snapshot restore then handles
        # the slate's DIRECT os.environ mutations (which monkeypatch never tracked). Both are required.
        monkeypatch.undo()
        os.environ.clear()
        os.environ.update(env_snapshot)


def test_double_judge_guard_condition():
    # The guard that skips the legacy judge: seam runs iff PG_FOUR_ROLE_MODE on AND
    # a transport is injected. Mirror the exact predicate used in the sweep.
    def seam_will_run(flag: str | None, transport) -> bool:
        return (str(flag or "0").strip() in ("1", "true", "True")) and transport is not None

    assert seam_will_run("1", object()) is True              # both -> skip legacy judge
    # I-run11-009 (#1055): no transport -> seam stays inert. The run NO LONGER silently falls back
    # to the legacy judge; it FAILS CLOSED (release HELD). The seam itself still does not run here.
    assert seam_will_run("1", None) is False                 # no transport -> seam inert (fail closed)
    assert seam_will_run("0", object()) is False             # flag off -> legacy runs (PG_FOUR_ROLE_MODE unset)
    assert seam_will_run(None, object()) is False
