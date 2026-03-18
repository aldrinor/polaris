"""v3 Integration Tests — validate the FULL pipeline wiring.

These tests catch the class of bugs that smoke tests miss:
- Evidence flows correctly from search → outline → synthesis → assembly
- Jaccard-based evidence assignment distributes evidence across sections
- Analysis toolkit produces real statistical output
- Code executor sandbox works
- Citations resolve to [N] with bibliography
- Structural sections (Key Findings, Contradictions, Conclusions) present
- Table of Contents generated
- Chart generation data flow works
- No silent failures (every phase produces verifiable output)

Unlike unit tests that mock at the function boundary, these tests run
multiple phases in sequence with realistic data, catching integration bugs
like the sub_question_id mapping failure.
"""

import os
import re

import pytest

# Disable expensive features in integration tests
os.environ["PG_NLI_ENABLED"] = "0"
os.environ["PG_CHART_GENERATION_ENABLED"] = "0"
os.environ["PG_STORM_ENABLED"] = "0"
os.environ["PG_V3_CODE_EXEC_ENABLED"] = "0"
os.environ["PG_V3_ANALYSIS_ENABLED"] = "0"

from unittest.mock import AsyncMock, MagicMock

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    OutlineSection,
    SubQuestion,
    VerifiedSectionDraft,
)


# ---------------------------------------------------------------------------
# Realistic test data factory
# ---------------------------------------------------------------------------

def _make_realistic_evidence_store(count: int = 30) -> dict:
    """Create evidence that spans multiple topics for distribution testing.

    Evidence covers 5 topics: mechanisms, efficiency, cost, limitations, applications.
    Each topic has distinct keywords that Jaccard matching can use.
    """
    topics = [
        {
            "topic": "mechanisms",
            "statements": [
                "Ion exchange is the primary adsorption mechanism for heavy metals on biochar surfaces",
                "Surface complexation between metal ions and carboxyl groups drives biochar adsorption",
                "Electrostatic attraction contributes to heavy metal binding on negatively charged biochar",
            ],
            "source_title": "Mechanisms of Heavy Metal Adsorption by Biochar",
        },
        {
            "topic": "efficiency",
            "statements": [
                "Biochar achieved 95.2% removal efficiency for lead at pH 5.0",
                "Removal efficiency for cadmium ranged from 78% to 93% across ten studies",
                "Chromium removal efficiency of 87.6% was observed under optimal conditions",
            ],
            "source_title": "Efficiency of Biochar Heavy Metal Removal",
        },
        {
            "topic": "cost",
            "statements": [
                "Cost analysis shows biochar treatment at $15/m3 versus $45/m3 for activated carbon",
                "Economic comparison demonstrates 67% cost reduction using agricultural waste biochar",
                "Life cycle cost assessment favors biochar over traditional adsorbents",
            ],
            "source_title": "Cost Comparison of Biochar vs Activated Carbon",
        },
        {
            "topic": "limitations",
            "statements": [
                "Biochar performance degrades significantly at pH below 3.0",
                "Regeneration of spent biochar remains technically challenging",
                "Competing ions in real wastewater reduce effective adsorption capacity by 30-40%",
            ],
            "source_title": "Limitations and Challenges of Biochar Application",
        },
        {
            "topic": "applications",
            "statements": [
                "Field-scale deployment in rural water treatment systems showed 89% contaminant reduction",
                "Agricultural runoff treatment using biochar-filled trenches removes 92% of zinc",
                "Industrial wastewater treatment pilot achieved discharge compliance within 6 months",
            ],
            "source_title": "Real-World Applications of Biochar Water Treatment",
        },
    ]

    store = {}
    idx = 0
    for topic_data in topics:
        for i, statement in enumerate(topic_data["statements"]):
            if idx >= count:
                return store
            idx += 1
            ev_id = f"ev_{idx:03d}"
            store[ev_id] = {
                "evidence_id": ev_id,
                "statement": statement,
                "direct_quote": f'"{statement[:80]}"',
                "source_url": f"https://example.com/{topic_data['topic']}-study-{i+1}",
                "source_title": topic_data["source_title"],
                "source_content": f"Full content about {topic_data['topic']}. {statement} " * 20,
                "quality_tier": "GOLD" if i == 0 else "SILVER",
                "relevance_score": round(0.9 - i * 0.1, 2),
                "perspective": "Scientific",
                "structured_data": [
                    {
                        "data_type": "measurement",
                        "label": f"{topic_data['topic']}_metric_{i}",
                        "value": str(80 + idx),
                        "unit": "%",
                        "year": "2024",
                        "context": statement[:100],
                    }
                ] if i == 0 else [],
            }

    return store


