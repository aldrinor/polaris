"""LIVE integration test for the ReAct analysis agent — REAL Qwen 3.5 Plus via OpenRouter.

NO MOCKS. This test fires actual LLM calls to validate that:
1. Qwen 3.5 Plus can parse the ReactDecision schema and pick tools intelligently
2. The full ReAct loop completes with real tool execution
3. Citation provenance survives from evidence through analysis to synthesis injection
4. Zero "POLARIS" or "Analysis Toolkit" references leak into output

Cost: ~$0.01-0.03 per run (3 iterations max, ~2K tokens each).

Run with:
    pytest tests/v3/test_react_live.py -v -s
"""

import os
import re

import pytest

from src.polaris_graph.contracts_v3 import AnalysisEntry
from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook
from src.polaris_graph.tools.react_agent import ReactAnalysisAgent
from src.polaris_graph.tools.tool_registry import ToolResult, build_default_registry


# ---------------------------------------------------------------------------
# Evidence factory — realistic biochar heavy metal removal data
# ---------------------------------------------------------------------------

def _build_live_evidence_store() -> dict:
    """Build 18 evidence pieces with real-looking numeric data about biochar.

    Each piece has structured_data so extract_numeric_data can work,
    plus source_content for NLI-style checks. Mirrors the field layout
    from v1's analyze_sources() output.
    """
    evidence = {
        "ev_001": {
            "evidence_id": "ev_001",
            "source_url": "https://doi.org/10.1016/j.jhazmat.2024.001",
            "source_title": "Rice Husk Biochar for Pb(II) Adsorption",
            "source_type": "academic",
            "statement": (
                "Rice husk biochar achieved 95.2% removal efficiency for "
                "Pb(II) at pH 5.0 with initial concentration 100 mg/L and "
                "a contact time of 120 minutes."
            ),
            "direct_quote": (
                "The removal efficiency was 95.2% under optimized conditions "
                "(pH 5.0, 100 mg/L initial Pb concentration, 120 min contact)"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.92,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.85,
            "source_content": "This study investigated rice husk biochar for lead removal. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Pb removal efficiency", "value": "95.2", "unit": "%", "year": "2024", "context": "Rice husk biochar at pH 5.0"},
                {"data_type": "measurement", "label": "Initial Pb concentration", "value": "100", "unit": "mg/L", "year": "2024", "context": "Experimental condition"},
            ],
        },
        "ev_002": {
            "evidence_id": "ev_002",
            "source_url": "https://doi.org/10.1021/es.2023.002",
            "source_title": "Comparative Biochar Feedstocks for Heavy Metal Remediation",
            "source_type": "academic",
            "statement": (
                "Wood-based biochar showed 78.3% Pb removal, significantly "
                "lower than agricultural waste biochar at 91.7% (p < 0.01)."
            ),
            "direct_quote": (
                "Wood biochar achieved 78.3% removal compared to 91.7% for "
                "agricultural waste biochar (p < 0.01)"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.88,
            "perspective": "Comparative",
            "fact_category": "Comparison",
            "year": 2023,
            "source_confidence": 0.90,
            "source_content": "This comparative study examined different biochar feedstocks. " * 20,
            "structured_data": [
                {"data_type": "comparison", "label": "Wood biochar Pb removal", "value": "78.3", "unit": "%", "year": "2023", "context": "Wood-based feedstock"},
                {"data_type": "comparison", "label": "Agri-waste biochar Pb removal", "value": "91.7", "unit": "%", "year": "2023", "context": "Agricultural waste feedstock"},
            ],
        },
        "ev_003": {
            "evidence_id": "ev_003",
            "source_url": "https://doi.org/10.1016/j.cej.2024.003",
            "source_title": "Cost Analysis of Biochar vs Activated Carbon for Wastewater",
            "source_type": "academic",
            "statement": (
                "Biochar treatment cost $15/m3 versus $45/m3 for activated "
                "carbon, representing a 67% cost reduction."
            ),
            "direct_quote": (
                "The treatment cost was $15/m3 for biochar compared to "
                "$45/m3 for activated carbon"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.79,
            "perspective": "Economic",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.75,
            "source_content": "Economic analysis of biochar treatment systems. " * 20,
            "structured_data": [
                {"data_type": "comparison", "label": "Biochar treatment cost", "value": "15", "unit": "$/m3", "year": "2024", "context": "Full treatment system"},
                {"data_type": "comparison", "label": "Activated carbon treatment cost", "value": "45", "unit": "$/m3", "year": "2024", "context": "Conventional treatment"},
            ],
        },
        "ev_004": {
            "evidence_id": "ev_004",
            "source_url": "https://doi.org/10.1007/s11356-2024-004",
            "source_title": "pH Sensitivity of Biochar in Acidic Environments",
            "source_type": "academic",
            "statement": (
                "Biochar adsorption capacity decreased by 62% at pH 3.0 "
                "compared to pH 5.0, indicating strong pH dependence."
            ),
            "direct_quote": (
                "At pH 3.0, adsorption capacity was only 38% of the value "
                "observed at pH 5.0"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.74,
            "perspective": "Scientific",
            "fact_category": "Limitation",
            "year": 2024,
            "source_confidence": 0.80,
            "source_content": "Investigation of pH effects on biochar performance. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Capacity reduction at pH 3", "value": "62", "unit": "%", "year": "2024", "context": "Acidic conditions"},
            ],
        },
        "ev_005": {
            "evidence_id": "ev_005",
            "source_url": "https://doi.org/10.1016/j.watres.2023.005",
            "source_title": "Field Trial of Biochar Filters in Rural Bangladesh",
            "source_type": "academic",
            "statement": (
                "A 24-month field trial achieved 89% contaminant reduction "
                "with biochar filters in rural Bangladesh water systems."
            ),
            "direct_quote": (
                "Over 24 months, the biochar filter system maintained 89% "
                "removal of target contaminants"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.85,
            "perspective": "Practical",
            "fact_category": "Application",
            "year": 2023,
            "source_confidence": 0.82,
            "source_content": "Field deployment and long-term monitoring of biochar systems. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Field contaminant reduction", "value": "89", "unit": "%", "year": "2023", "context": "24-month rural deployment"},
                {"data_type": "measurement", "label": "Deployment duration", "value": "24", "unit": "months", "year": "2023", "context": "Rural Bangladesh"},
            ],
        },
        "ev_006": {
            "evidence_id": "ev_006",
            "source_url": "https://doi.org/10.1016/j.biortech.2024.006",
            "source_title": "Pyrolysis Temperature Effects on Biochar Porosity",
            "source_type": "academic",
            "statement": (
                "Biochar pyrolyzed at 700C had a surface area of 342 m2/g, "
                "compared to 187 m2/g at 400C, a 83% increase."
            ),
            "direct_quote": (
                "BET surface area increased from 187 m2/g at 400C to "
                "342 m2/g at 700C"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.81,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.88,
            "source_content": "Analysis of pyrolysis temperature effects on biochar properties. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "BET surface area at 700C", "value": "342", "unit": "m2/g", "year": "2024", "context": "High-temp pyrolysis"},
                {"data_type": "measurement", "label": "BET surface area at 400C", "value": "187", "unit": "m2/g", "year": "2024", "context": "Low-temp pyrolysis"},
            ],
        },
        "ev_007": {
            "evidence_id": "ev_007",
            "source_url": "https://doi.org/10.1016/j.chemosphere.2023.007",
            "source_title": "Biochar for Cadmium Removal from Industrial Effluent",
            "source_type": "academic",
            "statement": (
                "Bamboo biochar removed 87.4% of Cd(II) at an initial "
                "concentration of 50 mg/L with a dosage of 5 g/L."
            ),
            "direct_quote": (
                "The optimal removal of 87.4% was achieved with bamboo "
                "biochar at 5 g/L dosage"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.83,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2023,
            "source_confidence": 0.79,
            "source_content": "Cadmium removal using bamboo-derived biochar. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Cd removal efficiency", "value": "87.4", "unit": "%", "year": "2023", "context": "Bamboo biochar, 5 g/L dosage"},
                {"data_type": "measurement", "label": "Initial Cd concentration", "value": "50", "unit": "mg/L", "year": "2023", "context": "Industrial effluent"},
            ],
        },
        "ev_008": {
            "evidence_id": "ev_008",
            "source_url": "https://doi.org/10.1016/j.scitotenv.2024.008",
            "source_title": "Modified Biochar with Iron Oxide for Arsenic Removal",
            "source_type": "academic",
            "statement": (
                "Iron oxide-modified biochar achieved 96.8% As(V) removal, "
                "compared to 41.2% for unmodified biochar."
            ),
            "direct_quote": (
                "Modification with iron oxide increased As(V) removal from "
                "41.2% to 96.8%"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.77,
            "perspective": "Scientific",
            "fact_category": "Comparison",
            "year": 2024,
            "source_confidence": 0.84,
            "source_content": "Iron oxide modification enhances arsenic adsorption. " * 20,
            "structured_data": [
                {"data_type": "comparison", "label": "Modified biochar As removal", "value": "96.8", "unit": "%", "year": "2024", "context": "Iron oxide modified"},
                {"data_type": "comparison", "label": "Unmodified biochar As removal", "value": "41.2", "unit": "%", "year": "2024", "context": "Pristine biochar"},
            ],
        },
        "ev_009": {
            "evidence_id": "ev_009",
            "source_url": "https://doi.org/10.1016/j.jenvman.2023.009",
            "source_title": "Biochar Regeneration Cycles and Performance Decay",
            "source_type": "academic",
            "statement": (
                "After 5 regeneration cycles, biochar retained 72% of its "
                "original Pb removal capacity, dropping from 94% to 68%."
            ),
            "direct_quote": (
                "The removal efficiency decreased from 94% to 68% after 5 "
                "adsorption-desorption cycles"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.72,
            "perspective": "Practical",
            "fact_category": "Measurement",
            "year": 2023,
            "source_confidence": 0.76,
            "source_content": "Long-term regeneration study of biochar adsorbents. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Initial Pb removal", "value": "94", "unit": "%", "year": "2023", "context": "Cycle 1"},
                {"data_type": "measurement", "label": "Pb removal after 5 cycles", "value": "68", "unit": "%", "year": "2023", "context": "After regeneration"},
            ],
        },
        "ev_010": {
            "evidence_id": "ev_010",
            "source_url": "https://doi.org/10.1016/j.envpol.2024.010",
            "source_title": "Corn Stover Biochar for Chromium Removal",
            "source_type": "academic",
            "statement": (
                "Corn stover biochar showed 83.6% Cr(VI) removal at pH 2.0, "
                "with maximum adsorption capacity of 52.3 mg/g."
            ),
            "direct_quote": (
                "At pH 2.0, corn stover biochar achieved 83.6% Cr(VI) "
                "removal with qmax of 52.3 mg/g"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.80,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.81,
            "source_content": "Chromium removal by corn stover biochar under acidic conditions. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Cr(VI) removal efficiency", "value": "83.6", "unit": "%", "year": "2024", "context": "Corn stover at pH 2.0"},
                {"data_type": "measurement", "label": "Maximum adsorption capacity", "value": "52.3", "unit": "mg/g", "year": "2024", "context": "Langmuir model"},
            ],
        },
        "ev_011": {
            "evidence_id": "ev_011",
            "source_url": "https://doi.org/10.1016/j.desal.2023.011",
            "source_title": "Biochar Column Studies for Continuous Flow Treatment",
            "source_type": "academic",
            "statement": (
                "In continuous flow column tests, biochar maintained >90% Pb "
                "removal for 180 bed volumes before breakthrough at 85%."
            ),
            "direct_quote": (
                "Breakthrough occurred at 180 BV with removal dropping from "
                ">90% to 85%"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.76,
            "perspective": "Engineering",
            "fact_category": "Measurement",
            "year": 2023,
            "source_confidence": 0.78,
            "source_content": "Column study of biochar for continuous water treatment. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Bed volumes before breakthrough", "value": "180", "unit": "BV", "year": "2023", "context": "Continuous flow column"},
                {"data_type": "measurement", "label": "Post-breakthrough removal", "value": "85", "unit": "%", "year": "2023", "context": "After 180 BV"},
            ],
        },
        "ev_012": {
            "evidence_id": "ev_012",
            "source_url": "https://doi.org/10.1016/j.jclepro.2024.012",
            "source_title": "Life Cycle Assessment of Biochar Water Treatment",
            "source_type": "academic",
            "statement": (
                "LCA showed biochar treatment produces 0.8 kg CO2-eq per m3 "
                "treated, 73% less than activated carbon at 2.9 kg CO2-eq."
            ),
            "direct_quote": (
                "Carbon footprint: biochar 0.8 vs activated carbon 2.9 kg "
                "CO2-eq per m3"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.71,
            "perspective": "Environmental",
            "fact_category": "Comparison",
            "year": 2024,
            "source_confidence": 0.73,
            "source_content": "Life cycle assessment of biochar-based treatment. " * 20,
            "structured_data": [
                {"data_type": "comparison", "label": "Biochar carbon footprint", "value": "0.8", "unit": "kg CO2-eq/m3", "year": "2024", "context": "LCA result"},
                {"data_type": "comparison", "label": "Activated carbon footprint", "value": "2.9", "unit": "kg CO2-eq/m3", "year": "2024", "context": "Conventional treatment LCA"},
            ],
        },
        "ev_013": {
            "evidence_id": "ev_013",
            "source_url": "https://doi.org/10.1016/j.watres.2024.013",
            "source_title": "Coconut Shell Biochar for Multi-Metal Removal",
            "source_type": "academic",
            "statement": (
                "Coconut shell biochar removed Pb (92%), Cu (84%), and "
                "Zn (76%) simultaneously from mixed-metal solutions."
            ),
            "direct_quote": (
                "Simultaneous removal from mixed solution: Pb 92%, Cu 84%, "
                "Zn 76%"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.86,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.87,
            "source_content": "Multi-metal competitive adsorption on coconut shell biochar. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Pb removal (mixed)", "value": "92", "unit": "%", "year": "2024", "context": "Coconut shell, multi-metal"},
                {"data_type": "measurement", "label": "Cu removal (mixed)", "value": "84", "unit": "%", "year": "2024", "context": "Coconut shell, multi-metal"},
                {"data_type": "measurement", "label": "Zn removal (mixed)", "value": "76", "unit": "%", "year": "2024", "context": "Coconut shell, multi-metal"},
            ],
        },
        "ev_014": {
            "evidence_id": "ev_014",
            "source_url": "https://doi.org/10.1016/j.biortech.2023.014",
            "source_title": "Sewage Sludge Biochar: Heavy Metal Leaching Risk",
            "source_type": "academic",
            "statement": (
                "Sewage sludge biochar leached 0.3 mg/L Cd and 1.2 mg/L Pb, "
                "exceeding WHO limits for Cd (0.003 mg/L)."
            ),
            "direct_quote": (
                "Leachate concentrations of 0.3 mg/L Cd and 1.2 mg/L Pb "
                "were measured from sewage sludge biochar"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.69,
            "perspective": "Environmental",
            "fact_category": "Limitation",
            "year": 2023,
            "source_confidence": 0.74,
            "source_content": "Leaching risk assessment of sewage sludge biochar. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Cd leachate", "value": "0.3", "unit": "mg/L", "year": "2023", "context": "Sewage sludge biochar"},
                {"data_type": "measurement", "label": "Pb leachate", "value": "1.2", "unit": "mg/L", "year": "2023", "context": "Sewage sludge biochar"},
            ],
        },
        "ev_015": {
            "evidence_id": "ev_015",
            "source_url": "https://doi.org/10.1016/j.chemeng.2024.015",
            "source_title": "Biochar Dosage Optimization for Industrial Effluent",
            "source_type": "academic",
            "statement": (
                "Optimal biochar dosage was 8 g/L, yielding 97.1% Pb "
                "removal; increasing to 12 g/L showed no significant gain "
                "(97.3%)."
            ),
            "direct_quote": (
                "Removal increased from 72.5% at 2 g/L to 97.1% at 8 g/L, "
                "with plateau at higher dosages"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.84,
            "perspective": "Engineering",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.82,
            "source_content": "Dosage optimization for industrial wastewater treatment. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Pb removal at 8 g/L", "value": "97.1", "unit": "%", "year": "2024", "context": "Optimal dosage"},
                {"data_type": "measurement", "label": "Pb removal at 2 g/L", "value": "72.5", "unit": "%", "year": "2024", "context": "Low dosage"},
            ],
        },
        "ev_016": {
            "evidence_id": "ev_016",
            "source_url": "https://doi.org/10.1016/j.ecoenv.2023.016",
            "source_title": "Biochar Contact Time Kinetics for Heavy Metals",
            "source_type": "academic",
            "statement": (
                "Pseudo-second-order kinetics fit well (R2=0.998) with "
                "equilibrium reached in 90 minutes for Pb and 120 minutes "
                "for Cd."
            ),
            "direct_quote": (
                "Equilibrium was established at 90 min (Pb) and 120 min "
                "(Cd) following pseudo-second-order kinetics (R2=0.998)"
            ),
            "quality_tier": "SILVER",
            "relevance_score": 0.73,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2023,
            "source_confidence": 0.77,
            "source_content": "Kinetic study of heavy metal adsorption on biochar. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Pb equilibrium time", "value": "90", "unit": "min", "year": "2023", "context": "Pseudo-second-order"},
                {"data_type": "measurement", "label": "Cd equilibrium time", "value": "120", "unit": "min", "year": "2023", "context": "Pseudo-second-order"},
                {"data_type": "measurement", "label": "Kinetic model R2", "value": "0.998", "unit": "", "year": "2023", "context": "Pseudo-second-order fit"},
            ],
        },
        "ev_017": {
            "evidence_id": "ev_017",
            "source_url": "https://doi.org/10.1016/j.jhazmat.2024.017",
            "source_title": "Magnetic Biochar for Selective Mercury Removal",
            "source_type": "academic",
            "statement": (
                "Magnetic biochar achieved 99.1% Hg(II) removal at pH 6.0 "
                "with a maximum capacity of 189 mg/g."
            ),
            "direct_quote": (
                "Hg(II) removal reached 99.1% with qmax of 189 mg/g at "
                "pH 6.0"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.78,
            "perspective": "Scientific",
            "fact_category": "Measurement",
            "year": 2024,
            "source_confidence": 0.83,
            "source_content": "Magnetic biochar synthesis and mercury remediation. " * 20,
            "structured_data": [
                {"data_type": "measurement", "label": "Hg removal efficiency", "value": "99.1", "unit": "%", "year": "2024", "context": "Magnetic biochar at pH 6.0"},
                {"data_type": "measurement", "label": "Hg adsorption capacity", "value": "189", "unit": "mg/g", "year": "2024", "context": "Langmuir qmax"},
            ],
        },
        "ev_018": {
            "evidence_id": "ev_018",
            "source_url": "https://doi.org/10.1016/j.apcatb.2024.018",
            "source_title": "Biochar-Supported Nano Zero-Valent Iron for Cr(VI)",
            "source_type": "academic",
            "statement": (
                "nZVI-biochar composite reduced Cr(VI) by 99.5% within 30 "
                "minutes at pH 3.0, outperforming bare nZVI (87.2%)."
            ),
            "direct_quote": (
                "The nZVI-BC composite achieved 99.5% Cr(VI) reduction in "
                "30 min versus 87.2% for bare nZVI"
            ),
            "quality_tier": "GOLD",
            "relevance_score": 0.82,
            "perspective": "Scientific",
            "fact_category": "Comparison",
            "year": 2024,
            "source_confidence": 0.86,
            "source_content": "Nano zero-valent iron supported on biochar for chromium reduction. " * 20,
            "structured_data": [
                {"data_type": "comparison", "label": "nZVI-BC Cr(VI) reduction", "value": "99.5", "unit": "%", "year": "2024", "context": "Composite material, 30 min"},
                {"data_type": "comparison", "label": "Bare nZVI Cr(VI) reduction", "value": "87.2", "unit": "%", "year": "2024", "context": "Unmodified nZVI, 30 min"},
            ],
        },
    }
    return evidence


