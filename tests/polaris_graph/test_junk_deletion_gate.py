"""GH I-deepfix-003 (#1374) — unit tests for the junk-deletion grounding gate.

Covers: chrome-non-source deletion, confirmed-off-topic deletion (predicate isolated
via monkeypatch), the marquee/contract anchor exemption, fail-open on an unjudged row,
both kill-switches OFF => byte-identical, and the disclosure-record shape.
"""
import pytest

from src.polaris_graph.generator import junk_deletion_gate as jd


def _clean():
    return {
        "evidence_id": "ev_ok",
        "title": "Generative AI at Work",
        "direct_quote": "Access to AI raises worker productivity by 14 percent.",
        "source_url": "https://doi.org/10.1093/qje/qjae044",
    }


def _chrome():
    return {
        "evidence_id": "ev_junk",
        "content_integrity_junk": True,
        "content_integrity_class": "bot_challenge",
        "title": "Are you a robot?",
        "source_url": "https://doi.org/x",
    }


def test_chrome_row_deleted(monkeypatch):
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    # isolate the offtopic predicate so the clean row is decided only by chrome logic
    monkeypatch.setattr(jd, "is_row_confirmed_offtopic", lambda row: False)
    kept, deleted = jd.partition_rows([_clean(), _chrome()])
    kept_ids = {r["evidence_id"] for r in kept}
    assert "ev_ok" in kept_ids and "ev_junk" not in kept_ids
    assert len(deleted) == 1 and deleted[0]["evidence_id"] == "ev_junk"
    assert deleted[0]["deletion_reason"].startswith("content_integrity_junk")
    assert deleted[0]["deletion_reason"].endswith("bot_challenge")


def test_marquee_exempt_never_deleted(monkeypatch):
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "1")
    monkeypatch.setattr(jd, "is_row_confirmed_offtopic", lambda row: False)
    # a junk row that is ALSO a marquee/contract anchor must be KEPT (exempt)
    kept, deleted = jd.partition_rows([_chrome()], exempt_ids={"ev_junk"})
    assert len(deleted) == 0 and len(kept) == 1
    assert kept[0]["evidence_id"] == "ev_junk"


def test_killswitch_off_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "0")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "0")
    rows = [_clean(), _chrome()]
    kept, deleted = jd.partition_rows(rows)
    assert kept == list(rows) and deleted == []


def test_offtopic_deleted_via_predicate(monkeypatch):
    # legacy weight-label path is reachable ONLY behind the OFF kill-switch (byte-identical
    # to pre-Fix-1); assert it still works there so the fallback is not silently broken.
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "0")
    monkeypatch.setattr(
        jd, "is_row_confirmed_offtopic",
        lambda row: row.get("evidence_id") == "ev_off",
    )
    off = {"evidence_id": "ev_off", "title": "Reconceptualising tourism co-creation"}
    kept, deleted = jd.partition_rows([_clean(), off])
    assert {r["evidence_id"] for r in kept} == {"ev_ok"}
    assert len(deleted) == 1 and deleted[0]["deletion_reason"] == "confirmed_offtopic"


def test_offtopic_failopen_keeps(monkeypatch):
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    # unjudged / uncertain => predicate False => KEEP (fail-open)
    monkeypatch.setattr(jd, "is_row_confirmed_offtopic", lambda row: False)
    kept, deleted = jd.partition_rows([_clean()])
    assert len(kept) == 1 and len(deleted) == 0


def test_disclosure_records_shape():
    recs = jd.disclosure_records([{
        "evidence_id": "e1", "title": "t", "source_url": "u",
        "deletion_reason": "content_integrity_junk:bot_challenge",
    }])
    assert recs[0]["evidence_id"] == "e1"
    assert recs[0]["deletion_reason"] == "content_integrity_junk:bot_challenge"
    assert recs[0]["excluded_from_grounding"] is True


# ── Fix 1: topic-judge-only off-topic DELETE predicate (default ON) ──────────────────────
# A weight/reranker ``content_relevance_label`` can NEVER delete; a positive relevance
# verdict vetoes unconditionally; only the topic judge's OFF_SUBJECT stamp deletes; missing
# verdict fails open (KEEP). These are the 4 confirmed I-deepfix-003 victim shapes.

def _label_demoted():
    # topic judge said ON (no OFF stamp) but the reranker demoted the numeric score. This is
    # the 197-row leak shape: Fed / OECD / ILO / McKinsey / Wikipedia all died on this label.
    return {"evidence_id": "ev_demoted", "title": "OECD Employment Outlook",
            "content_relevance_label": "demoted"}


