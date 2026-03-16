"""
Integration tests for LTM/override storage+retrieval and planner prompt
construction.

Tests real ChromaDB (EphemeralClient) with real sentence-transformer
embeddings, and verifies the planner prompt includes or excludes
PRIOR KNOWLEDGE / HUMAN CORRECTION HISTORY sections based on state.

Source files under test:
    src/polaris_graph/memory/cross_vector.py
    src/polaris_graph/agents/planner.py  (prompt construction only, no LLM)
"""

import logging
import uuid

import chromadb
import pytest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Single EphemeralClient for the entire module.  ChromaDB EphemeralClient
# instances share a singleton in-memory backend, so creating multiple
# instances does NOT provide isolation.  Use unique collection names
# per test invocation to guarantee full isolation.
_MODULE_CHROMA_CLIENT = chromadb.EphemeralClient()


@pytest.fixture()
def ephemeral_chroma(monkeypatch):
    """Provide a clean ChromaDB state for each test.

    Uses unique collection names per test (UUID suffix) so that the
    shared EphemeralClient backend cannot leak data across tests.

    The EphemeralClient uses the default embedding function
    (chromadb's built-in all-MiniLM-L6-v2 via sentence-transformers),
    which gives real semantic similarity -- zero mocks.
    """
    client = _MODULE_CHROMA_CLIENT
    suffix = uuid.uuid4().hex[:8]

    import src.polaris_graph.memory.cross_vector as cv

    ltm_name = f"{cv.LTM_COLLECTION_NAME}_{suffix}"
    ovr_name = f"{cv.OVERRIDE_COLLECTION_NAME}_{suffix}"

    monkeypatch.setattr(cv, "_get_chroma_manager", lambda: client)

    # Patch _get_collection to use unique per-test collection names
    def _patched_get_collection(manager):
        return manager.get_or_create_collection(name=ltm_name)

    def _patched_get_override_collection(manager):
        return manager.get_or_create_collection(name=ovr_name)

    monkeypatch.setattr(cv, "_get_collection", _patched_get_collection)
    monkeypatch.setattr(cv, "_get_override_collection", _patched_get_override_collection)

    yield client

    # Cleanup: remove per-test collections
    for col_name in (ltm_name, ovr_name):
        try:
            client.delete_collection(col_name)
        except Exception:
            pass


def _gold_evidence(evidence_id: str, statement: str, source: str = "https://example.com") -> dict:
    """Build a GOLD-tier evidence piece with high faithfulness."""
    return {
        "evidence_id": evidence_id,
        "statement": statement,
        "source": source,
        "quality_tier": "GOLD",
        "faithfulness": 0.95,
        "relevance_score": 0.88,
        "perspective": "Scientific",
    }


def _silver_evidence(evidence_id: str, statement: str) -> dict:
    """Build a SILVER-tier evidence piece."""
    return {
        "evidence_id": evidence_id,
        "statement": statement,
        "source": "https://silver-source.org",
        "quality_tier": "SILVER",
        "faithfulness": 0.80,
        "relevance_score": 0.70,
        "perspective": "Regulatory",
    }


def _bronze_evidence(evidence_id: str, statement: str) -> dict:
    """Build a BRONZE-tier evidence piece."""
    return {
        "evidence_id": evidence_id,
        "statement": statement,
        "source": "https://bronze-source.net",
        "quality_tier": "BRONZE",
        "faithfulness": 0.50,
        "relevance_score": 0.40,
        "perspective": "Industry",
    }


# ---------------------------------------------------------------------------
# Helper: replicate planner prompt construction (lines 100-170 of planner.py)
# ---------------------------------------------------------------------------

