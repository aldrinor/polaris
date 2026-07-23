"""M-42c tests for evidence-derived process weighting and prompt guidance."""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────
# Selector mechanism-evidence floor
# ─────────────────────────────────────────────────────────────────────


class TestM42cMechanismDetection:
    def test_mechanism_token_in_title_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {
            "title": "Mechanism of request routing",
            "statement": "Causal process model for queued requests",
        }
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_mechanism_token_in_statement_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {
            "title": "Worker allocation results",
            "statement": "Requests bind to workers and interact with the queue",
        }
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_mechanism_token_in_direct_quote_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {
            "title": "Network evaluation",
            "direct_quote": "Packets propagated through the network in 5 seconds",
        }
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_non_mechanism_row_not_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {
            "title": "ORION-2 throughput benchmark",
            "statement": "Throughput at day 40",
            "direct_quote": "Mean throughput increased by 2.30 percent",
        }
        assert _m42c_row_is_mechanism_rich(row) is False

    def test_process_language_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "Signalling pathways in a distributed controller"}
        assert _m42c_row_is_mechanism_rich(row) is True

    def test_process_verb_detected(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            _m42c_row_is_mechanism_rich,
        )
        row = {"title": "Signal propagation through nested queues"}
        assert _m42c_row_is_mechanism_rich(row) is True


class TestM42cMechanismFloorIntegration:
    def test_mechanism_floor_reserves_slots_when_pool_rich(self) -> None:
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        # Process-rich and result-only rows coexist in the same source pool.
        rows = []
        for i in range(5):
            rows.append({
                "evidence_id": f"ev_m{i}",
                "url": f"https://example.com/mech{i}",
                "tier": "T1",
                "title": f"Causal process and signal propagation study {i}",
                "statement": "Requests bind to workers and transition between queues",
            })
        for i in range(5):
            rows.append({
                "evidence_id": f"ev_e{i}",
                "url": f"https://example.com/eff{i}",
                "tier": "T1",
                "title": f"ORION-{i+1} performance results",
                "statement": "Latency reduction and throughput at day 40",
            })
        for i in range(3):
            rows.append({
                "evidence_id": f"ev_t2_{i}",
                "url": f"https://example.com/meta{i}",
                "tier": "T2",
                "title": f"Evidence review {i}",
                "statement": "Pooled latency reduction",
            })
        result = select_evidence_for_generation(
            research_question="request routing latency and throughput",
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
            if "Causal process" in t or "propagation" in t.lower()
        )
        assert mech_selected >= 1, (
            f"mechanism floor didn't reserve any slots; "
            f"selected={selected_titles}"
        )

    def test_process_weighting_follows_available_evidence(self) -> None:
        """Every evidence-derived process row is weighted without a fixed floor."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        rows = [
            # Two process rows; evidence supply, not a fixed minimum, controls
            # how many are eligible for weighting.
            {"evidence_id": "ev_m1", "url": "https://x.com/m1",
             "tier": "T1", "title": "Queue process study",
             "statement": "process model"},
            {"evidence_id": "ev_m2", "url": "https://x.com/m2",
             "tier": "T1", "title": "Worker allocation",
             "statement": "system components interact"},
            # The remaining rows report results without process evidence.
            {"evidence_id": "ev_e1", "url": "https://x.com/e1",
             "tier": "T1", "title": "ORION-1 performance",
             "statement": "latency reduction"},
            {"evidence_id": "ev_e2", "url": "https://x.com/e2",
             "tier": "T1", "title": "ORION-2 performance",
             "statement": "latency reduction"},
        ]
        result = select_evidence_for_generation(
            research_question="request routing performance",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,
        )
        m42c_notes = [n for n in result.notes if "m42c_mechanism_floor" in n]
        assert m42c_notes
        assert "pool_mech_rows=2" in m42c_notes[0]
        assert "weighted=2" in m42c_notes[0]

    def test_mechanism_floor_respects_t1_quota(self) -> None:
        """Mechanism floor does NOT expand T1 quota — it reserves
        within existing quota."""
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        # All T1 mechanism rows (no T2/T3)
        rows = [
            {"evidence_id": f"ev_m{i}", "url": f"https://x.com/m{i}",
             "tier": "T1", "title": "Mechanism study",
             "statement": "system components interact and propagate"}
            for i in range(10)
        ]
        result = select_evidence_for_generation(
            research_question="system mechanism",
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
        assert "MECHANISM OR CAUSAL-PROCESS RULE" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_has_no_sentence_count_targets(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        import re
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "MECHANISM OR CAUSAL-PROCESS RULE"
        )
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "EVIDENCE TIER DISCIPLINE", start,
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end]
        assert not re.search(
            r"\b\d+\s*-\s*\d+\s+sentences\b",
            body,
        )

    def test_rule_derives_process_topics_from_evidence(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "MECHANISM OR CAUSAL-PROCESS RULE"
        )
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "EVIDENCE TIER DISCIPLINE", start,
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end].lower()
        assert "derive its subtopics" in body
        assert "that recur in that section's evidence" in body

    def test_rule_uses_content_not_section_title_as_trigger(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "MECHANISM OR CAUSAL-PROCESS RULE"
        )
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "EVIDENCE TIER DISCIPLINE", start,
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end].lower()
        assert "do not use" in body
        assert "section title" in body

    def test_rule_requires_evidence_boundaries(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "MECHANISM OR CAUSAL-PROCESS RULE"
        )
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "EVIDENCE TIER DISCIPLINE", start,
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end].lower()
        assert "interpretive" in body
        assert "supports only part" in body

    def test_rule_does_not_hardcode_domain_vocabulary(self) -> None:
        """The process rule must derive its vocabulary from evidence."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "MECHANISM OR CAUSAL-PROCESS RULE"
        )
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "EVIDENCE TIER DISCIPLINE", start
        )
        assert end > start
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end].lower()
        banned = [
            "receptor", "pharmacokinetic", "clamp", "signaling",
            "drug", "disease",
        ]
        leaks = [d for d in banned if d in body]
        assert not leaks, f"process rule hardcodes domain vocabulary: {leaks}"
