"""
Final comprehensive mini test: Verify ALL issues found in TEST_063->TEST_067
are fixed before launching TEST_068.

Tests grouped by issue category:
  S*  = Search pipeline (academic filtering, Exa, source quality)
  C*  = Content quality (repetition, filler, newlines, hedging, tables)
  SC* = Schema/Citation (format, normalization, resolution)
  A*  = Artifacts (diagrams)
  E2E = End-to-end assembler integration

Run: python -u scripts/pg_micro_test_final.py
"""
import asyncio
import os
import re
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

results = {}


def register(test_id, name):
    def decorator(func):
        print(f"\n{'='*70}")
        print(f"TEST {test_id}: {name}")
        print(f"{'='*70}")
        try:
            passed = func()
        except Exception as e:
            import traceback
            traceback.print_exc()
            passed = False
        results[test_id] = (name, passed)
        print(f"  >>> {'PASS' if passed else 'FAIL'}")
        return func
    return decorator


# ===================================================================
# SEARCH PIPELINE
# ===================================================================

@register("S1a", "Synonym expansion: IF synonyms match academic titles")
def _():
    from src.polaris_graph.agents.searcher import _prefilter_academic_results
    papers = [
        {"title": "Effects of time-restricted eating on metabolic syndrome", "abstract": "This meta-analysis examines TRE effects on metabolic markers in adults.", "source_type": "academic"},
        {"title": "Impact of caloric restriction on cardiovascular markers", "abstract": "Systematic review of continuous and intermittent energy restriction.", "source_type": "academic"},
        {"title": "Alternate-day fasting effects on body weight", "abstract": "RCT comparing ADF with ad libitum diets over 12 weeks.", "source_type": "academic"},
        {"title": "Circadian rhythm disruption and glucose homeostasis", "abstract": "Review of circadian biology and insulin sensitivity.", "source_type": "academic"},
        {"title": "UAV radar systems for crop monitoring", "abstract": "Novel radar design for agricultural drone systems.", "source_type": "academic"},
        {"title": "Canine behavioral therapy for separation anxiety", "abstract": "Randomized trial of behavioral interventions in domestic dogs.", "source_type": "academic"},
    ]
    query = "What are the proven health benefits and risks of intermittent fasting based on clinical research and meta-analyses?"
    filtered = _prefilter_academic_results(papers, query)
    titles = [p["title"][:40] for p in filtered]
    print(f"  Input: {len(papers)} papers")
    print(f"  Passed: {len(filtered)} — {titles}")
    # First 4 should pass, last 2 should be rejected
    return len(filtered) == 4


@register("S1b", "OpenAlex snippet field recognized as abstract")
def _():
    from src.polaris_graph.agents.searcher import _prefilter_academic_results
    papers = [
        {"title": "Intermittent fasting meta-analysis 2024", "snippet": "We conducted a systematic review and meta-analysis of intermittent fasting interventions on metabolic health outcomes.", "source_type": "academic"},
    ]
    query = "intermittent fasting health benefits risks"
    filtered = _prefilter_academic_results(papers, query)
    print(f"  Passed with snippet field: {len(filtered)} (should be 1)")
    return len(filtered) == 1


@register("S2", "Exa headers prevent brotli encoding")
def _():
    from src.polaris_graph.agents.searcher import _run_exa_searches
    import inspect
    source = inspect.getsource(_run_exa_searches)
    has_accept_encoding = "Accept-Encoding" in source
    has_gzip = "gzip" in source
    print(f"  Accept-Encoding header: {has_accept_encoding}")
    print(f"  gzip specified: {has_gzip}")
    return has_accept_encoding and has_gzip


@register("S3", "Low-credibility domains get 0.2 authority")
def _():
    from src.polaris_graph.agents.analyzer import _get_domain_authority
    test_domains = {
        "https://www.droracle.ai/article": 0.2,
        "https://orthomolecular.org/paper": 0.2,
        "https://www.eatingwell.com/story": 0.2,
        "https://www.aarp.org/health": 0.2,
        "https://www.sciencefocus.com/article": 0.2,
        "https://www.webmd.com/health": 0.2,
        "https://pubmed.ncbi.nlm.nih.gov/123": 1.0,
        "https://www.nature.com/articles/x": 1.0,
    }
    all_ok = True
    for url, expected in test_domains.items():
        actual = _get_domain_authority(url)
        domain = url.split("/")[2]
        ok = abs(actual - expected) < 0.01
        if not ok:
            all_ok = False
        print(f"  {domain:35s}: {actual} (expected {expected}) {'OK' if ok else 'WRONG'}")
    return all_ok