def _make_evidence_meta(store: dict) -> dict:
    """Build evidence_meta from evidence_store (mirrors graph_v3.py search_node)."""
    meta = {}
    for ev_id, ev in store.items():
        meta[ev_id] = {
            "tier": ev.get("quality_tier", "BRONZE"),
            "score": ev.get("relevance_score", 0.0),
            "source_url": ev.get("source_url", ""),
            "source_title": ev.get("source_title", ""),
            "statement": ev.get("statement", ""),
        }
    return meta


# ---------------------------------------------------------------------------
# Test 1: Evidence assignment distributes across sections (FIX-CRITICAL)
# ---------------------------------------------------------------------------

class TestEvidenceAssignment:
    """Validates that Jaccard-based assignment distributes evidence across sections.

    This catches the sub_question_id bug: v1's analyze_sources() never sets
    sub_question_id, so the old code dumped ALL evidence into the first section.
    """

    def test_evidence_distributes_across_sections(self):
        """Each section should get evidence matching its topic, not all in section 1."""
        from src.polaris_graph.nodes.outline import _assign_evidence_to_outline

        store = _make_realistic_evidence_store(15)
        meta = _make_evidence_meta(store)

        outline = LiveOutline(
            title="Biochar Heavy Metal Removal",
            sections=[
                OutlineSection(id="s01", title="Adsorption Mechanisms and Surface Chemistry",
                               description="Ion exchange, surface complexation, electrostatic attraction",
                               order=1),
                OutlineSection(id="s02", title="Removal Efficiency Across Heavy Metals",
                               description="Lead, cadmium, chromium removal rates and conditions",
                               order=2),
                OutlineSection(id="s03", title="Cost Analysis and Economic Comparison",
                               description="Cost comparison biochar vs activated carbon treatment",
                               order=3),
                OutlineSection(id="s04", title="Limitations and Technical Challenges",
                               description="pH sensitivity, regeneration, competing ions limitations",
                               order=4),
                OutlineSection(id="s05", title="Field Applications and Deployment",
                               description="Real-world water treatment applications pilot deployment",
                               order=5),
            ],
        )

        result = _assign_evidence_to_outline(outline, meta)

        # CRITICAL: Evidence should NOT all be in section 1
        section_counts = {s.id: len(s.evidence_ids) for s in result.sections}
        non_empty_sections = sum(1 for c in section_counts.values() if c > 0)

        assert non_empty_sections >= 3, (
            f"Only {non_empty_sections} sections got evidence — Jaccard matching failed. "
            f"Distribution: {section_counts}"
        )

        # No section should have ALL the evidence
        max_section_ev = max(section_counts.values())
        assert max_section_ev < 15, (
            f"One section got {max_section_ev}/15 evidence — distribution failed. "
            f"Distribution: {section_counts}"
        )

    def test_empty_evidence_handled(self):
        from src.polaris_graph.nodes.outline import _assign_evidence_to_outline

        outline = LiveOutline(
            title="Test",
            sections=[OutlineSection(id="s01", title="Test", order=1)],
        )
        result = _assign_evidence_to_outline(outline, {})
        assert result.sections[0].evidence_ids == []

    def test_single_section_gets_everything(self):
        from src.polaris_graph.nodes.outline import _assign_evidence_to_outline

        store = _make_realistic_evidence_store(5)
        meta = _make_evidence_meta(store)

        outline = LiveOutline(
            title="Test",
            sections=[OutlineSection(id="s01", title="Everything About Biochar", order=1)],
        )
        result = _assign_evidence_to_outline(outline, meta)
        assert len(result.sections[0].evidence_ids) == 5


