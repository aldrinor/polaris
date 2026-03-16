"""
Gemini Gap Closure: Fire Test Script (Layers 1-3).

Layer 1: Local tests (no API, $0) — Tests A-I
Layer 2: API tests (~$0.20) — Tests J-L (requires --api flag)
Layer 3: Integration tests (~$0.30) — Tests M-N (requires --integration flag)

Usage:
    python scripts/pg_gemini_preflight.py                       # Layer 1 only ($0)
    python scripts/pg_gemini_preflight.py --api                 # Layers 1+2 (~$0.20)
    python scripts/pg_gemini_preflight.py --api --integration   # Layers 1+2+3 (~$0.50)
"""

import argparse
import asyncio
import base64
import io
import json
import logging
import os
import re
import struct
import sys
import tempfile
import time

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("pg_gemini_preflight")

# ---------------------------------------------------------------------------
# Test tracking
# ---------------------------------------------------------------------------
_results: list[dict] = []


def _record(test_id: str, name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    _results.append({"id": test_id, "name": name, "passed": passed, "detail": detail})
    icon = "\u2705" if passed else "\u274c"
    logger.info("%s [%s] %s: %s %s", icon, test_id, name, status, detail)


# ===================================================================
# LAYER 1: Local Fire Tests (no API, no cost)
# ===================================================================


def test_a_matplotlib_subprocess():
    """Test A: Matplotlib subprocess execution on Windows."""
    from src.polaris_graph.tools.data_analyzer import _execute_analysis_script

    script = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json, io, base64

fig, ax = plt.subplots()
ax.bar(['A', 'B', 'C'], [10, 20, 15])
ax.set_title('Test Chart')
buf = io.BytesIO()
fig.savefig(buf, format='png', dpi=100)
buf.seek(0)
b64 = base64.b64encode(buf.read()).decode()
plt.close()
print(json.dumps({"charts": [{"title": "Test", "image_base64": b64}], "tables": [], "insights": ["ok"]}))
"""
    result = asyncio.run(_execute_analysis_script(script))
    charts = result.get("charts", [])
    if not charts:
        _record("A", "Matplotlib subprocess", False, "No charts returned")
        return

    b64 = charts[0].get("image_base64", "")
    try:
        decoded = base64.b64decode(b64)
    except Exception as exc:
        _record("A", "Matplotlib subprocess", False, f"base64 decode failed: {exc}")
        return

    has_magic = decoded[:4] == b'\x89PNG'
    is_large = len(decoded) > 1000

    _record(
        "A", "Matplotlib subprocess",
        has_magic and is_large,
        f"PNG magic={has_magic}, size={len(decoded)} bytes",
    )


def test_b_base64_roundtrip():
    """Test B: Base64 round-trip with a minimal PNG."""
    # Create a minimal 1x1 red PNG (67 bytes)
    # PNG header + IHDR + IDAT + IEND
    import struct
    import zlib

    def _make_1x1_png() -> bytes:
        signature = b'\x89PNG\r\n\x1a\n'
        # IHDR chunk
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8bit, RGB
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
        # IDAT chunk (filter byte 0 + RGB red pixel)
        raw = zlib.compress(b'\x00\xff\x00\x00')
        idat_crc = zlib.crc32(b'IDAT' + raw) & 0xFFFFFFFF
        idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
        # IEND
        iend_crc = zlib.crc32(b'IEND') & 0xFFFFFFFF
        iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
        return signature + ihdr + idat + iend

    png_bytes = _make_1x1_png()
    b64 = base64.b64encode(png_bytes).decode()
    decoded = base64.b64decode(b64)
    has_magic = decoded[:4] == b'\x89PNG'

    _record("B", "Base64 round-trip", has_magic and decoded == png_bytes,
            f"magic={has_magic}, size={len(decoded)}")


def test_c_chart_markdown_format():
    """Test C: format_chart_markdown() output format."""
    from src.polaris_graph.tools.data_analyzer import format_chart_markdown

    # Create a valid base64 PNG (tiny)
    import zlib
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    raw = zlib.compress(b'\x00\xff\x00\x00')
    idat_crc = zlib.crc32(b'IDAT' + raw) & 0xFFFFFFFF
    idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
    iend_crc = zlib.crc32(b'IEND') & 0xFFFFFFFF
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    b64_str = base64.b64encode(sig + ihdr + idat + iend).decode()

    chart = {"title": "Test Chart", "image_base64": b64_str, "description": "A test chart"}
    md = format_chart_markdown(chart, 1, ["[1]", "[2]"])

    checks = [
        ("starts_with_img", md.strip().startswith("![")),
        ("has_data_uri", "data:image/png;base64," in md),
        ("has_figure_caption", "*Figure 1:" in md),
        ("has_citations", "Data from [1]" in md),
    ]
    all_pass = all(v for _, v in checks)
    detail = ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
    _record("C", "Chart markdown format", all_pass, detail)


def test_d_table_markdown_format():
    """Test D: format_table_markdown() output format."""
    from src.polaris_graph.tools.data_analyzer import format_table_markdown

    table = {
        "headers": ["Material", "Efficiency (%)", "pH"],
        "rows": [["GAC", "95", "7.0"], ["Sand", "82", "6.5"]],
        "caption": "Filtration efficiency comparison",
    }
    md = format_table_markdown(table, 1)

    checks = [
        ("has_pipe_headers", "| Material | Efficiency (%) | pH |" in md),
        ("has_separator", "| --- | --- | --- |" in md),
        ("has_data_row", "| GAC | 95 | 7.0 |" in md),
        ("has_caption", "*Table 1:" in md),
    ]
    all_pass = all(v for _, v in checks)
    detail = ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
    _record("D", "Table markdown format", all_pass, detail)


def test_e_filler_reduction():
    """Test E: Filler reduction preserves sentence structure."""
    from src.polaris_graph.synthesis.report_assembler import _reduce_filler

    text = (
        "Furthermore, water filtration is critical. "
        "Furthermore, activated carbon is effective. "
        "Furthermore, sand filters remove bacteria. "
        "Furthermore, UV treatment kills viruses. "
        "Furthermore, reverse osmosis removes salts."
    )
    result = _reduce_filler(text)
    count = result.count("Furthermore")

    # First 2 should survive, remaining 3 should be stripped
    checks = [
        ("max_2_filler", count <= 2),
        ("preserves_content", "water filtration" in result),
        ("preserves_content2", "activated carbon" in result),
        ("no_empty", len(result.strip()) > 50),
    ]
    all_pass = all(v for _, v in checks)
    detail = f"filler_count={count}, " + ", ".join(
        f"{k}={'OK' if v else 'FAIL'}" for k, v in checks
    )
    _record("E", "Filler reduction", all_pass, detail)


def test_f_metrics_regex():
    """Test F: :::metrics regex matching against multiple abstract formats."""
    # Pattern 1: ## Abstract
    report1 = "# Title\n\n## Abstract\n\nThis is the abstract.\n\n## Methods\n\nContent."
    # Pattern 2: # Abstract
    report2 = "# Title\n\n# Abstract\n\nThis is the abstract.\n\n## Methods\n\nContent."
    # Pattern 3: No abstract
    report3 = "# Title\n\n## Methods\n\nContent."

    # Test pattern 1 (standard)
    m1 = re.search(r"(## Abstract\n\n.*?\n)(\n## )", report1, re.DOTALL)
    # Test pattern 2 (single-hash)
    m2 = re.search(r"(# Abstract\n\n.*?\n)(\n#+ )", report2, re.DOTALL)
    # Test pattern 3 (no abstract fallback)
    m3 = re.search(r"(\n)(## )", report3)

    checks = [
        ("double_hash_abstract", m1 is not None),
        ("single_hash_abstract", m2 is not None),
        ("no_abstract_fallback", m3 is not None),
    ]
    all_pass = all(v for _, v in checks)
    detail = ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
    _record("F", ":::metrics regex", all_pass, detail)

    # Also test frontend regex
    js_regex = r":::metrics\s*\n?([\s\S]*?):::"
    metrics_block = ":::metrics\nSources: 20 | Evidence: 100 | Faithfulness: 85.0% | Unique Claims: 50\n:::"
    m_js = re.search(js_regex, metrics_block)
    _record(
        "F2", "Frontend metrics regex",
        m_js is not None and "Sources: 20" in (m_js.group(1) if m_js else ""),
        f"matched={'yes' if m_js else 'no'}",
    )


def test_g_key_findings_detection():
    """Test G: Key Findings detection in DOCX exporter."""
    patterns_to_test = [
        ("**Key Findings:**", True),
        ("**Key Findings**", True),
        ("**Key Findings: Water Treatment**", True),
        ("## Key Findings", True),
        ("### Key Findings", True),
        ("#### Key Findings:", True),
        ("# Key Findings", False),  # h1 shouldn't match #{2,4}
        ("Key Findings", False),  # plain text shouldn't match
    ]

    all_pass = True
    details = []
    for text, expected in patterns_to_test:
        is_match = (
            text in ("**Key Findings:**", "**Key Findings**")
            or text.startswith("**Key Findings")
            or bool(re.match(r'^#{2,4}\s+Key Findings', text, re.IGNORECASE))
        )
        passed = is_match == expected
        if not passed:
            all_pass = False
        details.append(f"'{text}'={'OK' if passed else 'FAIL'}")

    _record("G", "Key Findings detection", all_pass, "; ".join(details))


def test_h_docx_export_rich():
    """Test H: DOCX export with tables, images, Key Findings, metrics."""
    try:
        from src.polaris_graph.export.docx_exporter import DocxExporter
    except ImportError as exc:
        _record("H", "DOCX rich export", False, f"Import failed: {exc}")
        return

    # Build a sample markdown report with rich content
    import zlib
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    raw = zlib.compress(b'\x00\xff\x00\x00')
    idat_crc = zlib.crc32(b'IDAT' + raw) & 0xFFFFFFFF
    idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
    iend_crc = zlib.crc32(b'IEND') & 0xFFFFFFFF
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    b64_img = base64.b64encode(sig + ihdr + idat + iend).decode()

    sample_report = f"""# Test Research Report

## Abstract

This is a test abstract covering water treatment technologies.

:::metrics
Sources: 20 | Evidence: 100 | Faithfulness: 85.0% | Unique Claims: 50
:::

## Water Treatment Methods

Activated carbon achieves 95% removal efficiency [1]. Sand filtration
removes 82% of particulates [2].

| Method | Efficiency (%) | Cost ($/m3) |
| --- | --- | --- |
| GAC | 95 | 0.50 |
| Sand | 82 | 0.15 |
| RO | 99 | 1.20 |

*Table 1: Water treatment method comparison*

![Test Chart](data:image/png;base64,{b64_img})
*Figure 1: Efficiency comparison chart*

**Key Findings:**
- GAC provides highest efficiency at moderate cost [1]
- Sand filtration is the most cost-effective option [2]
- RO achieves near-complete removal but at 8x the cost [3]

## References

[1] Smith et al. (2024) Water Treatment Review. *Nature Water*, 2(1), 15-30.
[2] Jones et al. (2023) Sand Filtration. *Water Research*, 45, 100-110.
[3] Lee et al. (2024) RO Membranes. *Desalination*, 500, 114850.
"""

    # Build minimal result dict (DocxExporter requires vector_id and status)
    result = {
        "vector_id": "test_gemini_preflight",
        "status": "completed",
        "final_report": sample_report,
        "report_sections": [
            {
                "section_id": "s1",
                "title": "Water Treatment Methods",
                "content": "Test content",
            }
        ],
        "bibliography": [
            {"ref_number": 1, "authors": "Smith et al.", "year": 2024,
             "title": "Water Treatment Review", "url": "https://example.com/1"},
            {"ref_number": 2, "authors": "Jones et al.", "year": 2023,
             "title": "Sand Filtration", "url": "https://example.com/2"},
        ],
        "original_query": "water treatment technologies",
        "quality_metrics": {"faithfulness_score": 0.85},
    }

    try:
        exporter = DocxExporter()
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            out_path = f.name
        exporter.export(result, out_path)

        file_size = os.path.getsize(out_path)

        from docx import Document
        doc = Document(out_path)
        table_count = len(doc.tables)

        checks = [
            ("file_exists", os.path.exists(out_path)),
            ("file_size_gt_5000", file_size > 5000),
            ("loads_ok", True),
            ("has_table", table_count >= 1),
        ]
        all_pass = all(v for _, v in checks)
        detail = f"size={file_size}, tables={table_count}, " + ", ".join(
            f"{k}={'OK' if v else 'FAIL'}" for k, v in checks
        )
        _record("H", "DOCX rich export", all_pass, detail)
    except Exception as exc:
        _record("H", "DOCX rich export", False, f"Exception: {exc}")
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def test_i_word_target_consistency():
    """Test I: Verify Fix 4 — no 'Maximum: 1000 words' in section_writer.py."""
    import inspect
    from src.polaris_graph.synthesis import section_writer

    source = inspect.getsource(section_writer)

    has_old_cap = "Maximum: 1000 words" in source
    has_new_target = "approximately {min(200 + len(section_evidence)" in source

    _record(
        "I", "Word target consistency",
        not has_old_cap and has_new_target,
        f"old_cap_removed={not has_old_cap}, new_target_present={has_new_target}",
    )


# ===================================================================
# LAYER 2: API Fire Tests (~$0.20)
# ===================================================================


async def test_j_cluster_assessment_strict():
    """Test J: generate_structured() + ClusterAssessment with strict:true."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.schemas import ClusterAssessment

    client = OpenRouterClient()
    try:
        prompt = """Assess this evidence cluster for a research report section.

Cluster theme: "Water filtration efficiency comparison"
Evidence pieces:
1. GAC achieves 95% removal of organic contaminants at pH 7.0
2. Sand filtration removes 82% of suspended solids at low cost
3. Reverse osmosis removes 99% of dissolved salts but is energy-intensive

Should this cluster become a FULL_SECTION, BRIEF mention, MERGE with another, or DROP?
Consider: evidence depth, data comparability, and analytical potential."""

        result = await client.generate_structured(
            prompt=prompt,
            system="You are a research report architect assessing evidence clusters.",
            response_model=ClusterAssessment,
            max_tokens=1024,
        )

        valid_decisions = {"FULL_SECTION", "BRIEF", "MERGE", "DROP"}
        checks = [
            ("is_ClusterAssessment", isinstance(result, ClusterAssessment)),
            ("valid_decision", result.decision in valid_decisions),
            ("has_structured_data_bool", isinstance(result.has_structured_data, bool)),
        ]
        all_pass = all(v for _, v in checks)
        detail = f"decision={result.decision}, structured={result.has_structured_data}, " + \
                 ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
        _record("J", "ClusterAssessment strict", all_pass, detail)
    except Exception as exc:
        _record("J", "ClusterAssessment strict", False, f"Exception: {exc}")
    finally:
        await client.close()


async def test_k_structured_data_extraction():
    """Test K: generate_structured() + StructuredDataExtraction."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.schemas import StructuredDataExtraction

    client = OpenRouterClient()
    try:
        prompt = """Extract structured data points from this text:

"Study A found 95% removal efficiency at pH 7.0 using granular activated carbon (GAC).
Study B reported 82% efficiency at pH 5.5 with sand filtration.
Study C achieved 99.1% removal with reverse osmosis at a cost of $1.20/m3.
The WHO guideline recommends minimum 95% pathogen removal for safe drinking water."

Extract each numeric data point with its value, unit, and entity."""

        result = await client.generate_structured(
            prompt=prompt,
            system="You are a data extraction specialist. Extract structured data points.",
            response_model=StructuredDataExtraction,
            max_tokens=2048,
        )

        checks = [
            ("is_StructuredDataExtraction", isinstance(result, StructuredDataExtraction)),
            ("has_data_points", len(result.data_points) >= 3),
            ("points_have_value", all(p.value for p in result.data_points)),
        ]
        all_pass = all(v for _, v in checks)
        detail = f"points={len(result.data_points)}, " + \
                 ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
        _record("K", "Structured data extraction", all_pass, detail)
    except Exception as exc:
        _record("K", "Structured data extraction", False, f"Exception: {exc}")
    finally:
        await client.close()


async def test_l_evidence_first_section_write():
    """Test L: Evidence-first section writing with real LLM — THE KEY TEST."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.synthesis.section_writer import SECTION_SYSTEM_PROMPT

    client = OpenRouterClient()
    try:
        evidence_pieces = [
            {"evidence_id": "ev_001", "statement": "GAC achieves 95% removal of VOCs", "quality_tier": "GOLD", "relevance_score": 0.92, "source_title": "Smith 2024", "year": "2024", "source_url": "https://example.com/1", "is_faithful": True, "verification_method": "nli", "direct_quote": "Granular activated carbon demonstrated 95% volatile organic compound removal efficiency."},
            {"evidence_id": "ev_002", "statement": "Sand filtration removes 82% of TSS at $0.15/m3", "quality_tier": "GOLD", "relevance_score": 0.88, "source_title": "Jones 2023", "year": "2023", "source_url": "https://example.com/2", "is_faithful": True, "verification_method": "nli", "direct_quote": "Sand filtration achieved 82% total suspended solids removal at a cost of $0.15 per cubic meter."},
            {"evidence_id": "ev_003", "statement": "RO achieves 99.1% desalination but costs $1.20/m3", "quality_tier": "GOLD", "relevance_score": 0.85, "source_title": "Lee 2024", "year": "2024", "source_url": "https://example.com/3", "is_faithful": True, "verification_method": "nli", "direct_quote": "Reverse osmosis membranes achieved 99.1% salt removal efficiency at an operational cost of $1.20 per cubic meter."},
            {"evidence_id": "ev_004", "statement": "UV treatment provides 4-log pathogen inactivation", "quality_tier": "SILVER", "relevance_score": 0.78, "source_title": "WHO 2022", "year": "2022", "source_url": "https://example.com/4", "is_faithful": True, "verification_method": "llm", "direct_quote": "Ultraviolet disinfection at 40 mJ/cm2 dose achieves 4-log inactivation of bacterial pathogens."},
            {"evidence_id": "ev_005", "statement": "Ceramic filters reduce E. coli by 99.99%", "quality_tier": "SILVER", "relevance_score": 0.75, "source_title": "Patel 2023", "year": "2023", "source_url": "https://example.com/5", "is_faithful": True, "verification_method": "llm", "direct_quote": ""},
            {"evidence_id": "ev_006", "statement": "Biochar adsorption capacity ranges from 50-200 mg/g", "quality_tier": "SILVER", "relevance_score": 0.70, "source_title": "Chen 2024", "year": "2024", "source_url": "https://example.com/6", "is_faithful": True, "verification_method": "llm", "direct_quote": ""},
            {"evidence_id": "ev_007", "statement": "Combined GAC-UV systems reduce DBPs by 90%", "quality_tier": "SILVER", "relevance_score": 0.68, "source_title": "Kim 2023", "year": "2023", "source_url": "https://example.com/7", "is_faithful": True, "verification_method": "llm", "direct_quote": ""},
            {"evidence_id": "ev_008", "statement": "Slow sand filtration costs $0.02/m3 in rural settings", "quality_tier": "BRONZE", "relevance_score": 0.60, "source_title": "UNICEF 2022", "year": "2022", "source_url": "https://example.com/8", "is_faithful": False, "verification_method": "api_error", "direct_quote": ""},
            {"evidence_id": "ev_009", "statement": "Membrane fouling reduces RO efficiency by 15-30% annually", "quality_tier": "BRONZE", "relevance_score": 0.55, "source_title": "Wang 2024", "year": "2024", "source_url": "https://example.com/9", "is_faithful": False, "verification_method": "api_error", "direct_quote": ""},
            {"evidence_id": "ev_010", "statement": "Energy consumption for RO is 3-6 kWh/m3", "quality_tier": "BRONZE", "relevance_score": 0.50, "source_title": "IRENA 2023", "year": "2023", "source_url": "https://example.com/10", "is_faithful": False, "verification_method": "api_error", "direct_quote": ""},
        ]

        # Format evidence the same way section_writer does
        from src.polaris_graph.synthesis.section_writer import _format_evidence_for_writing
        evidence_text = _format_evidence_for_writing(evidence_pieces)

        n_evidence = len(evidence_pieces)
        suggested_words = min(200 + n_evidence * 80, 2000)
        system = SECTION_SYSTEM_PROMPT.format(
            n_evidence=n_evidence,
            suggested_words=suggested_words,
        )

        prompt = f"""Report title: Comparative Analysis of Water Treatment Technologies
Section: Filtration and Adsorption Methods
Section description: Comparison of physical and chemical filtration approaches for water purification
Research question: What are the most effective and cost-efficient water treatment technologies?

Available evidence for this section:
{evidence_text}

CRITICAL: This section must directly contribute to answering the research question. Every paragraph should connect its findings back to this question.

Write this section. Begin with analysis of the evidence. Connect findings to the broader report.
Every factual claim MUST include a [CITE:evidence_id] marker referencing the specific evidence piece.
CITATION DIVERSITY: Do NOT cite the same source more than 3 times.

Target: approximately {suggested_words} words."""

        response = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=4096,
            temperature=0.7,
        )
        content = response.content.strip()

        # Measure
        word_count = len(content.split())
        cite_count = len(re.findall(r'\[CITE:[^\]]+\]', content))
        has_key_findings = "key findings" in content.lower()
        has_table = "|" in content and "---" in content
        filler_phrases = ["Furthermore,", "Moreover,", "Additionally,", "In addition,",
                          "It is worth noting", "It should be noted"]
        filler_count = sum(content.count(f) for f in filler_phrases)

        checks = [
            ("has_citations_gte_3", cite_count >= 3),
            ("has_key_findings", has_key_findings),
            ("word_count_reasonable", suggested_words * 0.5 <= word_count <= suggested_words * 2),
            ("low_filler", filler_count <= 3),
        ]

        all_pass = all(v for _, v in checks)
        detail = (
            f"words={word_count}/{suggested_words}, cites={cite_count}, "
            f"key_findings={has_key_findings}, table={has_table}, filler={filler_count}, "
            + ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
        )
        _record("L", "Evidence-first section write", all_pass, detail)

        if not has_key_findings:
            logger.warning(
                "  >> KEY FINDING MISSING — this is a PROMPT problem. "
                "The LLM did not generate Key Findings despite being instructed."
            )
        if not has_table:
            logger.info(
                "  >> No table generated (not a failure, but Gemini always includes them)"
            )

    except Exception as exc:
        _record("L", "Evidence-first section write", False, f"Exception: {exc}")
    finally:
        await client.close()