def _fresh_off_subject():
    return {"evidence_id": "ev_subj", "title": "Reconceptualising tourism co-creation",
            "topic_off_subject": True, "topic_relevance_verdict": "OFF_SUBJECT", "tier": "T6"}


def _positive_plus_stale_off():
    # judges disagree: content-relevance judge affirmatively said RELEVANT, a stale topic
    # stamp says OFF. The positive verdict must win (KEEP).
    return {"evidence_id": "ev_pos", "title": "Generative AI at Work",
            "content_relevance_label": "relevant", "topic_off_subject": True,
            "topic_offtopic_demoted": True}


def test_deletable_predicate_label_demoted_not_deletable():
    assert jd.is_row_deletable_offtopic(_label_demoted()) is False
    assert jd.is_row_deletable_offtopic({"content_relevance_label": "escalated_demoted"}) is False


def test_deletable_predicate_fresh_off_subject_is_deletable():
    assert jd.is_row_deletable_offtopic(_fresh_off_subject()) is True
    # string-form sidecar is honoured; legacy topic_offtopic_demoted alone is NOT deletable
    assert jd.is_row_deletable_offtopic({"topic_off_subject": "off_subject"}) is True
    assert jd.is_row_deletable_offtopic({"topic_offtopic_demoted": True}) is False


def test_deletable_predicate_positive_verdict_vetoes():
    assert jd.is_row_deletable_offtopic(_positive_plus_stale_off()) is False


def test_deletable_predicate_missing_verdict_failopen():
    assert jd.is_row_deletable_offtopic({}) is False
    assert jd.is_row_deletable_offtopic(_clean()) is False
    assert jd.is_row_deletable_offtopic("not-a-mapping") is False


def test_partition_topic_judge_only_default_on(monkeypatch):
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    rows = [_clean(), _label_demoted(), _positive_plus_stale_off(), _fresh_off_subject(), {}]
    kept, deleted = jd.partition_rows(rows)
    kept_ids = {r.get("evidence_id") for r in kept if isinstance(r, dict)}
    # KEPT: clean, weight-demoted, positive+stale-off, and the bare {} (fail-open)
    assert {"ev_ok", "ev_demoted", "ev_pos"} <= kept_ids
    assert {} in kept
    # DELETED: only the fresh OFF_SUBJECT source, with the subject-specific reason
    assert len(deleted) == 1 and deleted[0]["evidence_id"] == "ev_subj"
    assert deleted[0]["deletion_reason"] == "confirmed_offtopic_subject"


def test_partition_off_subject_never_deletes_weight_label(monkeypatch):
    # with default-ON topic-judge-only, a monkeypatched legacy predicate is INERT — a
    # weight-label row is decided only by the OFF_SUBJECT stamp (absent => KEEP).
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    monkeypatch.setattr(jd, "is_row_confirmed_offtopic", lambda row: True)  # would delete all
    kept, deleted = jd.partition_rows([_label_demoted()])
    assert len(deleted) == 0 and len(kept) == 1


def test_off_subject_marquee_exempt_never_deleted(monkeypatch):
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    kept, deleted = jd.partition_rows([_fresh_off_subject()], exempt_ids={"ev_subj"})
    assert len(deleted) == 0 and kept[0]["evidence_id"] == "ev_subj"


# ── Fix 5 (records half): per-source disclosure carries signal + judge verdict + tier ────

def test_disclosure_records_per_source_signal_and_verdict():
    # a deleted OFF_SUBJECT row carries its signal + judge verdict + tier for the manifest
    _kept, deleted = jd.partition_rows([_fresh_off_subject()])
    recs = jd.disclosure_records(deleted)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["evidence_id"] == "ev_subj"
    assert rec["signal"] == "topic_judge_off_subject"
    assert rec["tier"] == "T6"
    assert "OFF_SUBJECT" in rec["judge_verdict"]
    assert rec["excluded_from_grounding"] is True
    # chrome disclosure keeps the chrome signal + class + tier
    chrome_recs = jd.disclosure_records([{
        "evidence_id": "c1", "deletion_reason": "content_integrity_junk:bot_challenge",
        "content_integrity_class": "bot_challenge", "tier": "T4",
    }])
    assert chrome_recs[0]["signal"] == "chrome:bot_challenge"
    assert chrome_recs[0]["tier"] == "T4"
    assert "content_integrity_class=bot_challenge" in chrome_recs[0]["judge_verdict"]


# ── Fix 2: fresh-verdict-only deletion; a STALE snapshot OFF_SUBJECT stamp demote-KEEPs ──