# ---------------------------------------------------------------------------
# Test 2: Structural sections injected
# ---------------------------------------------------------------------------

class TestStructuralSections:
    """Validates that Key Findings, Contradictions, Conclusions are added."""

    def test_structural_sections_added(self):
        from src.polaris_graph.nodes.outline import _ensure_structural_sections

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="Introduction", order=1),
                OutlineSection(id="s02", title="Results", order=2),
            ],
        )
        result = _ensure_structural_sections(outline, "test query")

        titles = [s.title.lower() for s in result.sections]
        assert any("key findings" in t for t in titles), f"Missing Key Findings. Titles: {titles}"
        assert any("contradictions" in t or "limitations" in t for t in titles), f"Missing Contradictions. Titles: {titles}"
        assert any("conclusions" in t for t in titles), f"Missing Conclusions. Titles: {titles}"

    def test_no_duplicate_structural_sections(self):
        from src.polaris_graph.nodes.outline import _ensure_structural_sections

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="Key Findings and Analysis", order=1),
                OutlineSection(id="s02", title="Conclusions", order=2),
            ],
        )
        result = _ensure_structural_sections(outline, "test")

        # Should not add duplicate Key Findings or Conclusions
        key_findings_count = sum(1 for s in result.sections if "key findings" in s.title.lower())
        conclusions_count = sum(1 for s in result.sections if "conclusions" in s.title.lower())
        assert key_findings_count == 1, f"Duplicate Key Findings: {key_findings_count}"
        assert conclusions_count == 1, f"Duplicate Conclusions: {conclusions_count}"

    def test_min_sections_enforced(self):
        from src.polaris_graph.nodes.outline import _enforce_min_sections

        sub_questions = [
            SubQuestion(id=f"sq_{i:02d}", question=f"Question {i}")
            for i in range(1, 9)
        ]

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="Only Section", sub_question_id="sq_01", order=1),
            ],
        )
        result = _enforce_min_sections(outline, sub_questions)
        assert len(result.sections) >= 6, f"Only {len(result.sections)} sections, expected >= 6"


# ---------------------------------------------------------------------------
# Test 3: Full synthesis → assembly pipeline
# ---------------------------------------------------------------------------

