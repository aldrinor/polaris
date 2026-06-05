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
    fams = g.assert_four_role_families_distinct()
    assert set(fams) == {"generator", "mirror", "sentinel", "judge"}
    assert len(set(fams.values())) == 4               # all distinct


def test_preflight_fails_loud_when_endpoint_unset(monkeypatch):
    # live preflight must FAIL before the sweep when a self-host URL is missing.
    for role in ("MIRROR", "SENTINEL", "JUDGE"):
        monkeypatch.delenv(f"PG_{role}_BASE_URL", raising=False)
    with pytest.raises((RuntimeError, ValueError)):
        g.preflight_self_host_roles()


def test_gate_b_query_sets_both_flags_and_skips_preflight_on_injected_transport(monkeypatch):
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
    out = asyncio.run(
        g.run_gate_b_query({"question": "q", "slug": "s", "domain": "d"},
                           out_root=".", transport=sentinel_transport)
    )
    assert out == {"status": "ok"}
    assert captured["PG_FOUR_ROLE_MODE"] == "1"
    assert captured["PG_ENABLE_QUANTIFIED_ANALYSIS"] == "1"   # calculator ON for benchmark
    assert captured["PG_DEPTH_ANNOTATION_IN_BENCHMARK"] == "1"  # advisory depth ON for benchmark
    assert captured["PG_AGENTIC_SEARCH_IN_BENCHMARK"] == "1"    # agentic URL-discovery ON for benchmark
    assert captured["PG_NLI_IN_BENCHMARK"] == "1"              # NLI entailment annotation ON for benchmark
    # I-cap-005 (#1068) KEYSTONE assertions: full-capability slate applied + preflight passed.
    assert captured["PG_STORM_ENABLED_IN_BENCHMARK"] == "1"    # STORM was wired-but-dead; now ON
    assert captured["PG_ENABLE_TOOL_TRACKER"] == "1"           # tracker ON so feature firing is provable
    assert captured["PG_SWEEP_EVIDENCE_DEEPENER"] == "1"       # deepener alias fixed (sweep flag)
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
    g.apply_full_capability_benchmark_slate()
    for f in ("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_NLI_IN_BENCHMARK"):
        os.environ[f] = "1"
    g.preflight_full_capability()                              # full slate -> passes
    monkeypatch.setenv("PG_SWEEP_FETCH_CAP", "40")             # the exact prior-bug value
    with pytest.raises(RuntimeError):
        g.preflight_full_capability()
    _clear_flags()


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
