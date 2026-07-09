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
    monkeypatch.setenv("PG_DELETE_CHROME_NONSOURCE", "1")
    monkeypatch.setenv("PG_DELETE_OFFTOPIC_SOURCE", "1")
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
