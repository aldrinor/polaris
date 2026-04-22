"""M-42c tests: mechanism-evidence selector floor + conditional
section prompt.

Codex plan pass-3 approved two coordinated changes:
1. Selector: reserve 2-4 T1+T2 slots for mechanism-flagged rows
   when the pool has >=4 mechanism rows.
2. Section prompt: CONDITIONAL mechanism-section target (20-35
   sentences if >=8 mech ev_ids; 15-20 if 4-7; 10-15 if <4 with
   disclosure).
"""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────
# Selector mechanism-evidence floor
# ─────────────────────────────────────────────────────────────────────


class TestM42cMechanismDetection:
    def test_mechanism_token_in_title_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "Pharmacokinetics of tirzepatide in T2D",
               "statement": "drug metabolism"}
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_mechanism_token_in_statement_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "SURPASS-2 trial results",
               "statement": "Tirzepatide binds GIP receptor with high affinity"}
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_mechanism_token_in_direct_quote_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "Efficacy study",
               "direct_quote": "Half-life of approximately 5 days supports once-weekly dosing"}
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_non_mechanism_row_not_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "SURPASS-2: tirzepatide vs semaglutide",
               "statement": "HbA1c reduction at week 40",
               "direct_quote": "Mean HbA1c reduction was 2.30 pp"}
        assert _m42c_row_is_mechanism_rich(row) is False

    def test_british_spelling_signalling_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "Incretin signalling pathways in glucose homeostasis"}
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_glucagon_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "GIP and glucagon secretion in T2D"}
        assert _m42c_row_is_mechanism_rich(row) is True


class TestM42cMechanismFloorIntegration:
    def test_mechanism_floor_reserves_slots_when_pool_rich(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        # 5 mechanism rows (enough to trigger floor) + 5 non-mech
        # efficacy rows + 3 meta-analyses
        rows = []
        for i in range(5):
            rows.append({
                "evidence_id": f"ev_m{i}",
                "url": f"https://example.com/mech{i}",
                "tier": "T1",
                "title": f"Pharmacokinetics and receptor binding study {i}",
                "statement": "Half-life, bioavailability, receptor affinity",
            })
        for i in range(5):
            rows.append({
                "evidence_id": f"ev_e{i}",
                "url": f"https://example.com/eff{i}",
                "tier": "T1",
                "title": f"SURPASS-{i+1} efficacy results",
                "statement": "HbA1c reduction and weight loss at week 40",
            })
        for i in range(3):
            rows.append({
                "evidence_id": f"ev_t2_{i}",
                "url": f"https://example.com/meta{i}",
                "tier": "T2",
                "title": f"Meta-analysis {i}",
                "statement": "Pooled HbA1c reduction",
            })
        result = select_evidence_for_generation(
            research_question="tirzepatide efficacy safety type 2 diabetes",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=8,
        )
        # Mechanism floor must fire (pool has 5 mech rows, above threshold 4)
        m42c_notes = [n for n in result.notes if "m42c_mechanism_floor" in n]
        assert m42c_notes, f"M-42c telemetry missing; notes={result.notes}"
        # Check that at least some mechanism rows made it into selection
        selected_titles = [r.get("title", "") for r in result.selected_rows]
        mech_selected = sum(
            1 for t in selected_titles
            if "Pharmacokinetics" in t or "receptor" in t.lower()
        )
        assert mech_selected >= 1, (
            f"mechanism floor didn't reserve any slots; "
            f"selected={selected_titles}"
        )

    def test_no_mechanism_floor_when_pool_thin(self) -> None:
        """Pool with <4 mechanism rows → floor does not fire."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            # 2 mechanism rows (below threshold 4)
            {"evidence_id": "ev_m1", "url": "https://x.com/m1",
             "tier": "T1", "title": "Pharmacokinetic study",
             "statement": "half-life"},
            {"evidence_id": "ev_m2", "url": "https://x.com/m2",
             "tier": "T1", "title": "Receptor binding",
             "statement": "affinity measurements"},
            # Rest are efficacy
            {"evidence_id": "ev_e1", "url": "https://x.com/e1",
             "tier": "T1", "title": "SURPASS-1 efficacy",
             "statement": "HbA1c reduction"},
            {"evidence_id": "ev_e2", "url": "https://x.com/e2",
             "tier": "T1", "title": "SURPASS-2 efficacy",
             "statement": "HbA1c reduction"},
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide efficacy",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,
        )
        m42c_notes = [n for n in result.notes if "m42c_mechanism_floor" in n]
        assert not m42c_notes, (
            f"m42c fired with insufficient pool: {m42c_notes}"
        )

    def test_mechanism_floor_respects_t1_quota(self) -> None:
        """Mechanism floor does NOT expand T1 quota — it reserves
        within existing quota."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        # All T1 mechanism rows (no T2/T3)
        rows = [
            {"evidence_id": f"ev_m{i}", "url": f"https://x.com/m{i}",
             "tier": "T1", "title": "Pharmacokinetics study",
             "statement": "receptor half-life metabolism"}
            for i in range(10)
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide mechanism",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=5,
        )
        # All selected are T1; mechanism floor within 5-slot T1 quota
        assert len(result.selected_rows) == 5


# ─────────────────────────────────────────────────────────────────────
# Section prompt conditional mechanism target
# ─────────────────────────────────────────────────────────────────────


class TestM42cSectionPromptRule:
    def test_m42c_rule_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "M-42c" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "MECHANISM-SECTION DEPTH RULE" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_conditional_tiers_stated(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        # All three tiers must be stated
        assert "20-35 sentences" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "15-20 sentences" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "10-15 sentences" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_specifies_mechanism_topics(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "M-42c MECHANISM-SECTION DEPTH RULE"
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000].lower()
        required_topics = [
            "receptor", "pharmacokinetic", "clamp", "signaling",
        ]
        for topic in required_topics:
            assert topic in body, f"missing topic: {topic}"

    def test_rule_applies_only_to_mechanism_section(self) -> None:
        """Rule body must explicitly say it applies ONLY when section
        title is Mechanism."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "M-42c MECHANISM-SECTION DEPTH RULE"
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000]
        assert "ONLY when" in body
        assert 'title is "Mechanism"' in body or "Mechanism" in body

    def test_rule_requires_honest_disclosure_for_thin_pools(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "M-42c MECHANISM-SECTION DEPTH RULE"
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000].lower()
        assert "disclosure" in body or "honest" in body or "limited" in body

    def test_rule_does_not_hardcode_drug_names(self) -> None:
        """M-32 generalization discipline — rule body must not name
        specific drugs (tirzepatide, semaglutide). Narrow the scan
        to ONLY the M-42c rule body (stops at next block heading)."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "M-42c MECHANISM-SECTION DEPTH RULE"
        )
        # Stop at next block heading (EVIDENCE TIER DISCIPLINE or
        # TRIAL-SPECIFIC CITATION RULE or similar all-caps section).
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "EVIDENCE TIER DISCIPLINE", start
        )
        assert end > start, "could not find M-42c rule end boundary"
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end].lower()
        banned = [
            "tirzepatide", "semaglutide", "liraglutide", "dulaglutide",
            "mounjaro", "zepbound", "ozempic",
        ]
        leaks = [d for d in banned if d in body]
        assert not leaks, f"M-42c rule hardcodes drug names: {leaks}"
