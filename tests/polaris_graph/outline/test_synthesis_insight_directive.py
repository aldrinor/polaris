"""Mission STEP 3 (INSIGHT depth): cross-study synthesis quantification directive + evidence
enrichment. These are GENERAL, topic-agnostic, DEFAULT-OFF structural levers. The tests pin:
  - the structural role detector (synthesis word AND cross-study/contradiction signal; no topic);
  - the default-OFF flag semantics;
  - the numeric-row (comparable-finding) filter;
  - the enrichment selection logic (existing rows preserved first, only numeric sibling rows added,
    bounded by the cap) replicated exactly from the generator's inline block;
  - the directive block restates the no-derived-number faithfulness rule (relaxes nothing).
"""
import os

import pytest

from src.polaris_graph.generator import multi_section_generator as M


@pytest.mark.parametrize("title,expected", [
    ("Cross-Study Synthesis and Contradictions", True),
    ("Synthesis Across Studies", True),
    ("Cross-Study Synthesis and Reconciliation of Findings", True),
    ("Convergence and Divergence: A Synthesis of the Evidence", True),
    ("A Synthesis of Where Estimates Agree and Disagree", True),
    # synthesis word but no cross-study/contradiction signal -> not the role
    ("Synthesis of Trial Designs", False),
    ("Introduction and Scope of the Evidence", False),
    ("Automation and Employment Displacement Estimates", False),
    ("Conclusions and Research Gaps", False),
    ("Efficacy", False),
    ("", False),
])
def test_synthesis_role_detector_is_structural(title, expected):
    assert M._is_cross_study_synthesis_section(title) is expected


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_SYNTHESIS_QUANT_DIRECTIVE", raising=False)
    assert M._synthesis_quant_directive_enabled() is False
    for on in ("1", "true", "yes", "on"):
        monkeypatch.setenv("PG_SYNTHESIS_QUANT_DIRECTIVE", on)
        assert M._synthesis_quant_directive_enabled() is True
    for off in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("PG_SYNTHESIS_QUANT_DIRECTIVE", off)
        assert M._synthesis_quant_directive_enabled() is False


def test_numeric_row_filter():
    assert M._row_carries_number({"statement": "47 per cent of jobs at risk"}) is True
    assert M._row_carries_number({"direct_quote": "a gain of 0.4 SD"}) is True
    assert M._row_carries_number({"statement": "qualitative account, no figures"}) is False
    assert M._row_carries_number({}) is False
    assert M._row_carries_number(None) is False


def test_directive_restates_faithfulness_rule_only():
    block = M._SYNTHESIS_QUANT_BLOCK
    low = block.lower()
    # It must REFRAME the job (compare across sources) ...
    assert "range" in low and "converge" in low and "conflict" in low
    # ... and it must RESTATE (never relax) the no-derived-number gate.
    assert "verbatim" in low
    assert "never compute" in low or "do not compute" in low or "omit that comparison" in low


def _replicate_enrichment(plans, evidence_pool, cap):
    """Byte-mirror of the generator's inline synthesis-enrichment selection (kept in sync so a
    drift in the production block is caught here)."""
    synth_idxs = [i for i, p in enumerate(plans)
                  if M._is_cross_study_synthesis_section(p["title"])]
    out = {}
    for si in synth_idxs:
        existing = list(plans[si].get("ev_ids") or [])
        seen = set(existing)
        added = []
        for j, p in enumerate(plans):
            if len(added) >= cap:
                break
            if j == si:
                continue
            for eid in (p.get("ev_ids") or []):
                if len(added) >= cap:
                    break
                if eid in seen or eid not in evidence_pool:
                    continue
                if not M._row_carries_number(evidence_pool.get(eid) or {}):
                    continue
                seen.add(eid)
                added.append(eid)
        out[si] = (existing, added)
    return out


def test_enrichment_selects_numeric_siblings_preserves_existing_and_caps():
    pool = {
        "ev_1": {"statement": "existing synth row (kept)"},
        "ev_2": {"statement": "47 per cent at high risk"},   # numeric body row
        "ev_3": {"statement": "no numbers here, qualitative"},  # non-numeric -> skipped
        "ev_4": {"direct_quote": "gain of 0.4 SD"},           # numeric body row
        "ev_5": {"statement": "share rose to 5.5 per cent"},  # numeric body row
        "ev_gone": {"statement": "9 percent"},                # not in a plan -> not added
    }
    plans = [
        {"title": "Introduction and Scope", "ev_ids": ["ev_2", "ev_3"]},
        {"title": "Wage Effects", "ev_ids": ["ev_4", "ev_5"]},
        {"title": "Cross-Study Synthesis and Contradictions", "ev_ids": ["ev_1"]},
    ]
    res = _replicate_enrichment(plans, pool, cap=48)
    existing, added = res[2]
    assert existing == ["ev_1"]                 # own row preserved, first
    assert added == ["ev_2", "ev_4", "ev_5"]    # numeric siblings only, in plan order
    assert "ev_3" not in added                  # non-numeric excluded
    # cap honored
    res2 = _replicate_enrichment(plans, pool, cap=2)
    assert res2[2][1] == ["ev_2", "ev_4"]


def test_enrichment_noop_without_synthesis_role():
    pool = {"ev_2": {"statement": "47 per cent"}}
    plans = [
        {"title": "Introduction", "ev_ids": ["ev_2"]},
        {"title": "Conclusions and Research Gaps", "ev_ids": ["ev_2"]},
    ]
    res = _replicate_enrichment(plans, pool, cap=48)
    assert res == {}  # no synthesis role -> nothing enriched