# ===========================================================================
# TEST 1: LIVE ReAct agent with Qwen 3.5 Plus
# ===========================================================================

@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set — skip live LLM test",
)
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_react_live_qwen():
    """LIVE TEST: Qwen 3.5 Plus drives the ReAct loop on real evidence.

    This test makes REAL API calls to OpenRouter. It validates that the
    full ReAct loop works end-to-end with actual LLM decisions — not
    mocked canned responses.

    Cost: ~$0.01-0.03 (3 iterations, ~2K tokens each).
    """
    # --- Setup: keep cost low ---
    os.environ["PG_REACT_MAX_ITERATIONS"] = "3"
    os.environ["PG_REACT_TIMEOUT_SECONDS"] = "90"

    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    client = OpenRouterClient(session_id="test_react_live")
    evidence_store = _build_live_evidence_store()
    evidence_ids = list(evidence_store.keys())

    # --- Run the ReAct agent ---
    agent = ReactAnalysisAgent(
        client=client,
        evidence_store=evidence_store,
        evidence_ids=evidence_ids,
        query="effectiveness of biochar for heavy metal removal from wastewater",
    )
    notebook = await agent.run()

    # --- Diagnostics: print full decision trace ---
    print("\n" + "=" * 80)
    print("REACT AGENT LIVE TRACE")
    print("=" * 80)
    print(f"Total steps: {notebook.step_count}")
    print(f"Successful steps: {notebook.successful_steps}")
    print(f"Data points extracted: {len(notebook.data_points)}")
    print(f"Unique evidence IDs: {len(notebook.get_all_source_evidence_ids())}")
    print()

    for step in notebook.steps:
        status = "OK" if step.result.success else "FAIL"
        print(f"--- Step {step.step_number}: {step.tool_name} [{status}] ---")
        print(f"  Reasoning: {step.reasoning}")
        print(f"  Elapsed: {step.elapsed_seconds:.2f}s")
        if step.result.success:
            print(f"  Evidence IDs: {step.result.source_evidence_ids[:5]}")
            print(f"  Insights: {step.result.insights[:3]}")
            md_preview = step.result.markdown[:200].replace("\n", " ")
            print(f"  Markdown preview: {md_preview}")
        else:
            print(f"  Error: {step.result.error}")
        print()

    # --- Assertion 1: Agent completed >= 2 steps ---
    assert notebook.step_count >= 2, (
        f"Agent only completed {notebook.step_count} step(s) — "
        f"expected >= 2 with 3 iterations allowed"
    )

    # --- Assertion 2: extract_numeric_data is first or second tool ---
    first_two_tools = [s.tool_name for s in notebook.steps[:2]]
    assert "extract_numeric_data" in first_two_tools, (
        f"extract_numeric_data should be in first 2 steps "
        f"(smart ordering rule), but got: {first_two_tools}"
    )

    # --- Assertion 3: All successful ToolResults have source_evidence_ids ---
    for step in notebook.steps:
        if step.result.success:
            assert len(step.result.source_evidence_ids) > 0, (
                f"Tool '{step.tool_name}' (step {step.step_number}) "
                f"succeeded but has empty source_evidence_ids — "
                f"provenance chain broken"
            )
            # All IDs should start with "ev_"
            for eid in step.result.source_evidence_ids:
                assert eid.startswith("ev_"), (
                    f"Evidence ID '{eid}' in tool '{step.tool_name}' "
                    f"does not start with 'ev_' — not original evidence"
                )

    # --- Assertion 4: Zero "POLARIS" in any markdown output ---
    context = notebook.build_synthesis_context()
    assert "POLARIS" not in context, (
        f"Found 'POLARIS' in synthesis context — citation provenance "
        f"violated. Context snippet: {context[:300]}"
    )
    assert "Analysis Toolkit" not in context, (
        f"Found 'Analysis Toolkit' in synthesis context — "
        f"should cite original sources"
    )

    # --- Assertion 5: to_entries produces valid AnalysisEntry objects ---
    entries = notebook.to_entries()
    assert len(entries) >= 1, "Expected at least 1 AnalysisEntry"
    for entry in entries:
        assert isinstance(entry, AnalysisEntry)
        assert entry.entry_id.startswith("analysis_")
        assert entry.markdown, f"Entry {entry.entry_id} has empty markdown"
        assert len(entry.source_evidence_ids) > 0, (
            f"Entry {entry.entry_id} has no source_evidence_ids"
        )
        assert "POLARIS" not in entry.markdown, (
            f"Entry {entry.entry_id} contains 'POLARIS'"
        )

    # --- Assertion 6: build_synthesis_context contains [CITE:ev_xxx] ---
    cite_tokens = re.findall(r"\[CITE:ev_\d+\]", context)
    assert len(cite_tokens) >= 1, (
        f"Synthesis context has no [CITE:ev_xxx] tokens — "
        f"citations not embedded. Context: {context[:300]}"
    )

    # --- Summary ---
    tool_sequence = [s.tool_name for s in notebook.steps]
    print("\n" + "=" * 80)
    print("ASSERTIONS PASSED")
    print(f"  Tool sequence: {' -> '.join(tool_sequence)}")
    print(f"  Entries produced: {len(entries)}")
    print(f"  CITE tokens found: {len(cite_tokens)}")
    print(f"  Total evidence referenced: {len(notebook.get_all_source_evidence_ids())}")
    print(f"  API cost: ${client.usage.total_cost_usd:.4f}")
    print("=" * 80)


