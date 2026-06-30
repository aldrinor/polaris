"""Unit tests for the diced preflight's D5 credibility-tiering dice (I-deepfix-001 #1344, wave-3).

Focus: the FIX 2 gate-READ path. The D5 wiring serializes the batch tiering status NESTED as
``corpus_credibility_disclosure.tiering_status.tiering_mode`` (weighted_corpus_gate.disclosure_to_dict
-> asdict of CorpusCredibilityDisclosure.tiering_status). The dice previously read the TOP-level
``ccd.get("tiering_mode")``, which is ALWAYS None under the real serialization, so the STRONG
invariant (mode != rules_floor_degraded) never fired even on a fresh ON run -- a banked-replay-blind
false-PASS. These tests build SYNTHETIC manifests in a temp fixture dir and prove the NESTED read
fires across all three real serialization shapes (dict / None / absent).

Tiny SYNTHETIC manifest fixtures in -> DiceResult verdicts out. No run, no model, no network, no
spend. The module is loaded by file path; D6's heavy report_redactor is imported lazily INSIDE that
dice only, so importing the module here stays read-only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_DICED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_diced_preflight.py"


def _load_diced():
    spec = importlib.util.spec_from_file_location("pipeline_diced_preflight_under_test", str(_DICED_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: @dataclass resolves sys.modules[cls.__module__].__dict__, which is
    # None for an unregistered synthetic module (Py3.12+ dataclasses fail-loud otherwise).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


diced = _load_diced()


def _ctx(tmp_path: Path, manifest: dict):
    """Build a Ctx over a temp fixture dir whose manifest.json carries the synthetic disclosure."""
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    fx = diced.FixtureResolver([tmp_path])
    return diced.Ctx(fx=fx, th=diced.Thresholds())


def _disclosure(tiering_status, *, total=3, counts=None):
    """A credibility disclosure that passes status_present + count_ok (so the tiering_mode branch is
    the ONLY thing under test). ``tiering_status`` is spliced in exactly as the caller passes it
    (a dict / None / omitted-via-sentinel)."""
    counts = counts if counts is not None else {"T1": 2, "T2": 1}
    ccd = {
        "gate": "PG_SWEEP_WEIGHTED_CORPUS_GATE",
        "disclosure_note": "credibility disclosed (weighted, domain-aware)",
        "tier_counts": dict(counts),
        "total_sources": total,
    }
    if tiering_status is not _OMIT:
        ccd["tiering_status"] = tiering_status
    return {"corpus": {"count": total}, "corpus_credibility_disclosure": ccd}


_OMIT = object()


# --------------------------------------------------------------------------------------------
# FIX 2 -- the NESTED tiering_status.tiering_mode read (the load-bearing proof).
# --------------------------------------------------------------------------------------------

def test_d5_nested_honest_tiering_mode_green(tmp_path):
    # Fresh ON run: nested tiering_status.tiering_mode is an HONEST mode -> STRONG branch fires GREEN.
    manifest = _disclosure({"tiering_mode": "llm_tiered", "total": 3, "llm_success_count": 3})
    r = diced.dice_d5_credibility_honest_tiering(_ctx(tmp_path, manifest))
    assert r.status == diced.GREEN, r.detail
    assert "tiering_mode='llm_tiered'" in r.detail  # the STRONG branch (read the real nested value)


def test_d5_nested_degraded_tiering_mode_red(tmp_path):
    # The load-bearing assertion: a DEGRADED nested mode must flip RED. If the dice still read the
    # TOP-level ccd.get("tiering_mode") (always None), this nested degraded value would be invisible
    # and the dice would wrongly take the weak branch -> GREEN. Proving RED proves the nested read.
    manifest = _disclosure({"tiering_mode": "rules_floor_degraded", "total": 3, "rules_floor_count": 3})
    r = diced.dice_d5_credibility_honest_tiering(_ctx(tmp_path, manifest))
    assert r.status == diced.RED, r.detail
    assert "rules_floor_degraded" in r.detail


def test_d5_top_level_tiering_mode_is_ignored_green(tmp_path):
    # Defends the fix direction: a DEGRADED mode placed at the OLD TOP-level (not nested) must NOT be
    # read -- the dice falls through to the weak classified-count branch -> GREEN. (If the dice still
    # read top-level, this would wrongly go RED.)
    manifest = _disclosure(_OMIT)
    manifest["corpus_credibility_disclosure"]["tiering_mode"] = "rules_floor_degraded"  # legacy top-level
    r = diced.dice_d5_credibility_honest_tiering(_ctx(tmp_path, manifest))
    assert r.status == diced.GREEN, r.detail
    assert "WEAKER invariant" in r.detail


def test_d5_tiering_status_none_off_path_weak_green(tmp_path):
    # OFF path / replay: tiering_status serializes as None -> defensive `or {}` -> weak branch GREEN,
    # no AttributeError on None.
    manifest = _disclosure(None)
    r = diced.dice_d5_credibility_honest_tiering(_ctx(tmp_path, manifest))
    assert r.status == diced.GREEN, r.detail
    assert "WEAKER invariant" in r.detail


def test_d5_tiering_status_absent_banked_weak_green(tmp_path):
    # Banked fixture: the tiering_status key is ABSENT entirely -> weak branch GREEN (no regression on
    # the banked replay; the nested read is invisible here -- that is WHY a live/synthetic run is the
    # only honest proof of the strong branch, exercised by the cases above).
    manifest = _disclosure(_OMIT)
    r = diced.dice_d5_credibility_honest_tiering(_ctx(tmp_path, manifest))
    assert r.status == diced.GREEN, r.detail
    assert "WEAKER invariant" in r.detail


def test_d5_nested_degraded_still_red_even_if_counts_ok(tmp_path):
    # A degraded mode is RED regardless of the count invariant being satisfied (the mode is the gate).
    manifest = _disclosure({"tiering_mode": "rules_floor_degraded"}, total=5, counts={"T1": 3, "T3": 2})
    r = diced.dice_d5_credibility_honest_tiering(_ctx(tmp_path, manifest))
    assert r.status == diced.RED, r.detail
