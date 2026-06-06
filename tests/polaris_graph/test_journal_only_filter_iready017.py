"""Unit tests for the journal_only corpus-quality filter (I-ready-017 #1134).

Validates the fail-closed citeability predicate, the single source-filter,
contract-plan pruning (with the drb_72 WEF non-journal entity), the no-leak
assertion, and the adequacy floor. Pure / offline — no network, no spend.
"""

from __future__ import annotations

import importlib

import pytest

jof = importlib.import_module("src.polaris_graph.nodes.journal_only_filter")


# ── gating ──────────────────────────────────────────────────────────────────


def test_flag_off_is_default(monkeypatch):
    monkeypatch.delenv(jof.JOURNAL_ONLY_FLAG, raising=False)
    assert jof.journal_only_flag_enabled() is False
    assert jof.journal_only_active({"source_restriction": "journal_only"}) is False


def test_active_requires_both_flag_and_protocol(monkeypatch):
    monkeypatch.setenv(jof.JOURNAL_ONLY_FLAG, "1")
    assert jof.journal_only_active({"source_restriction": "journal_only"}) is True
    # flag on but protocol does not declare it → inactive
    assert jof.journal_only_active({"source_restriction": "open_web"}) is False
    assert jof.journal_only_active({}) is False
    assert jof.journal_only_active(None) is False


def test_flag_must_be_exactly_one(monkeypatch):
    for val in ("true", "True", "yes", "on", "0", "", "  1  "):
        monkeypatch.setenv(jof.JOURNAL_ONLY_FLAG, val)
        assert jof.journal_only_flag_enabled() is False, val
    monkeypatch.setenv(jof.JOURNAL_ONLY_FLAG, "1")
    assert jof.journal_only_flag_enabled() is True


# ── canonicalize_url ────────────────────────────────────────────────────────


def test_canonicalize_url_variants_collapse():
    a = jof.canonicalize_url("https://www.Example.com/article/X?utm_source=tw#frag")
    b = jof.canonicalize_url("http://example.com/article/X/")
    assert a == b == "https://example.com/article/X"


def test_canonicalize_keeps_meaningful_query():
    assert "id=42" in jof.canonicalize_url("https://j.org/a?id=42&utm_medium=x")


# ── is_citeable_journal: the fail-closed predicate ──────────────────────────


def _meta(**kw):
    return jof.journal_metadata_entry(**kw)


def _sidecar(url, **kw):
    return {jof.canonicalize_url(url): _meta(**kw)}


def test_citeable_true_for_peer_reviewed_journal_article():
    url = "https://www.aeaweb.org/articles?id=10.1257/jep.33.2.3"
    sc = _sidecar(
        url, openalex_pub_type="article", openalex_source_type="journal",
        is_peer_reviewed=True, doi="10.1257/jep.33.2.3",
    )
    ok, reason = jof.is_citeable_journal(url, "T1", sc)
    assert ok is True, reason


def test_not_citeable_when_tier_non_journal():
    url = "https://example.com/explainer"
    sc = _sidecar(url, openalex_pub_type="article", openalex_source_type="journal",
                  is_peer_reviewed=True)
    ok, reason = jof.is_citeable_journal(url, "T4", sc)
    assert ok is False and reason.startswith("tier_not_journal")


def test_not_citeable_when_no_metadata():
    ok, reason = jof.is_citeable_journal("https://x.org/a", "T1", {})
    assert ok is False and reason == "no_journal_metadata"


def test_not_citeable_when_not_peer_reviewed():
    url = "https://news.harvard.edu/gazette/story/ai-labor"
    sc = _sidecar(url, openalex_pub_type="", openalex_source_type="",
                  is_peer_reviewed=False)
    ok, reason = jof.is_citeable_journal(url, "T1", sc)
    assert ok is False and reason == "not_peer_reviewed_journal_article"