def _build_planner_prompt(
    query: str,
    application: str,
    region: str,
    iteration: int,
    ltm_priors: list,
    overrides: list,
    gaps: list | None = None,
) -> str:
    """Replicate the prompt construction logic from planner.py lines 100-170.

    This does NOT call the LLM.  It builds the exact same string that
    ``plan_queries()`` would pass to ``client.generate_structured()``.
    """
    gaps_context = ""
    if gaps:
        gaps_context = (
            "\n\nPrevious iteration identified these evidence gaps:\n"
            + "\n".join(f"- {g}" for g in gaps)
            + "\n\nPrioritize queries that fill these gaps."
        )

    prior_context = ""
    if ltm_priors:
        prior_lines = []
        for p in ltm_priors[:10]:
            stmt = p.get("statement", "")[:120]
            tier = p.get("quality_tier", "")
            src_vec = p.get("vector_id", "")[:30]
            prior_lines.append(f"- [{tier}] {stmt} (from {src_vec})")
        prior_context = (
            "\n\nPRIOR KNOWLEDGE (from previous research \u2014 target gaps, not duplications):\n"
            + "\n".join(prior_lines)
            + "\n\nWe already know the above. Focus queries on uncovered aspects "
            "and perspectives not represented in prior knowledge."
        )

    override_context = ""
    if overrides:
        override_lines = []
        for o in overrides[:5]:
            ctx = o.get("context", "")[:200]
            otype = o.get("override_type", "unknown")
            override_lines.append(f"- Previous correction ({otype}): {ctx}")
        override_context = (
            "\n\nHUMAN CORRECTION HISTORY (avoid these mistakes):\n"
            + "\n".join(override_lines)
        )

    # Reproduce the f-string from planner.py lines 162-170
    # (QUERIES_PER_VECTOR, STORM_PERSPECTIVES, QUERIES_PER_PERSPECTIVE are
    # imported at the module level of planner.py; we replicate the template)
    from src.polaris_graph.state import (
        QUERIES_PER_VECTOR,
        STORM_PERSPECTIVES,
        QUERIES_PER_PERSPECTIVE,
    )

    prompt = f"""Research question: {query}
Application domain: {application}
Geographic focus: {region}
Iteration: {iteration + 1}
{gaps_context}{prior_context}{override_context}

Generate a comprehensive STORM query plan with {QUERIES_PER_VECTOR}+ sub-queries
covering all {len(STORM_PERSPECTIVES)} perspectives ({QUERIES_PER_PERSPECTIVE} per perspective).
Ensure every perspective is represented for maximum evidence diversity."""
    return prompt


# ---------------------------------------------------------------------------
# ChromaDB + cross_vector tests
# ---------------------------------------------------------------------------