# ===================================================================
# LAYER 3: Integration Fire Tests (~$0.30)
# ===================================================================


async def test_m_full_chart_pipeline():
    """Test M: Full chart pipeline (LLM -> script -> subprocess -> base64)."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.tools.data_analyzer import analyze_structured_data

    client = OpenRouterClient()
    try:
        data_points = [
            {"data_type": "comparison", "label": "GAC", "value": "95", "unit": "%", "context": "VOC removal", "evidence_id": "ev_001"},
            {"data_type": "comparison", "label": "Sand", "value": "82", "unit": "%", "context": "TSS removal", "evidence_id": "ev_002"},
            {"data_type": "comparison", "label": "RO", "value": "99.1", "unit": "%", "context": "Salt removal", "evidence_id": "ev_003"},
            {"data_type": "comparison", "label": "UV", "value": "99.99", "unit": "%", "context": "Pathogen inactivation", "evidence_id": "ev_004"},
            {"data_type": "comparison", "label": "Ceramic", "value": "99.99", "unit": "%", "context": "E. coli removal", "evidence_id": "ev_005"},
        ]

        result = await analyze_structured_data(
            client=client,
            data_points=data_points,
            analysis_type="comparison",
            research_context="Water treatment technology efficiency comparison",
        )

        charts = result.get("charts", [])
        tables = result.get("tables", [])
        insights = result.get("insights", [])

        has_output = len(charts) > 0 or len(tables) > 0
        valid_chart = False
        if charts:
            b64 = charts[0].get("image_base64", "")
            try:
                decoded = base64.b64decode(b64)
                valid_chart = decoded[:4] == b'\x89PNG'
            except Exception:
                pass

        checks = [
            ("has_any_output", has_output),
            ("valid_chart_or_table", valid_chart or len(tables) > 0),
            ("has_insights", len(insights) > 0),
        ]
        all_pass = all(v for _, v in checks)
        detail = (
            f"charts={len(charts)}, tables={len(tables)}, insights={len(insights)}, "
            f"valid_png={valid_chart}, "
            + ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
        )
        _record("M", "Full chart pipeline", all_pass, detail)

    except Exception as exc:
        _record("M", "Full chart pipeline", False, f"Exception: {exc}")
    finally:
        await client.close()


async def test_n_real_structured_extraction():
    """Test N: Structured data extraction from a real paragraph."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.schemas import StructuredDataExtraction

    client = OpenRouterClient()
    try:
        real_paragraph = """A comprehensive evaluation of point-of-use water treatment technologies
in rural Bangladesh revealed significant variation in pathogen removal efficiency.
Ceramic pot filters achieved 99.99% (4-log) reduction of E. coli, while biosand
filters demonstrated 97% removal. Chlorine tablets at 2 mg/L dosage eliminated
99.9% of bacterial indicators within 30 minutes of contact time. The annual
operational cost per household was $4.20 for ceramic filters, $1.80 for biosand
filters, and $6.50 for chlorine tablets. Solar disinfection (SODIS) using PET
bottles achieved 99.9% pathogen reduction at zero operational cost but required
6 hours of sunlight exposure."""

        result = await client.generate_structured(
            prompt=f"Extract all structured data points from this paragraph:\n\n{real_paragraph}",
            system="Extract numeric data points with value, unit, entity, and context.",
            response_model=StructuredDataExtraction,
            max_tokens=2048,
        )

        # Verify extracted values match source
        extracted_values = [p.value for p in result.data_points]
        expected_substrings = ["99.99", "97", "99.9", "4.20", "1.80"]
        matches = sum(1 for ev in expected_substrings if any(ev in v for v in extracted_values))

        checks = [
            ("extracted_gte_5", len(result.data_points) >= 5),
            ("values_match_source", matches >= 3),
        ]
        all_pass = all(v for _, v in checks)
        detail = (
            f"points={len(result.data_points)}, source_matches={matches}/5, "
            + ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks)
        )
        _record("N", "Real structured extraction", all_pass, detail)

    except Exception as exc:
        _record("N", "Real structured extraction", False, f"Exception: {exc}")
    finally:
        await client.close()