# ===================================================================
# CITATION / SCHEMA
# ===================================================================

@register("SC1", "Analytical prompt uses [CITE:evidence_id] not [SRC-NNN]")
def _():
    from src.polaris_graph.retrieval.synthesis_prompts import build_section_writer_prompt
    prompt = build_section_writer_prompt(n_evidence=5, suggested_words=500)
    has_cite = "[CITE:evidence_id]" in prompt
    # Check for SRC as a citation instruction (not as "NEVER use [SRC-NNN]")
    has_src = bool(re.search(r"Cite sources inline as \[SRC-", prompt))
    print(f"  Contains [CITE:evidence_id]: {has_cite}")
    print(f"  Contains [SRC-NNN]: {has_src}")
    return has_cite and not has_src


@register("SC2", "ReportOutline normalizes report_outline + research_question")
def _():
    from src.polaris_graph.schemas import ReportOutline
    data = {
        "research_question": "Test query?",
        "report_outline": [
            {"section_title": "Intro", "description": "D1", "section_id": "s01", "order": 1},
            {"section_title": "Body", "description": "D2", "section_id": "s02", "order": 2},
        ],
    }
    outline = ReportOutline.model_validate(data)
    print(f"  title: '{outline.title}', sections: {len(outline.sections)}")
    return outline.title == "Test query?" and len(outline.sections) == 2


@register("SC3", "EvidenceCluster normalizes section_title -> theme")
def _():
    from src.polaris_graph.schemas import EvidenceCluster
    data = {"section_title": "Glycemic Control", "description": "Blood sugar", "evidence_ids": ["1","2"]}
    c = EvidenceCluster.model_validate(data)
    print(f"  theme: '{c.theme}', cluster_id: '{c.cluster_id}'")
    return c.theme == "Glycemic Control"


# ===================================================================
# CONTENT POST-PROCESSING
# ===================================================================

@register("C1", "Filler stripped after period, semicolon, colon, and start")
def _():
    from src.polaris_graph.synthesis.report_assembler import _clean_filler_and_tables
    text = "Additionally, A [1]. Moreover, B [2]; Furthermore, C [3]: Indeed, D [4]."
    cleaned = _clean_filler_and_tables(text)
    remaining = sum(1 for f in ["Additionally","Moreover","Furthermore","Indeed"] if f in cleaned)
    print(f"  Fillers remaining: {remaining}/4 (should be 0)")
    print(f"  Cleaned: {cleaned[:120]}")
    return remaining == 0


@register("C2", "Table filler removed (Moreover,| -> |)")
def _():
    from src.polaris_graph.synthesis.report_assembler import _clean_filler_and_tables
    text = "| Header1 | Header2 |\n|:---|:---|\nMoreover, | Data1 | Data2 |\nIndeed, | Data3 | Data4 |"
    cleaned = _clean_filler_and_tables(text)
    has_filler_pipe = bool(re.search(r"(Moreover|Indeed),?\s*\|", cleaned))
    print(f"  Filler before |: {has_filler_pipe} (should be False)")
    return not has_filler_pipe


@register("C3", "Hedge replaced on cited claims, May 2024 preserved")
def _():
    from src.polaris_graph.synthesis.report_assembler import _clean_filler_and_tables
    text = "IF may reduce glucose [1]. Results from May 2024 showed IF might help [2]. Uncited claim may be true."
    cleaned = _clean_filler_and_tables(text)
    # Check lowercase "may" before citation is replaced (not "May 2024")
    has_lowercase_may_cited = bool(re.search(r"\bmay\b(?=[^.]*\[\d+\])", cleaned))  # case-sensitive
    may_2024 = "May 2024" in cleaned
    uncited_may = "claim may be true" in cleaned
    does_reduce = "does reduce" in cleaned  # "may reduce" -> "does reduce"
    print(f"  Lowercase 'may' before citation gone: {not has_lowercase_may_cited}")
    print(f"  May 2024 kept: {may_2024}, Uncited hedge kept: {uncited_may}, 'does reduce': {does_reduce}")
    print(f"  Cleaned: {cleaned}")
    return not has_lowercase_may_cited and may_2024 and uncited_may and does_reduce


