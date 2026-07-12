"""FLYWHEEL Rank4 — arming the §-1.3.1(b) semantic topic judge on a PRE-BUILT corpus.

OFFLINE, fixture-driven, $0 (the judge takes an injected ``llm_callable``, so a stub drives it).
Each test proves a BEHAVIOUR, not a flag-check:

  * the fresh-verdict set threaded from the caller actually ARMS the pool seam's off-topic arm
    (RED before Rank4: the seam hardcoded ``fresh_off_subject_ids=()`` so the arm was inert);
  * every fail-open guarantee §-1.3.1(b) demands survives (uncertainty => KEEP);
  * the positive-relevance veto still beats an OFF_SUBJECT stamp;
  * a STALE stamp (no fresh verdict) still cannot delete — the Rank2b fence is not weakened;
  * UNARMED (judge OFF) is byte-identical: nothing is deleted by the off-topic arm.
"""
from __future__ import annotations

from src.polaris_graph.generator import junk_deletion_gate
from src.polaris_graph.generator.junk_deletion_gate import (
    is_row_deletable_offtopic,
    partition_rows,
)


def _row(eid: str, **kw) -> dict:
    row = {
        "evidence_id": eid,
        "title": f"title {eid}",
        "statement": f"statement {eid}",
        "direct_quote": f"a substantive quote about the labour market from {eid}" * 3,
        "tier": "T3",
        "source_url": f"https://example.org/{eid}",
    }
    row.update(kw)
    return row


# ── the core Rank4 behaviour: a FRESH verdict arms the arm; its ABSENCE keeps it inert ──────────


def test_fresh_verdict_deletes_the_judged_off_subject_row(monkeypatch):
    """ARMED: a row the judge freshly stamped OFF_SUBJECT, and whose id is in the fresh set, deletes."""
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY", "1")
    off = _row("ev_climate", topic_off_subject=True)   # judge said OFF_SUBJECT this run
    on = _row("ev_labor")                              # no stamp
    kept, deleted = partition_rows([off, on], fresh_off_subject_ids={"ev_climate"})
    kept_ids = {r["evidence_id"] for r in kept}
    deleted_ids = {r.get("evidence_id") for r in deleted}
    assert deleted_ids == {"ev_climate"}, "an affirmative FRESH OFF_SUBJECT verdict must delete"
    assert kept_ids == {"ev_labor"}, "an unstamped row must never be touched"


def test_unarmed_empty_fresh_set_deletes_nothing_even_with_a_stamp(monkeypatch):
    """UNARMED (no judge ran => empty concrete set): a stamped row is a STALE stamp => KEEP.

    This is the Rank2b fence and Rank4 must not weaken it: the pre-built corpus can carry a
    ``topic_off_subject`` baked in by an earlier run under a DIFFERENT question. Deleting on it
    would be a foreign verdict — the false hard-drop §-1.3.1(b) forbids.
    """
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY", "1")
    stale = _row("ev_stale", topic_off_subject=True)
    kept, deleted = partition_rows([stale], fresh_off_subject_ids=())
    assert not deleted, "a stale stamp with NO fresh verdict must never delete (fail-open)"
    assert [r["evidence_id"] for r in kept] == ["ev_stale"]


def test_positive_relevance_vetoes_deletion_unconditionally(monkeypatch):
    """A seminal on-topic paper wrongly stamped OFF_SUBJECT is SAVED by the relevance veto."""
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY", "1")
    seminal = _row(
        "ev_acemoglu", tier="T1",
        topic_off_subject=True,                  # a WRONG affirmative verdict
        content_relevance_label="relevant",      # ... but relevance affirmatively says on-topic
    )
    assert is_row_deletable_offtopic(
        seminal, fresh_off_subject_ids={"ev_acemoglu"},
    ) is False, "positive relevance must VETO deletion even against a fresh OFF_SUBJECT verdict"
    kept, deleted = partition_rows([seminal], fresh_off_subject_ids={"ev_acemoglu"})
    assert not deleted and kept[0]["evidence_id"] == "ev_acemoglu"