class TestSynthesisAssemblyPipeline:
    """Validates that synthesis output feeds correctly into assembly."""

    @pytest.mark.asyncio
    async def test_synthesis_output_assembles_correctly(self):
        from src.polaris_graph.nodes.synthesize import run_synthesis_phase
        from src.polaris_graph.nodes.assemble import run_assemble_phase

        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=MagicMock(
            content=(
                "Biochar demonstrates exceptional heavy metal removal capacity through "
                "ion exchange and surface complexation [CITE:ev_001]. Studies show 95% "
                "removal efficiency for lead under controlled conditions [CITE:ev_002]. "
                "Cost analysis reveals biochar is 67% cheaper than activated carbon [CITE:ev_003]. "
                "However, performance degrades below pH 3.0 [CITE:ev_004]. Field deployment "
                "achieved 89% contaminant reduction in rural systems [CITE:ev_005]. "
                "Additional research confirms the viability of agricultural waste feedstocks [CITE:ev_006]. "
                "The evidence strongly supports large-scale adoption with appropriate safeguards."
            ),
            reasoning_content="",
        ))
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            passed=True, feedback="", score=0.9,
        ))
        mock_client.model = "mock/test"

        store = _make_realistic_evidence_store(10)

        outline = LiveOutline(
            title="Biochar Report",
            sections=[
                OutlineSection(id="s01", title="Mechanisms", evidence_ids=["ev_001", "ev_002", "ev_003"],
                               target_words=600, order=1),
                OutlineSection(id="s02", title="Effectiveness", evidence_ids=["ev_004", "ev_005", "ev_006"],
                               target_words=600, order=2),
            ],
        )

        # Phase 4: Synthesize
        synth_result = await run_synthesis_phase(
            client=mock_client,
            outline=outline,
            evidence_store=store,
            query="biochar heavy metal removal",
        )

        sections = synth_result["sections"]
        assert len(sections) == 2, f"Expected 2 sections, got {len(sections)}"

        # Phase 5: Assemble
        assembly_result = await run_assemble_phase(
            sections=sections,
            evidence_store=store,
            query="biochar heavy metal removal",
            vector_id="V3_INTEGRATION_001",
            expected_sections=2,
        )

        report = assembly_result["final_report"]
        bibliography = assembly_result["bibliography"]
        metrics = assembly_result["quality_metrics"]

        # CRITICAL assertions
        assert len(report) > 500, f"Report too short: {len(report)} chars"
        assert len(bibliography) > 0, "Empty bibliography"
        assert metrics["citation_count"] > 0, "No citations resolved"
        assert metrics["word_count"] > 100, f"Only {metrics['word_count']} words"
        assert "## Table of Contents" in report, "Missing Table of Contents"
        assert "[1]" in report, "Citations not resolved to [N] format"
        assert "## References" in report, "Missing References section"
        assert metrics.get("has_toc") is True, "TOC metric not set"

    @pytest.mark.asyncio
    async def test_empty_sections_handled(self):
        """Pipeline should handle case where synthesis produces zero sections."""
        from src.polaris_graph.nodes.assemble import run_assemble_phase

        result = await run_assemble_phase(
            sections=[],
            evidence_store={},
            query="test",
            vector_id="V3_EMPTY",
            expected_sections=3,
        )

        assert result["status"] in ("failed", "partial"), f"Expected failed/partial, got {result['status']}"
        assert result["quality_metrics"]["word_count"] >= 0


# ---------------------------------------------------------------------------
# Test 4: Table of Contents generation
# ---------------------------------------------------------------------------

class TestTableOfContents:
    def test_toc_generated(self):
        from src.polaris_graph.nodes.assemble import _generate_table_of_contents

        sections = [
            VerifiedSectionDraft(section_id="s01", title="Introduction", content="...", word_count=100),
            VerifiedSectionDraft(section_id="s02", title="Key Findings", content="...", word_count=200),
            VerifiedSectionDraft(section_id="s03", title="Conclusions", content="...", word_count=150),
        ]

        toc = _generate_table_of_contents(sections)
        assert "Introduction" in toc
        assert "Key Findings" in toc
        assert "Conclusions" in toc
        assert "References" in toc
        # Should be numbered
        assert "1." in toc
        assert "2." in toc

    def test_empty_toc(self):
        from src.polaris_graph.nodes.assemble import _generate_table_of_contents
        assert _generate_table_of_contents([]) == ""


# ---------------------------------------------------------------------------
# Test 5: Analysis toolkit functions
# ---------------------------------------------------------------------------