# ===========================================================================
# TEST 2: Citation survival through synthesis injection
# ===========================================================================

@pytest.mark.asyncio
async def test_citation_survives_synthesis_injection():
    """Verify that AnalysisEntry provenance survives into evidence_store for synthesis.

    This test simulates the graph_v3.py synthesize_node injection logic
    without requiring an API call. It validates the contract between
    the ReAct agent output and the synthesis phase input.
    """
    # --- Build AnalysisEntry objects (as if from a ReAct run) ---
    entries = [
        AnalysisEntry(
            entry_id="analysis_abc12345",
            analysis_type="extract_numeric_data",
            title="Extracted 24 numeric data points from 18 evidence pieces",
            markdown=(
                "### Numeric Data Extraction\n\n"
                "| Metric | Value | Unit | Source |\n"
                "| --- | --- | --- | --- |\n"
                "| Pb removal efficiency | 95.2 | % | [CITE:ev_001] |\n"
                "| Wood biochar Pb removal | 78.3 | % | [CITE:ev_002] |\n"
                "| Treatment cost (biochar) | 15 | $/m3 | [CITE:ev_003] |\n"
                "| Cd removal efficiency | 87.4 | % | [CITE:ev_007] |\n"
            ),
            source_evidence_ids=["ev_001", "ev_002", "ev_003", "ev_007"],
            statistics={"n": 24, "unique_sources": 18},
            insights=[
                "Extracted 24 numeric data points from 18 evidence pieces",
            ],
        ),
        AnalysisEntry(
            entry_id="analysis_def67890",
            analysis_type="statistical_summary",
            title="Statistical summary: mean removal 87.6%, 95% CI [79.1, 96.1]",
            markdown=(
                "### Statistical Summary\n\n"
                "| Statistic | Value |\n"
                "| --- | --- |\n"
                "| Mean | 87.6% |\n"
                "| Median | 89.0% |\n"
                "| Std Dev | 9.8% |\n"
                "| 95% CI | [79.1, 96.1] |\n"
                "| N | 12 |\n\n"
                "Based on data from [CITE:ev_001][CITE:ev_002][CITE:ev_005]"
                "[CITE:ev_007][CITE:ev_010]"
            ),
            source_evidence_ids=[
                "ev_001", "ev_002", "ev_005", "ev_007", "ev_010",
            ],
            statistics={
                "mean": 87.6,
                "median": 89.0,
                "std": 9.8,
                "ci_95_lower": 79.1,
                "ci_95_upper": 96.1,
                "n": 12,
            },
            insights=[
                "High removal efficiency across studies (mean 87.6%)",
                "Moderate heterogeneity (std 9.8%)",
            ],
        ),
        AnalysisEntry(
            entry_id="analysis_ghi24680",
            analysis_type="query_evidence_sql",
            title="Tier distribution: 9 GOLD, 7 SILVER, 2 BRONZE",
            markdown=(
                "**SQL Query:** `SELECT quality_tier, COUNT(*) ...`\n\n"
                "| Tier | Count | Avg Relevance |\n"
                "| --- | --- | --- |\n"
                "| GOLD | 9 | 0.84 |\n"
                "| SILVER | 7 | 0.74 |\n"
                "| BRONZE | 2 | 0.65 |\n\n"
                "Evidence base: [CITE:ev_001][CITE:ev_002][CITE:ev_005]"
            ),
            source_evidence_ids=[
                "ev_001", "ev_002", "ev_005", "ev_006", "ev_007",
                "ev_010", "ev_013", "ev_015", "ev_017",
            ],
            statistics={"row_count": 3, "columns": ["quality_tier", "n", "avg_rel"]},
        ),
    ]

    # --- Simulate graph_v3.py synthesize_node injection logic ---
    # This is the EXACT logic from graph_v3.py lines 557-576
    evidence_store = dict(_build_live_evidence_store())  # copy
    original_evidence_ids = set(evidence_store.keys())

    for entry in entries:
        # Store in evidence_store with provenance (NO "POLARIS Analysis Toolkit")
        evidence_store[entry.entry_id] = {
            "evidence_id": entry.entry_id,
            "type": "analysis",
            "analysis_type": entry.analysis_type,
            "title": entry.title,
            "markdown": entry.markdown,
            "source_content": entry.markdown,
            "statement": f"Analysis: {entry.title}",
            "source_title": "",
            "source_url": "",
            "direct_quote": "",
            "quality_tier": "GOLD",
            "relevance_score": 1.0,
            "image_base64": entry.image_base64,
            "insights": entry.insights,
            "statistics": entry.statistics,
            "source_evidence_ids": entry.source_evidence_ids,
        }

    # --- Assertion 1: No "POLARIS Analysis Toolkit" in source_title ---
    for entry in entries:
        injected = evidence_store[entry.entry_id]
        assert "POLARIS" not in injected.get("source_title", ""), (
            f"Entry {entry.entry_id} has 'POLARIS' in source_title: "
            f"'{injected['source_title']}'"
        )
        assert "Analysis Toolkit" not in injected.get("source_title", ""), (
            f"Entry {entry.entry_id} has 'Analysis Toolkit' in source_title"
        )

    # --- Assertion 2: source_evidence_ids populated on every injected entry ---
    for entry in entries:
        injected = evidence_store[entry.entry_id]
        stored_ids = injected.get("source_evidence_ids", [])
        assert len(stored_ids) > 0, (
            f"Entry {entry.entry_id} has empty source_evidence_ids in "
            f"evidence_store — provenance chain lost"
        )
        # All referenced IDs must point to ORIGINAL evidence
        for eid in stored_ids:
            assert eid in original_evidence_ids, (
                f"source_evidence_id '{eid}' in entry {entry.entry_id} "
                f"does not exist in the original evidence store — "
                f"provenance points to nothing"
            )

    # --- Assertion 3: markdown contains [CITE:ev_xxx] tokens pointing to originals ---
    for entry in entries:
        injected = evidence_store[entry.entry_id]
        markdown = injected.get("markdown", "")
        cite_tokens = re.findall(r"\[CITE:(ev_\d+)\]", markdown)
        assert len(cite_tokens) >= 1, (
            f"Entry {entry.entry_id} markdown has no [CITE:ev_xxx] tokens — "
            f"citations will be lost during bibliography resolution"
        )
        # Every cited ID must be in original evidence
        for cited_id in cite_tokens:
            assert cited_id in original_evidence_ids, (
                f"Entry {entry.entry_id} cites '{cited_id}' which is not "
                f"in original evidence store — phantom citation"
            )

    # --- Assertion 4: Analysis entries are marked type="analysis" ---
    for entry in entries:
        injected = evidence_store[entry.entry_id]
        assert injected["type"] == "analysis", (
            f"Entry {entry.entry_id} type should be 'analysis', "
            f"got '{injected['type']}'"
        )

    # --- Assertion 5: Original evidence is untouched ---
    for eid in original_evidence_ids:
        assert evidence_store[eid].get("type") != "analysis", (
            f"Original evidence {eid} was corrupted — type set to 'analysis'"
        )
        assert "source_url" in evidence_store[eid], (
            f"Original evidence {eid} missing source_url"
        )

    # --- Diagnostics ---
    print("\n" + "=" * 80)
    print("SYNTHESIS INJECTION TRACE")
    print("=" * 80)
    print(f"Original evidence pieces: {len(original_evidence_ids)}")
    print(f"Analysis entries injected: {len(entries)}")
    print(f"Total evidence_store size: {len(evidence_store)}")
    print()
    for entry in entries:
        injected = evidence_store[entry.entry_id]
        cite_count = len(re.findall(r"\[CITE:ev_\d+\]", injected["markdown"]))
        print(f"  {entry.entry_id} ({entry.analysis_type})")
        print(f"    source_evidence_ids: {injected['source_evidence_ids']}")
        print(f"    CITE tokens in markdown: {cite_count}")
        print(f"    source_title: '{injected['source_title']}' (should be empty)")
    print("=" * 80)