def test_not_citeable_for_preprint_doi():
    url = "https://arxiv.org/abs/2303.10130"
    sc = _sidecar(url, openalex_pub_type="preprint", openalex_source_type="repository",
                  is_peer_reviewed=True, doi="10.48550/arxiv.2303.10130")
    ok, reason = jof.is_citeable_journal(url, "T1", sc)
    assert ok is False and reason.startswith("preprint_doi")


def test_not_citeable_for_nav_search_issue_pages():
    for url in (
        "https://www.sciencedirect.com/search?qs=ai+labor",
        "https://www.journals.uchicago.edu/toc/jpe/current",
        "https://www.aeaweb.org/",  # bare homepage
        "https://link.springer.com/journal/10657",
    ):
        sc = _sidecar(url, openalex_pub_type="article", openalex_source_type="journal",
                      is_peer_reviewed=True)
        ok, reason = jof.is_citeable_journal(url, "T1", sc)
        assert ok is False, f"{url} should be rejected"


def test_not_citeable_when_source_type_not_journal():
    url = "https://repo.org/record/123"
    sc = _sidecar(url, openalex_pub_type="article", openalex_source_type="repository",
                  is_peer_reviewed=True)
    ok, reason = jof.is_citeable_journal(url, "T1", sc)
    assert ok is False and reason.startswith("source_type_not_journal")


def test_not_citeable_when_retracted():
    url = "https://j.org/a/1"
    sc = _sidecar(url, openalex_pub_type="article", openalex_source_type="journal",
                  is_peer_reviewed=True, is_retracted=True, doi="10.1/abc")
    ok, reason = jof.is_citeable_journal(url, "T1", sc)
    assert ok is False and reason == "retracted"


# ── filter_to_citeable on the real mixed corpus shape ───────────────────────


def test_filter_partitions_mixed_corpus():
    rows = [
        {"source_url": "https://aeaweb.org/articles?id=10.1257/jep.33.2.3", "tier": "T1"},
        {"source_url": "https://news.harvard.edu/gazette/story/ai", "tier": "T4"},
        {"source_url": "https://weforum.org/4ir", "tier": "T6"},
        {"source_url": "https://qje.org/article/qjae044", "tier": "T1"},
    ]
    sc = {}
    sc.update(_sidecar("https://aeaweb.org/articles?id=10.1257/jep.33.2.3",
                       openalex_pub_type="article", openalex_source_type="journal",
                       is_peer_reviewed=True, doi="10.1257/jep.33.2.3"))
    sc.update(_sidecar("https://qje.org/article/qjae044",
                       openalex_pub_type="article", openalex_source_type="journal",
                       is_peer_reviewed=True, doi="10.1093/qje/qjae044"))
    res = jof.filter_to_citeable(rows, sc)
    assert len(res.citeable) == 2
    assert len(res.excluded) == 2
    excluded_urls = {e["url"] for e in res.excluded}
    assert any("harvard" in u for u in excluded_urls)
    assert any("weforum" in u for u in excluded_urls)


# ── contract-plan pruning: drb_72 WEF entity ────────────────────────────────


def test_prune_contract_keeps_journal_drops_wef():
    entities = {
        "acemoglu_restrepo_automation_tasks": {
            "type": "economic_report", "doi": "10.1257/jep.33.2.3",
        },
        "brynjolfsson_genai_at_work": {
            "type": "economic_report", "doi": "10.1093/qje/qjae044",
        },
        "fourth_industrial_revolution_framing": {
            "type": "policy_report", "type_note": "authoritative_source",
            "url_pattern": "https://www.weforum.org/...",
        },
    }
    rendering_slots = {
        "theory_task_framework": {"entity_id": "acemoglu_restrepo_automation_tasks",
                                  "required": True},
        "genai_productivity": {"entity_id": "brynjolfsson_genai_at_work",
                               "required": True},
        "theory_4ir_framing": {"entity_id": "fourth_industrial_revolution_framing",
                               "required": False},
    }
    res = jof.prune_contract_plans(entities, rendering_slots)
    assert "acemoglu_restrepo_automation_tasks" in res.kept_entity_ids
    assert "brynjolfsson_genai_at_work" in res.kept_entity_ids
    assert "fourth_industrial_revolution_framing" in res.dropped_entity_ids
    # WEF slot is required:false → no hard conflict (prunes cleanly)
    assert res.required_conflicts == []