class TestAnalysisToolkit:
    """Validates that Python analysis tools produce real output."""

    def test_statistical_summary(self):
        from src.polaris_graph.tools.analysis_toolkit import statistical_summary

        data_points = [
            {"label": "removal_efficiency", "value": "95.2", "unit": "%",
             "source_url": "https://study1.com", "year": "2024", "evidence_id": "ev_001"},
            {"label": "removal_efficiency", "value": "87.6", "unit": "%",
             "source_url": "https://study2.com", "year": "2023", "evidence_id": "ev_002"},
            {"label": "removal_efficiency", "value": "91.3", "unit": "%",
             "source_url": "https://study3.com", "year": "2024", "evidence_id": "ev_003"},
            {"label": "removal_efficiency", "value": "78.0", "unit": "%",
             "source_url": "https://study4.com", "year": "2022", "evidence_id": "ev_004"},
        ]

        result = statistical_summary(data_points)

        assert "statistics" in result
        stats = result["statistics"]
        assert stats["n"] == 4
        assert 80 < stats["mean"] < 95, f"Mean {stats['mean']} out of range"
        assert stats["std"] > 0, "Std should be positive"
        assert stats["ci_95_lower"] < stats["mean"]
        assert stats["ci_95_upper"] > stats["mean"]
        assert result.get("markdown_table"), "No markdown table generated"
        assert "|" in result["markdown_table"], "Table should have pipe chars"

    def test_comparison_table(self):
        from src.polaris_graph.tools.analysis_toolkit import build_comparison_table

        data_points = [
            {"source_url": "study1", "label": "Pb removal", "value": "95%"},
            {"source_url": "study1", "label": "Cd removal", "value": "87%"},
            {"source_url": "study2", "label": "Pb removal", "value": "91%"},
            {"source_url": "study2", "label": "Cd removal", "value": "82%"},
        ]

        table = build_comparison_table(data_points)
        assert "|" in table, "Table should have pipe chars"
        assert "study1" in table or "Study" in table
        assert "Pb removal" in table or "Pb" in table

    def test_agreement_score(self):
        from src.polaris_graph.tools.analysis_toolkit import compute_agreement_score

        similar = [
            "Biochar removes heavy metals through ion exchange",
            "Heavy metal removal by biochar involves ion exchange mechanisms",
            "Ion exchange is the primary mechanism for biochar heavy metal adsorption",
        ]
        result = compute_agreement_score(similar)
        assert result["agreement_score"] > 0.1, "Similar statements should show some agreement"
        assert result["consensus_strength"] in ("strong", "moderate", "weak", "no consensus")

    def test_meta_analysis(self):
        from src.polaris_graph.tools.analysis_toolkit import generate_meta_analysis_summary

        data_points = [
            {"label": "efficiency", "value": "95", "source_url": "study_a", "evidence_id": "ev_001"},
            {"label": "efficiency", "value": "87", "source_url": "study_b", "evidence_id": "ev_002"},
            {"label": "efficiency", "value": "91", "source_url": "study_c", "evidence_id": "ev_003"},
        ]

        result = generate_meta_analysis_summary(data_points)
        assert len(result) > 50, "Meta-analysis should produce substantial output"
        assert "pooled" in result.lower() or "weighted" in result.lower() or "|" in result


# ---------------------------------------------------------------------------
# Test 6: Code executor sandbox
# ---------------------------------------------------------------------------