def test_deletable_predicate_stale_stamp_not_deleted(monkeypatch):
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY", "1")
    row = _fresh_off_subject()  # carries topic_off_subject=True but is a STALE (reloaded) stamp
    # id NOT in this run's fresh set (a plain resume => empty set) => demote-KEEP (not deletable)
    assert jd.is_row_deletable_offtopic(row, fresh_off_subject_ids=set()) is False
    # id IN the fresh set (the judge re-confirmed it THIS run) => deletable
    assert jd.is_row_deletable_offtopic(row, fresh_off_subject_ids={"ev_subj"}) is True


def test_deletable_predicate_fresh_none_is_byte_identical():
    # fresh_off_subject_ids=None => freshness un-enforced => Fix-1 behaviour (deletable)
    assert jd.is_row_deletable_offtopic(_fresh_off_subject(), fresh_off_subject_ids=None) is True
    assert jd.is_row_deletable_offtopic(_fresh_off_subject()) is True


def test_deletable_predicate_fresh_flag_off_ignores_set(monkeypatch):
    # flag OFF => freshness NOT checked even with an empty set (byte-identical Fix-1)
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY", "0")
    assert jd.is_row_deletable_offtopic(_fresh_off_subject(), fresh_off_subject_ids=set()) is True


def test_partition_fresh_verdict_only_stale_kept(monkeypatch):
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY", "1")
    rows = [_clean(), _fresh_off_subject()]
    # empty fresh set (stale-only stamps, e.g. a plain resume) => nothing deleted
    kept, deleted = jd.partition_rows(rows, fresh_off_subject_ids=set())
    assert len(deleted) == 0 and {r.get("evidence_id") for r in kept} == {"ev_ok", "ev_subj"}
    # the id IS fresh this run => the OFF_SUBJECT source is deleted
    kept2, deleted2 = jd.partition_rows(rows, fresh_off_subject_ids={"ev_subj"})
    assert len(deleted2) == 1 and deleted2[0]["evidence_id"] == "ev_subj"
    assert deleted2[0]["deletion_reason"] == "confirmed_offtopic_subject"


# --- UNSTAMPED-CORPUS chrome fallback (the pre-built-corpus hole) ------------

def _unstamped_rg_card():
    """A ResearchGate challenge card exactly as it sits in a PRE-BUILT corpus: real
    evidence_id, real tier, real URL — and NO ``content_integrity_junk`` stamp, because
    nothing on the pre-built path ever runs the fetch-time stamp pass."""
    return {
        "evidence_id": "ev_072",
        "tier": "T7",
        "title": "Just a moment...",
        "source_url": "https://www.researchgate.net/publication/397097756_A_Review",
        "direct_quote": (
            "## Security check required\n\nWe've detected unusual activity from your "
            "network. To continue, complete the security check below.\n\n"
            "Ray ID: a17bc0b3e998eb06\nClient IP: 2600:1900:0:2d09::b00\n"
            "© 2008-2026 ResearchGate GmbH. All rights reserved.\n"
        ),
    }


def test_unstamped_chrome_row_is_deleted():
    """A chrome row with NO stamp must still be deleted.

    The stamp is only written by the fetch-path fold-in, so a run fed a pre-built corpus
    carries none — a stamp-only predicate fails open on every row and silently reduces this
    gate to a no-op precisely when it is the last thing between a failed fetch and the
    grounding pool. 52 of these were citable T7 sources in the baseline corpus.
    """
    kept, deleted = jd.partition_rows([_clean(), _unstamped_rg_card()])
    assert [r["evidence_id"] for r in deleted] == ["ev_072"]
    assert [r["evidence_id"] for r in kept] == ["ev_ok"]
    assert deleted[0]["deletion_reason"].startswith("content_integrity_junk")


def test_unstamped_empty_row_is_kept():
    """FAIL-OPEN fence: the unstamped fallback must NOT delete on the detector's ``empty``
    class. At the pool, "no text in any field I know" is an ABSENCE, not an affirmative chrome
    signature — a row keeping its prose under an unfamiliar key would otherwise be deleted for
    the predicate's own ignorance (the false hard-drop §-1.3 forbids)."""
    rows = [{}, {"evidence_id": "ev_meta"}, {"evidence_id": "ev_t", "title": "A Study"}]
    kept, deleted = jd.partition_rows(rows)
    assert deleted == []
    assert len(kept) == 3


def test_unstamped_real_source_never_deleted():
    """Precision fence: a real ON-TOPIC paper — even low-tier — is never chrome."""
    real = {
        "evidence_id": "ev_real", "tier": "T7",
        "title": "Generative AI and the Future of Work",
        "direct_quote": (
            "We study 5,179 customer-support agents and find a 14 percent increase in "
            "issues resolved per hour, concentrated among novice workers."
        ),
        "source_url": "https://example.org/paper",
    }
    kept, deleted = jd.partition_rows([real])
    assert deleted == []
    assert kept == [real]