class TestPromoteToLtm:
    """Tests for promote_to_ltm with real ChromaDB upserts."""

    # 1. promote GOLD evidence -- real ChromaDB upsert
    def test_promote_gold_evidence(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import promote_to_ltm

        evidence = [
            _gold_evidence("ev_001", "PFAS contamination exceeds EPA limits in 30% of US water supplies"),
            _gold_evidence("ev_002", "Activated carbon filters remove 95% of PFAS compounds"),
        ]
        count = promote_to_ltm(evidence, vector_id="v_test_001", min_quality="GOLD", min_faithfulness=0.9)
        assert count == 2

    # 2. query_ltm returns relevant items ordered by distance
    def test_query_ltm_returns_relevant_items(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        evidence = [
            _gold_evidence("ev_water_1", "Reverse osmosis removes 99% of dissolved solids from drinking water"),
            _gold_evidence("ev_water_2", "Chlorine disinfection is the most widely used water treatment method globally"),
            _gold_evidence("ev_unrelated", "Solar panel efficiency has increased by 25% since 2020", source="https://solar.example.com"),
        ]
        promote_to_ltm(evidence, vector_id="v_water", min_quality="GOLD", min_faithfulness=0.9)

        results = query_ltm("water purification and filtration methods", max_results=10)
        assert len(results) >= 1
        # Water-related items should have smaller distance than solar panel item
        water_items = [r for r in results if "water" in r["statement"].lower() or "chlorine" in r["statement"].lower()]
        solar_items = [r for r in results if "solar" in r["statement"].lower()]
        if water_items and solar_items:
            assert min(w["distance"] for w in water_items) < min(s["distance"] for s in solar_items)

    # 3. query_ltm result shape
    def test_query_ltm_result_shape(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        evidence = [_gold_evidence("ev_shape_01", "Lead pipes corrode and release lead into drinking water")]
        promote_to_ltm(evidence, vector_id="v_shape", min_quality="GOLD", min_faithfulness=0.9)

        results = query_ltm("lead contamination in water", max_results=5)
        assert len(results) >= 1
        item = results[0]
        expected_keys = {"id", "statement", "source", "quality_tier", "faithfulness", "relevance_score", "vector_id", "distance"}
        assert expected_keys == set(item.keys())
        assert isinstance(item["distance"], float)
        assert isinstance(item["faithfulness"], float)
        assert item["quality_tier"] == "GOLD"
        assert item["vector_id"] == "v_shape"

    # 4. store_human_override returns True
    def test_store_human_override_returns_true(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import store_human_override

        override = {
            "override_id": "ovr_001",
            "vector_id": "v_test",
            "checkpoint_id": "chk_abc",
            "node": "verify",
            "override_type": "evidence_correction",
            "original_value": "PFAS is completely safe",
            "corrected_value": "PFAS bioaccumulates and poses health risks",
            "context": "Correcting false claim about PFAS safety in water treatment research",
        }
        result = store_human_override(override)
        assert result is True

    # 5. query_human_overrides -- real semantic retrieval
    def test_query_human_overrides_retrieval(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import (
            store_human_override,
            query_human_overrides,
        )

        override = {
            "override_id": "ovr_retrieval_01",
            "vector_id": "v_ret",
            "checkpoint_id": "chk_ret",
            "node": "analyze",
            "override_type": "factual_correction",
            "original_value": "UV treatment kills 50% of bacteria",
            "corrected_value": "UV treatment kills 99.99% of bacteria at proper dosage",
            "context": "UV water disinfection effectiveness was understated",
        }
        store_human_override(override)

        results = query_human_overrides("UV disinfection bacteria removal", k=5)
        assert len(results) >= 1
        item = results[0]
        assert "id" in item
        assert "context" in item
        assert "override_type" in item
        assert "node" in item
        assert "distance" in item

    # 6. promote_to_ltm filters by min_quality
    def test_promote_filters_by_quality(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        evidence = [
            _gold_evidence("ev_q_gold", "Gold-tier evidence about water quality standards"),
            _silver_evidence("ev_q_silver", "Silver-tier evidence about filtration methods"),
            _bronze_evidence("ev_q_bronze", "Bronze-tier evidence about tap water testing"),
        ]
        # Only GOLD should pass when min_quality="GOLD"
        count = promote_to_ltm(evidence, vector_id="v_quality", min_quality="GOLD", min_faithfulness=0.0)
        assert count == 1

        results = query_ltm("water quality", max_results=10)
        statements = [r["statement"] for r in results]
        assert any("Gold-tier" in s for s in statements)
        assert not any("Silver-tier" in s for s in statements)
        assert not any("Bronze-tier" in s for s in statements)

    # 7. promote_to_ltm filters by min_faithfulness
    def test_promote_filters_by_faithfulness(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        evidence = [
            {
                "evidence_id": "ev_high_faith",
                "statement": "High faithfulness evidence about membrane filtration",
                "source": "https://example.com/high",
                "quality_tier": "GOLD",
                "faithfulness": 0.98,
                "relevance_score": 0.85,
                "perspective": "Scientific",
            },
            {
                "evidence_id": "ev_low_faith",
                "statement": "Low faithfulness evidence about membrane filtration",
                "source": "https://example.com/low",
                "quality_tier": "GOLD",
                "faithfulness": 0.60,
                "relevance_score": 0.85,
                "perspective": "Scientific",
            },
        ]
        count = promote_to_ltm(evidence, vector_id="v_faith", min_quality="GOLD", min_faithfulness=0.90)
        assert count == 1

        results = query_ltm("membrane filtration", max_results=10)
        statements = [r["statement"] for r in results]
        assert any("High faithfulness" in s for s in statements)
        assert not any("Low faithfulness" in s for s in statements)

    # 8. Empty query returns []
    def test_empty_query_returns_empty(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import query_ltm

        results = query_ltm("", max_results=10)
        assert results == []

    # 9. LTM items ordered by distance ascending
    def test_results_ordered_by_distance_ascending(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        # Promote diverse evidence so distances vary
        evidence = [
            _gold_evidence("ev_close", "Granular activated carbon adsorbs PFAS from drinking water"),
            _gold_evidence("ev_medium", "Ion exchange resins are used in industrial water treatment"),
            _gold_evidence("ev_far", "The Wright brothers achieved powered flight in 1903"),
        ]
        promote_to_ltm(evidence, vector_id="v_order", min_quality="GOLD", min_faithfulness=0.9)

        results = query_ltm("PFAS removal from drinking water using activated carbon", max_results=10)
        assert len(results) >= 2
        distances = [r["distance"] for r in results]
        assert distances == sorted(distances), (
            f"Expected ascending distance order, got: {distances}"
        )

    # 10. Max 10 priors cap in prompt
    def test_max_ten_priors_in_prompt(self, ephemeral_chroma):
        """Promote 15 items, verify only 10 appear in the planner prompt."""
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        evidence = [
            _gold_evidence(f"ev_cap_{i:02d}", f"Evidence statement number {i} about water treatment")
            for i in range(15)
        ]
        count = promote_to_ltm(evidence, vector_id="v_cap", min_quality="GOLD", min_faithfulness=0.9)
        assert count == 15

        # query_ltm returns up to max_results, but planner caps at 10
        all_priors = query_ltm("water treatment", max_results=20)
        assert len(all_priors) >= 10

        # Build the prompt with all priors (>10) -- the helper caps at [:10]
        prompt = _build_planner_prompt(
            query="water treatment methods",
            application="water filtration",
            region="United States",
            iteration=0,
            ltm_priors=all_priors,
            overrides=[],
        )
        # Count the prior knowledge lines (each starts with "- [")
        prior_lines = [line for line in prompt.split("\n") if line.startswith("- [GOLD]")]
        assert len(prior_lines) <= 10

    # 11. Unrelated query gives higher distances
    def test_unrelated_query_higher_distances(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        evidence = [
            _gold_evidence("ev_topic_a", "PFAS forever chemicals accumulate in human blood plasma"),
            _gold_evidence("ev_topic_b", "Nanofiltration membranes reject 90% of divalent ions"),
        ]
        promote_to_ltm(evidence, vector_id="v_dist", min_quality="GOLD", min_faithfulness=0.9)

        related_results = query_ltm("PFAS contamination in blood", max_results=5)
        unrelated_results = query_ltm("quantum computing algorithms", max_results=5)

        # Both should return results (ChromaDB returns nearest even if far)
        assert len(related_results) >= 1
        assert len(unrelated_results) >= 1
        # Related query should have smaller minimum distance
        assert min(r["distance"] for r in related_results) < min(r["distance"] for r in unrelated_results)

    # 12. Promote + query roundtrip
    def test_promote_and_query_roundtrip(self, ephemeral_chroma):
        """Promote PFAS evidence, query 'water filtration', verify retrieval."""
        from src.polaris_graph.memory.cross_vector import promote_to_ltm, query_ltm

        evidence = [
            _gold_evidence(
                "ev_pfas_rt",
                "Per- and polyfluoroalkyl substances (PFAS) are persistent organic pollutants found in water supplies worldwide",
                source="https://epa.gov/pfas",
            ),
        ]
        count = promote_to_ltm(evidence, vector_id="v_pfas", min_quality="GOLD", min_faithfulness=0.9)
        assert count == 1

        results = query_ltm("water filtration and contaminant removal", max_results=5)
        assert len(results) >= 1
        found = [r for r in results if "PFAS" in r["statement"] or "polyfluoroalkyl" in r["statement"]]
        assert len(found) >= 1
        assert found[0]["source"] == "https://epa.gov/pfas"
        assert found[0]["quality_tier"] == "GOLD"

    # 13. Override storage + retrieval roundtrip
    def test_override_storage_retrieval_roundtrip(self, ephemeral_chroma):
        from src.polaris_graph.memory.cross_vector import (
            store_human_override,
            query_human_overrides,
        )

        override = {
            "override_id": "ovr_rt_001",
            "vector_id": "v_override_rt",
            "checkpoint_id": "chk_rt_1",
            "node": "synthesize",
            "override_type": "tone_correction",
            "original_value": "Water filters are useless",
            "corrected_value": "Water filters vary in effectiveness depending on contaminant type",
            "context": "Overgeneralization about water filter effectiveness in synthesis output",
        }
        stored = store_human_override(override)
        assert stored is True

        results = query_human_overrides("water filter effectiveness", k=5)
        assert len(results) >= 1
        found = results[0]
        assert found["id"] == "ovr_rt_001"
        assert found["node"] == "synthesize"
        assert found["override_type"] == "tone_correction"
        assert found["vector_id"] == "v_override_rt"
        assert "water filter" in found["context"].lower()


# ---------------------------------------------------------------------------
# Planner prompt construction tests
# ---------------------------------------------------------------------------


class TestPlannerPromptConstruction:
    """Tests that verify the planner prompt string includes or excludes
    PRIOR KNOWLEDGE and HUMAN CORRECTION HISTORY sections based on input.

    These tests do NOT call the LLM.  They replicate the prompt construction
    logic from planner.py lines 100-170 via ``_build_planner_prompt()``.
    """

    # 14. Prompt includes "PRIOR KNOWLEDGE" when ltm_priors provided
    def test_prompt_includes_prior_knowledge(self):
        ltm_priors = [
            {"statement": "Activated carbon removes PFAS at 95% efficiency", "quality_tier": "GOLD", "vector_id": "v_prior_1"},
            {"statement": "EPA MCL for lead is 15 ppb", "quality_tier": "SILVER", "vector_id": "v_prior_2"},
        ]
        prompt = _build_planner_prompt(
            query="water treatment methods",
            application="water filtration",
            region="United States",
            iteration=0,
            ltm_priors=ltm_priors,
            overrides=[],
        )
        assert "PRIOR KNOWLEDGE" in prompt
        assert "target gaps, not duplications" in prompt
        assert "Activated carbon" in prompt
        assert "[GOLD]" in prompt
        assert "[SILVER]" in prompt
        assert "v_prior_1" in prompt
        assert "Focus queries on uncovered aspects" in prompt

    # 15. Prompt has NO "PRIOR" section when ltm_priors is empty
    def test_prompt_excludes_prior_when_empty(self):
        prompt = _build_planner_prompt(
            query="water treatment methods",
            application="water filtration",
            region="United States",
            iteration=0,
            ltm_priors=[],
            overrides=[],
        )
        assert "PRIOR KNOWLEDGE" not in prompt
        assert "target gaps" not in prompt

    def test_prompt_includes_override_history(self):
        """Prompt includes HUMAN CORRECTION HISTORY when overrides provided."""
        overrides = [
            {"context": "UV dosage was incorrectly stated as 10 mJ/cm2", "override_type": "factual_correction"},
            {"context": "Source reliability was overestimated for blog post", "override_type": "source_quality"},
        ]
        prompt = _build_planner_prompt(
            query="UV disinfection research",
            application="water treatment",
            region="Global",
            iteration=0,
            ltm_priors=[],
            overrides=overrides,
        )
        assert "HUMAN CORRECTION HISTORY" in prompt
        assert "avoid these mistakes" in prompt
        assert "UV dosage" in prompt
        assert "factual_correction" in prompt
        assert "source_quality" in prompt

    def test_prompt_excludes_override_when_empty(self):
        """Prompt has NO override section when overrides list is empty."""
        prompt = _build_planner_prompt(
            query="water treatment",
            application="water filtration",
            region="US",
            iteration=0,
            ltm_priors=[],
            overrides=[],
        )
        assert "HUMAN CORRECTION HISTORY" not in prompt
        assert "avoid these mistakes" not in prompt

    def test_prompt_includes_both_priors_and_overrides(self):
        """Both sections appear when both priors and overrides are provided."""
        ltm_priors = [
            {"statement": "Membrane bioreactors achieve 99.9% pathogen removal", "quality_tier": "GOLD", "vector_id": "v_mbr"},
        ]
        overrides = [
            {"context": "Cost data was from 2015, not 2024", "override_type": "data_freshness"},
        ]
        prompt = _build_planner_prompt(
            query="membrane bioreactor water treatment",
            application="wastewater treatment",
            region="EU",
            iteration=1,
            ltm_priors=ltm_priors,
            overrides=overrides,
        )
        assert "PRIOR KNOWLEDGE" in prompt
        assert "HUMAN CORRECTION HISTORY" in prompt
        assert "Membrane bioreactors" in prompt
        assert "Cost data was from 2015" in prompt
        # Verify iteration is correctly injected
        assert "Iteration: 2" in prompt

    def test_prompt_caps_priors_at_ten(self):
        """Even with 15 priors, only the first 10 appear in the prompt."""
        ltm_priors = [
            {
                "statement": f"Prior statement number {i} about water chemistry",
                "quality_tier": "GOLD",
                "vector_id": f"v_cap_{i}",
            }
            for i in range(15)
        ]
        prompt = _build_planner_prompt(
            query="water chemistry",
            application="water analysis",
            region="US",
            iteration=0,
            ltm_priors=ltm_priors,
            overrides=[],
        )
        # Statements 0-9 should be present, 10-14 should not
        for i in range(10):
            assert f"Prior statement number {i}" in prompt
        for i in range(10, 15):
            assert f"Prior statement number {i}" not in prompt

    def test_prompt_caps_overrides_at_five(self):
        """Even with 10 overrides, only the first 5 appear in the prompt."""
        overrides = [
            {
                "context": f"Override context number {i} about data accuracy",
                "override_type": f"type_{i}",
            }
            for i in range(10)
        ]
        prompt = _build_planner_prompt(
            query="data accuracy",
            application="water monitoring",
            region="US",
            iteration=0,
            ltm_priors=[],
            overrides=overrides,
        )
        for i in range(5):
            assert f"Override context number {i}" in prompt
        for i in range(5, 10):
            assert f"Override context number {i}" not in prompt

    def test_prompt_includes_gaps_context(self):
        """Gaps from previous iteration appear in the prompt."""
        prompt = _build_planner_prompt(
            query="PFAS removal",
            application="water filtration",
            region="US",
            iteration=1,
            ltm_priors=[],
            overrides=[],
            gaps=["No data on short-chain PFAS removal", "Missing cost-effectiveness analysis"],
        )
        assert "evidence gaps" in prompt
        assert "No data on short-chain PFAS removal" in prompt
        assert "Missing cost-effectiveness analysis" in prompt
        assert "Prioritize queries that fill these gaps" in prompt

    def test_prompt_basic_fields(self):
        """Core fields (query, application, region, iteration) always present."""
        prompt = _build_planner_prompt(
            query="arsenic in groundwater",
            application="environmental monitoring",
            region="Bangladesh",
            iteration=2,
            ltm_priors=[],
            overrides=[],
        )
        assert "Research question: arsenic in groundwater" in prompt
        assert "Application domain: environmental monitoring" in prompt
        assert "Geographic focus: Bangladesh" in prompt
        assert "Iteration: 3" in prompt
