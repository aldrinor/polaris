"""GH I-deepfix-003 (#1374), Fable gate P1-C — render-side same-work URL mirror.

weighted_enrichment._work_identity must key a no-DOI / weak-title multi-chunk PDF by
its normalized source_url (in lockstep with finding_dedup._same_work_key), so the
Evidence-base / CWF render collapses the 18-chunk PDF to ONE entry (not 18).
"""
import pytest

from src.polaris_graph.generator.weighted_enrichment import _work_identity
from src.polaris_graph.synthesis.finding_dedup import _same_work_key


def _chunk(eid, title):
    # 18 chunks of the SAME predatory PDF: identical URL, NO doi, varying weak titles.
    return {
        "evidence_id": eid,
        "source_url": "https://dgpu-journals.ru/wp-content/uploads/reb-t-9-2-2026.pdf",
        "title": title,
    }


def test_same_url_collapses_to_one_work(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "1")
    keys = {_work_identity(f"ev_{i}", _chunk(f"ev_{i}", f"chunk {i}")) for i in range(18)}
    assert len(keys) == 1, "18 same-URL chunks must share ONE work key"
    assert next(iter(keys)).startswith("url:")


def test_lockstep_with_finding_dedup(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "1")
    row = _chunk("ev_a", "chunk A")
    assert _work_identity("ev_a", row) == _same_work_key(row), (
        "the two consolidators must produce the SAME key for the same URL"
    )


def test_killswitch_off_falls_through(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "0")
    # OFF => no url leg; a no-DOI / weak-title chunk falls through to the ev_id (its OWN unit).
    k = _work_identity("ev_a", _chunk("ev_a", "chunk A"))
    assert not k.startswith("url:")


def test_distinct_works_not_merged(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "1")
    a = {"evidence_id": "ev_a", "source_url": "https://x.org/paper-a.pdf", "title": "A"}
    b = {"evidence_id": "ev_b", "source_url": "https://x.org/paper-b.pdf", "title": "B"}
    assert _work_identity("ev_a", a) != _work_identity("ev_b", b), (
        "different URLs must stay different works (never over-merge)"
    )
