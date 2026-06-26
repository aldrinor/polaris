"""I-cap-002 feature 2/4 (#1060): tests for the shared analytical-depth heuristic + report splitter.

Covers BOTH:
- ``evaluate_analytical_depth`` (the Pipeline-B RC-8 heuristic, now shared) — marker counts, the
  per-section ``ops_present < 2`` deficient flag, the ``passed`` threshold boundary, and safety on
  malformed/empty section dicts.
- ``split_report_into_sections`` (the benchmark surface) — multi-header split, Preamble capture,
  ``##`` vs ``###`` headers, empty/no-header inputs, and the known benchmark Key-Findings behavior
  (front ``## Key Findings`` ATX block is NOT counted by the bold-form regex; per-section
  ``**Key Findings**`` subsections ARE counted).
"""

from __future__ import annotations

from src.polaris_graph.generator.analytical_depth import (
    evaluate_analytical_depth,
    split_report_into_sections,
)


# --------------------------------------------------------------------------- #
# evaluate_analytical_depth — marker counting
# --------------------------------------------------------------------------- #

def test_counts_markers_across_sections():
    sections = [
        {"title": "A", "content": "Drug X outperformed placebo. **Key Findings** here."},
        {"title": "B", "content": "In contrast, cohort Y differs from Z. A limitation remains."},
    ]
    out = evaluate_analytical_depth(sections)
    # "outperformed", "in contrast", "differs from" = 3 comparison markers
    assert out["comparison_markers"] == 3
    assert out["challenge_markers"] == 1          # "limitation"
    assert out["key_findings"] == 1               # one bold **Key Findings**


def test_markdown_table_is_detected():
    sections = [{"title": "T", "content": "| a | b |\n| 1 | 2 |"}]
    out = evaluate_analytical_depth(sections)
    assert out["tables"] >= 2                      # two table rows


def test_deficient_section_flag_under_two_ops():
    # one section with >=2 ops present, one with <2 (only a comparison) -> the latter is deficient
    rich = {"title": "Rich", "content": "X outperformed Y. **Key Findings** noted."}
    thin = {"title": "Thin", "content": "However, that is all."}   # 1 op (comparison) only
    out = evaluate_analytical_depth([rich, thin])
    assert "Thin" in out["deficient_sections"]
    assert "Rich" not in out["deficient_sections"]


def test_passed_threshold_boundary():
    # Build a report that JUST clears every threshold: comparison>=10, tables>=2,
    # key_findings>=3, challenge>=3, deficient<=2.
    comparisons = " ".join(["outperformed"] * 10)
    challenges = " ".join(["limitation"] * 3)
    kfs = " ".join(["**Key Findings**"] * 3)
    table = "| a | b |\n| c | d |\n| e | f |"
    passing = [{"title": "All", "content": f"{comparisons} {challenges} {kfs}\n{table}"}]
    assert evaluate_analytical_depth(passing)["passed"] is True

    # Drop one comparison -> 9 < 10 -> fails (single-axis shortfall flips passed).
    comparisons_short = " ".join(["outperformed"] * 9)
    failing = [{"title": "All", "content": f"{comparisons_short} {challenges} {kfs}\n{table}"}]
    assert evaluate_analytical_depth(failing)["passed"] is False


def test_malformed_and_empty_sections_are_safe():
    assert evaluate_analytical_depth([])["passed"] is False
    # missing 'content' / 'title' keys must not raise
    out = evaluate_analytical_depth([{}, {"title": "only-title"}, {"content": "no title here"}])
    assert out["comparison_markers"] == 0
    # a section with no content + no title contributes "?" to deficient (its .get('title','?'))
    assert "?" in out["deficient_sections"]


# --------------------------------------------------------------------------- #
# split_report_into_sections — the benchmark surface
# --------------------------------------------------------------------------- #

def test_split_multi_header_and_preamble():
    report = (
        "# Research report: Q\n\n"
        "Intro paragraph before any subsection header.\n\n"
        "### Efficacy\n\nBody of efficacy.\n\n"
        "### Limitations\n\nBody of limitations.\n"
    )
    sections = split_report_into_sections(report)
    titles = [s["title"] for s in sections]
    # The H1 title line is itself a header, so 'Research report: Q' is the first section title and
    # the intro paragraph is its content; then the two H3 sections follow.
    assert "Efficacy" in titles
    assert "Limitations" in titles
    efficacy = next(s for s in sections if s["title"] == "Efficacy")
    assert "Body of efficacy." in efficacy["content"]
    # header lines are excluded from content
    assert "### Efficacy" not in efficacy["content"]


def test_split_preamble_when_no_leading_header():
    report = "Just some text with no header at all.\nSecond line."
    sections = split_report_into_sections(report)
    assert len(sections) == 1
    assert sections[0]["title"] == "Preamble"
    assert "no header at all" in sections[0]["content"]


def test_split_empty_and_blank_are_empty_list():
    assert split_report_into_sections("") == []
    assert split_report_into_sections("   \n  \n") == []


def test_split_handles_h2_and_h3():
    report = "## Key Findings\n\n- bullet one\n\n## Per-Trial Summaries\n\nbody\n"
    titles = [s["title"] for s in split_report_into_sections(report)]
    assert "Key Findings" in titles
    assert "Per-Trial Summaries" in titles


def test_front_atx_key_findings_counted_by_default_kill_switch_restores_undercount(monkeypatch):
    # I-wire-012 (#1326): the benchmark front block is emitted as an ATX header `## Key Findings`
    # (generator/key_findings.py). By DEFAULT it is now COUNTED (so a report that ships a Key-Findings
    # block scores key_findings>0 instead of the prior 0). The default-ON kill-switch
    # PG_DEPTH_COUNT_ATX_KEY_FINDINGS=0 restores the prior bold-only undercount for RC-8 parity.
    front_atx = "## Key Findings\n\n- finding one\n- finding two\n"
    monkeypatch.delenv("PG_DEPTH_COUNT_ATX_KEY_FINDINGS", raising=False)
    atx_depth = evaluate_analytical_depth(split_report_into_sections(front_atx))
    assert atx_depth["key_findings"] == 1          # default ON: ATX header form IS counted

    monkeypatch.setenv("PG_DEPTH_COUNT_ATX_KEY_FINDINGS", "0")
    atx_off = evaluate_analytical_depth(split_report_into_sections(front_atx))
    assert atx_off["key_findings"] == 0            # kill-switch: prior bold-only undercount restored
    monkeypatch.delenv("PG_DEPTH_COUNT_ATX_KEY_FINDINGS", raising=False)

    # The per-section bold `**Key Findings**` subsection form IS counted (both modes).
    body_bold = "### Efficacy\n\nResults here.\n\n**Key Findings**\n\n- x\n"
    bold_depth = evaluate_analytical_depth(split_report_into_sections(body_bold))
    assert bold_depth["key_findings"] == 1
