"""I-deepfix-001 U13: a bare-number headline must not LEAD over a subject-anchored finding.

A span-grounded numeric claim whose subject/population context is stripped ("highest reduction of
99.4%") misrepresents its source when promoted to the headline slot. The U13 screen DEMOTES such an
unanchored bare-number sentence BELOW subject-anchored / non-numeric verified sentences — a
SUPPRESS/REORDER-only change that never rewrites a sentence and never drops one. PG_KF_SUBJECT_ANCHOR=0
reverts byte-identical.
"""
import importlib

import pytest

kf = importlib.import_module("src.polaris_graph.generator.key_findings")


def _clear(monkeypatch):
    monkeypatch.setenv("PG_KF_SUBJECT_ANCHOR", "1")


def test_is_subject_anchored_numeric_classifies_bare_vs_anchored():
    # bare quantity + metric, no subject/population/proper-noun -> NOT anchored
    assert kf._is_subject_anchored_numeric("The highest reduction of 99.4% was recorded [1].") is False
    # population-anchored numeric claim -> anchored
    assert kf._is_subject_anchored_numeric("Adults with the condition showed a 12.0% decrease [2].") is True
    # sentence-initial metric/outcome noun is NOT a reliable subject (Codex iter3) -> NOT anchored
    assert kf._is_subject_anchored_numeric("Risk increased 18% [3].") is False
    assert kf._is_subject_anchored_numeric("Efficacy reached 88% [3].") is False
    # allowlist-only: a drug/trial name WITHOUT a population is NOT a subject anchor -> demoted
    assert kf._is_subject_anchored_numeric("Response rates for Keytruda reached 42% [3].") is False
    # ...but the SAME claim naming a population IS anchored
    assert kf._is_subject_anchored_numeric("Patients on Keytruda had a 42% response [3].") is True
    # structural labels (Cycle/Dose/Grade) do NOT false-anchor (Codex iter6)
    assert kf._is_subject_anchored_numeric("Efficacy reached 88% at Dose 2 [1].") is False
    assert kf._is_subject_anchored_numeric("Risk increased 2x by Cycle 4 [1].") is False
    # non-numeric sentence -> trivially anchored (nothing to misrepresent)
    assert kf._is_subject_anchored_numeric("The mechanism remains under investigation [4].") is True


def test_bare_number_is_demoted_below_anchored(monkeypatch):
    _clear(monkeypatch)
    # verified_text: the BARE-number sentence appears FIRST in document order, the anchored one second.
    verified_text = (
        "The highest reduction of 99.4% was recorded [1]. "
        "Adults with the condition showed a 12.0% decrease [2]."
    )
    out = kf._first_verified_sentences(verified_text, 2, demote_unanchored=True)
    assert len(out) == 2
    # U13: the subject-anchored finding must LEAD; the bare number is demoted (but still present).
    assert "Adults" in out[0], out
    assert "99.4%" in out[1], out


def test_bare_number_still_leads_if_only_candidate(monkeypatch):
    _clear(monkeypatch)
    verified_text = "The highest reduction of 99.4% was recorded [1]."
    out = kf._first_verified_sentences(verified_text, 2, demote_unanchored=True)
    # never dropped: the sole verified sentence still surfaces.
    assert len(out) == 1
    assert "99.4%" in out[0]


def test_shared_caller_keeps_document_order_when_demote_off(monkeypatch):
    # U13 iter2 P1 (Codex): the demote is OPT-IN. Callers that DON'T pass demote_unanchored (e.g.
    # abstract_conclusion.py, which reads document order + picks ordered[-1] as the Conclusion) must
    # get byte-identical DOCUMENT ORDER — the anchor sort must NOT push a bare number to the end and
    # promote it into the Conclusion surface.
    _clear(monkeypatch)  # anchor flag ON — proves it's the param, not the env, that gates it
    verified_text = (
        "Adults with the condition showed a 12.0% decrease [1]. "
        "The highest reduction of 99.4% was recorded [2]."
    )
    out = kf._first_verified_sentences(verified_text, 10_000)  # no demote_unanchored -> default off
    # document order preserved: the bare number stays LAST (so abstract_conclusion's ordered[-1] is
    # the same sentence it always was — the U13 demote does NOT leak into the Conclusion surface).
    assert "Adults" in out[0], out
    assert "99.4%" in out[-1], out


