"""LIVE TOOLS CANARY TEST — zero mocks, real computation, real subprocess.

This test verifies that every tool in the v3 pipeline actually WORKS
with real Python execution. No mocks. No stubs. If scipy is broken,
if subprocess can't capture stdout, if citation resolution is dead —
this test catches it.

Run this before every live pipeline run. If any test fails, the pipeline
will silently produce garbage.

Tests are ordered by dependency: earlier tests validate primitives that
later tests depend on.
"""

import os
import re

import pytest

# Disable features that need LLM API calls (we test tools, not LLM)
os.environ["PG_NLI_ENABLED"] = "0"
os.environ["PG_CHART_GENERATION_ENABLED"] = "0"
os.environ["PG_STORM_ENABLED"] = "0"
os.environ["PG_V3_CODE_EXEC_ENABLED"] = "0"
os.environ["PG_V3_ANALYSIS_ENABLED"] = "0"


# ---------------------------------------------------------------------------
# Realistic evidence factory (used by all tests)
# ---------------------------------------------------------------------------

def _build_evidence_store():
    """Build evidence that mirrors what v1's analyze_sources() actually returns.

    Fields match EvidencePiece TypedDict exactly. Includes structured_data
    for analysis tools and source_content for NLI verification.
    """
    return {
        "ev_001": {
            "evidence_id": "ev_001",
            "source_url": "https://doi.org/10.1016/j.jhazmat.2024.001",
            "source_title": "Biochar Adsorption of Lead from Aqueous Solutions",
            "source_type": "academic",
            "statement": "Rice husk biochar achieved 95.2% removal efficiency for Pb(II) at pH 5.0 with initial concentration 100 mg/L",
            "direct_quote": "The removal efficiency was 95.2% under optimized conditions (pH 5.0, 100 mg/L initial Pb concentration)",
            "quality_tier": "GOLD",
            "relevance_score": 0.92,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.85,
            "source_content": "This study investigated rice husk biochar for lead removal. " * 50,
            "structured_data": [
                {"data_type": "measurement", "label": "Pb removal efficiency", "value": "95.2", "unit": "%", "year": "2024", "context": "Rice husk biochar at pH 5.0"},
                {"data_type": "measurement", "label": "Initial Pb concentration", "value": "100", "unit": "mg/L", "year": "2024", "context": "Experimental condition"},
            ],
        },
        "ev_002": {
            "evidence_id": "ev_002",
            "source_url": "https://doi.org/10.1021/es.2023.002",
            "source_title": "Comparative Study of Biochar Types for Heavy Metal Remediation",
            "source_type": "academic",
            "statement": "Wood-based biochar showed 78.3% Pb removal, significantly lower than agricultural waste biochar at 91.7%",
            "direct_quote": "Wood biochar achieved 78.3% removal compared to 91.7% for agricultural waste biochar (p < 0.01)",
            "quality_tier": "GOLD",
            "relevance_score": 0.88,
            "perspective": "Comparative",
            "fact_category": "Comparison",
            "year": 2023,
            "source_confidence": 0.90,
            "source_content": "This comparative study examined different biochar feedstocks. " * 50,
            "structured_data": [
                {"data_type": "comparison", "label": "Wood biochar Pb removal", "value": "78.3", "unit": "%", "year": "2023", "context": "Wood-based feedstock"},
                {"data_type": "comparison", "label": "Agri-waste biochar Pb removal", "value": "91.7", "unit": "%", "year": "2023", "context": "Agricultural waste feedstock"},
            ],
        },
        "ev_003": {
            "evidence_id": "ev_003",
            "source_url": "https://doi.org/10.1016/j.cej.2024.003",
            "source_title": "Cost Analysis of Biochar vs Activated Carbon for Wastewater Treatment",
            "source_type": "academic",
            "statement": "Biochar treatment cost $15/m3 versus $45/m3 for activated carbon, a 67% cost reduction",
            "direct_quote": "The treatment cost was $15/m3 for biochar compared to $45/m3 for activated carbon",
            "quality_tier": "SILVER",
            "relevance_score": 0.79,
            "perspective": "Economic",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.75,
            "source_content": "Economic analysis of biochar treatment systems. " * 50,
            "structured_data": [
                {"data_type": "comparison", "label": "Biochar treatment cost", "value": "15", "unit": "$/m3", "year": "2024", "context": "Full treatment system"},
                {"data_type": "comparison", "label": "Activated carbon treatment cost", "value": "45", "unit": "$/m3", "year": "2024", "context": "Conventional treatment"},
            ],
        },
        "ev_004": {
            "evidence_id": "ev_004",
            "source_url": "https://doi.org/10.1007/s11356-2024-004",
            "source_title": "Limitations of Biochar Application in Acidic Environments",
            "source_type": "academic",
            "statement": "Biochar adsorption capacity decreased by 62% at pH 3.0 compared to pH 5.0",
            "direct_quote": "At pH 3.0, adsorption capacity was only 38% of the value observed at pH 5.0",
            "quality_tier": "SILVER",
            "relevance_score": 0.74,
            "perspective": "Scientific",
            "fact_category": "Limitation",
            "year": 2024,
            "source_confidence": 0.80,
            "source_content": "Investigation of pH effects on biochar performance. " * 50,
            "structured_data": [
                {"data_type": "measurement", "label": "Capacity reduction at pH 3", "value": "62", "unit": "%", "year": "2024", "context": "Acidic conditions"},
            ],
        },
        "ev_005": {
            "evidence_id": "ev_005",
            "source_url": "https://doi.org/10.1016/j.watres.2023.005",
            "source_title": "Field Deployment of Biochar Filters in Rural Water Systems",
            "source_type": "academic",
            "statement": "A 24-month field trial achieved 89% contaminant reduction with biochar filters in rural Bangladesh",
            "direct_quote": "Over 24 months, the biochar filter system maintained 89% removal of target contaminants",
            "quality_tier": "GOLD",
            "relevance_score": 0.85,
            "perspective": "Practical",
            "fact_category": "Application",
            "year": 2023,
            "source_confidence": 0.82,
            "source_content": "Field deployment and long-term monitoring of biochar systems. " * 50,
            "structured_data": [
                {"data_type": "measurement", "label": "Field contaminant reduction", "value": "89", "unit": "%", "year": "2023", "context": "24-month rural deployment"},
                {"data_type": "measurement", "label": "Deployment duration", "value": "24", "unit": "months", "year": "2023", "context": "Rural Bangladesh"},
            ],
        },
    }


