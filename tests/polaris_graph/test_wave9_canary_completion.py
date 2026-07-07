"""I-deepfix-001 Wave-9 (#1344) — ANTI-DARK canary completion for the wave-1/2 FORCE-ON flags.

Four Gate-B quad-pinned FORCE-ON flags previously carried NO ``_ActivationMarkerSpec``, so a DARK one
could not crash the paid run. Wave-9 emits a realized-effect ``[activation]`` marker at each flag's
GUARANTEED-reached ON-path (credibility tiering / section composition / retrieval post-fetch) and
REGISTERS a fail-loud spec in the sibling ``_ACTIVATION_MARKER_SPECS_WAVE3`` registry:

  * PG_WORKFORCE_T3_TARGETING          -> ``workforce_t3_targeting: promoted=N checked=M``
  * PG_DEBATE_CON_BASKET_CONSOLIDATION -> ``debate_con_basket_consolidation: consolidated=N``
  * PG_POST_FETCH_ENRICH_PARALLEL      -> ``post_fetch_enrich_parallel: batched=N enriched=M``
  * PG_WALL_CLASSIFY_RESCUE            -> ``wall_classify_rescue: armed enrich_parallel=<bool>`` (pre-existing)

Every assertion is OFFLINE (no model / GPU / network / spend): the canary is pure string logic over a
synthetic run-log. STRUCTURAL presence / degrade-absence only, NEVER a >0 count threshold (§-1.3): a
realized ran-ok-zero (promoted=0 / consolidated=0 / batched=0) is HONEST and PASSES. The three
render/compose/contract-seam flags (PG_A1_BASKET_FALLBACK / PG_RENDER_CHROME_SCREEN /
PG_DEPTH_DECHROME_MEMBERS) are DEFERRED (their ON-path is conditional on a report shape — a run-level
force-ON spec would false-FAIL a legitimate released run that skips the seam), so they are intentionally
absent here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.environ.setdefault("PG_VERIFICATION_MODE", "off")

import scripts.dr_benchmark.run_gate_b as rg  # noqa: E402

_CANARY = "PG_ACTIVATION_CANARY"
# A realistic run-log prefix (level/logger/timestamp) — the canary regexes use .search/.finditer so they
# must match the marker MID-line, not only at column 0.
_PREFIX = "2026-07-07 12:00:00,123 INFO src.polaris_graph - "

# name -> (env_flag, on_token, realized_marker, realized_zero_marker, degrade_marker | None)
_WAVE9 = {
    "workforce_t3_targeting": (
        "PG_WORKFORCE_T3_TARGETING", "1",
        "[activation] workforce_t3_targeting: promoted=3 checked=42",
        "[activation] workforce_t3_targeting: promoted=0 checked=0",
        None,
    ),
    "debate_con_basket_consolidation": (
        "PG_DEBATE_CON_BASKET_CONSOLIDATION", "1",
        "[activation] debate_con_basket_consolidation: consolidated=2",
        "[activation] debate_con_basket_consolidation: consolidated=0",
        "[activation] debate_con_basket_consolidation: unavailable_failopen",
    ),
    "post_fetch_enrich_parallel": (
        "PG_POST_FETCH_ENRICH_PARALLEL", "1",
        "[activation] post_fetch_enrich_parallel: batched=35 enriched=12",
        "[activation] post_fetch_enrich_parallel: batched=0 enriched=0",
        None,
    ),
    "wall_classify_rescue": (
        "PG_WALL_CLASSIFY_RESCUE", "1",
        "[activation] wall_classify_rescue: armed enrich_parallel=True",
        "[activation] wall_classify_rescue: armed enrich_parallel=False",
        None,
    ),
}

# Every spec flag the canary self-scopes on (main + WAVE3) — used to delenv the whole slate so a single
# spec can be isolated under test.
_ALL_SPEC_FLAGS = tuple(
    s.env_flag for s in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3)
)


def _by_name():
    return {s.name: s for s in rg._ACTIVATION_MARKER_SPECS_WAVE3}


def _isolate(monkeypatch, on_flag, on_token="1"):
    """Enable the canary and scope it to a SINGLE spec: delenv every spec flag, force the default-ON
    ``summary_table`` sibling explicitly OFF (delenv would leave its default-on path ON), then set
    ``on_flag`` ON. So ONLY ``on_flag``'s marker is demanded by the canary."""
    monkeypatch.setenv(_CANARY, "1")
    for f in _ALL_SPEC_FLAGS:
        monkeypatch.delenv(f, raising=False)
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")  # default-ON sibling: explicit OFF
    monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "0")  # default-ON sibling (Wave-9 P1): explicit OFF
    monkeypatch.setenv(on_flag, on_token)


