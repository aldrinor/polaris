"""Unit tests for the journal_only corpus-quality filter (I-ready-017 #1134).

RETIRED (GATE_GENERALIZE_FIX45_PLAN §5/§7 U11): the journal-only fail-closed corpus
filter is the C2-violating "hard-mask-a-frozen-corpus" pattern all three reviewers
condemned; it is REPLACED by the adequacy + acquisition-receipt-gated
``build_source_kind_eligibility`` path in quality_eligibility.py. The four mask entry
points (``journal_only_active`` / ``filter_to_citeable`` / ``assert_no_leak`` /
``prune_contract_plans``) are NEUTRALIZED to inert no-ops; the tests below now assert
the RETIRED no-op contract (no masking, no pruning, no leak-abort can ever fire). The
pure predicate helpers (``canonicalize_url`` / ``is_citeable_journal`` / adequacy floor)
are unchanged and still validated. Pure / offline — no network, no spend.
"""

from __future__ import annotations

import importlib

import pytest

jof = importlib.import_module("src.polaris_graph.nodes.journal_only_filter")


# ── gating ──────────────────────────────────────────────────────────────────


def test_keystone_activation_from_real_workforce_template(monkeypatch):
    # Codex diff-gate P1 (keystone): journal_only config lives in the RAW scope
    # template (the serialized ProtocolDocument drops it). With the flag ON and
    # the real workforce.yaml, journal_only MUST activate; with the flag OFF it
    # must not. Guards against the feature being silently inert on the paid path.
    from src.polaris_graph.nodes.scope_gate import load_scope_template, ProtocolDocument
    import dataclasses
    cfg = load_scope_template("workforce")
    assert cfg.get("source_restriction") == "journal_only"
    # The serialized protocol the sweep would otherwise read drops the field:
    assert "source_restriction" not in {f.name for f in dataclasses.fields(ProtocolDocument)}
    # RETIRED (U11): journal_only_active is neutralized to always-False so the mask
    # can never arm — even with the flag ON and the declaring template.
    monkeypatch.setenv(jof.JOURNAL_ONLY_FLAG, "1")
    assert jof.journal_only_active(cfg) is False
    monkeypatch.delenv(jof.JOURNAL_ONLY_FLAG, raising=False)
    assert jof.journal_only_active(cfg) is False


def test_flag_off_is_default(monkeypatch):
    monkeypatch.delenv(jof.JOURNAL_ONLY_FLAG, raising=False)
    assert jof.journal_only_flag_enabled() is False
    assert jof.journal_only_active({"source_restriction": "journal_only"}) is False


def test_active_requires_both_flag_and_protocol(monkeypatch):
    # RETIRED (U11): journal_only_active is a neutralized no-op — always False,
    # regardless of flag or protocol declaration, so no call-site can ever mask.
    monkeypatch.setenv(jof.JOURNAL_ONLY_FLAG, "1")
    assert jof.journal_only_active({"source_restriction": "journal_only"}) is False
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
    # RETIRED (U11): filter_to_citeable is a neutralized IDENTITY passthrough — EVERY
    # row is citeable, NONE excluded (no journal-only corpus masking).
    res = jof.filter_to_citeable(rows, sc)
    assert len(res.citeable) == 4
    assert len(res.excluded) == 0


# ── contract-plan pruning: drb_72 WEF entity ────────────────────────────────


def test_prune_contract_keeps_journal_drops_wef():
    # REAL contract shape: each entity names its rendering_slot; the slot carries
    # `required` (slots do NOT carry entity_id).
    entities = {
        "acemoglu_restrepo_automation_tasks": {
            "type": "economic_report", "doi": "10.1257/jep.33.2.3",
            "journal": "Journal of Economic Perspectives",
            "rendering_slot": "theory_task_framework",
        },
        "brynjolfsson_genai_at_work": {
            "type": "economic_report", "doi": "10.1093/qje/qjae044",
            "journal": "Quarterly Journal of Economics",
            "rendering_slot": "genai_productivity",
        },
        "fourth_industrial_revolution_framing": {
            "type": "policy_report", "type_note": "authoritative_source",
            "url_pattern": "https://www.weforum.org/...",
            "rendering_slot": "theory_4ir_framing",
        },
    }
    rendering_slots = {
        "theory_task_framework": {"required": True},
        "genai_productivity": {"required": True},
        "theory_4ir_framing": {"required": False},
    }
    # RETIRED (U11): prune_contract_plans is neutralized to KEEP-ALL — every entity is
    # kept, nothing dropped, no conflicts — so it can never starve a frozen corpus.
    res = jof.prune_contract_plans(entities, rendering_slots)
    assert res.kept_entity_ids == set(entities)
    assert res.dropped_entity_ids == set()
    assert res.required_conflicts == []