# ===========================================================================
# CANARY 1: scipy.stats — Does CI computation actually work?
# ===========================================================================

class TestLiveStatisticalAnalysis:
    """Verify scipy.stats.t.interval() produces real confidence intervals."""

    def test_ci_computation_is_real(self):
        """The 95% CI must be mathematically correct, not a stub."""
        from src.polaris_graph.tools.analysis_toolkit import statistical_summary

        store = _build_evidence_store()
        data_points = []
        for ev in store.values():
            for dp in ev.get("structured_data", []):
                dp_copy = dict(dp)
                dp_copy["source_url"] = ev.get("source_url", "")
                dp_copy["evidence_id"] = ev.get("evidence_id", "")
                data_points.append(dp_copy)

        result = statistical_summary(data_points)
        stats = result["statistics"]

        # Must have computed real statistics (not zeros or defaults)
        assert stats["n"] >= 5, f"Expected >= 5 data points, got {stats['n']}"
        assert stats["mean"] > 0, "Mean should be positive"
        assert stats["std"] > 0, "Std should be positive (data is not all identical)"
        assert stats["ci_95_lower"] < stats["mean"], "CI lower must be below mean"
        assert stats["ci_95_upper"] > stats["mean"], "CI upper must be above mean"
        assert stats["ci_95_lower"] > 0, "CI lower should be positive for this data"

        # Verify the CI is actually from scipy.stats, not a fake formula
        # Real 95% CI for n=5+ with these values should be within a reasonable range
        ci_width = stats["ci_95_upper"] - stats["ci_95_lower"]
        assert ci_width > 1, f"CI width {ci_width} suspiciously narrow — scipy.stats not working?"
        assert ci_width < 200, f"CI width {ci_width} suspiciously wide"

    def test_markdown_table_has_real_numbers(self):
        """The markdown table must contain actual computed numbers."""
        from src.polaris_graph.tools.analysis_toolkit import statistical_summary

        store = _build_evidence_store()
        data_points = []
        for ev in store.values():
            for dp in ev.get("structured_data", []):
                dp_copy = dict(dp)
                dp_copy["source_url"] = ev.get("source_url", "")
                dp_copy["evidence_id"] = ev.get("evidence_id", "")
                data_points.append(dp_copy)

        result = statistical_summary(data_points)
        table = result["markdown_table"]

        assert "|" in table, "Table must have pipe chars"
        assert "---" in table, "Table must have separator row"
        # Must contain actual numbers from the data, not placeholders
        numbers_in_table = re.findall(r'\d+\.?\d*', table)
        assert len(numbers_in_table) >= 3, f"Table has only {len(numbers_in_table)} numbers — seems like a stub"

    def test_meta_analysis_produces_pooled_estimate(self):
        """Meta-analysis must compute a real weighted pooled estimate."""
        from src.polaris_graph.tools.analysis_toolkit import generate_meta_analysis_summary

        store = _build_evidence_store()
        data_points = []
        for ev in store.values():
            for dp in ev.get("structured_data", []):
                dp_copy = dict(dp)
                dp_copy["source_url"] = ev.get("source_url", "")
                dp_copy["evidence_id"] = ev.get("evidence_id", "")
                data_points.append(dp_copy)

        result = generate_meta_analysis_summary(data_points)

        assert len(result) > 100, f"Meta-analysis too short ({len(result)} chars)"
        assert "|" in result, "Should contain a table"
        # Must mention pooled/weighted/heterogeneity (real meta-analysis language)
        result_lower = result.lower()
        has_meta_terms = (
            "pooled" in result_lower or
            "weighted" in result_lower or
            "heterogeneity" in result_lower or
            "i-squared" in result_lower or
            "i²" in result_lower
        )
        assert has_meta_terms, f"Meta-analysis missing statistical terms — might be a stub. Content: {result[:200]}"

    def test_comparison_table_pivots_correctly(self):
        """Comparison table must create a real pivot with sources as rows."""
        from src.polaris_graph.tools.analysis_toolkit import build_comparison_table

        store = _build_evidence_store()
        data_points = []
        for ev in store.values():
            for dp in ev.get("structured_data", []):
                # Propagate source_url into data point (mirrors analyze_node behavior)
                dp_copy = dict(dp)
                dp_copy["source_url"] = ev.get("source_url", "")
                dp_copy["evidence_id"] = ev.get("evidence_id", "")
                data_points.append(dp_copy)

        table = build_comparison_table(data_points)

        assert "|" in table, "Must be a markdown table"
        lines = [l for l in table.split("\n") if "|" in l and "---" not in l]
        # Header + at least 2 data rows + summary row
        assert len(lines) >= 3, f"Table has only {len(lines)} rows — not a real pivot"

    def test_agreement_score_differentiates(self):
        """Agreement score must distinguish similar vs different statements."""
        from src.polaris_graph.tools.analysis_toolkit import compute_agreement_score

        similar = [
            "Biochar removes heavy metals through ion exchange",
            "Heavy metal removal by biochar involves ion exchange mechanisms",
            "Ion exchange is the primary mechanism for biochar heavy metal adsorption",
        ]
        different = [
            "Biochar removes heavy metals through ion exchange",
            "Solar panels convert sunlight to electricity using photovoltaic cells",
            "Machine learning models predict protein folding structures",
        ]

        sim_result = compute_agreement_score(similar)
        diff_result = compute_agreement_score(different)

        assert sim_result["agreement_score"] > diff_result["agreement_score"], (
            f"Similar ({sim_result['agreement_score']:.3f}) should score higher than "
            f"different ({diff_result['agreement_score']:.3f})"
        )


