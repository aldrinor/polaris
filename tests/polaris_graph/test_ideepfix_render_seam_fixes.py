"""I-deepfix-001 (#1369) — offline unit tests for the 4 render-seam fixes proving each catches the
box-2 defect and preserves the safe case. Faithfulness-neutral presentation fixes; no live models."""

import os

from src.polaris_graph.generator import summary_table as st
from src.polaris_graph.generator import verified_compose as vc
from src.polaris_graph.generator.weighted_enrichment import (
    _is_generated_narration_or_masthead,
)


def _row(num, literature, claim):
    return st._RowData(
        num=num, literature=literature, claim=claim, claim_truncated=False,
        geography=[], domain=[], risk=[], doc_key="", cite_nums=[num],
    )


# ---- FIX 1: label-regroup merges same-source paraphrase/number dup rows ----
def test_fix1_serbe_six_paraphrase_rows_merge_to_one():
    rows = [
        _row(29, "SERBE-vol-4-issue-1.pdf [29]",
             "The survey concerned collaboration and knowledge-sharing, and the response rate was 43%, given the statistical sample for the entire country was the basis of the study."),
        _row(30, "SERBE-vol-4-issue-1.pdf [30]",
             "The poll covered collaboration and knowledge-sharing, resulting in a response rate of 43%, given the statistical sample for the entire country was applied."),
        _row(31, "SERBE-vol-4-issue-1.pdf [31]",
             "The research focused on collaboration and knowledge-sharing, achieving a response rate of 43%, given the statistical sample for the entire country was drawn."),
        _row(34, "SERBE-vol-4-issue-1.pdf [34]",
             "The inquiry centered on collaboration and knowledge-sharing, producing a response rate of 43%, given the statistical sample for the entire country was selected."),
    ]
    out = st._regroup_rows_by_label(rows)
    assert len(out) == 1, f"expected 6->1 merge, got {len(out)} rows"
    assert sorted(out[0].cite_nums) == [29, 30, 31, 34], "keep-all citations must survive"


def test_fix1_different_numbers_never_merge():
    rows = [
        _row(1, "Same Source [1]", "Unemployment rose by 5% among clerical workers."),
        _row(2, "Same Source [2]", "Inflation rose by 5% across the economy."),
    ]
    # same number '5%' but different claims -> containment low -> NOT merged (safety)
    out = st._regroup_rows_by_label(rows)
    assert len(out) == 2, "distinct findings from one source must not collapse"


def test_fix1_offswitch_is_passthrough(monkeypatch):
    monkeypatch.setenv("PG_SUMMARY_TABLE_LABEL_REGROUP", "0")
    rows = [_row(1, "X [1]", "a b c 43%"), _row(2, "X [2]", "a b c 43%")]
    assert len(st._regroup_rows_by_label(rows)) == 2


# ---- FIX 2: uncovered-subject hygiene ----
def test_fix2_word_boundary_truncation_no_midword():
    s = "There is no shortage of headlines and articles on artificial intelligence and the future of work today around the globe everywhere"
    out = vc._truncate_subject_word_safe(s, 40)
    assert out.endswith("…")
    assert not out[:-1].rstrip().endswith("sho"), "must not slice mid-word"
    assert " " in out and out.split()[-1].strip("…").isalpha()


def test_fix2_markdown_and_affiliation_subjects_are_chrome():
    assert vc._uncovered_subject_is_chrome("**1. What's a conversation we're**_**not**_**having**")
    assert vc._uncovered_subject_is_chrome("Alexandra Shajek 1. Institut fur Innovation, GmbH, Berlin, Germany 2.")
    assert vc._uncovered_subject_is_chrome("(https://doi.org] Alexandra Shajek")
    assert not vc._uncovered_subject_is_chrome("generative AI productivity gains among support agents")


# ---- FIX 3: topical gate drops off-topic table rows ----
def test_fix3_offtopic_row_demoted_not_dropped():
    """WEIGHT-NOT-FILTER / no-drop (Codex+Fable P1): a zero-overlap off-topic row is DEMOTED to the bottom,
    NEVER dropped — a verified row is never deleted on topical grounds (lexical overlap is unreliable)."""
    q = "impact of Generative AI on the future labor market and employment"
    rows = [
        _row(28, "Smart Factory [28]", "Samples improved with the addition of MWCNTs as filler and graphene oxides in the polymer matrix."),
        _row(3, "Acemoglu [3]", "One more robot per thousand workers reduces the employment-to-population ratio."),
    ]
    out = st._topical_gate_rows(rows, q)
    assert len(out) == 2, "no verified row may be dropped on topical grounds"
    assert any("MWCNT" in r.claim for r in out), "the off-topic row is KEPT (demoted, not dropped)"
    assert "employment" in out[0].claim, "the on-topic row surfaces FIRST"
    assert "MWCNT" in out[-1].claim, "the off-topic row is demoted LAST"