class TestCodeExecutor:
    def test_validate_safe_script(self):
        from src.polaris_graph.tools.code_executor import validate_script

        safe_script = """
import json, sys, numpy as np
data = json.load(sys.stdin)
values = [float(d['value']) for d in data['points']]
result = {"mean": float(np.mean(values)), "std": float(np.std(values))}
print(json.dumps(result))
"""
        is_safe, reason = validate_script(safe_script)
        assert is_safe, f"Safe script rejected: {reason}"

    def test_validate_dangerous_script(self):
        from src.polaris_graph.tools.code_executor import validate_script

        # Network access
        is_safe, _ = validate_script("import requests; requests.get('http://evil.com')")
        assert not is_safe, "Should block requests import"

        # File system access
        is_safe, _ = validate_script("import shutil; shutil.rmtree('/')")
        assert not is_safe, "Should block shutil import"

        # Subprocess
        is_safe, _ = validate_script("import subprocess; subprocess.run(['rm', '-rf', '/'])")
        assert not is_safe, "Should block subprocess import"

    @pytest.mark.asyncio
    async def test_execute_simple_script(self):
        from src.polaris_graph.tools.code_executor import execute_analysis_script

        script = """
import json, sys
data = json.load(sys.stdin)
values = [float(v) for v in data['values']]
mean = sum(values) / len(values)
print(json.dumps({"mean": mean, "count": len(values)}))
"""
        result = await execute_analysis_script(
            script=script,
            input_data={"values": [10, 20, 30, 40, 50]},
            timeout=15,
        )

        assert result["success"], f"Script failed: {result.get('error')} stderr: {result.get('stderr')}"
        assert result["result"]["mean"] == 30.0
        assert result["result"]["count"] == 5

    @pytest.mark.asyncio
    async def test_timeout_enforced(self):
        from src.polaris_graph.tools.code_executor import execute_analysis_script

        script = """
import time
time.sleep(60)
print('{"done": true}')
"""
        result = await execute_analysis_script(
            script=script,
            input_data={},
            timeout=2,
        )

        assert not result["success"], "Should have timed out"
        assert "timeout" in (result.get("error") or "").lower() or result.get("execution_time_seconds", 0) >= 1.5

    @pytest.mark.asyncio
    async def test_matplotlib_chart_capture(self):
        from src.polaris_graph.tools.code_executor import execute_analysis_script

        script = """
import json, sys, base64, io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

data = json.load(sys.stdin)
values = data['values']
plt.figure(figsize=(8, 5))
plt.bar(range(len(values)), values)
plt.title('Test Chart')

buf = io.BytesIO()
plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
buf.seek(0)
chart_b64 = base64.b64encode(buf.read()).decode('utf-8')
plt.close()

print(json.dumps({
    "summary": "Bar chart of values",
    "charts": [{"title": "Test Chart", "image_base64": chart_b64}]
}))
"""
        result = await execute_analysis_script(
            script=script,
            input_data={"values": [10, 25, 15, 30, 20]},
            timeout=30,
        )

        assert result["success"], f"Chart script failed: {result.get('error')}"
        charts = result.get("charts", [])
        assert len(charts) >= 1, "Should produce at least 1 chart"
        assert len(charts[0].get("image_base64", "")) > 100, "Chart base64 too short"


# ---------------------------------------------------------------------------
# Test 7: Outline → Section evidence integrity
# ---------------------------------------------------------------------------

class TestOutlineSectionEvidence:
    """Evidence assigned in outline must flow correctly to synthesis."""

    @pytest.mark.asyncio
    async def test_outline_evidence_reaches_writer(self):
        """Sections with assigned evidence should have it available during write."""
        from src.polaris_graph.nodes.outline import (
            _assign_evidence_to_outline,
            _ensure_structural_sections,
        )
        from src.polaris_graph.nodes.synthesize import write_verified_section

        store = _make_realistic_evidence_store(10)
        meta = _make_evidence_meta(store)

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="Adsorption Mechanisms",
                               description="Ion exchange surface complexation", order=1),
                OutlineSection(id="s02", title="Removal Efficiency",
                               description="Lead cadmium chromium removal rates", order=2),
            ],
        )

        # Assign evidence
        outline = _assign_evidence_to_outline(outline, meta)

        # Both sections should have evidence
        for section in outline.sections:
            assert len(section.evidence_ids) > 0, (
                f"Section '{section.title}' got 0 evidence — assignment broken"
            )
            # Verify evidence IDs exist in store
            for eid in section.evidence_ids:
                assert eid in store, f"Evidence {eid} not in store"


# ---------------------------------------------------------------------------
# Test 8: Quality metrics completeness
# ---------------------------------------------------------------------------

