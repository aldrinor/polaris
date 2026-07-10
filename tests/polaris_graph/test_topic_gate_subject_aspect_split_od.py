"""I-deepfix-003 #1374 Fix 3 — topic-gate OFF split into OFF_ASPECT vs OFF_SUBJECT.

ROOT DEFECT (over-deletion): the topic gate emitted a single ``OFF`` verdict, and the
downstream junk-deletion gate treated every OFF/demoted source as deletable. But most
OFF rows are OFF_ASPECT — the SAME subject entity, a DIFFERENT aspect (an education-AI
paper, an HBR hub for a labor-market question). Deleting those is the over-deletion bug:
40-48% of deleted rows were topic-adjacent hubs / on-topic sources, not junk.

THE FIX (Fix 3): the topic prompt now returns ``ON | OFF_ASPECT | OFF_SUBJECT``.
  * OFF_SUBJECT = a clearly DIFFERENT subject (scholar-mill / unrelated-domain junk) —
    the ONLY deletable OFF. It carries the ``topic_off_subject=True`` sidecar the
    junk-deletion gate keys deletion on.
  * OFF_ASPECT = same entity, wrong aspect (a topic hub) — DEMOTED-and-kept, NEVER
    deletable (``topic_offtopic_demoted=True`` only, no ``topic_off_subject``).
  * A legacy bare ``OFF`` parses as OFF_ASPECT (conservative — never delete on the old
    verdict form).

Gated ``PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT`` (default ON); OFF restores the byte-identical
legacy two-verdict prompt + parser (no ``topic_off_subject`` sidecar).

FAITHFULNESS-NEUTRAL: this touches only the selection-side topic gate's PROMPT + verdict
bookkeeping. strict_verify / NLI / the 4-role D8 audit / provenance are byte-for-byte
untouched. The gate still only ever demotes (or, in the legacy hard-drop mode, subtracts)
a source — it never edits a sentence, span, or citation.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.topic_relevance_gate import (
    _build_batch_prompt,
    _parse_batch_verdicts_split,
    classify_topic_relevance,
    topic_gate_subject_aspect_split_enabled,
)

_RESEARCH_QUESTION = "the impact of generative AI on the labor market / employment"

_ON_TITLE = "Generative AI and employment: wage effects and job displacement estimates"
_OFF_ASPECT_TITLE = "Generative AI in the classroom: perceptions of L2 writing students"
_OFF_SUBJECT_TITLE = "Blockchain for supply-chain sustainability: a systematic review"


@pytest.fixture(autouse=True)
def _split_env(monkeypatch):
    """Default the split ON for these tests, independent of any leaked env."""
    monkeypatch.setenv("PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT", "1")
    yield


def _split_llm(prompt: str) -> str:
    """A competent-model stub that answers the three-verdict split contract.

    Reads the SOURCES block the gate built and returns one ``<idx>: <verdict>`` line
    per source (verdict-only). Decision by markers:
      * labor / employment source  -> ON
      * a clearly different subject (blockchain / supply-chain) -> OFF_SUBJECT
      * a same-entity wrong-aspect source (classroom / L2 writing) -> OFF_ASPECT
      * otherwise -> ON (fail-open)
    """
    labor = ("employment", "wage", "job displacement", "labor market", "labour")
    off_subject = ("blockchain", "supply-chain", "supply chain")
    off_aspect = ("classroom", "l2 writing", "perceptions", "students")
    out: list[str] = []
    in_sources = False
    for raw_line in prompt.splitlines():
        line = raw_line.strip()
        if line == "SOURCES:":
            in_sources = True
            continue
        if not in_sources or ":" not in line:
            continue
        idx_part, _, text = line.partition(":")
        idx = idx_part.strip()
        if not idx.isdigit():
            continue  # skips the trailing "VERDICTS (...)" trailer
        low = text.lower()
        if any(k in low for k in labor):
            out.append(f"{idx}: ON")
        elif any(k in low for k in off_subject):
            out.append(f"{idx}: OFF_SUBJECT")
        elif any(k in low for k in off_aspect):
            out.append(f"{idx}: OFF_ASPECT")
        else:
            out.append(f"{idx}: ON")
    return "\n".join(out)


# ── the split parser recognises all three verdicts + conservative legacy OFF ──────

def test_split_parser_recognises_three_verdicts():
    assert _parse_batch_verdicts_split("0: ON\n1: OFF_ASPECT\n2: OFF_SUBJECT", [0, 1, 2]) == {
        0: "ON", 1: "OFF_ASPECT", 2: "OFF_SUBJECT",
    }


def test_split_parser_legacy_bare_off_is_aspect():
    """A legacy bare ``OFF`` (old verdict form) maps to OFF_ASPECT — NEVER deletable."""
    assert _parse_batch_verdicts_split("0: OFF\n1: off", [0, 1]) == {0: "OFF_ASPECT", 1: "OFF_ASPECT"}


def test_split_parser_separator_tolerant():
    """``off subject`` / ``off-subject`` / ``off_subject`` all collapse to OFF_SUBJECT."""
    assert _parse_batch_verdicts_split("0: off subject\n1: OFF-SUBJECT", [0, 1]) == {
        0: "OFF_SUBJECT", 1: "OFF_SUBJECT",
    }


def test_split_parser_fails_open_on_count_mismatch():
    assert _parse_batch_verdicts_split("0: ON", [0, 1]) is None


def test_split_parser_fails_open_on_garbage():
    assert _parse_batch_verdicts_split("the second one is unrelated", [0, 1]) is None


# ── end-to-end through classify_topic_relevance (split default ON) ────────────────

def test_off_subject_stamped_deletable_off_aspect_demote_only():
    """Scholar-mill / different-subject source -> OFF_SUBJECT -> demoted AND stamped
    ``topic_off_subject=True`` (deletable). Education hub -> OFF_ASPECT -> demoted only,
    NO ``topic_off_subject``. Labor source -> ON -> kept, undemoted."""
    r_on = {"title": _ON_TITLE, "source_url": "https://doi.org/10.0/labor"}
    r_aspect = {"title": _OFF_ASPECT_TITLE, "source_url": "https://doi.org/10.0/edu"}
    r_subject = {"title": _OFF_SUBJECT_TITLE, "source_url": "https://doi.org/10.0/chain"}

    result = classify_topic_relevance(
        [r_on, r_aspect, r_subject], _RESEARCH_QUESTION, _split_llm,
    )

    # §-1.3 WEIGHT-not-FILTER: keep-all, demote both OFF kinds, drop nothing.
    assert result.n_in == 3
    assert result.n_kept == 3
    assert result.n_dropped_offtopic == 0
    assert result.n_demoted_offtopic == 2  # aspect + subject

    # OFF_SUBJECT: demoted AND deletable-flagged.
    assert r_subject.get("topic_offtopic_demoted") is True
    assert r_subject.get("topic_off_subject") is True

    # OFF_ASPECT: demoted, but NEVER deletable (no topic_off_subject stamp).
    assert r_aspect.get("topic_offtopic_demoted") is True
    assert "topic_off_subject" not in r_aspect

    # ON: kept, undemoted, not deletable.
    assert r_on.get("topic_offtopic_demoted") is not True
    assert "topic_off_subject" not in r_on


def test_end_to_end_legacy_off_verdict_is_aspect_not_deletable():
    """A stub still emitting the OLD bare ``OFF`` verdict -> OFF_ASPECT: demoted, but
    NOT stamped deletable. Proves the conservative mapping holds end-to-end (an old
    prompt/model can never trigger a deletion via the split)."""
    r_on = {"title": _ON_TITLE, "source_url": "https://doi.org/10.0/labor"}
    r_off = {"title": _OFF_SUBJECT_TITLE, "source_url": "https://doi.org/10.0/x"}

    def _legacy_off_llm(prompt: str) -> str:
        return "0: ON\n1: OFF"

    result = classify_topic_relevance([r_on, r_off], _RESEARCH_QUESTION, _legacy_off_llm)
    assert result.n_demoted_offtopic == 1
    assert result.n_dropped_offtopic == 0
    assert r_off.get("topic_offtopic_demoted") is True
    assert "topic_off_subject" not in r_off  # bare OFF is NEVER deletable


def test_on_source_never_demoted_or_flagged():
    """An on-aspect labor source is kept, undemoted, unflagged — regardless of tier."""
    r_on = {"title": _ON_TITLE, "source_url": "https://someblog.example/genai-jobs"}
    result = classify_topic_relevance([r_on], _RESEARCH_QUESTION, _split_llm)
    assert result.n_demoted_offtopic == 0
    assert result.n_dropped_offtopic == 0
    assert "topic_off_subject" not in r_on


def test_stale_off_subject_popped_on_fresh_off_aspect_and_on(monkeypatch):
    """Codex P1 regression — a STALE ``topic_off_subject=True`` reloaded from an earlier
    corpus_snapshot MUST be popped when THIS run's judge re-verdicts the row OFF_ASPECT (or
    ON). run_honest_sweep_r3 builds its fresh OFF_SUBJECT delete set from ``demoted_rows
    where topic_off_subject is True``; without the pop the stale stamp is misread as a fresh
    OFF_SUBJECT and the on-topic hub is deleted as confirmed_offtopic_subject (defeating Fix
    2 fresh-verdict-only AND Fix 3 OFF_ASPECT=demote-KEEP)."""
    # Both rows carry a stale True baked in by an earlier run.
    r_aspect = {
        "title": _OFF_ASPECT_TITLE, "source_url": "https://doi.org/10.0/edu",
        "topic_off_subject": True, "evidence_id": "aspect1",
    }
    r_on = {
        "title": _ON_TITLE, "source_url": "https://doi.org/10.0/labor",
        "topic_off_subject": True, "evidence_id": "on1",
    }

    result = classify_topic_relevance([r_on, r_aspect], _RESEARCH_QUESTION, _split_llm)

    # This run re-verdicts r_aspect=OFF_ASPECT (demote-keep), r_on=ON: the stale stamp is gone.
    assert "topic_off_subject" not in r_aspect
    assert "topic_off_subject" not in r_on
    assert r_aspect.get("topic_offtopic_demoted") is True  # still demoted (weight), not deletable
    # The fresh OFF_SUBJECT id set the run script derives must NOT include the stale-stamped hub.
    fresh_off_subject = {
        r.get("evidence_id") for r in result.demoted_rows
        if r.get("topic_off_subject") is True
    }
    assert "aspect1" not in fresh_off_subject
    assert "on1" not in fresh_off_subject


def test_fresh_off_subject_verdict_still_stamps_deletable():
    """Control for the pop fix — a row THIS run genuinely re-verdicts OFF_SUBJECT KEEPS the
    deletable stamp (the pop clears ONLY non-OFF_SUBJECT verdicts, never a fresh confirmed
    one)."""
    r_subject = {
        "title": _OFF_SUBJECT_TITLE, "source_url": "https://doi.org/10.0/chain",
        "evidence_id": "subj1",
    }
    result = classify_topic_relevance([r_subject], _RESEARCH_QUESTION, _split_llm)
    assert r_subject.get("topic_off_subject") is True
    fresh = {
        r.get("evidence_id") for r in result.demoted_rows
        if r.get("topic_off_subject") is True
    }
    assert fresh == {"subj1"}


def test_split_fail_open_on_llm_error_no_flags():
    """A raising llm_callable keeps the whole batch and stamps nothing."""
    r_on = {"title": _ON_TITLE, "source_url": "https://doi.org/10.0/labor"}
    r_subject = {"title": _OFF_SUBJECT_TITLE, "source_url": "https://doi.org/10.0/chain"}

    def _boom(prompt: str) -> str:
        raise RuntimeError("LLM down")

    result = classify_topic_relevance([r_on, r_subject], _RESEARCH_QUESTION, _boom)
    assert result.n_kept == 2
    assert result.n_demoted_offtopic == 0
    assert "topic_off_subject" not in r_subject


# ── flag OFF => byte-identical legacy (no split prompt, no deletable sidecar) ──────

def test_flag_off_is_byte_identical_legacy(monkeypatch):
    """PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT=0 restores the legacy two-verdict prompt +
    parser and stamps NO ``topic_off_subject``. A confident-OFF source is demoted
    exactly as before (byte-identical)."""
    monkeypatch.setenv("PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT", "0")
    assert topic_gate_subject_aspect_split_enabled() is False

    r_on = {"title": _ON_TITLE, "source_url": "https://doi.org/10.0/labor"}
    r_off = {"title": _OFF_SUBJECT_TITLE, "source_url": "https://doi.org/10.0/x"}

    def _legacy_llm(prompt: str) -> str:
        # Under the flag-OFF legacy prompt the model returns bare ON/OFF.
        return "0: ON\n1: OFF"

    result = classify_topic_relevance([r_on, r_off], _RESEARCH_QUESTION, _legacy_llm)
    assert result.n_demoted_offtopic == 1
    assert result.n_dropped_offtopic == 0
    assert r_off.get("topic_offtopic_demoted") is True
    assert "topic_off_subject" not in r_off  # split OFF => sidecar never written


def test_legacy_prompt_two_verdict_split_prompt_three_verdict():
    """The non-split (legacy) prompt uses the ``ON`` / ``OFF`` contract and NEVER
    names the split verdicts; the split prompt names both OFF_ASPECT and OFF_SUBJECT
    while preserving the facet-scoped rubric + explicit fail-open. Guards the
    byte-identical-OFF contract at the prompt level, self-contained (no git / HEAD)."""
    batch = [(0, _ON_TITLE, ""), (1, _OFF_SUBJECT_TITLE, "a snippet")]

    legacy = _build_batch_prompt(_RESEARCH_QUESTION, batch)  # default: non-split
    assert "`<index>: ON` or `<index>: OFF`" in legacy
    assert "OFF_SUBJECT" not in legacy and "OFF_ASPECT" not in legacy

    split = _build_batch_prompt(_RESEARCH_QUESTION, batch, subject_aspect_split=True)
    assert "OFF_SUBJECT" in split and "OFF_ASPECT" in split
    assert "specific aspect" in split.lower()
    assert "same subject, wrong question" in split.lower()
    assert "when in doubt, answer on" in split.lower()  # fail-open preserved