def test_fix3_no_question_tokens_drops_nothing():
    rows = [_row(1, "X [1]", "anything at all")]
    assert len(st._topical_gate_rows(rows, "")) == 1


# ---- FIX 4: generated-narration + masthead chrome ----
def test_fix4_page_figure_narration_flagged():
    assert _is_generated_narration_or_masthead(
        "The document outlines challenges across countries and systems on page 46, "
        "presents Figure 4.1 on dynamic risk benefit assessment on page 61, and includes "
        "Figure 6.1 as a schematic."
    )


def test_fix4_masthead_without_orcid_flagged():
    assert _is_generated_narration_or_masthead(
        "Alexandra Shajek 1. Institut fur Innovation und Technik, VDI/VDE Innovation + "
        "Technik GmbH, Berlin, Germany 2."
    )


def test_fix4_real_claim_with_one_figure_not_flagged():
    assert not _is_generated_narration_or_masthead(
        "As shown in Figure 3, generative AI raised call-center productivity by 14% among agents."
    )


def test_fix4_qualitative_findings_with_description_verbs_not_flagged():
    """Codex iter-3 P1 regression (WEIGHT-NOT-FILTER / no-drop): 'present/illustrate/depict' are REAL
    finding verbs when they govern CONTENT — only flag when the verb governs a STRUCTURE NOUN
    ('presents Figure 4.1'). These qualitative findings (2 structure refs, no metric) must be KEPT."""
    for claim in (
        "Table 2 and Table 3 present evidence that automation displaces routine work.",
        "Figure 1 and Figure 2 illustrate that employment shifted toward services.",
        "Table 4 and Table 5 depict a shift in occupational demand.",
        "Table 2 and Table 3 show that automation displaces routine cognitive work.",
        "Table 2 and Table 3 show job losses of 1,200 and 900 workers.",
        # Codex iter-4 counterexample: a real finding with a SINGLE 'see Figure' locator tail (one
        # nav-governs-structure phrase, low structure-share) must be KEPT.
        "Automation exposure is highest in clerical occupations and lowest in care occupations; see Figure 2 and Table 3.",
        # Fable iter-5 counterexample: TWO bare 'see X' parenthetical locators on a real finding. The weak
        # locators together count AT MOST ONCE toward the chain, so this is KEPT (not chrome).
        "Job displacement was concentrated in clerical roles (see Table 2) and manufacturing (see Figure 3).",
    ):
        assert not _is_generated_narration_or_masthead(claim), f"real finding wrongly flagged: {claim!r}"


def test_fix4_navigation_governing_structure_noun_flagged():
    """The description verb DIRECTLY governing a structure noun IS navigation chrome (still caught)."""
    assert _is_generated_narration_or_masthead(
        "The document outlines the framework on page 3, presents Figure 4.1 on page 61, and "
        "includes Figure 6.1 as a schematic."
    )


def test_p0_emitter_failclosed_calls_real_promote_fn_no_nameerror():
    """Fable iter-5 P0 regression: the emitter fail-closed guard must call the REAL _promote_mode_active().
    Layer ON + PROMOTE OFF => generate_analyst_synthesis returns ('', 0, 0) fail-closed WITHOUT raising
    NameError (and without any LLM call). The prior bug referenced a non-existent _promote_grounded_active(),
    so EVERY layer-ON run NameError'd, the caller swallowed it as 'non-fatal', and the depth layer silently
    vanished -> shallow report. No prior test exercised the layer-ON emitter path, so it slipped through."""
    import asyncio
    from src.polaris_graph.generator import analyst_synthesis as _asyn

    monkeypatch_env = {
        "PG_SWEEP_ANALYST_SYNTHESIS": "1",
        "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED": "0",
        "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK": "0",
    }
    saved = {k: os.environ.get(k) for k in monkeypatch_env}
    try:
        os.environ.update(monkeypatch_env)
        out = asyncio.run(
            _asyn.generate_analyst_synthesis(
                verified_prose="Employment fell 3% [1].",
                bibliography=[{"n": 1, "title": "X", "url": "http://x"}],
                evidence_rows=[{"evidence_id": "e1", "text": "Employment fell 3%."}],
                research_question="What are the labor effects of generative AI?",
            )
        )
        assert out == ("", 0, 0), f"expected fail-closed empty tuple, got {out!r}"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