@register("C4", "Transition injection disabled")
def _():
    source = Path("src/polaris_graph/synthesis/report_assembler.py").read_text()
    active = re.findall(r"^\s+section\[\"content\"\] = _inject_transitions\(", source, re.M)
    print(f"  Active _inject_transitions calls: {len(active)} (should be 0)")
    return len(active) == 0


@register("C5", "Hard evidence dedup configured and wired")
def _():
    val = os.getenv("PG_HARD_EVIDENCE_DEDUP", "0")
    source = Path("src/polaris_graph/synthesis/section_writer.py").read_text()
    has_claimed = "_globally_claimed" in source
    print(f"  PG_HARD_EVIDENCE_DEDUP={val}, _globally_claimed in code: {has_claimed}")
    return val == "1" and has_claimed


@register("C6", "Statistics exclusion list passed to section writer prompt")
def _():
    source = Path("src/polaris_graph/synthesis/section_writer.py").read_text()
    has_stats_block = "STATISTICS ALREADY REPORTED" in source
    has_stat_extraction = 'STATISTIC:' in source
    print(f"  STATISTICS ALREADY REPORTED in prompt: {has_stats_block}")
    print(f"  STATISTIC: extraction in code: {has_stat_extraction}")
    return has_stats_block and has_stat_extraction


# ===================================================================
# E2E ASSEMBLER (the real integration test)
# ===================================================================

@register("E2E", "Full assemble_report() produces correct output")
def _():
    from src.polaris_graph.synthesis.report_assembler import assemble_report
    from src.polaris_graph.synthesis.section_writer import SectionDraft
    from src.polaris_graph.schemas import ReportOutline, SectionOutlineItem

    outline = ReportOutline(
        title="IF Research Report",
        abstract="Abstract text here.",
        sections=[
            SectionOutlineItem(section_id="s01", title="Efficacy", description="Weight loss",
                               evidence_ids=["ev_a","ev_b","ev_c","ev_d"], target_words=500, order=1),
            SectionOutlineItem(section_id="s02", title="Safety", description="Risks",
                               evidence_ids=["ev_e","ev_f","ev_g"], target_words=500, order=2),
            SectionOutlineItem(section_id="s03", title="Thin Section", description="Sparse",
                               evidence_ids=["ev_h"], target_words=100, order=3),
        ],
    )
    sections = [
        SectionDraft(section_id="s01", title="Efficacy",
            content="Additionally, IF reduced weight by 5.5 to 6.5 kg over 6 months [CITE:ev_a]. Moreover, 99 RCTs confirmed this finding [CITE:ev_b]. Furthermore, the confidence interval may exclude zero [CITE:ev_c]. Indeed, this suggests efficacy [CITE:ev_d]. | Protocol | Result | Source | |:---|:---|:---| Moreover, | ADF | -5kg | [CITE:ev_a] | Additionally, | TRE | -3kg | [CITE:ev_b] | **Key Findings:** IF works [CITE:ev_a].",
            word_count=80, evidence_count=4),
        SectionDraft(section_id="s02", title="Safety",
            content="In addition, HR was 1.91 for mortality [CITE:ev_e]. Significantly, eating windows under 8h may increase CV death risk by 135% [CITE:ev_f]. The findings from May 2024 were alarming [CITE:ev_g].",
            word_count=30, evidence_count=3),
        SectionDraft(section_id="s03", title="Thin Section",
            content="Moreover, guidelines are cautious [CITE:ev_h].",
            word_count=5, evidence_count=1),
    ]
    sections[0].evidence_ids = ["ev_a","ev_b","ev_c","ev_d"]
    sections[1].evidence_ids = ["ev_e","ev_f","ev_g"]
    sections[2].evidence_ids = ["ev_h"]

    evidence = [
        {"evidence_id": f"ev_{c}", "statement": f"Statement {c}", "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{i}", "source_title": f"Paper {c}", "tier": "GOLD"}
        for i, c in enumerate("abcdefgh")
    ]

    class MockMapping:
        def __init__(self, eid, num):
            self.evidence_id = eid
            self.citation_number = num
            self.is_grounded = True
    class MockAudit:
        def __init__(self):
            self.mappings = [MockMapping(f"ev_{c}", i+1) for i, c in enumerate("abcdefgh")]

    try:
        full_report, report_sections, bibliography = assemble_report(outline, sections, evidence, MockAudit())
    except Exception as e:
        print(f"  CRASH: {e}")
        import traceback; traceback.print_exc()
        return False

    issues = []

    # Newlines
    nl = full_report.count("\n")
    if nl < 5:
        issues.append(f"Newlines: {nl} (need >5)")

    # Fillers
    filler_count = sum(full_report.count(f) for f in ["Additionally","Moreover","Furthermore","In addition","Indeed","Consequently","Specifically","Significantly"])
    if filler_count > 1:
        issues.append(f"Fillers: {filler_count}")

    # Table filler
    if re.search(r"(Moreover|Additionally|Indeed),?\s*\|", full_report):
        issues.append("Table filler present")

    # Citations resolved
    raw_cite = full_report.count("[CITE:")
    if raw_cite > 0:
        issues.append(f"Unresolved [CITE:]: {raw_cite}")
    num_cite = len(re.findall(r"\[\d+\]", full_report))
    if num_cite < 5:
        issues.append(f"Resolved citations: {num_cite} (need >5)")

    # Hedging on cited claims
    cited_hedges = len(re.findall(r"\b(?:may|might)\b(?=[^.]*\[\d+\])", full_report, re.I))
    # Exclude "May 2024"
    may_month = "May 2024" in full_report
    if cited_hedges > (1 if may_month else 0):
        issues.append(f"Cited hedges: {cited_hedges}")

    # May 2024 preserved
    if "Does 2024" in full_report:
        issues.append("'May 2024' mangled to 'Does 2024'")

    # Thin section merged
    sec_titles = [s["title"] for s in report_sections]
    if "Thin Section" in sec_titles:
        issues.append("Thin section not merged")

    # ## headings
    h2 = full_report.count("## ")
    if h2 < 2:
        issues.append(f"Only {h2} ## headings")

    # **Key Findings** on own line
    kf_line = "\n\n**Key Findings" in full_report or "\n**Key Findings" in full_report
    if not kf_line:
        issues.append("Key Findings not on own line")

    # Print results
    print(f"  Report: {len(full_report)} chars, {nl} newlines, {len(report_sections)} sections")
    print(f"  Fillers: {filler_count}, Citations: {num_cite}, Hedges: {cited_hedges}")
    print(f"  May 2024 preserved: {may_month}, Thin merged: {'Thin Section' not in sec_titles}")
    if full_report:
        print(f"  First 400 chars:\n{full_report[:400]}")

    if issues:
        print(f"\n  ISSUES ({len(issues)}):")
        for iss in issues:
            print(f"    - {iss}")
    else:
        print(f"\n  NO ISSUES FOUND")

    return len(issues) == 0