def _line(marker: str) -> str:
    return _PREFIX + marker + "\n"


# ── (a) each spec registered in the WAVE3 sibling registry with the right env_flag ────────────────

@pytest.mark.parametrize("name", list(_WAVE9))
def test_spec_registered_with_env_flag(name):
    env_flag = _WAVE9[name][0]
    by_name = _by_name()
    assert name in by_name, f"{name} spec missing from _ACTIVATION_MARKER_SPECS_WAVE3"
    assert by_name[name].env_flag == env_flag, f"{name} spec env_flag != {env_flag}"


# ── (b) positive_re matches the REALIZED marker and does NOT match empty ──────────────────────────

@pytest.mark.parametrize("name", list(_WAVE9))
def test_positive_re_matches_realized_not_empty(name):
    spec = _by_name()[name]
    _, _, realized, realized_zero, _ = _WAVE9[name]
    assert spec.positive_re is not None
    assert spec.positive_re.search(_PREFIX + realized) is not None, f"{name} positive_re misses realized marker"
    assert spec.positive_re.search(_PREFIX + realized_zero) is not None, f"{name} positive_re misses ran-ok-zero"
    assert spec.positive_re.search("") is None, f"{name} positive_re false-matches empty text"
    # A bare prefix with no numeric field must NOT satisfy the positive_re (guards against a stub marker).
    stub = f"[activation] {name}:"
    assert spec.positive_re.search(_PREFIX + stub) is None, f"{name} positive_re matches a field-less stub"


# ── (c) flag ON + marker present => canary PASSES (incl. the ran-ok-zero realized count) ──────────

@pytest.mark.parametrize("name", list(_WAVE9))
def test_flag_on_marker_present_passes(monkeypatch, name):
    env_flag, on_token, realized, realized_zero, _ = _WAVE9[name]
    _isolate(monkeypatch, env_flag, on_token)
    rg.assert_activation_markers_fired(_line(realized))       # no raise
    rg.assert_activation_markers_fired(_line(realized_zero))  # §-1.3: realized zero PASSES (never a >0 gate)


# ── (d) flag ON + marker ABSENT => canary FAILS (the anti-dark leg) ───────────────────────────────

@pytest.mark.parametrize("name", list(_WAVE9))
def test_flag_on_marker_absent_fails(monkeypatch, name):
    env_flag, on_token, _, _, _ = _WAVE9[name]
    _isolate(monkeypatch, env_flag, on_token)
    with pytest.raises(RuntimeError, match=f"{name.upper()} MARKER ABSENT"):
        rg.assert_activation_markers_fired(_line("[activation] some_unrelated_marker: x=1"))


# ── (e) flag OFF/unset => canary self-scopes OFF (demands no marker) ──────────────────────────────

@pytest.mark.parametrize("name", list(_WAVE9))
def test_flag_off_selfskips_no_demand(monkeypatch, name):
    """OFF (explicit '0') emits no marker and the canary demands none — a log with NO marker passes."""
    env_flag = _WAVE9[name][0]
    _isolate(monkeypatch, env_flag, "0")  # target flag explicitly OFF
    rg.assert_activation_markers_fired("")  # whole slate OFF => no demand => no raise


# The DEFAULT-OFF (whitelist) producers self-skip when unset; debate is DEFAULT-ON and is the exception,
# tested separately (unset => DEMANDED) in test_debate_default_on_unset_demands below.
@pytest.mark.parametrize("name", [n for n in _WAVE9 if n != "debate_con_basket_consolidation"])
def test_flag_unset_selfskips_no_demand(monkeypatch, name):
    env_flag = _WAVE9[name][0]
    _isolate(monkeypatch, env_flag, "0")
    monkeypatch.delenv(env_flag, raising=False)  # UNSET (not even '0')
    rg.assert_activation_markers_fired("")  # no raise


# ── (f) the fail-open degrade marker (debate) is REJECTED while its flag is ON ────────────────────

def test_debate_unavailable_failopen_rejected(monkeypatch):
    env_flag, on_token, realized, _, degrade = _WAVE9["debate_con_basket_consolidation"]
    assert degrade is not None
    _isolate(monkeypatch, env_flag, on_token)
    # The positive marker is present too, but the fail-open degrade also fired => REJECT (dark on error).
    text = _line(realized) + _line(degrade)
    with pytest.raises(RuntimeError, match="DEBATE_CON_BASKET_CONSOLIDATION OLD/DEGRADE MARKER PRESENT"):
        rg.assert_activation_markers_fired(text)


