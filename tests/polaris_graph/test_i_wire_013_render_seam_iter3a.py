"""I-wire-013 (#1327) iter-3a — offline self-tests for the UNBLINDED render predicates + the
render-seam chokepoint.

No live calls; every helper is pure. Asserts the faithfulness-STRENGTHENING invariants:
  * ``is_render_chrome_or_unrenderable`` now flags glued CONTAINMENT chrome (ToC / inline header /
    author-ORCID/affiliation / masthead / license / bibliographic / nav / stats-table / predominantly
    non-Latin) welded INTO real prose — while a clean grounded finding, a magnitude pair, a
    "Figure 1 Results" prose line and a year-pair prose line are NEVER flagged (drop-path precision).
  * ``is_truncated_fragment`` catches a corpus-grounded span cut at a ``[N]`` boundary when (and only
    when) a corpus allowlist is supplied — a real, complete corpus word is never flagged.
  * ``sanitize_rendered_report`` (the chokepoint) removes glued ToC + author block + cut-word-before
    -``[N]`` units from every claim-bearing section (Abstract / Key-Findings / ### section bodies incl.
    multi_section output / Corroborated Weighted Findings / Conclusion), REPAIRS a real paragraph with
    a glued inline header (prefix kept), and byte-preserves a clean finding AND the Bibliography
    scaffolding (its legitimate DOIs/URLs).
"""
from __future__ import annotations

from src.polaris_graph.generator import key_findings as kf
from src.polaris_graph.generator import weighted_enrichment as we

# A small, explicit run-corpus vocabulary (the truncation false-positive guard). "research" /
# "methodology" / "occupations" / "productivity" are KNOWN; "resea" / "hodology" / "occupati" are the
# span-cut fragments that are absent from it.
_KNOWN = {
    "research", "researchers", "methodology", "occupations", "productivity", "automation",
    "computerisation", "analyses", "labor", "market", "framework", "wages",
}


# ── unblinded chrome containment predicate ───────────────────────────────────
def test_chrome_containment_flags_glued_furniture():
    # glued ToC welded after a real sentence
    assert we.is_render_chrome_or_unrenderable(
        "1 Introduction 1.1 Research background to the study 1.2 Methodology"
    )
    # an inline second markdown header glued onto a title (CONTAINMENT)
    assert we.is_render_chrome_or_unrenderable(
        "A Fourth Industrial Revolution Paradigm Shift? ## Dennis Zami Atibuni, Deborah Manyiraho"
    )
    # author / ORCID / affiliation block (superscript-affiliation middot list)
    assert we.is_render_chrome_or_unrenderable(
        "Anna Matysiak1 · Daniela Bellani2 · Honorata Bogusz1 Received: 17 October 2022"
    )
    assert we.is_render_chrome_or_unrenderable("Jane Doe 0000-0002-1825-0097, John Roe")
    # journal masthead / submission metadata
    assert we.is_render_chrome_or_unrenderable(
        "Policy Research Working Paper 11057 The Exposure of Workers Pages Posted: 9 Jan 2018"
    )
    # a regression-table run of parenthesised std-errors
    assert we.is_render_chrome_or_unrenderable(
        "Robot Exposure 0.034 0.030 0.027 (0.018) (0.016) (0.011) (0.009)"
    )
    # predominantly non-Latin scrape (CJK)
    assert we.is_render_chrome_or_unrenderable("人工智能对劳动力市场的影响研究综述分析报告")


def test_chrome_containment_precision_keeps_real_findings():
    # a clean, complete, on-topic finding is NEVER chrome
    assert not we.is_render_chrome_or_unrenderable(
        "Automation reduced the employment-to-population ratio by 0.2 percentage points."
    )
    # a magnitude pair must not read as a two-token ToC (3.2 Million / 4.5 Billion)
    assert not we.is_render_chrome_or_unrenderable(
        "Revenue compared 3.2 Million versus 4.5 Billion outcomes overall."
    )
    # "Figure 1 Results" / "Table 2 Methods" prose is not a numbered ToC (does not OPEN with a number)
    assert not we.is_render_chrome_or_unrenderable(
        "Figure 1 Results and Table 2 Methods are summarized in the appendix."
    )
    # a year-pair prose line is not a ToC
    assert not we.is_render_chrome_or_unrenderable(
        "In 2020 China expanded output while 2021 India lagged behind."
    )
    # an English finding quoting a SHORT foreign term survives (no language drop)
    assert not we.is_render_chrome_or_unrenderable(
        "The traditional medicine 中药 reduced fatigue in the treated cohort by twelve percent."
    )


# ── corpus-grounded truncation predicate ─────────────────────────────────────
def test_truncation_corpus_boundary_span_cut():
    # end cut before a marker: "Resea" is a non-inflectional prefix of the known word "research"
    assert kf.is_truncated_fragment("1.1 Research background 1.2 Resea", _KNOWN, ends_before_marker=True)
    # start cut after a marker: "hodology" is a suffix of the known word "methodology"
    assert kf.is_truncated_fragment("hodology to estimate the probability", _KNOWN, starts_after_marker=True)
    # a complete known word is never a cut
    assert not kf.is_truncated_fragment(
        "the model improved productivity", _KNOWN, ends_before_marker=True
    )
    assert not kf.is_truncated_fragment(
        "across many occupations", _KNOWN, ends_before_marker=True
    )