# ===================================================================
# LLM INTEGRATION (requires API call)
# ===================================================================

@register("LLM1", "Section write produces [CITE:] format (live API call)")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.retrieval.synthesis_prompts import build_section_writer_prompt
        client = OpenRouterClient()
        system = build_section_writer_prompt(n_evidence=2, suggested_words=200)
        prompt = (
            "SECTION TITLE: Glycemic Effects\n"
            "RESEARCH QUESTION: IF health effects?\n\n"
            "EVIDENCE:\n"
            "Evidence ID: ev_aaa111\n  Tier: GOLD [VERIFIED]\n  Statement: IF reduced blood sugar SMD -0.51.\n  Quote: \"IF reduced blood sugar SMD -0.51\"\n\n"
            "Evidence ID: ev_bbb222\n  Tier: GOLD [VERIFIED]\n  Statement: TRE reduced glucose -0.74 mmol/L.\n  Quote: \"TRE reduced glucose -0.74 mmol/L\"\n\n"
            "Write this section. Every factual claim MUST include a [CITE:evidence_id] marker."
        )
        r = await client.generate(prompt=prompt, system=system, max_tokens=800, temperature=0.4)
        cite = r.content.count("[CITE:")
        src = r.content.count("[SRC-")
        print(f"  [CITE:]: {cite}, [SRC-]: {src}")
        print(f"  First 200 chars: {r.content[:200]}")
        return cite > 0 and src == 0
    return asyncio.run(_test())


# ===================================================================
# SUMMARY
# ===================================================================

print(f"\n{'='*70}")
print("FINAL COMPREHENSIVE SUMMARY")
print(f"{'='*70}")
total = len(results)
passed = sum(1 for _, p in results.values() if p)
all_pass = passed == total

for tid in sorted(results.keys()):
    name, ok = results[tid]
    print(f"  {tid:5s} {name:60s} {'PASS' if ok else 'FAIL'}")

print(f"\n  TOTAL: {passed}/{total} PASS")
print(f"  ALL PASS: {all_pass}")