# ===========================================================================
# CANARY 2: subprocess — Does code executor actually spawn Python?
# ===========================================================================

class TestLiveCodeExecution:
    """Verify real subprocess execution with numpy/matplotlib."""

    @pytest.mark.asyncio
    async def test_numpy_computation_in_subprocess(self):
        """Subprocess must actually import numpy and compute."""
        from src.polaris_graph.tools.code_executor import execute_analysis_script

        script = """
import json, sys
import numpy as np
from scipy import stats

data = json.load(sys.stdin)
values = np.array(data["values"], dtype=float)

result = {
    "mean": float(np.mean(values)),
    "median": float(np.median(values)),
    "std": float(np.std(values, ddof=1)),
    "ci_95": list(stats.t.interval(0.95, len(values)-1, loc=np.mean(values), scale=stats.sem(values))),
    "n": len(values),
    "numpy_version": np.__version__,
}
print(json.dumps(result))
"""
        result = await execute_analysis_script(
            script=script,
            input_data={"values": [95.2, 78.3, 91.7, 89.0, 62.0, 45.0, 15.0, 24.0]},
            timeout=30,
        )

        assert result["success"], f"numpy script failed: {result.get('error')} stderr: {result.get('stderr')}"
        data = result["result"]
        assert data["n"] == 8
        assert 40 < data["mean"] < 70, f"Mean {data['mean']} out of expected range"
        assert data["std"] > 0, "Std should be positive"
        assert len(data["ci_95"]) == 2, "CI should have lower and upper"
        assert data["ci_95"][0] < data["mean"] < data["ci_95"][1], "Mean should be within CI"
        assert data["numpy_version"], "numpy version should be populated"

    @pytest.mark.asyncio
    async def test_matplotlib_chart_is_real_png(self):
        """Subprocess must produce a real PNG image, not empty base64."""
        from src.polaris_graph.tools.code_executor import execute_analysis_script
        import base64

        script = """
import json, sys, io, base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

data = json.load(sys.stdin)
studies = data["studies"]
values = data["values"]

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(range(len(values)), values, color=['#2ecc71' if v > 80 else '#e74c3c' for v in values])
ax.set_xticks(range(len(studies)))
ax.set_xticklabels(studies, rotation=45, ha='right')
ax.set_ylabel('Removal Efficiency (%)')
ax.set_title('Heavy Metal Removal by Biochar Type')
ax.axhline(y=np.mean(values), color='gray', linestyle='--', label=f'Mean: {np.mean(values):.1f}%')
ax.legend()
plt.tight_layout()

buf = io.BytesIO()
plt.savefig(buf, format='png', dpi=150)
buf.seek(0)
img_bytes = buf.read()
plt.close()

print(json.dumps({
    "chart_bytes": len(img_bytes),
    "charts": [{"title": "Biochar Removal Efficiency", "image_base64": base64.b64encode(img_bytes).decode()}],
}))
"""
        result = await execute_analysis_script(
            script=script,
            input_data={
                "studies": ["Rice Husk", "Wood", "Corn Stover", "Coconut Shell", "Wheat Straw"],
                "values": [95.2, 78.3, 91.7, 85.0, 88.5],
            },
            timeout=30,
        )

        assert result["success"], f"Chart script failed: {result.get('error')} stderr: {result.get('stderr')}"

        # Verify real PNG
        charts = result.get("charts", [])
        assert len(charts) >= 1, "Should produce at least 1 chart"

        img_b64 = charts[0].get("image_base64", "")
        assert len(img_b64) > 1000, f"Chart base64 too short ({len(img_b64)} chars) — not a real image"

        # Decode and verify PNG header
        img_bytes = base64.b64decode(img_b64)
        assert img_bytes[:4] == b'\x89PNG', "Decoded bytes should start with PNG header"
        assert len(img_bytes) > 5000, f"PNG only {len(img_bytes)} bytes — too small for a real chart"

    @pytest.mark.asyncio
    async def test_pandas_dataframe_in_subprocess(self):
        """Subprocess must be able to use pandas DataFrames."""
        from src.polaris_graph.tools.code_executor import execute_analysis_script

        script = """
import json, sys
import pandas as pd
import numpy as np

data = json.load(sys.stdin)
df = pd.DataFrame(data["records"])

result = {
    "shape": list(df.shape),
    "columns": list(df.columns),
    "mean_value": float(df["value"].mean()),
    "grouped": df.groupby("source")["value"].mean().to_dict(),
    "pandas_version": pd.__version__,
}
print(json.dumps(result))
"""
        result = await execute_analysis_script(
            script=script,
            input_data={"records": [
                {"source": "Study A", "metric": "Pb removal", "value": 95.2},
                {"source": "Study A", "metric": "Cd removal", "value": 87.6},
                {"source": "Study B", "metric": "Pb removal", "value": 78.3},
                {"source": "Study B", "metric": "Cd removal", "value": 72.1},
            ]},
            timeout=30,
        )

        assert result["success"], f"Pandas script failed: {result.get('error')} stderr: {result.get('stderr')}"
        data = result["result"]
        assert data["shape"] == [4, 3], f"DataFrame shape wrong: {data['shape']}"
        assert len(data["grouped"]) == 2, "Should have 2 groups"
        assert data["pandas_version"], "pandas version should be populated"