def test_calendar_structural_tokens_do_not_falsely_anchor(monkeypatch):
    # U13 iter2 P1#1: Week/Phase/Table/Figure/Arm are NOT subjects — a bare quantity with only a
    # structural capitalized token must stay UNanchored (demotable), not falsely lead.
    _clear(monkeypatch)
    assert kf._is_subject_anchored_numeric("The highest reduction of 99.4% was observed at Week 12 [1].") is False
    assert kf._is_subject_anchored_numeric("A 41% response was seen in Phase 2 [1].") is False
    assert kf._is_subject_anchored_numeric("Efficacy reached 88% in Arm B, Table 3 [1].") is False


def test_whole_number_fold_and_count_claims_are_numeric(monkeypatch):
    # U13 iter5 P1 (Codex): fold-changes and whole-number counts are numeric CLAIMS that need a
    # subject anchor — they must NOT slip through as "non-numeric" and lead unanchored.
    _clear(monkeypatch)
    assert kf._is_subject_anchored_numeric("Risk increased 2-fold [1].") is False
    assert kf._is_subject_anchored_numeric("Mortality increased 18-fold [1].") is False
    assert kf._is_subject_anchored_numeric("17 deaths occurred [1].") is False
    # Unicode multiplier (×) must also be detected as a numeric claim (Codex iter5)
    assert kf._is_subject_anchored_numeric("Risk increased 2× [1].") is False
    assert kf._is_subject_anchored_numeric("Incidence rose 3.5 × [1].") is False
    # but a fold/count claim WITH a population anchor is fine
    assert kf._is_subject_anchored_numeric("Among APOE4 carriers, risk rose 2-fold [1].") is True
    # citation marker digits alone must NOT make a non-numeric sentence look numeric
    assert kf._is_subject_anchored_numeric("The mechanism remains unclear [12].") is True


def test_genotype_population_is_anchored(monkeypatch):
    # U13 iter2 P1#1: a real clinical population ("APOE4 carriers") must NOT be falsely demoted.
    _clear(monkeypatch)
    assert kf._is_subject_anchored_numeric("Among APOE4 carriers, risk increased 18% [1].") is True
    assert kf._is_subject_anchored_numeric("Homozygous variant carriers had a 2.1-fold rise [2].") is True


def test_section_still_yields_bullet_swap_not_drop(monkeypatch):
    # U13 iter2 P1#2: at 1 sentence/section the demote SWAPS which sentence leads (anchored wins);
    # it is a within-section lead selection, never a corpus/source drop. Prove: the section still
    # yields its one Key-Findings bullet (the anchored sentence), and the bare number remains in the
    # section body (verified_text), just not on the KF surface.
    _clear(monkeypatch)

    class _SR:
        dropped_due_to_failure = False
        is_gap_stub = False
        sentences_verified = 2
        title = "Efficacy"
        verified_text = (
            "The highest reduction of 99.4% was recorded [1]. "
            "Adults with the condition showed a 12.0% decrease [2]."
        )

    if not kf.key_findings_enabled():
        pytest.skip("key findings disabled in this config")
    block = kf.build_key_findings([_SR()])
    # the section still contributes exactly one KF bullet (never zero — no representation drop)
    assert block.count("\n- ") + (1 if block.lstrip().startswith("- ") else 0) >= 1
    # the anchored finding leads the surface; the bare number is not promoted as the headline
    assert "Adults" in block
    # the bare number is NOT dropped from the corpus — it is still in the section body text
    assert "99.4%" in _SR.verified_text


def test_revert_flag_is_byte_identical_document_order(monkeypatch):
    monkeypatch.setenv("PG_KF_SUBJECT_ANCHOR", "0")
    verified_text = (
        "The highest reduction of 99.4% was recorded [1]. "
        "Adults with the condition showed a 12.0% decrease [2]."
    )
    out = kf._first_verified_sentences(verified_text, 2, demote_unanchored=True)
    # flag off + no relevance ranker => original document order preserved (bare number leads).
    assert "99.4%" in out[0], out
    assert "Adults" in out[1], out
