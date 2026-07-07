"""SUMMARY-TABLE source consolidation (I-deepfix-001 UNIT-2, #1344).

The deterministic summary-table renderer emitted ONE row per ``evidence_id``. When a single
source document (e.g. ``SERBE-vol-4-issue-1.pdf``) restated the SAME verified finding under six
distinct evidence ids, six near-identical rows survived — a repetition defect. This module builds
the CONSOLIDATE-KEEP-ALL post-pass (CLAUDE.md §-1.3): same-document, same-finding rows collapse
into ONE multi-citation row that keeps EVERY source cited; distinct number-sets from the same
document stay separate; different documents are never merged.

Faithfulness is untouched — each row still carries a strict-verify-passed claim; this only groups
and presents. All fixtures are plain dicts (no live data / no model / no GPU).
"""
from __future__ import annotations

import logging

import pytest

from src.polaris_graph.generator.summary_table import (
    _build_rows,
    _consolidate_jaccard,
    _doc_identity,
    _salient_numbers,
    _same_finding,
    _source_consolidate_enabled,
)

_FLAG = "PG_SUMMARY_TABLE_SOURCE_CONSOLIDATE"
_JACCARD_ENV = "PG_SUMMARY_TABLE_CONSOLIDATE_JACCARD"

# One source document restating the SAME finding six times (the SERBE repetition defect).
SERBE_URL = "https://journals.example.org/serbe-vol-4-issue-1.pdf"
SERBE_TITLE = "SERBE Vol 4 Issue 1"
SERBE_CLAIM = "The survey response rate was 43%."


def _bib(num, eid, *, url=None, source_title=None, authors=None):
    b: dict = {"num": num, "evidence_id": eid}
    if url is not None:
        b["url"] = url
    if source_title is not None:
        b["source_title"] = source_title
    if authors is not None:
        b["authors"] = authors
    return b


def _claim(eid, sentence, *, is_verified=True, verdict="SUPPORTS"):
    return {
        "evidence_id": eid,
        "sentence": sentence,
        "span_verdict": verdict,
        "is_verified": is_verified,
    }


def _serbe_bib():
    return [_bib(n, f"serbe_{n}", url=SERBE_URL, source_title=SERBE_TITLE) for n in range(10, 16)]


def _serbe_claims():
    return [_claim(f"serbe_{n}", SERBE_CLAIM) for n in range(10, 16)]


@pytest.fixture(autouse=True)
def _default_on(monkeypatch):
    """Every test starts with the default-ON consolidation flag and default jaccard; individual
    tests override as needed. Guards against a leaked env var from a sibling test."""
    monkeypatch.delenv(_FLAG, raising=False)
    monkeypatch.delenv(_JACCARD_ENV, raising=False)


# ── the core defect: 6 SERBE rows collapse to ONE multi-citation row ──────────────────────────
def test_six_serbe_rows_collapse_to_one_multicitation_row():
    rows = _build_rows(_serbe_bib(), _serbe_claims())
    assert len(rows) == 1, f"expected one consolidated row, got {[r.num for r in rows]}"
    row = rows[0]
    assert row.num == 10  # min member num is the stable anchor
    # literature carries ALL six citations (multi-citation, keep-all).
    assert "[10][11][12][13][14][15]" in row.literature
    for n in range(10, 16):
        assert f"[{n}]" in row.literature


def test_keep_all_union_is_every_source():
    """CONSOLIDATE-KEEP-ALL: cite_nums is the sorted union of ALL six member citations — no source
    is dropped when the rows collapse."""
    rows = _build_rows(_serbe_bib(), _serbe_claims())
    assert rows[0].cite_nums == [10, 11, 12, 13, 14, 15]
    assert set(rows[0].cite_nums) == set(range(10, 16))


# ── distinctness: same document, DIFFERENT number-set stays a separate row ────────────────────
def test_same_document_distinct_numbers_stay_separate_rows():
    bib = [
        _bib(10, "s10", url=SERBE_URL, source_title=SERBE_TITLE),
        _bib(11, "s11", url=SERBE_URL, source_title=SERBE_TITLE),
    ]
    claims = [
        _claim("s10", "The survey response rate was 43%."),
        _claim("s11", "Defense spending represented 2.5% of GDP."),
    ]
    rows = _build_rows(bib, claims)
    assert len(rows) == 2  # {43%} != {2.5%} => a real second finding is never merged
    assert [r.num for r in rows] == [10, 11]
    assert rows[0].cite_nums == [10]
    assert rows[1].cite_nums == [11]