class TestQualityMetrics:
    def test_metrics_include_all_fields(self):
        from src.polaris_graph.nodes.assemble import _compute_quality_metrics

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="Test",
                content="Analysis [1] shows results [2] with data [3].",
                claims_verified=5, claims_total=8,
                faithfulness_score=0.75, critic_passed=True,
                word_count=50,
            ),
        ]
        bibliography = [{"citation_number": 1}, {"citation_number": 2}, {"citation_number": 3}]
        report = "Analysis [1] shows results [2] with data [3]. Compared to alternatives, however this is better."

        metrics = _compute_quality_metrics(sections, bibliography, report)

        required_fields = [
            "word_count", "citation_count", "unique_sources",
            "citation_density_per_100w", "faithfulness_pct",
            "sections_total", "sections_critic_passed",
            "comparison_markers", "table_blocks",
            "chart_count", "nli_claims_verified", "nli_claims_total", "has_toc",
        ]
        for field in required_fields:
            assert field in metrics, f"Missing metric: {field}"


# ===========================================================================
# GAP CLOSURE TESTS — 5 capabilities that close the Claude Code gap
# ===========================================================================

# ---------------------------------------------------------------------------
# GAP-1: Dynamic package installation
# ---------------------------------------------------------------------------

class TestPackageInstaller:
    """Validates whitelist-based package installation."""

    def test_approved_packages_exist(self):
        from src.polaris_graph.tools.package_installer import get_approved_packages
        packages = get_approved_packages()
        assert len(packages) >= 10, f"Only {len(packages)} approved packages"
        assert "pdfplumber" in packages
        assert "networkx" in packages
        assert "scikit-learn" in packages

    def test_whitelist_rejects_dangerous(self):
        from src.polaris_graph.tools.package_installer import is_approved
        assert not is_approved("requests"), "requests should be blocked"
        assert not is_approved("flask"), "flask should be blocked"
        assert not is_approved("django"), "django should be blocked"

    def test_whitelist_approves_scientific(self):
        from src.polaris_graph.tools.package_installer import is_approved
        assert is_approved("pdfplumber"), "pdfplumber should be approved"
        assert is_approved("networkx"), "networkx should be approved"
        assert is_approved("seaborn"), "seaborn should be approved"
        assert is_approved("statsmodels"), "statsmodels should be approved"

    def test_safe_install_rejects_unapproved(self):
        from src.polaris_graph.tools.package_installer import safe_install
        result = safe_install(["requests", "flask"])
        assert len(result["rejected"]) == 2
        assert len(result["installed"]) == 0


# ---------------------------------------------------------------------------
# GAP-2: PDF table extraction
# ---------------------------------------------------------------------------

class TestPdfTableExtractor:
    """Validates PDF table extraction pipeline."""

    def test_extract_from_nonexistent_file(self):
        from src.polaris_graph.tools.pdf_table_extractor import extract_tables_from_pdf
        tables = extract_tables_from_pdf("/nonexistent/path.pdf")
        assert tables == [], "Should return empty list for missing file"

    def test_tables_to_structured_data(self):
        from src.polaris_graph.tools.pdf_table_extractor import tables_to_structured_data
        tables = [{
            "page": 1, "table_index": 0,
            "headers": ["Study", "Removal %", "pH"],
            "rows": [
                ["Smith 2024", "95.2", "5.0"],
                ["Jones 2023", "87.6", "6.0"],
            ],
            "markdown": "| Study | Removal % | pH |\n|---|---|---|\n| Smith 2024 | 95.2 | 5.0 |",
            "row_count": 2, "col_count": 3,
        }]
        data_points = tables_to_structured_data(tables)
        assert len(data_points) >= 2, f"Expected >= 2 data points, got {len(data_points)}"
        # Should extract numeric values
        values = [dp["value"] for dp in data_points]
        assert any("95" in v for v in values), "Should extract 95.2"


# ---------------------------------------------------------------------------
# GAP-4: Sandbox file I/O
# ---------------------------------------------------------------------------