def test_truncation_backward_compatible_without_corpus():
    # No corpus allowlist => byte-identical legacy behaviour (marker leg only). A span cut with NO
    # ellipsis/hyphen marker is NOT flagged (the legacy predicate could not see it).
    assert not kf.is_truncated_fragment("1.1 Research background 1.2 Resea")
    # the legacy marker leg still fires (ellipsis / trailing hyphen)
    assert kf.is_truncated_fragment("Automation does indeed su…")
    assert kf.is_truncated_fragment("a partial word ending in hyphen-")
    assert not kf.is_truncated_fragment("Wages rose 5% in 2023.")


# ── render-seam chokepoint ───────────────────────────────────────────────────
_CRAFTED_REPORT = """# Research report: impact of AI on the labor market

## Abstract

Automation reduced the employment-to-population ratio by 0.2 percentage points.[1] 1 Introduction 1.1 Research background to the study 1.2 Resea.[2]

## Key Findings

- **Displacement.** Robots displaced routine workers in manufacturing labor markets.[3]
- **Authors.** Anna Matysiak1 · Daniela Bellani2 · Honorata Bogusz1 Received: 17 October 2022[4]

### Empirical evidence

Identification used variation in robot exposure across local labor markets.[5] 3.3 Recommender Systems are out of scope here.[6] The risk was estimated for hundreds of detailed occupati.[7]

## Bibliography

[1] Automation and New Tasks — https://doi.org/10.1257/jep.33.2.3
[2] Recommender Systems Review — https://doi.org/10.1016/j.example.2020.01.001
"""


def test_sanitize_rendered_report_removes_chrome_and_truncation_keeps_findings():
    clean, removed = we.sanitize_rendered_report(_CRAFTED_REPORT, _KNOWN)
    assert removed >= 4  # glued ToC + author bullet + ToC line + cut-before-[N]

    # clean grounded findings SURVIVE
    assert "Automation reduced the employment-to-population ratio by 0.2 percentage points.[1]" in clean
    assert "Robots displaced routine workers in manufacturing labor markets.[3]" in clean
    assert "Identification used variation in robot exposure across local labor markets.[5]" in clean

    # glued ToC welded into the Abstract is GONE (and its stray marker [2] with it)
    assert "1.1 Research background to the study" not in clean
    assert "1.2 Resea" not in clean
    # the author/ORCID/affiliation Key-Findings bullet is GONE
    assert "Anna Matysiak1" not in clean and "Received: 17 October" not in clean
    # the glued ToC line inside the multi_section body is GONE
    assert "3.3 Recommender Systems are out of scope" not in clean
    # the cut-word-before-[N] unit ("occupati.[7]") is GONE
    assert "hundreds of detailed occupati" not in clean

    # Bibliography is SCAFFOLDING — its legitimate DOIs survive byte-for-byte
    assert "[1] Automation and New Tasks — https://doi.org/10.1257/jep.33.2.3" in clean
    assert "https://doi.org/10.1016/j.example.2020.01.001" in clean


def test_sanitize_repairs_glued_inline_header_keeps_prefix():
    # a real paragraph (no [N]) with a glued inline header mid-unit -> prefix kept, header dropped.
    report = (
        "## Limitations\n\n"
        "The corpus shows notable tier-distribution gaps across the sources sampled here.## "
        "Analytical synthesis of the remaining furniture follows.\n"
    )
    clean, removed = we.sanitize_rendered_report(report, _KNOWN)
    assert removed >= 1
    assert "The corpus shows notable tier-distribution gaps across the sources sampled here." in clean
    assert "## Analytical synthesis of the remaining furniture" not in clean


def test_sanitize_kill_switch_is_byte_identical(monkeypatch):
    monkeypatch.setenv(we._RENDER_SEAM_SANITIZE_ENV, "0")
    clean, removed = we.sanitize_rendered_report(_CRAFTED_REPORT, _KNOWN)
    assert removed == 0 and clean == _CRAFTED_REPORT


def test_canary_now_sees_glued_chrome_bullets():
    # the canary screens TOP-LEVEL claim bullets with the now-unblinded predicate, so a glued-chrome
    # bullet is counted (it could not be before the CONTAINMENT unblinding).
    report = (
        "## Key Findings\n\n"
        "- Real finding: automation reduced the wage share over the period.\n"
        "- 1 Introduction 1.1 Research background to the study 1.2 Methodology\n"
        "- Anna Matysiak1 · Daniela Bellani2 · Honorata Bogusz1 Received: 17 October 2022\n"
    )
    result = we.evaluate_render_chrome_canary(report)
    assert result["total_claim_bullets"] == 3
    assert result["chrome_claim_bullets"] == 2  # the glued ToC bullet + the author block bullet


# ── known-word builder ───────────────────────────────────────────────────────
def test_build_known_words_from_evidence_rows_and_map():
    rows = [
        {"evidence_id": "a", "direct_quote": "research research research methodology methodology"},
        {"evidence_id": "b", "statement": "research methodology", "title": "research"},
    ]
    known = we.build_corpus_vocabulary_from_evidence(rows, floor=3)
    assert "research" in known          # occurs 5x >= floor 3
    assert "methodology" in known       # occurs 3x >= floor 3
    # the in-memory ev_pool MAP shape ({evidence_id: row}) is accepted too
    known_map = we.build_corpus_vocabulary_from_evidence({r["evidence_id"]: r for r in rows}, floor=3)
    assert known_map == known