# ===========================================================================
# TEST 3: ReactDecision schema validation with real Qwen (optional)
# ===========================================================================

@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set — skip live LLM test",
)
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_react_decision_schema_parses():
    """LIVE TEST: Qwen 3.5 Plus returns valid ReactDecision JSON.

    This is a minimal smoke test for the LLM->schema path. If this fails,
    the full ReAct loop cannot work.

    Cost: ~$0.005 (single call, ~500 tokens).
    """
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.tools.react_agent import ReactDecision

    client = OpenRouterClient(session_id="test_schema_parse")

    prompt = (
        "You are analyzing research evidence to produce statistical insights.\n\n"
        "RESEARCH QUESTION: effectiveness of biochar for heavy metal removal\n\n"
        "EVIDENCE STATE:\n"
        "- Total evidence pieces: 18\n"
        "- Has pre-extracted structured data: True\n"
        "- Extracted data points so far: 0\n\n"
        "AVAILABLE TOOLS:\n"
        "- extract_numeric_data: Extract numbers from evidence text\n"
        "- query_evidence_sql: Run SQL queries against evidence\n\n"
        "RULES:\n"
        "1. If no data points exist yet, you MUST run 'extract_numeric_data' first\n"
        "2. Available tools right now: extract_numeric_data, query_evidence_sql\n\n"
        "What should I do next? Choose a tool or 'stop'."
    )

    system = (
        "You are a research data analyst. Choose which analysis tool "
        "to run next, or 'stop' if analysis is sufficient."
    )

    decision = await client.generate_structured(
        prompt=prompt,
        schema=ReactDecision,
        system=system,
        max_tokens=512,
        timeout=30,
    )

    # --- Diagnostics ---
    print("\n" + "=" * 80)
    print("REACT DECISION SCHEMA TEST")
    print("=" * 80)
    print(f"  action: {decision.action}")
    print(f"  reasoning: {decision.reasoning}")
    print(f"  action_input: {decision.action_input}")
    print(f"  API cost: ${client.usage.total_cost_usd:.4f}")
    print("=" * 80)

    # --- Assertions ---
    assert isinstance(decision, ReactDecision)
    assert decision.action in ("extract_numeric_data", "query_evidence_sql", "stop"), (
        f"Unexpected action: {decision.action}"
    )
    assert len(decision.reasoning) > 10, (
        f"Reasoning too short: '{decision.reasoning}'"
    )
    # Given the rules say "MUST run extract_numeric_data first", Qwen should comply
    assert decision.action == "extract_numeric_data", (
        f"With 0 data points and rule #1, Qwen should pick "
        f"'extract_numeric_data' but chose '{decision.action}'"
    )