# ── cross-document isolation: different documents with the SAME finding never merge ───────────
def test_cross_document_same_finding_stays_separate_rows():
    bib = [
        _bib(10, "a10", source_title="Document A"),
        _bib(11, "b11", source_title="Document B"),
    ]
    claims = [
        _claim("a10", "The survey response rate was 43%."),
        _claim("b11", "The survey response rate was 43%."),
    ]
    rows = _build_rows(bib, claims)
    assert len(rows) == 2  # distinct doc_key => not the same source => not consolidated
    assert [r.num for r in rows] == [10, 11]


# ── kill-switch OFF => byte-identical one-row-per-eid (6 untouched rows) ───────────────────────
def test_flag_off_is_byte_identical_six_rows(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    rows = _build_rows(_serbe_bib(), _serbe_claims())
    assert len(rows) == 6
    assert [r.num for r in rows] == [10, 11, 12, 13, 14, 15]
    for r in rows:
        assert r.cite_nums == [r.num]                 # single-citation, unmerged
        assert r.literature.endswith(f"[{r.num}]")    # one [N] only
        assert "][" not in r.literature               # no multi-citation concatenation


# ── empty doc_key is NEVER consolidated (no source identity => fail-closed to its own row) ─────
def test_empty_doc_key_never_consolidated():
    bib = [_bib(10, "n10"), _bib(11, "n11")]  # no url, no source_title => doc_key ""
    claims = [
        _claim("n10", "The survey response rate was 43%."),
        _claim("n11", "The survey response rate was 43%."),
    ]
    rows = _build_rows(bib, claims)
    assert len(rows) == 2
    assert all(r.doc_key == "" for r in rows)


# ── threshold env (LAW VI): malformed => documented default 0.6; valid parses/clamps ──────────
def test_malformed_jaccard_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(_JACCARD_ENV, "not-a-float")
    assert _consolidate_jaccard() == 0.6


def test_jaccard_default_when_unset_and_valid_parse_and_clamp(monkeypatch):
    monkeypatch.delenv(_JACCARD_ENV, raising=False)
    assert _consolidate_jaccard() == 0.6                 # documented default
    monkeypatch.setenv(_JACCARD_ENV, "0.8")
    assert _consolidate_jaccard() == 0.8                 # valid parse
    monkeypatch.setenv(_JACCARD_ENV, "5")
    assert _consolidate_jaccard() == 1.0                 # clamp high
    monkeypatch.setenv(_JACCARD_ENV, "-2")
    assert _consolidate_jaccard() == 0.0                 # clamp low


# ── helper-level guards ───────────────────────────────────────────────────────────────────────
def test_doc_identity_normalizes_url_and_falls_back_to_title():
    a = _doc_identity({"url": "HTTPS://Journals.Example.org/SERBE.pdf?ref=x#p2/"})
    b = _doc_identity({"source_url": "https://journals.example.org/serbe.pdf"})
    assert a == b == "journals.example.org/serbe.pdf"
    assert _doc_identity({"source_title": "  SERBE Vol 4  "}) == "serbe vol 4"
    assert _doc_identity({}) == ""  # no identity => never consolidated


def test_salient_numbers_and_same_finding():
    assert _salient_numbers("response rate was 43%") == frozenset({"43%"})
    assert _same_finding("response rate was 43%", "the response rate was 43%")
    assert not _same_finding("rate was 43%", "spending was 2.5% of GDP")


def test_source_consolidate_enabled_default_on_and_off(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    assert _source_consolidate_enabled() is True   # default ON
    monkeypatch.setenv(_FLAG, "0")
    assert _source_consolidate_enabled() is False


# ── the realized-effect [activation] marker fires on the default-ON path (anti-dark) ──────────
def test_activation_marker_emitted_default_on(caplog):
    with caplog.at_level(logging.INFO):
        _build_rows(_serbe_bib(), _serbe_claims())
    msgs = [r.getMessage() for r in caplog.records]
    assert any(
        "[activation] summary_table_source_consolidate: clusters=1 rows_in=6 rows_out=1" in m
        for m in msgs
    ), msgs