def test_debate_degrade_selfskips_when_flag_off(monkeypatch):
    """Self-scoping parity: with the debate flag OFF the degrade literal is not asserted."""
    env_flag, _, realized, _, degrade = _WAVE9["debate_con_basket_consolidation"]
    _isolate(monkeypatch, env_flag, "0")
    rg.assert_activation_markers_fired(_line(realized) + _line(degrade))  # no raise


# ── (g) predicate scoping matches each producer's OWN truthy vocabulary ───────────────────────────

def test_whitelist_producers_scope_on_their_tokens(monkeypatch):
    # workforce/post_fetch/wall producers accept 1/true/yes/on (whitelist). "yes" reads ON.
    for name in ("workforce_t3_targeting", "post_fetch_enrich_parallel", "wall_classify_rescue"):
        env_flag, _, _, _, _ = _WAVE9[name]
        _isolate(monkeypatch, env_flag, "yes")
        with pytest.raises(RuntimeError, match=f"{name.upper()} MARKER ABSENT"):
            rg.assert_activation_markers_fired("[activation] noise: x=1")


def test_debate_default_on_unset_demands(monkeypatch):
    """Codex Wave-9 P1: the producer debate_consolidation_enabled() is DEFAULT-ON, so the canary spec is
    flag_default_on=True — an UNSET flag reads ON at the canary (matching the producer), which is what makes
    a DARK default-on debate path CRASH the run instead of false-greening it. An explicit '0' still reads
    OFF. (Sibling canary tests that isolate other specs therefore force PG_DEBATE_CON_BASKET_CONSOLIDATION=0.)"""
    spec = _by_name()["debate_con_basket_consolidation"]
    assert spec.flag_whitelist is None, "debate spec is a blocklist (flag_whitelist=None) — but default-ON"
    assert spec.flag_default_on is True, "debate producer is DEFAULT-ON, so the canary must be too"
    assert rg._activation_flag_on("PG_DEBATE_CON_BASKET_CONSOLIDATION", None, True) is True   # unset => ON
    monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "0")
    assert rg._activation_flag_on("PG_DEBATE_CON_BASKET_CONSOLIDATION", None, True) is False  # explicit 0 => OFF
    monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "1")
    assert rg._activation_flag_on("PG_DEBATE_CON_BASKET_CONSOLIDATION", None, False) is True  # slate "1" => ON


# ── (h) the sibling 10-boolean sync-guard is UNPERTURBED (WAVE3 is a separate registry) ───────────

def test_main_spec_sync_guard_still_ten():
    # The Wave-9 specs live in the SIBLING _ACTIVATION_MARKER_SPECS_WAVE3, so the 1:1 main-registry guard
    # (len(_ACTIVATION_MARKER_SPECS) == 10 == len(_MODULE_FLAGS)) must remain 10.
    assert len(rg._ACTIVATION_MARKER_SPECS) == 10


def test_wave9_specs_added_to_wave3_registry():
    names = {s.name for s in rg._ACTIVATION_MARKER_SPECS_WAVE3}
    for name in _WAVE9:
        assert name in names, f"{name} not registered in _ACTIVATION_MARKER_SPECS_WAVE3"


# ── (i) producer/canary drift guard: the exact realized-marker format literals live in the producers ─

def test_producer_marker_literals_exist_in_source():
    def _src(rel):
        return (_REPO_ROOT / rel).read_text(encoding="utf-8")

    cred = _src("src/polaris_graph/retrieval/credibility_llm_tiering.py")
    assert "[activation] workforce_t3_targeting: promoted=%d checked=%d" in cred

    vc = _src("src/polaris_graph/generator/verified_compose.py")
    assert "[activation] debate_con_basket_consolidation: consolidated=%d" in vc
    assert "[activation] debate_con_basket_consolidation: unavailable_failopen" in vc

    lr = _src("src/polaris_graph/retrieval/live_retriever.py")
    assert "[activation] post_fetch_enrich_parallel: batched=%d enriched=%d" in lr
    # the pre-existing armed liveness marker the wall_classify_rescue spec registers.
    assert "[activation] wall_classify_rescue: armed enrich_parallel=" in lr


# ── (j) offline import smoke ──────────────────────────────────────────────────────────────────────

def test_smoke_symbols_present():
    assert hasattr(rg, "_ACTIVATION_MARKER_SPECS_WAVE3")
    assert hasattr(rg, "assert_activation_markers_fired")
    assert hasattr(rg, "_activation_flag_on")