def test_prune_plan_entities_rebuilds_frozen_slot():
    # ContractSlotPlan is frozen in production; prune must REBUILD the slot with
    # filtered entity_ids (dataclasses.replace), not silently fail to mutate.
    import dataclasses

    @dataclasses.dataclass(frozen=True)
    class _FrozenSlot:
        entity_ids: tuple
        title: str = "Slot"

    @dataclasses.dataclass
    class _Plan:
        ev_ids: list
        slots: list
        focus: str = ""
        frame_rows_by_entity: dict = dataclasses.field(default_factory=dict)
        contract_entities_by_id: dict = dataclasses.field(default_factory=dict)

    plan = _Plan(
        ev_ids=["keep_a", "drop_b"],
        slots=[_FrozenSlot(entity_ids=("keep_a", "drop_b"))],
        frame_rows_by_entity={"keep_a": 1, "drop_b": 2},
        contract_entities_by_id={"keep_a": 1, "drop_b": 2},
    )
    out = jof.prune_plan_entities([plan], {"keep_a"})
    assert len(out) == 1
    p = out[0]
    assert p.ev_ids == ["keep_a"]
    assert len(p.slots) == 1
    # The frozen slot was rebuilt with the dropped entity removed.
    assert list(p.slots[0].entity_ids) == ["keep_a"]
    assert "drop_b" not in p.frame_rows_by_entity
    assert "drop_b" not in p.contract_entities_by_id


def test_prune_contract_required_non_journal_is_conflict():
    # REAL shape: a non-journal entity bound (via rendering_slot) to a slot whose
    # required=True must raise a conflict (not be silently dropped).
    entities = {
        "wef_required": {
            "type": "policy_report", "type_note": "authoritative_source",
            "rendering_slot": "slot_a",
        },
    }
    rendering_slots = {
        "slot_a": {"required": True},
    }
    # RETIRED (U11): keep-all no-op — a non-journal required entity is now KEPT (no
    # journal-only conflict-abort can fire). The C2-safe eligibility path replaces it.
    res = jof.prune_contract_plans(entities, rendering_slots)
    assert res.required_conflicts == []
    assert "wef_required" in res.kept_entity_ids
    assert res.dropped_entity_ids == set()


# ── no-leak assertion ───────────────────────────────────────────────────────


def test_assert_no_leak_clean_and_dirty():
    citeable_url = "https://aeaweb.org/articles?id=10.1257/jep.33.2.3"
    sc = _sidecar(citeable_url, openalex_pub_type="article",
                  openalex_source_type="journal", is_peer_reviewed=True,
                  doi="10.1257/jep.33.2.3")
    # RETIRED (U11): assert_no_leak is neutralized to ALWAYS-CLEAN (returns []) — the
    # journal-only leak backstop can never raise/abort on a frozen corpus.
    clean = [{"source_url": citeable_url, "tier": "T1"}]
    assert jof.assert_no_leak(clean, sc) == []
    dirty = clean + [{"source_url": "https://weforum.org/4ir", "tier": "T6"}]
    assert jof.assert_no_leak(dirty, sc) == []


# ── adequacy floor ──────────────────────────────────────────────────────────


def _journal_rows(n, start=0):
    rows, sc = [], {}
    for i in range(start, start + n):
        u = f"https://journal{i}.org/article/{i}"
        rows.append({"source_url": u, "tier": "T1"})
        sc.update(_sidecar(u, openalex_pub_type="article", openalex_source_type="journal",
                           is_peer_reviewed=True, doi=f"10.{1000 + i}/{i}",
                           venue=f"Journal of Testing {i}"))
    return rows, sc


def test_adequacy_counts_distinct_venues_not_urls():
    # 12 articles but all from ONE journal venue must NOT satisfy ">=12 distinct".
    rows, sc = [], {}
    for i in range(12):
        u = f"https://onejournal.org/article/{i}"
        rows.append({"source_url": u, "tier": "T1"})
        sc.update(_sidecar(u, openalex_pub_type="article", openalex_source_type="journal",
                           is_peer_reviewed=True, doi=f"10.1/{i}",
                           venue="The Only Journal"))
    r = jof.assess_journal_only_adequacy(rows, sc, min_distinct=12)
    assert r.ok is False
    assert r.distinct_journals == 1
    assert any("too_few_distinct_journals" in x for x in r.reasons)


def test_predicate_fail_closed_on_blank_types():
    # is_peer_reviewed=True but blank source_type/pub_type (malformed) → NOT citeable.
    url = "https://j.org/a/1"
    sc = _sidecar(url, openalex_pub_type="", openalex_source_type="",
                  is_peer_reviewed=True, doi="10.1/abc")
    ok, reason = jof.is_citeable_journal(url, "T1", sc)
    assert ok is False
    assert "source_type_not_journal:blank" in reason or "pub_type_not_article:blank" in reason


def test_contract_entity_requires_journal_venue():
    # The pure predicate _entity_is_citeable_journal is unchanged (still validated): a
    # DOI-bearing entity with NO journal venue (a book/report) is NOT a citeable journal.
    book = {"type": "economic_report", "doi": "10.1/book", "journal": ""}
    real = {"type": "economic_report", "doi": "10.1257/jep.33.2.3",
            "journal": "Journal of Economic Perspectives"}
    assert jof._entity_is_citeable_journal(book)[0] is False
    assert jof._entity_is_citeable_journal(real)[0] is True
    # RETIRED (U11): prune_contract_plans itself is keep-all — the predicate no longer
    # DROPS the book entity (no journal-only starvation).
    res = jof.prune_contract_plans({"book_with_doi": book, "real_journal": real}, {})
    assert res.kept_entity_ids == {"book_with_doi", "real_journal"}
    assert res.dropped_entity_ids == set()


def test_adequacy_fails_below_min():
    rows, sc = _journal_rows(5)
    r = jof.assess_journal_only_adequacy(rows, sc, min_distinct=12)
    assert r.ok is False
    assert any("too_few_distinct_journals" in x for x in r.reasons)


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
