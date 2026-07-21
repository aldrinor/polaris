"""LEVER F (canonicalize works) — unit check.

Proves the ``PG_CANONICAL_WORK_BIBLIOGRAPHY`` flag:
  * OFF (unset) => byte-identical: one bibliography entry per evidence_id, no marker collapse,
    and no extra keys added to the biblio dicts.
  * ON => two mirror manifestations of ONE work (same DOI, different URLs) fold to a SINGLE
    canonical ``[N]`` with every member marker remapped and adjacent duplicates collapsed.

Deterministic identity + numbering only — no model, no network.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    SectionResult,
    _merge_bibliographies,
    _remap_section_markers_to_global,
)


def _make_section(title: str, verified_text: str, biblio_slice):
    return SectionResult(
        title=title,
        focus="",
        ev_ids_assigned=[],
        raw_draft="",
        rewritten_draft="",
        verified_text=verified_text,
        biblio_slice=biblio_slice,
        sentences_verified=0,
        sentences_dropped=0,
        regen_attempted=False,
        dropped_due_to_failure=False,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Run under the REAL DEFAULT config: PG_SAMEWORK_URL_LEG is left at its default-ON value (the
    # shared _same_work_key is URL-first). The bibliography canonicalization is DOI-FIRST, so two
    # DIFFERENT-URL manifestations sharing one DOI MUST still fold under the default — that is the
    # property this test proves. Only the LEVER-F flag itself is toggled per test.
    monkeypatch.delenv("PG_SAMEWORK_URL_LEG", raising=False)
    monkeypatch.delenv("PG_CANONICAL_WORK_BIBLIOGRAPHY", raising=False)
    yield


def _inputs():
    # Section-local: [1]=evA (mirror1), [2]=evB (mirror2, SAME DOI as evA), [3]=evC (distinct work).
    biblio_slice = [
        {"num": 1, "evidence_id": "evA", "url": "https://mirror1.example/x",
         "doi": "10.1/xyz", "pmid": "", "tier": "A", "statement": "s"},
        {"num": 2, "evidence_id": "evB", "url": "https://mirror2.example/x",
         "doi": "10.1/XYZ", "pmid": "", "tier": "A", "statement": "s"},
        {"num": 3, "evidence_id": "evC", "url": "https://other.example/y",
         "doi": "10.2/other", "pmid": "", "tier": "B", "statement": "t"},
    ]
    text = "Claim one [1] and mirror [2] plus distinct [3]."
    sections = [_make_section("Sec", text, biblio_slice)]
    return sections


def test_off_is_byte_identical():
    sections = _inputs()  # flag unset by fixture
    biblio = _merge_bibliographies([s.biblio_slice for s in sections])
    remapped = _remap_section_markers_to_global(sections, biblio)

    # One entry per evidence_id, numbered 1..3, no folding.
    assert [b["evidence_id"] for b in biblio] == ["evA", "evB", "evC"]
    assert [b["num"] for b in biblio] == [1, 2, 3]
    # No collapse: each distinct marker preserved.
    assert remapped == ["Claim one [1] and mirror [2] plus distinct [3]."]
    # Byte-identical dict shape: the canonical member key is NOT added on the OFF path.
    assert all("same_work_member_evidence_ids" not in b for b in biblio)


def test_on_folds_two_mirrors_to_one_canonical_marker(monkeypatch):
    monkeypatch.setenv("PG_CANONICAL_WORK_BIBLIOGRAPHY", "1")
    sections = _inputs()
    biblio = _merge_bibliographies([s.biblio_slice for s in sections])
    remapped = _remap_section_markers_to_global(sections, biblio)

    # evA/evB (same DOI) fold to ONE work; evC stays distinct => 2 canonical entries.
    assert len(biblio) == 2
    assert biblio[0]["evidence_id"] == "evA" and biblio[0]["num"] == 1
    assert biblio[1]["evidence_id"] == "evC" and biblio[1]["num"] == 2
    # The canonical entry carries every member evidence_id.
    assert set(biblio[0]["same_work_member_evidence_ids"]) == {"evA", "evB"}
    # Both mirror markers point at the single canonical [1]; the distinct work becomes [2].
    assert remapped == ["Claim one [1] and mirror [1] plus distinct [2]."]


def test_on_collapses_adjacent_duplicate_markers(monkeypatch):
    monkeypatch.setenv("PG_CANONICAL_WORK_BIBLIOGRAPHY", "1")
    biblio_slice = [
        {"num": 1, "evidence_id": "evA", "url": "https://m1/x",
         "doi": "10.1/xyz", "pmid": "", "tier": "A", "statement": "s"},
        {"num": 2, "evidence_id": "evB", "url": "https://m2/x",
         "doi": "10.1/xyz", "pmid": "", "tier": "A", "statement": "s"},
    ]
    sections = [_make_section("S", "Both mirrors cited here [1][2].", biblio_slice)]
    biblio = _merge_bibliographies([s.biblio_slice for s in sections])
    remapped = _remap_section_markers_to_global(sections, biblio)
    # '[1][2]' both fold to canonical [1]; the resulting '[1][1]' collapses to '[1]'.
    assert remapped == ["Both mirrors cited here [1]."]