def test_demoted_label_is_never_a_delete_trigger(monkeypatch):
    """The 633 ``demoted``/``topic_offtopic_demoted`` rows are WEIGHT labels — never deletable.

    Reusing them as a delete trigger is the documented 197-on-topic-row disaster.
    """
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    demoted = _row("ev_demoted", content_relevance_label="demoted", topic_offtopic_demoted=True)
    assert is_row_deletable_offtopic(demoted, fresh_off_subject_ids={"ev_demoted"}) is False
    kept, deleted = partition_rows([demoted], fresh_off_subject_ids={"ev_demoted"})
    assert not deleted, "a demote label must NEVER delete — only an affirmative OFF_SUBJECT stamp"


def test_predicate_fails_open_on_a_broken_row(monkeypatch):
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    assert is_row_deletable_offtopic(None, fresh_off_subject_ids={"x"}) is False
    assert is_row_deletable_offtopic("not a row", fresh_off_subject_ids={"x"}) is False


# ── the judge-side contract the script's arming code depends on ─────────────────────────────────


def test_judge_stamps_off_subject_only_on_off_subject_and_script_reads_it(monkeypatch):
    """The judge stamps ``topic_off_subject`` ONLY on OFF_SUBJECT; OFF_ASPECT is demote-KEEP.

    The script builds its fresh set from exactly this stamp, so an OFF_ASPECT row can never
    become deletable — the distinction Rank4's whole safety story rests on.
    """
    from src.polaris_graph.retrieval.topic_relevance_gate import classify_topic_relevance

    rows = [
        _row("ev_1"),  # -> ON
        _row("ev_2"),  # -> OFF_ASPECT (related field, wrong facet) => demote-KEEP, NOT deletable
        _row("ev_3"),  # -> OFF_SUBJECT (a different subject entirely) => deletable
    ]

    def _stub_llm(prompt: str) -> str:
        # The judge indexes each batch 0-based and the parser accepts nothing else; a format
        # mismatch fails the batch OPEN (keeps everything), so this contract is load-bearing.
        return "0: ON\n1: OFF_ASPECT\n2: OFF_SUBJECT"

    res = classify_topic_relevance(rows, "AI and the labour market", _stub_llm)
    stamped = {
        r["evidence_id"] for r in (res.demoted_rows or [])
        if r.get("topic_off_subject") is True
    }
    assert stamped == {"ev_3"}, (
        "only the OFF_SUBJECT row may carry the deletable sidecar; OFF_ASPECT is demote-KEEP"
    )
    # And that stamp is exactly what makes it deletable — the end-to-end contract.
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY", "1")
    kept, deleted = partition_rows(rows, fresh_off_subject_ids=stamped)
    assert {r.get("evidence_id") for r in deleted} == {"ev_3"}
    assert {r["evidence_id"] for r in kept} == {"ev_1", "ev_2"}


def test_judge_fails_open_when_the_llm_errors_or_is_starved():
    """The token-starvation / outage path: empty or garbage LLM output => NOTHING is deletable.

    This is the silent no-op Rank4 is built to make loud: a reasoning-first judge starved of budget
    returns empty content. It must yield ZERO stamps (keep everything), never a false verdict.
    """
    from src.polaris_graph.retrieval.topic_relevance_gate import classify_topic_relevance

    rows = [_row("ev_1"), _row("ev_2")]

    def _starved(prompt: str) -> str:
        return ""  # reasoning burned the whole budget; no verdict lines were emitted

    res = classify_topic_relevance(rows, "AI and the labour market", _starved)
    assert not [
        r for r in (res.demoted_rows or []) if r.get("topic_off_subject") is True
    ], "a starved/empty judge response must stamp NOTHING (fail-open keeps every row)"

    def _boom(prompt: str) -> str:
        raise RuntimeError("provider 500")

    res2 = classify_topic_relevance(rows, "AI and the labour market", _boom)
    assert not [
        r for r in (res2.demoted_rows or []) if r.get("topic_off_subject") is True
    ], "an LLM exception must stamp NOTHING (fail-open keeps every row)"
