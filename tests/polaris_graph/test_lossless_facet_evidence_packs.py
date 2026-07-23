"""STEP 6: complete per-facet packs, basket co-location, and residual fold-in."""

from types import SimpleNamespace

import src.polaris_graph.generator.multi_section_generator as generator
from src.polaris_graph.generator.facet_evidence_packs import (
    build_basket_memberships,
    build_lossless_facet_packs,
)


def _plan(title, focus, ids):
    return SimpleNamespace(title=title, focus=focus, ev_ids=list(ids))


def _member(evidence_id):
    return SimpleNamespace(evidence_id=evidence_id)


def test_all_pool_rows_survive_and_whole_basket_has_one_facet_home():
    plans = [
        _plan("Orbital effects", "orbital calibration", ["e1"]),
        _plan("Thermal effects", "thermal transfer", []),
        _plan("Residual", "uncategorized", ["e3"]),
    ]
    pool = {
        "e1": {"evidence_id": "e1", "statement": "Orbital calibration rose."},
        "e2": {"evidence_id": "e2", "statement": "Orbital calibration agreed."},
        "e3": {"evidence_id": "e3", "statement": "Thermal transfer changed."},
        "e4": {"evidence_id": "e4", "statement": "A boundary condition remained."},
    }
    basket = SimpleNamespace(
        claim_cluster_id="claim_orbit",
        claim_text="orbital calibration",
        subject="orbital calibration",
        predicate="agreement",
        supporting_members=[_member("e1"), _member("e2")],
    )
    result, ledger, membership = build_lossless_facet_packs(
        plans,
        pool,
        credibility_analysis=SimpleNamespace(baskets=[basket]),
        auxiliary_plan=lambda plan: plan.title == "Residual",
        ordered_evidence_ids=["e2", "e1", "e3", "e4"],
    )
    assert [plan.title for plan in result] == ["Orbital effects", "Thermal effects"]
    assert ledger["missing_evidence_ids"] == []
    assert ledger["covered_evidence_ids"] == ["e2", "e1", "e3", "e4"]
    assert set(ledger["input_evidence_ids"]) == set(pool)
    orbital = next(plan for plan in result if plan.title == "Orbital effects")
    assert {"e1", "e2"}.issubset(set(orbital.ev_ids))
    assert membership["e1"] == membership["e2"] == ["claim_orbit"]


def test_residual_container_removed_only_after_every_id_is_folded():
    body = _plan("Facet", "surface response", [])
    residual = _plan("Residual", "uncategorized", ["e1", "e2"])
    pool = {
        "e1": {"evidence_id": "e1", "statement": "Surface response one."},
        "e2": {"evidence_id": "e2", "statement": "Surface response two."},
    }
    result, ledger, _ = build_lossless_facet_packs(
        [body, residual], pool, auxiliary_plan=lambda plan: plan.title == "Residual",
    )
    assert result == [body]
    assert body.ev_ids == ["e1", "e2"]
    moved = ledger["auxiliary_sections_folded"][0]["moved"]
    assert {entry["evidence_id"] for entry in moved} == {"e1", "e2"}
    assert ledger["missing_evidence_ids"] == []


def test_writer_pack_has_no_top_n_or_length_target(monkeypatch):
    monkeypatch.setenv("PG_BASKET_SYNTHESIS", "1")
    rows = [
        {
            "evidence_id": f"e{index}",
            "statement": f"Finding {index}.",
            "direct_quote": f"Finding {index}.",
            "evidence_basket_ids": ["shared"],
        }
        for index in range(7)
    ]
    packed = generator._build_writer_evidence_blocks(rows)
    assert packed.count("<<<evidence:") == len(rows)
    assert packed.count("basket_ids: shared") == len(rows)
    directive = generator._BASKET_SYNTHESIS_DIRECTIVE.lower()
    assert "complete ordered stream" in directive
    assert "do not write to a sentence or word target" in directive
    assert "top-n" not in directive


def test_basket_prompt_removes_legacy_one_paragraph_constraint(monkeypatch):
    monkeypatch.setenv("PG_BASKET_SYNTHESIS", "1")
    monkeypatch.setenv("PG_SECTION_STRUCTURE", "0")
    prompt = generator._select_section_system_prompt(True, anti_verbosity=False)
    assert "Just the paragraph body." not in prompt
    assert generator._BASKET_BODY_RULE_7 in prompt
    assert "do not write to a paragraph, sentence, or word target" in prompt


def test_prompt_only_membership_supports_mapping_baskets():
    credibility = {
        "baskets": [{
            "claim_cluster_id": "claim-1",
            "supporting_members": [
                {"evidence_id": "ev_a"}, {"evidence_id": "ev_b"},
            ],
        }],
    }
    assert build_basket_memberships(
        credibility, {"ev_a": {}, "ev_b": {}, "ev_c": {}},
    ) == {"ev_a": ["claim-1"], "ev_b": ["claim-1"]}