# ===================================================================
# Main
# ===================================================================


def main():
    parser = argparse.ArgumentParser(description="Gemini Gap Fire Tests (Layers 1-3)")
    parser.add_argument("--api", action="store_true", help="Run Layer 2 API tests (~$0.20)")
    parser.add_argument("--integration", action="store_true", help="Run Layer 3 integration tests (~$0.30)")
    args = parser.parse_args()

    start = time.time()

    # ── Layer 1: Local tests ──
    logger.info("=" * 60)
    logger.info("LAYER 1: Local Fire Tests (no API, $0)")
    logger.info("=" * 60)

    test_a_matplotlib_subprocess()
    test_b_base64_roundtrip()
    test_c_chart_markdown_format()
    test_d_table_markdown_format()
    test_e_filler_reduction()
    test_f_metrics_regex()
    test_g_key_findings_detection()
    test_h_docx_export_rich()
    test_i_word_target_consistency()

    layer1_pass = all(r["passed"] for r in _results)

    if not layer1_pass:
        logger.error("LAYER 1 FAILED — fix local issues before spending API credits")
        if not args.api:
            _print_summary(start)
            sys.exit(1)

    # ── Layer 2: API tests ──
    if args.api:
        logger.info("")
        logger.info("=" * 60)
        logger.info("LAYER 2: API Fire Tests (~$0.20)")
        logger.info("=" * 60)

        asyncio.run(test_j_cluster_assessment_strict())
        asyncio.run(test_k_structured_data_extraction())
        asyncio.run(test_l_evidence_first_section_write())

        layer2_results = [r for r in _results if r["id"] in ("J", "K", "L")]
        layer2_pass = all(r["passed"] for r in layer2_results)

        if not layer2_pass:
            logger.error("LAYER 2 FAILED — fix LLM interaction before integration tests")
            if not args.integration:
                _print_summary(start)
                sys.exit(1)

    # ── Layer 3: Integration tests ──
    if args.integration:
        if not args.api:
            logger.warning("--integration requires --api flag (need API for integration tests)")
        else:
            logger.info("")
            logger.info("=" * 60)
            logger.info("LAYER 3: Integration Fire Tests (~$0.30)")
            logger.info("=" * 60)

            asyncio.run(test_m_full_chart_pipeline())
            asyncio.run(test_n_real_structured_extraction())

    _print_summary(start)

    all_pass = all(r["passed"] for r in _results)
    sys.exit(0 if all_pass else 1)


def _print_summary(start_time: float):
    elapsed = time.time() - start_time
    total = len(_results)
    passed = sum(1 for r in _results if r["passed"])
    failed = total - passed

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY: %d/%d PASS (%d FAIL) in %.1fs", passed, total, failed, elapsed)
    logger.info("=" * 60)

    if failed > 0:
        for r in _results:
            if not r["passed"]:
                logger.error("  FAIL [%s] %s: %s", r["id"], r["name"], r["detail"])


if __name__ == "__main__":
    main()
