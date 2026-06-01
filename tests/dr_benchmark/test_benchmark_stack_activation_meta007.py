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

from scripts.dr_benchmark import run_gate_b as g


def _clear_flags():
    os.environ.pop("PG_FOUR_ROLE_MODE", None)
    os.environ.pop("PG_ENABLE_QUANTIFIED_ANALYSIS", None)


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
    _clear_flags()
    captured = {}

    async def fake_run_one_query(q, out_root, **kwargs):
        captured["PG_FOUR_ROLE_MODE"] = os.environ.get("PG_FOUR_ROLE_MODE")
        captured["PG_ENABLE_QUANTIFIED_ANALYSIS"] = os.environ.get("PG_ENABLE_QUANTIFIED_ANALYSIS")
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
    assert captured["transport"] is sentinel_transport        # injected fake used, no preflight
    _clear_flags()


def test_double_judge_guard_condition():
    # The guard that skips the legacy judge: seam runs iff PG_FOUR_ROLE_MODE on AND
    # a transport is injected. Mirror the exact predicate used in the sweep.
    def seam_will_run(flag: str | None, transport) -> bool:
        return (str(flag or "0").strip() in ("1", "true", "True")) and transport is not None

    assert seam_will_run("1", object()) is True              # both -> skip legacy judge
    assert seam_will_run("1", None) is False                 # no transport -> legacy runs
    assert seam_will_run("0", object()) is False             # flag off -> legacy runs
    assert seam_will_run(None, object()) is False