def test_prune_contract_required_non_journal_is_conflict():
    entities = {
        "wef_required": {"type": "policy_report", "type_note": "authoritative_source"},
    }
    rendering_slots = {
        "slot_a": {"entity_id": "wef_required", "required": True},
    }
    res = jof.prune_contract_plans(entities, rendering_slots)
    assert res.required_conflicts  # required + non-journal → conflict


# ── no-leak assertion ───────────────────────────────────────────────────────


def test_assert_no_leak_clean_and_dirty():
    citeable_url = "https://aeaweb.org/articles?id=10.1257/jep.33.2.3"
    sc = _sidecar(citeable_url, openalex_pub_type="article",
                  openalex_source_type="journal", is_peer_reviewed=True,
                  doi="10.1257/jep.33.2.3")
    clean = [{"source_url": citeable_url, "tier": "T1"}]
    assert jof.assert_no_leak(clean, sc) == []
    dirty = clean + [{"source_url": "https://weforum.org/4ir", "tier": "T6"}]
    leaks = jof.assert_no_leak(dirty, sc)
    assert len(leaks) == 1 and "weforum" in leaks[0]["url"]


# ── adequacy floor ──────────────────────────────────────────────────────────


def _journal_rows(n, start=0):
    rows, sc = [], {}
    for i in range(start, start + n):
        u = f"https://journal{i}.org/article/{i}"
        rows.append({"source_url": u, "tier": "T1"})
        sc.update(_sidecar(u, openalex_pub_type="article", openalex_source_type="journal",
                           is_peer_reviewed=True, doi=f"10.1/{i}"))
    return rows, sc


def test_adequacy_fails_below_min():
    rows, sc = _journal_rows(5)
    r = jof.assess_journal_only_adequacy(rows, sc, min_distinct=12)
    assert r.ok is False
    assert any("too_few_citeable_journals" in x for x in r.reasons)


def test_adequacy_fails_missing_anchor():
    rows, sc = _journal_rows(12)
    r = jof.assess_journal_only_adequacy(
        rows, sc, required_anchor_dois=["10.1257/jep.33.2.3"], min_distinct=12,
    )
    assert r.ok is False
    assert any("missing_s1_anchor_dois" in x for x in r.reasons)


def test_adequacy_anchor_satisfied_by_contract_guarantee():
    # 12 distinct retrieved journals but the anchor DOI is NOT among them — it is
    # a V30 contract frame row injected later. contract_guaranteed_dois credits
    # it (the real held-billed-set §-1.1 finding).
    rows, sc = _journal_rows(12)
    r = jof.assess_journal_only_adequacy(
        rows, sc,
        required_anchor_dois=["10.1093/qje/qjae044"],
        min_distinct=12,
        contract_guaranteed_dois=["10.1093/qje/qjae044"],
    )
    assert r.ok is True, r.reasons
    assert r.missing_anchor_dois == []


def test_adequacy_passes_with_count_and_anchors():
    rows, sc = _journal_rows(11, start=1)
    anchor_url = "https://aeaweb.org/articles?id=10.1257/jep.33.2.3"
    rows.append({"source_url": anchor_url, "tier": "T1"})
    sc.update(_sidecar(anchor_url, openalex_pub_type="article",
                       openalex_source_type="journal", is_peer_reviewed=True,
                       doi="10.1257/jep.33.2.3"))
    r = jof.assess_journal_only_adequacy(
        rows, sc, required_anchor_dois=["10.1257/jep.33.2.3"], min_distinct=12,
    )
    assert r.ok is True, r.reasons
    assert r.distinct_journals == 12


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