# ===========================================================================
# CANARY 3: Citation resolution — Do [CITE:ev_xxx] become [1] with bibliography?
# ===========================================================================

class TestLiveCitationResolution:
    """Verify citation resolution is not dead code."""

    def test_cite_tokens_resolve_to_numbers(self):
        """[CITE:ev_xxx] must become [1], [2], etc."""
        from src.polaris_graph.nodes.assemble import _resolve_all_citations
        from src.polaris_graph.contracts_v3 import VerifiedSectionDraft

        store = _build_evidence_store()

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="Mechanisms",
                content=(
                    "Rice husk biochar achieved 95.2% removal [CITE:ev_001]. "
                    "Wood-based biochar showed lower efficiency at 78.3% [CITE:ev_002]. "
                    "Cost analysis shows biochar at $15/m3 [CITE:ev_003]."
                ),
                evidence_ids_used=["ev_001", "ev_002", "ev_003"],
                word_count=30,
            ),
            VerifiedSectionDraft(
                section_id="s02", title="Limitations",
                content=(
                    "Performance degrades at low pH [CITE:ev_004]. "
                    "However, field trials show 89% reduction [CITE:ev_005]. "
                    "Earlier studies confirmed this [CITE:ev_001]."
                ),
                evidence_ids_used=["ev_004", "ev_005", "ev_001"],
                word_count=25,
            ),
        ]

        resolved, bibliography = _resolve_all_citations(sections, store)

        # Citations must be resolved to [N]
        for section in resolved:
            assert "[CITE:" not in section.content, (
                f"Unresolved CITE tokens in '{section.title}': {section.content[:100]}"
            )
            numbers = re.findall(r'\[(\d+)\]', section.content)
            assert len(numbers) >= 2, (
                f"Section '{section.title}' has only {len(numbers)} resolved citations"
            )

        # Bibliography must have entries
        assert len(bibliography) >= 4, f"Bibliography has only {len(bibliography)} entries"

        # Each bibliography entry must have real data from evidence
        for entry in bibliography:
            assert entry["citation_number"] > 0
            assert entry["evidence_id"].startswith("ev_")
            assert entry["url"].startswith("https://"), f"URL missing: {entry}"
            assert len(entry["title"]) > 10, f"Title too short: {entry['title']}"

        # Citation numbers must be sequential
        numbers = [e["citation_number"] for e in bibliography]
        assert numbers == list(range(1, len(numbers) + 1)), f"Non-sequential: {numbers}"

    def test_invalid_citations_stripped(self):
        """Citations to non-existent evidence must be silently removed."""
        from src.polaris_graph.nodes.assemble import _resolve_all_citations
        from src.polaris_graph.contracts_v3 import VerifiedSectionDraft

        store = _build_evidence_store()

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="Test",
                content="Valid [CITE:ev_001] and invalid [CITE:ev_999] and another valid [CITE:ev_002].",
                evidence_ids_used=["ev_001", "ev_999", "ev_002"],
                word_count=15,
            ),
        ]

        resolved, bibliography = _resolve_all_citations(sections, store)

        content = resolved[0].content
        assert "[CITE:ev_999]" not in content, "Invalid citation should be stripped"
        assert "[1]" in content, "Valid citation should be resolved"
        assert "[2]" in content, "Second valid citation should be resolved"
        assert len(bibliography) == 2, f"Bibliography should have 2 entries, got {len(bibliography)}"


