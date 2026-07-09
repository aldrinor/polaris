"""I-deepfix-003 STEP 4 (#1374) — same-URL / same-file consolidation.

The drb_72 defect: ~18 chunks of ONE PDF ("reb-t-9-2-2026.pdf") carrying the SAME
source_url, NO DOI, and only weak/varying per-chunk titles produced an EMPTY
``_same_work_key`` for every chunk, so each chunk became its OWN singleton work — 18
phantom independent sources padding breadth/attribution. STEP 4 adds a FIRST,
highest-precedence normalized-source_url leg so all chunks of one file share ONE
same-work key and consolidate to ONE work (KEEP-ALL: every member kept as a
corroborating locator, counted/presented as ONE source).

Pure CPU — no network, no LLM, no cross-encoder (every NLI flag stays default-OFF).
Plain-dict fixtures, NO unittest.mock (§9.4). Serialized per §8.4.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.synthesis.finding_dedup import (
    _normalize_source_url,
    _same_work_key,
    consolidate_same_work,
    dedup_by_finding,
)

_GOV = load_authority_data()["psl_gov_suffixes"]

# The real bug's file: 18 chunks of ONE PDF at ONE URL.
_PDF_URL = "https://reader.example.org/files/reb-t-9-2-2026.pdf"
# A clinical quote VERIFIED to extract a numeric finding (mirrors the phase5 fixtures)
# so all 18 chunks cluster into ONE numeric finding for the corroboration assertion.
_QUOTE = "Tirzepatide produced a mean weight loss of 20.9% at week 72."


def _pdf_chunk(i: int) -> dict:
    """One chunk row of the SAME PDF: same source_url, NO doi, and a weak/varying short
    title that folds to nothing (< 12 chars) so the title leg NEVER groups them — the
    URL leg is the only thing that can consolidate the chunks."""
    return {
        "evidence_id": f"ev{i}",
        "source_url": _PDF_URL,
        "url": _PDF_URL,
        "source_title": f"REB {i}",  # weak/varying: folds < 12 chars => no title key
        "direct_quote": _QUOTE,
        "statement": _QUOTE,
        "tier": "T2",
        "authority_score": 0.5,
    }


def _chunks(n: int = 18) -> list[dict]:
    return [_pdf_chunk(i) for i in range(n)]


# ── 1. `_same_work_key`: 18 same-URL chunks => ONE identical url: key ──────────
def test_same_work_key_identical_for_18_same_url_chunks(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "1")
    rows = _chunks(18)
    keys = [_same_work_key(r) for r in rows]
    assert len(set(keys)) == 1, "all 18 same-URL chunks must share ONE same-work key"
    assert keys[0].startswith("url:"), "the URL leg (highest precedence) must produce the key"
    assert keys[0] == "url:" + _normalize_source_url(rows[0])
    # No DOI + weak/varying titles: the URL leg is the ONLY thing that grouped them.


def test_same_work_key_leg_off_restores_empty_singleton_keys(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "0")
    rows = _chunks(18)
    keys = [_same_work_key(r) for r in rows]
    # No DOI + weak/varying titles => the DOI + title legs produce NO key: every chunk is
    # its own singleton (empty key) — byte-identical to the pre-STEP-4 behavior.
    assert set(keys) == {""}


# ── 2. `consolidate_same_work`: collapse 18 => ONE work (leg ON) ───────────────
def test_consolidate_collapses_18_same_url_to_one_work(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "1")
    rows = _chunks(18)
    res = consolidate_same_work(rows)

    url_groups = [g for g in res.groups if g.same_work_id.startswith("url:")]
    assert len(url_groups) == 1, "the 18 same-URL chunks must consolidate to ONE same-work group"
    group = url_groups[0]
    assert sorted(group.member_indices) == list(range(18)), "keep-all: every chunk stays a member"
    assert len(group.member_evidence_ids) == 18, "every chunk kept as a corroborating locator"
    assert group.member_urls == [_PDF_URL], "one shared URL (deduped locator list)"
    assert not res.dropped_indices, "keep-all: nothing dropped"

    # All 18 map to ONE work id + ONE canonical index => ONE origin downstream.
    assert len(res.work_id_by_index) == 18
    assert set(res.work_id_by_index.values()) == {group.same_work_id}
    assert len(set(res.canonical_index_by_index.values())) == 1


def test_consolidate_leg_off_keeps_18_singletons(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "0")
    rows = _chunks(18)
    res = consolidate_same_work(rows)
    # Old behavior: no real same-work grouping — 18 singleton works, no work-id / canonical
    # annotations (the exact phantom-independent-source padding STEP 4 fixes).
    assert res.work_id_by_index == {}
    assert res.canonical_index_by_index == {}
    assert len(res.groups) == 18
    assert all(g.same_work_id.startswith("__singleton__") for g in res.groups)


# ── 3. `dedup_by_finding`: ONE independent origin + ONE rendered source ────────
def test_dedup_by_finding_one_origin_and_one_source(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "1")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")  # consolidate-keep-all regime
    rows = _chunks(18)
    res = dedup_by_finding(rows, gov_suffixes=_GOV)

    # All 18 chunks carry the SAME numeric finding => ONE cluster.
    assert res.distinct_finding_count == 1
    cluster = res.clusters[0]
    # 18 same-URL chunks of ONE work => ONE independent origin, not 18.
    assert cluster.corroboration_count == 1
    assert len(cluster.member_hosts) == 1

    # Keep-all: every one of the 18 chunk rows still flows through.
    assert len(res.deduped_rows) == 18
    # Every surviving row is annotated as the SAME one work => ONE source in the render.
    work_ids = {r.get("same_work_id") for r in res.deduped_rows}
    assert len(work_ids) == 1
    assert next(iter(work_ids)).startswith("url:")
    canonical = [r for r in res.deduped_rows if r.get("is_same_work_canonical")]
    assert len(canonical) == 1, "exactly one canonical row represents the one work"
    assert len(canonical[0]["same_work_member_evidence_ids"]) == 18


def test_dedup_by_finding_leg_off_no_same_work_annotation(monkeypatch):
    monkeypatch.setenv("PG_SAMEWORK_URL_LEG", "0")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    rows = _chunks(18)
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    # Leg OFF: no DOI + weak titles => no same-work grouping => the render sees the chunks
    # as separate rows (no same_work_id). (The independent-host tally still collapses to 1
    # because all chunks share the host; the URL leg's decisive effect is the same-work /
    # breadth / render de-padding proven in the leg-ON cases above.)
    assert all("same_work_id" not in r for r in res.deduped_rows)