class TestSandboxFileIO:
    """Validates controlled file system access in sandbox."""

    def test_sandbox_paths_exist(self):
        from src.polaris_graph.tools.code_executor import get_sandbox_paths
        paths = get_sandbox_paths()
        assert "read_dir" in paths
        assert "write_dir" in paths
        assert os.path.isabs(paths["read_dir"]), "read_dir should be absolute"
        assert os.path.isabs(paths["write_dir"]), "write_dir should be absolute"

    @pytest.mark.asyncio
    async def test_script_can_access_sandbox_dirs(self):
        """Scripts should see SANDBOX_READ_DIR and SANDBOX_WRITE_DIR env vars."""
        from src.polaris_graph.tools.code_executor import execute_analysis_script

        script = """
import json, sys, os
result = {
    "read_dir": os.environ.get("SANDBOX_READ_DIR", "NOT_SET"),
    "write_dir": os.environ.get("SANDBOX_WRITE_DIR", "NOT_SET"),
    "read_exists": os.path.isdir(os.environ.get("SANDBOX_READ_DIR", "")),
}
print(json.dumps(result))
"""
        result = await execute_analysis_script(script=script, input_data={}, timeout=10)
        assert result["success"], f"Script failed: {result.get('error')}"
        assert result["result"]["read_dir"] != "NOT_SET", "SANDBOX_READ_DIR not passed to sandbox"
        assert result["result"]["write_dir"] != "NOT_SET", "SANDBOX_WRITE_DIR not passed to sandbox"


# ---------------------------------------------------------------------------
# GAP-5: SQLite evidence database
# ---------------------------------------------------------------------------

class TestEvidenceDatabase:
    """Validates SQLite analytical queries on evidence."""

    def test_load_and_query(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        store = _make_realistic_evidence_store(15)
        db = EvidenceDatabase()
        loaded = db.load_evidence(store)

        assert loaded == 15, f"Expected 15, loaded {loaded}"

        # Tier distribution query
        result = db.query(
            "SELECT quality_tier, COUNT(*) as n FROM evidence "
            "GROUP BY quality_tier ORDER BY n DESC"
        )
        assert result["success"], f"Query failed: {result['error']}"
        assert result["row_count"] >= 1, "Should have at least 1 tier"
        assert "|" in result["markdown_table"], "Should produce markdown"

        db.close()

    def test_source_summary_view(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        store = _make_realistic_evidence_store(15)
        db = EvidenceDatabase()
        db.load_evidence(store)

        result = db.query(
            "SELECT source_title, evidence_count, ROUND(avg_relevance, 2) "
            "FROM source_summary ORDER BY evidence_count DESC"
        )
        assert result["success"]
        assert result["row_count"] >= 3, "Should have multiple sources"

        db.close()

    def test_blocks_dangerous_queries(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        db = EvidenceDatabase()
        db.load_evidence(_make_realistic_evidence_store(5))

        result = db.query("DROP TABLE evidence")
        assert not result["success"], "Should block DROP"

        result = db.query("DELETE FROM evidence WHERE 1=1")
        assert not result["success"], "Should block DELETE"

        result = db.query("INSERT INTO evidence (evidence_id) VALUES ('hack')")
        assert not result["success"], "Should block INSERT"

        db.close()

    def test_schema_for_llm(self):
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        db = EvidenceDatabase()
        schema = db.get_schema()
        assert "evidence" in schema
        assert "structured_data" in schema
        assert "source_summary" in schema
        assert "SELECT" in schema
        db.close()

    def test_structured_data_queries(self):
        """Test queries on numeric structured data from evidence."""
        from src.polaris_graph.tools.evidence_database import EvidenceDatabase

        store = _make_realistic_evidence_store(15)
        db = EvidenceDatabase()
        db.load_evidence(store)

        result = db.query(
            "SELECT label, COUNT(*) as n, AVG(value) as mean "
            "FROM structured_data GROUP BY label ORDER BY n DESC"
        )
        assert result["success"], f"Structured data query failed: {result['error']}"
        # Should have data points from evidence with structured_data
        assert result["row_count"] >= 1, "Should have structured data"

        db.close()