# ===========================================================================
# CANARY 4: SQLite — Does evidence load and query correctly?
# ===========================================================================

class TestLiveSQLiteQueries:
    """Verify SQLite actually loads evidence and runs real queries."""

    def test_evidence_loads_with_correct_counts(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        store = _build_evidence_store()
        db = EvidenceDatabase()
        loaded = db.load_evidence(store)

        assert loaded == 5, f"Expected 5, loaded {loaded}"

        # Verify actual data in database
        result = db.query("SELECT COUNT(*) as total FROM evidence")
        assert result["success"]
        assert result["rows"][0][0] == 5

        db.close()

    def test_tier_aggregation_returns_real_data(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        store = _build_evidence_store()
        db = EvidenceDatabase()
        db.load_evidence(store)

        result = db.query(
            "SELECT quality_tier, COUNT(*) as n, ROUND(AVG(relevance_score), 3) as avg_rel "
            "FROM evidence GROUP BY quality_tier ORDER BY n DESC"
        )

        assert result["success"]
        assert result["row_count"] == 2, f"Expected 2 tiers (GOLD, SILVER), got {result['row_count']}"

        # Verify actual values
        tiers = {row[0]: {"count": row[1], "avg_rel": row[2]} for row in result["rows"]}
        assert "GOLD" in tiers, f"Missing GOLD tier. Tiers: {tiers}"
        assert "SILVER" in tiers, f"Missing SILVER tier. Tiers: {tiers}"
        assert tiers["GOLD"]["count"] == 3, f"Expected 3 GOLD, got {tiers['GOLD']['count']}"
        assert tiers["SILVER"]["count"] == 2, f"Expected 2 SILVER, got {tiers['SILVER']['count']}"
        assert tiers["GOLD"]["avg_rel"] > tiers["SILVER"]["avg_rel"], "GOLD should have higher avg relevance"

        db.close()

    def test_structured_data_loads(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        store = _build_evidence_store()
        db = EvidenceDatabase()
        db.load_evidence(store)

        result = db.query(
            "SELECT label, value, unit FROM structured_data ORDER BY value DESC LIMIT 5"
        )

        assert result["success"]
        assert result["row_count"] >= 3, f"Expected >= 3 structured data rows, got {result['row_count']}"

        # Verify actual numeric values loaded
        values = [row[1] for row in result["rows"]]
        assert max(values) > 90, f"Max value {max(values)} — data not loaded correctly"

        db.close()

    def test_source_summary_view_works(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        store = _build_evidence_store()
        db = EvidenceDatabase()
        db.load_evidence(store)

        result = db.query(
            "SELECT source_title, evidence_count, ROUND(avg_relevance, 3) "
            "FROM source_summary ORDER BY evidence_count DESC"
        )

        assert result["success"]
        assert result["row_count"] == 5, f"Expected 5 sources, got {result['row_count']}"

        db.close()


# ===========================================================================
# CANARY 5: Full assembly pipeline — report has all required parts
# ===========================================================================

class TestLiveReportAssembly:
    """Verify the full assembly produces a complete report."""

    @pytest.mark.asyncio
    async def test_full_assembly_with_real_evidence(self):
        from src.polaris_graph.nodes.assemble import run_assemble_phase
        from src.polaris_graph.contracts_v3 import VerifiedSectionDraft

        store = _build_evidence_store()

        sections = [
            VerifiedSectionDraft(
                section_id="s01",
                title="Adsorption Mechanisms and Efficiency",
                content=(
                    "Rice husk biochar demonstrates exceptional heavy metal removal capacity "
                    "through multiple adsorption mechanisms [CITE:ev_001]. Comparative studies "
                    "show wood-based biochar achieves 78.3% removal versus 91.7% for agricultural "
                    "waste biochar [CITE:ev_002]. The cost advantage is substantial, with biochar "
                    "treatment at $15/m3 compared to $45/m3 for activated carbon [CITE:ev_003]."
                ),
                evidence_ids_used=["ev_001", "ev_002", "ev_003"],
                claims_verified=3, claims_total=3,
                faithfulness_score=0.85, critic_passed=True,
                word_count=55,
            ),
            VerifiedSectionDraft(
                section_id="s02",
                title="Limitations and Field Applications",
                content=(
                    "Performance degrades significantly at pH below 3.0, with a 62% reduction "
                    "in adsorption capacity [CITE:ev_004]. However, 24-month field trials in "
                    "rural Bangladesh demonstrated sustained 89% contaminant reduction [CITE:ev_005]. "
                    "These results align with earlier laboratory findings [CITE:ev_001], suggesting "
                    "that real-world conditions do not significantly impair biochar performance."
                ),
                evidence_ids_used=["ev_004", "ev_005", "ev_001"],
                claims_verified=3, claims_total=3,
                faithfulness_score=0.90, critic_passed=True,
                word_count=55,
            ),
        ]

        result = await run_assemble_phase(
            sections=sections,
            evidence_store=store,
            query="biochar heavy metal removal from aqueous solutions",
            vector_id="CANARY_TEST_001",
            expected_sections=2,
        )

        report = result["final_report"]
        bib = result["bibliography"]
        metrics = result["quality_metrics"]

        # --- Report structure checks ---
        assert "# Research Report:" in report, "Missing report title"
        assert "## Abstract" in report, "Missing abstract"
        assert "## Table of Contents" in report, "Missing TOC"
        assert "## Adsorption Mechanisms" in report, "Missing section 1"
        assert "## Limitations and Field" in report, "Missing section 2"
        assert "## References" in report, "Missing references"

        # --- Citation resolution checks ---
        assert "[CITE:" not in report, f"Unresolved CITE tokens in report"
        resolved_citations = re.findall(r'\[\d+\]', report)
        assert len(resolved_citations) >= 5, f"Only {len(resolved_citations)} resolved citations"

        # --- Bibliography checks ---
        assert len(bib) >= 4, f"Only {len(bib)} bibliography entries"
        for entry in bib:
            assert "doi.org" in entry.get("url", ""), f"Bibliography URL missing DOI: {entry}"

        # --- Quality metrics checks ---
        assert metrics["word_count"] > 50, f"Only {metrics['word_count']} words"
        assert metrics["citation_count"] >= 5, f"Only {metrics['citation_count']} citations"
        assert metrics["unique_sources"] >= 4, f"Only {metrics['unique_sources']} unique sources"
        assert metrics["faithfulness_pct"] > 80, f"Faithfulness only {metrics['faithfulness_pct']}%"
        assert metrics["has_toc"] is True, "TOC metric not set"
        assert metrics["sections_total"] == 2
        assert metrics["nli_claims_verified"] == 6, f"NLI verified: {metrics['nli_claims_verified']}"

        # --- Status check ---
        assert result["status"] == "completed"


# ===========================================================================
# CANARY 6: Evidence distribution — Jaccard matching produces balanced output
# ===========================================================================

class TestLiveEvidenceDistribution:
    """Verify Jaccard matching distributes evidence correctly with real data."""

    def test_real_evidence_distributes_to_matching_sections(self):
        from src.polaris_graph.nodes.outline import _assign_evidence_to_outline
        from src.polaris_graph.contracts_v3 import LiveOutline, OutlineSection

        store = _build_evidence_store()
        meta = {}
        for ev_id, ev in store.items():
            meta[ev_id] = {
                "tier": ev["quality_tier"],
                "score": ev["relevance_score"],
                "source_url": ev["source_url"],
                "source_title": ev["source_title"],
                "statement": ev["statement"],
            }

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(
                    id="s01",
                    title="Adsorption Mechanisms and Removal Efficiency",
                    description="Ion exchange, surface complexation, removal rates for Pb, Cd, Cr",
                    order=1,
                ),
                OutlineSection(
                    id="s02",
                    title="Cost Analysis and Economic Comparison",
                    description="Treatment cost comparison biochar vs activated carbon",
                    order=2,
                ),
                OutlineSection(
                    id="s03",
                    title="Limitations and Field Deployment",
                    description="pH sensitivity, acidic environments, rural field trials",
                    order=3,
                ),
            ],
        )

        result = _assign_evidence_to_outline(outline, meta)

        dist = {s.id: len(s.evidence_ids) for s in result.sections}

        # Every section should have at least 1 evidence
        for sec in result.sections:
            assert len(sec.evidence_ids) > 0, (
                f"Section '{sec.title}' got 0 evidence — Jaccard matching failed. "
                f"Distribution: {dist}"
            )

        # ev_003 (cost analysis) should be in s02 (cost section)
        s02_ids = result.sections[1].evidence_ids
        assert "ev_003" in s02_ids, (
            f"ev_003 (cost analysis) should be in s02 (cost section), "
            f"but s02 has: {s02_ids}"
        )

        # ev_004 (pH limitations) should be in s03 (limitations)
        s03_ids = result.sections[2].evidence_ids
        assert "ev_004" in s03_ids, (
            f"ev_004 (pH limitations) should be in s03 (limitations section), "
            f"but s03 has: {s03_ids}"
        )
