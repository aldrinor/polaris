"""I-scope-001 — flexible per-question SCOPE + TIMELINE compliance gate test matrix.

The gate is a SELECTION / WEIGHT / DISCLOSURE layer over existing machinery — NOT a new hard
gate. The ONE hard gate (the faithfulness engine) stays byte-untouched. DNA §-1.3: WEIGHT-
DON'T-FILTER; the NO-constraint default is widest+deepest and byte-identical to today.

Each test asserts extraction (op + strictness + trigger_span) AND enforcement outcome
(weight-demote vs hard-mask vs include-boost). The no-constraint row asserts a TRUE
byte-identical no-op. RED before the build (the symbols did not exist / were RED against a
clean tree); GREEN after.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.retrieval.blocked_reference_registry import (
    BlockedRegistry,
    build_blocked_registry,
    is_blocked_source,
)
from src.polaris_graph.retrieval.constraint_enforcement import (
    ScopeEnforcementPlan,
    build_scope_enforcement,
)
from src.polaris_graph.retrieval.intake_constraint_extractor import (
    extract_scope_constraints,
    extract_user_constraints,
)
from src.polaris_graph.retrieval.scope_facet_classifier import (
    classify_source_facets,
    load_scope_ontology,
)


# ── synthetic corpus rows with clear facet signals (offline, deterministic) ───────────────
_JOURNAL = {"url": "https://www.nature.com/articles/s41586-023-1",
            "doi": "10.1038/s41586-023-1", "title": "A peer-reviewed journal paper"}
_GOV = {"url": "https://www.whitehouse.gov/briefing/report", "title": "A gov report"}
_PATENT = {"url": "https://patents.google.com/patent/US12345", "title": "A patent"}
_SOCIAL = {"url": "https://twitter.com/x/status/1", "title": "a tweet"}
_WEF = {"url": "https://www.weforum.org/reports/future-of-jobs-2025", "title": "WEF report"}
_NEWS = {"url": "https://www.reuters.com/technology/story", "title": "news story"}
_CA = {"url": "https://www.statcan.gc.ca/data/housing", "title": "Canadian data"}
_WHO = {"url": "https://www.who.int/publications/guidelines-x", "title": "WHO guideline"}


@pytest.fixture()
def enforce_on(monkeypatch):
    monkeypatch.setenv("PG_SCOPE_CONSTRAINT_ENFORCE", "1")


def _facet(sc, facet_id):
    for f in sc.facets:
        if f.facet_id == facet_id:
            return f
    return None


def _plan(question, rows, *, timeline_question=None):
    sc = extract_scope_constraints(question)
    proto = {"scope_constraints": sc.to_dict(), "user_constraints": {}, "date_range": {}}
    if timeline_question is not None:
        uc = extract_user_constraints(timeline_question)
        proto["user_constraints"] = uc.to_dict()
        proto["date_range"] = {"start": uc.date_start_iso(), "end": uc.date_end_iso()}
    return build_scope_enforcement(proto, rows)


# ========================================================================================
# 1. Law/legal scope (prefer, weight)
# ========================================================================================
def test_01_law_prefer_weight(enforce_on):
    sc = extract_scope_constraints("focus on case law and statutes")
    f = _facet(sc, "law_legal")
    assert f is not None and f.op == "prefer" and f.strictness == "weight"
    assert "focus on" in f.trigger_span.lower()
    p = _plan("focus on case law and statutes", [_JOURNAL, _GOV])
    # a non-legal credible source is DEMOTED-and-KEPT (weight<1, nothing dropped)
    assert p.url_to_scope_weight.get(_JOURNAL["url"], 1.0) < 1.0
    assert not p.grounding_excluded_ids


# ========================================================================================
# 2. Patent scope (prefer, hard = restrict-to)
# ========================================================================================
def test_02_patent_hard_restrict(enforce_on):
    sc = extract_scope_constraints("use patent filings only")
    f = _facet(sc, "patent")
    assert f is not None and f.op == "prefer" and f.strictness == "hard"
    assert "only" in f.trigger_span.lower()
    p = _plan("use patent filings only", [_PATENT, _JOURNAL, _WEF])
    # non-patent ids masked from grounding; patent KEPT
    assert _JOURNAL["url"] in p.grounding_excluded_ids
    assert _WEF["url"] in p.grounding_excluded_ids
    assert _PATENT["url"] not in p.grounding_excluded_ids


# ========================================================================================
# 3. Government scope (prefer, weight)
# ========================================================================================
def test_03_gov_prefer_weight(enforce_on):
    sc = extract_scope_constraints("prioritize government sources")
    f = _facet(sc, "government")
    assert f is not None and f.op == "prefer" and f.strictness == "weight"
    p = _plan("prioritize government sources", [_GOV, _JOURNAL])
    assert p.url_to_scope_weight.get(_GOV["url"], 1.0) == 1.0  # gov full weight
    assert p.url_to_scope_weight.get(_JOURNAL["url"], 1.0) < 1.0
    assert not p.grounding_excluded_ids  # weight => nothing hard-masked


# ========================================================================================
# 4. Central-bank / finance scope — WEF/OECD stay at credibility weight (operator lock)
# ========================================================================================
def test_04_central_bank_weight_not_filter(enforce_on):
    sc = extract_scope_constraints("central bank publications on inflation")
    f = _facet(sc, "central_bank_finance")
    assert f is not None and f.op == "prefer" and f.strictness == "weight"
    p = _plan("central bank publications on inflation", [_WEF])
    # a WEF report is DEMOTED but KEPT (weight>0, never dropped) — weight-not-filter
    w = p.url_to_scope_weight.get(_WEF["url"], 1.0)
    assert 0.0 < w < 1.0
    assert _WEF["url"] not in p.grounding_excluded_ids


# ========================================================================================
# 5. [FIX-5] include-also vs prefer — the distinguishing case
# ========================================================================================
def test_05_include_also_does_not_demote_journals(enforce_on):
    sc = extract_scope_constraints("include social media discussion")
    f = _facet(sc, "social_web")
    assert f is not None and f.op == "include" and f.strictness == "weight"
    p = _plan("include social media discussion", [_SOCIAL, _JOURNAL])
    assert _SOCIAL["url"] in p.must_include_urls           # social boosted
    assert _JOURNAL["url"] not in p.url_to_scope_weight    # journal NOT demoted
    # contrast: "focus on social media" DOES demote the journal
    p2 = _plan("focus on social media", [_SOCIAL, _JOURNAL])
    assert p2.url_to_scope_weight.get(_JOURNAL["url"], 1.0) < 1.0


# ========================================================================================
# 6. [FIX-4] must-include is NOT hard
# ========================================================================================
def test_06_must_include_is_weight_not_hard(enforce_on):
    sc = extract_scope_constraints("must include government sources")
    f = _facet(sc, "government")
    assert f is not None and f.op == "include" and f.strictness == "weight"
    p = _plan("must include government sources", [_GOV, _JOURNAL])
    assert not p.grounding_excluded_ids                       # no hard mask
    assert _JOURNAL["url"] not in p.url_to_scope_weight       # non-gov NOT demoted


# ========================================================================================
# 7. Journal scope (prefer, weight, veto-safe) — no distinct-journal COUNT floor
# ========================================================================================
def test_07_journal_prefer_weight_no_count_floor(enforce_on):
    sc = extract_scope_constraints("focus on peer-reviewed journals")
    f = _facet(sc, "peer_reviewed_journal")
    assert f is not None and f.op == "prefer" and f.strictness == "weight"
    p = _plan("focus on peer-reviewed journals", [_JOURNAL, _WEF])
    assert p.url_to_scope_weight.get(_WEF["url"], 1.0) < 1.0  # non-journal demoted-kept
    assert not p.grounding_excluded_ids                       # weight => nothing masked


# ========================================================================================
# 8. Journal scope (hard, disclose-and-proceed)
# ========================================================================================
def test_08_journal_hard_masks_nonjournals(enforce_on):
    sc = extract_scope_constraints("journal articles ONLY")
    f = _facet(sc, "peer_reviewed_journal")
    assert f is not None and f.op == "prefer" and f.strictness == "hard"
    p = _plan("journal articles ONLY", [_JOURNAL, _WEF, _NEWS])
    assert _WEF["url"] in p.grounding_excluded_ids
    assert _NEWS["url"] in p.grounding_excluded_ids
    assert _JOURNAL["url"] not in p.grounding_excluded_ids
    # disclosed-and-kept: the masked rows are recorded, not deleted
    assert any(r["source_url"] == _WEF["url"] for r in p.scope_disclosed_rows)


# ========================================================================================
# 9. Exclude-facet (hard)
# ========================================================================================
def test_09_exclude_facet_hard(enforce_on):
    sc = extract_scope_constraints("do not use social media")
    f = _facet(sc, "social_web")
    assert f is not None and f.op == "exclude" and f.strictness == "hard"
    p = _plan("do not use social media", [_SOCIAL, _JOURNAL])
    assert _SOCIAL["url"] in p.grounding_excluded_ids
    assert _JOURNAL["url"] not in p.grounding_excluded_ids  # others untouched


# ========================================================================================
# 10. Timeline window (weight)
# ========================================================================================
def test_10_timeline_weight(monkeypatch, enforce_on):
    monkeypatch.setenv("PG_EXTRACT_USER_CONSTRAINTS", "1")
    uc = extract_user_constraints("studies since 2020, before June 2023")
    assert uc.timeline_strictness == "weight"
    assert uc.date_end_year == 2023 and uc.date_end_month == 6
    late = {"url": "https://ex.com/jul2023", "title": "late", "year": 2023,
            "publication_date": "2023-07"}
    p = _plan("x", [late, _JOURNAL],
              timeline_question="studies since 2020, before June 2023")
    # weight timeline => NOT hard-masked (the selector demotes it instead)
    assert not p.grounding_excluded_ids


# ========================================================================================
# 11. [FIX-3] Timeline window (hard)
# ========================================================================================
def test_11_timeline_hard_excludes(monkeypatch, enforce_on):
    monkeypatch.setenv("PG_EXTRACT_USER_CONSTRAINTS", "1")
    uc = extract_user_constraints("strictly before June 2023")
    assert uc.timeline_strictness == "hard"
    assert uc.timeline_trigger_span  # the verbatim phrase was captured
    late = {"url": "https://ex.com/2024", "title": "late", "year": 2024}
    p = _plan("x", [late, _JOURNAL], timeline_question="strictly before June 2023")
    assert "https://ex.com/2024" in p.grounding_excluded_ids  # out-of-window masked


# ========================================================================================
# 12. [FIX-1] Named must-exclude with mirrors (hard, identity)
# ========================================================================================
_BLOCKED_DOAJ_ID = "2e2e2ccc110d4455b3269bfdb682b170"
_BLOCKED_TITLE = (
    "Impacts of generative artificial intelligence on the future of "
    "labor market: A systematic review"
)
_DO_NOT_VIEW = (
    "Research GenAI on labor."
    "\n\n**important**The following is a rule of highest priority that you must not "
    "violate. During the research process, you are not allowed to view the following "
    "article and urls: {'title': '" + _BLOCKED_TITLE + "', "
    "'doi': '10.1016/j.chbr.2025.100652', 'urls': "
    "['https://doaj.org/article/" + _BLOCKED_DOAJ_ID + "']}. Even if you accidentally "
    "read it, please ignore the content of the article and do not quote it.**"
)
_KAB_MIRROR = "https://library.kab.ac.ug/server/api/core/items/" + _BLOCKED_DOAJ_ID


def test_12_named_exclude_mirror_by_identity(tmp_path):
    reg = build_blocked_registry(_DO_NOT_VIEW)
    assert _BLOCKED_DOAJ_ID in reg.doaj_ids
    # a DIFFERENT mirror URL with the SAME DOAJ id is caught by identity (not exact-url).
    hit, reason = is_blocked_source({"url": _KAB_MIRROR, "title": "opaque repo item"}, reg)
    assert hit and reason.startswith("doaj:")
    # exact-URL-only matching would MISS it (the listed url is doaj.org, not kab).
    assert reg.is_blocked(url="https://doaj.org/OTHER")[0] is False
    # claim-level redaction fires REGARDLESS of a D8-SUPPORTED verdict.
    from src.polaris_graph.retrieval.forbidden_identity_gate import scope_gate_redact_claims

    claims = [
        {"claim_id": "c1", "d8_verdict": "SUPPORTED",
         "supporting_sources": [{"url": _KAB_MIRROR}]},
        {"claim_id": "c2", "d8_verdict": "SUPPORTED",
         "supporting_sources": [{"url": "https://www.nature.com/articles/keep"}]},
    ]
    kept, redacted = scope_gate_redact_claims(claims, reg, run_dir=tmp_path)
    assert {c["claim_id"] for c in kept} == {"c2"}
    assert redacted and redacted[0]["claim_id"] == "c1"


# ========================================================================================
# 13. Named must-include (include, boost)
# ========================================================================================
def test_13_named_include_boost(enforce_on):
    sc = extract_scope_constraints("focus on WHO guidelines")
    assert any(n.op == "include" and "WHO" in n.label for n in sc.named_include)
    p = _plan("focus on WHO guidelines", [_WHO, _JOURNAL])
    assert _WHO["url"] in p.must_include_urls
    # an unnamed credible source is NOT demoted merely for being unnamed
    assert _JOURNAL["url"] not in p.url_to_scope_weight


# ========================================================================================
# 14. Jurisdiction scope (prefer, weight)
# ========================================================================================
def test_14_jurisdiction_prefer_weight(enforce_on):
    sc = extract_scope_constraints("Canadian sources on housing")
    f = _facet(sc, "jurisdiction:CA")
    assert f is not None and f.op == "prefer" and f.strictness == "weight"
    assert classify_source_facets(_CA)[0] & {"jurisdiction:CA"}
    p = _plan("Canadian sources on housing", [_CA, _JOURNAL])
    assert p.url_to_scope_weight.get(_JOURNAL["url"], 1.0) < 1.0  # non-CA demoted-kept
    assert p.url_to_scope_weight.get(_CA["url"], 1.0) == 1.0


# ========================================================================================
# 15. [P1] No-constraint TRUE no-op — byte-identical to flag-OFF
# ========================================================================================
def test_15_no_constraint_true_noop(monkeypatch):
    q = "What is the impact of generative AI on the labor market?"
    sc = extract_scope_constraints(q)
    uc = extract_user_constraints(q)
    assert sc.is_empty()
    assert uc.is_empty()
    # enforce ON but NO constraint => empty plan (no weight, no mask, no boost)
    monkeypatch.setenv("PG_SCOPE_CONSTRAINT_ENFORCE", "1")
    plan = build_scope_enforcement(
        {"scope_constraints": sc.to_dict(), "user_constraints": uc.to_dict(),
         "date_range": {}},
        [_JOURNAL, _WEF, _NEWS],
    )
    assert plan.is_empty()
    assert not plan.url_to_scope_weight
    assert not plan.grounding_excluded_ids
    assert not plan.must_include_urls
    assert not plan.out_of_scope_urls


def test_15b_enforce_flag_off_is_empty_plan(monkeypatch):
    # flag OFF => empty plan even WITH a stated scope (byte-identical selection).
    monkeypatch.delenv("PG_SCOPE_CONSTRAINT_ENFORCE", raising=False)
    sc = extract_scope_constraints("use patent filings only")
    plan = build_scope_enforcement(
        {"scope_constraints": sc.to_dict(), "user_constraints": {}, "date_range": {}},
        [_JOURNAL, _PATENT],
    )
    assert plan.is_empty()


# ========================================================================================
# 16. Ambiguity => prefer/weight (deontic safety) — HARD requires an explicit token
# ========================================================================================
def test_16_ambiguity_defaults_to_prefer_weight():
    sc = extract_scope_constraints("journal articles")
    f = _facet(sc, "peer_reviewed_journal")
    assert f is not None and f.op == "prefer" and f.strictness == "weight"  # NOT hard


# ========================================================================================
# 17. Fail-open on extractor error — a malformed LLM reply invents NO facet
# ========================================================================================
def test_17_fail_open_on_bad_llm_reply():
    def _bad_llm(_prompt):
        return "not json at all {{{ broken"

    sc = extract_scope_constraints(
        "some prose the regex cannot resolve to a facet", llm_fn=_bad_llm
    )
    assert sc.is_empty()  # no facet invented on a bad reply


# ========================================================================================
# 18. Faithfulness untouched — scope only reorders / masks-from-surface, never re-scores
# ========================================================================================
def test_18_faithfulness_inputs_untouched(enforce_on):
    rows = [_JOURNAL, _WEF, _PATENT]
    p = _plan("use patent filings only", rows)
    # the plan is advisory maps only — it NEVER mutates or removes a row from the pool.
    assert rows == [_JOURNAL, _WEF, _PATENT]
    # a source that REMAINS in grounding (patent) carries NO scope re-score.
    assert _PATENT["url"] not in p.url_to_scope_weight
    assert _PATENT["url"] not in p.grounding_excluded_ids
    # hard-masked sources are DISCLOSED + KEPT, not deleted (§-1.3).
    for r in p.scope_disclosed_rows:
        assert r["disclosed"].startswith("hard_excluded_from_grounding_kept")


# ========================================================================================
# ontology smoke — every requested facet id resolves in the config (LAW VI, extensible)
# ========================================================================================
def test_ontology_loads_and_covers_facets():
    ont = load_scope_ontology()
    ids = {str(f.get("id")) for f in ont["facets"]}
    for required in ("peer_reviewed_journal", "law_legal", "patent", "government",
                     "central_bank_finance", "news_media", "social_web",
                     "clinical_medical", "analyst_report"):
        assert required in ids, required
    assert ont["op_lexicon"]["restrict_hard"]  # deontic lexicon present
