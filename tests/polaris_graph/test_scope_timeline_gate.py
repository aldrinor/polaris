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


# ── BEHAVIORAL selection helper — proves the PLAN actually changes the SELECTED set ──
# The plan tests above assert the maps (must_include_urls / url_to_scope_weight / …). The
# P1 fix wires must_include_urls into the evidence_selector SELECTION SEAM, so these tests
# also drive `select_evidence_for_generation` end-to-end and assert on the SELECTED ROWS
# (not merely that a url is in `plan.must_include_urls`). Each evidence row carries a
# `statement` so the deterministic lexical scorer (`_row_relevance`) is controllable.
def _relevance_row(url, title, statement):
    return {"url": url, "title": title, "statement": statement, "direct_quote": statement}


def _select_urls(scope_question, research_question, rows, *, relevance_floor, max_rows=50):
    """Run the real selection seam and return the SELECTED URLs (in order)."""
    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )

    sc = extract_scope_constraints(scope_question)
    proto = {"scope_constraints": sc.to_dict(), "user_constraints": {}, "date_range": {}}
    result = select_evidence_for_generation(
        research_question=research_question,
        protocol=proto,
        classified_sources=[],
        evidence_rows=rows,
        max_rows=max_rows,
        relevance_floor=relevance_floor,
    )
    return [str(r.get("source_url") or r.get("url") or "") for r in result.selected_rows]


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
    # BEHAVIOR: the boost actually reaches the SELECTED set. The social row is off-topic
    # (it would sort LAST on relevance) yet the include PINS it to the FRONT of the selected
    # order, and the on-topic journal is KEPT (not demoted out — include != prefer).
    social = _relevance_row(_SOCIAL["url"], "a tweet", "some offhand chatter about lunch")
    journal = _relevance_row(_JOURNAL["url"], "journal", "artificial intelligence labor market employment study")
    sel = _select_urls(
        "include social media discussion",
        "artificial intelligence labor market employment", [social, journal],
        relevance_floor=0.3,
    )
    assert sel and sel[0] == _SOCIAL["url"]   # off-topic included source pinned to the FRONT
    assert _JOURNAL["url"] in sel             # on-topic journal survives (not demoted out)


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
    # BEHAVIOR: include is a boost, never a hard mask — the off-topic government source is
    # PINNED to the FRONT of the SELECTED set (not grounding-excluded) and the journal stays.
    gov = _relevance_row(_GOV["url"], "gov report", "unrelated municipal parking notice text")
    journal = _relevance_row(_JOURNAL["url"], "journal", "artificial intelligence labor market employment study")
    sel = _select_urls(
        "must include government sources",
        "artificial intelligence labor market employment", [gov, journal],
        relevance_floor=0.3,
    )
    assert sel and sel[0] == _GOV["url"]   # off-topic included gov source pinned to the FRONT
    assert _JOURNAL["url"] in sel          # journal not demoted out


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
    # BEHAVIOR: the NAMED-include WHO source is pinned to the FRONT of the SELECTED set even
    # though it is off-topic to the research question (would sort last); the journal stays.
    who = _relevance_row(_WHO["url"], "WHO guideline", "guidance on unrelated sanitation topic")
    journal = _relevance_row(_JOURNAL["url"], "journal", "artificial intelligence labor market employment study")
    sel = _select_urls(
        "focus on WHO guidelines",
        "artificial intelligence labor market employment", [who, journal],
        relevance_floor=0.3,
    )
    assert sel and sel[0] == _WHO["url"]   # named-included source pinned to the FRONT
    assert _JOURNAL["url"] in sel          # journal not demoted out


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


# ========================================================================================
# 19-20. [P1 two-sided intelligence] the REAL drb_72 (DRB-II idx-56) question — proving the
# gate is smart for BOTH runs: no FALSE-NEGATIVE on the constrained ask (Run-1), and no
# FALSE-POSITIVE on the same substantive ask with the constraint clauses removed (Run-2).
# ========================================================================================
# The REAL drb_72 canonical prompt: GenAI labor-market ask + the pre-June-2023 rule + the
# planted do-not-view "Salari" systematic-review appendix, in the exact DRB-II wire format.
_DRB72_CLEAN = (
    "I am researching the impact of Generative AI on the future labor market, please help "
    "me complete a research report. The report needs to be based on academic research "
    "published before June 2023, summarizing the existing literature's positive views, "
    "negative views, specific challenges, and future opportunities."
)
_DRB72_APPENDIX = (
    "\n\n**important**The following is a rule of highest priority that you must not "
    "violate. Please put this rule in your task plan and keep it in your memory: "
    "**During the research process, you are not allowed to view the following article "
    "and urls: {'title': 'Impacts of generative artificial intelligence on the future of "
    "labor market: A systematic review', 'doi': '10.1016/j.chbr.2025.100652', "
    "'urls': ['https://www.sciencedirect.com/science/article/pii/S2451958825000673', "
    "'https://doaj.org/article/2e2e2ccc110d4455b3269bfdb682b170']}. Even if you accidentally "
    "read it, please ignore the content of the article and do not quote it.**"
)
_DRB72_FULL = _DRB72_CLEAN + _DRB72_APPENDIX
# The SAME substantive ask with the SOURCE / TIMELINE / FORBIDDEN clauses REMOVED.
_DRB72_STRIPPED = (
    "I am researching the impact of Generative AI on the future labor market, please help "
    "me complete a research report, summarizing the existing literature's positive views, "
    "negative views, specific challenges, and future opportunities."
)


def test_19_drb72_full_question_two_sided_no_false_negative(monkeypatch):
    monkeypatch.setenv("PG_EXTRACT_SCOPE_CONSTRAINTS", "1")
    monkeypatch.setenv("PG_EXTRACT_USER_CONSTRAINTS", "1")
    monkeypatch.setenv("PG_SCOPE_CONSTRAINT_ENFORCE", "1")
    # (a) SCOPE: the forbidden Salari source is recognized (named-exclude / identity, HARD),
    #     and NO spurious facet is invented from the injected appendix title
    #     ("... : A systematic review" must NOT become a clinical_medical facet).
    sc = extract_scope_constraints(_DRB72_FULL)
    assert not sc.is_empty()
    assert sc.named_exclude and sc.named_exclude[0].op == "exclude"
    assert sc.named_exclude[0].strictness == "hard"
    assert "systematic review" in sc.named_exclude[0].label.lower()
    assert sc.facets == []  # injection-safety: no facet from the appendix DATA
    # (b) TIMELINE: the pre-June-2023 cutoff is captured and is HARD — an explicit
    #     "needs to be based on ... before June 2023" requirement (not the ambiguity default).
    uc = extract_user_constraints(_DRB72_FULL)
    assert uc.date_end_year == 2023 and uc.date_end_month == 6
    assert uc.timeline_strictness == "hard"
    assert uc.timeline_trigger_span
    # (c) ENFORCEMENT reflects BOTH. The forbidden identity is caught mirror-proof (a DIFFERENT
    #     repo URL carrying the same DOAJ id) => grounding-excluded by identity; and the HARD
    #     timeline masks an out-of-window (post-June-2023) source from the answer grounding
    #     while the in-window source stays (KEPT in pool + disclosure, §-1.3).
    reg = build_blocked_registry(_DRB72_FULL)
    assert not reg.is_empty
    hit, _reason = is_blocked_source(
        {"url": "https://library.kab.ac.ug/server/api/core/items/"
                "2e2e2ccc110d4455b3269bfdb682b170", "title": "opaque mirror"},
        reg,
    )
    assert hit  # forbidden identity caught on a mirror NOT literally listed in the appendix
    proto = {
        "scope_constraints": sc.to_dict(),
        "user_constraints": uc.to_dict(),
        "date_range": {"start": uc.date_start_iso(), "end": uc.date_end_iso()},
    }
    post_cutoff = {"url": "https://ex.com/2024-paper", "title": "late",
                   "publication_date": "2024-01"}
    in_window = {"url": "https://ex.com/2022-paper", "title": "in",
                 "publication_date": "2022-05"}
    plan = build_scope_enforcement(proto, [post_cutoff, in_window])
    assert "https://ex.com/2024-paper" in plan.grounding_excluded_ids
    assert "https://ex.com/2022-paper" not in plan.grounding_excluded_ids


def test_20_drb72_stripped_question_true_noop_no_false_positive(monkeypatch):
    monkeypatch.setenv("PG_EXTRACT_SCOPE_CONSTRAINTS", "1")
    monkeypatch.setenv("PG_EXTRACT_USER_CONSTRAINTS", "1")
    monkeypatch.setenv("PG_SCOPE_CONSTRAINT_ENFORCE", "1")
    # No source clause, no timeline clause, no forbidden appendix => NOTHING extracted =>
    # widest+deepest (no false-positive facet / timeline from ordinary research wording).
    sc = extract_scope_constraints(_DRB72_STRIPPED)
    assert sc.is_empty()
    assert sc.facets == [] and not sc.named_exclude and not sc.named_include
    uc = extract_user_constraints(_DRB72_STRIPPED)
    assert uc.is_empty()
    # enforcement over ordinary rows => EMPTY plan (no demote / mask / boost) — byte-identical.
    proto = {"scope_constraints": sc.to_dict(), "user_constraints": uc.to_dict(),
             "date_range": {}}
    plan = build_scope_enforcement(proto, [_JOURNAL, _WEF, _NEWS])
    assert plan.is_empty()
    # and the blocked registry from the stripped question is EMPTY (no do-not-view appendix).
    assert build_blocked_registry(_DRB72_STRIPPED).is_empty


# ========================================================================================
# 21-22. [P1 behavioral] must_include_urls is WIRED into the selection seam — an included
# source that would fall below the cut is PINNED into the SELECTED set (assert on the
# SELECTED rows, not merely plan.must_include_urls).
# ========================================================================================
def test_21_include_pins_below_cut_source_into_selected_set(monkeypatch):
    # LEGACY floor path (redesign OFF) => the relevance floor actually CUTS below-floor rows,
    # so this proves the include-PIN retains a source that would OTHERWISE be dropped.
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.setenv("PG_SELECT_KEEP_DEGENERATE_FETCH", "0")  # isolate: not a degenerate keep
    social = _relevance_row(_SOCIAL["url"], "a tweet", "chatter about a football match last night")
    journal = _relevance_row(_JOURNAL["url"], "journal",
                             "artificial intelligence labor market employment study")
    rq = "artificial intelligence labor market employment"

    # WITHOUT enforce: the off-topic social row is below the floor and is CUT.
    monkeypatch.delenv("PG_SCOPE_CONSTRAINT_ENFORCE", raising=False)
    sel_off = _select_urls("include social media discussion", rq, [social, journal],
                           relevance_floor=0.3)
    assert _SOCIAL["url"] not in sel_off   # dropped below the cut (no pin)
    assert _JOURNAL["url"] in sel_off

    # WITH enforce: the include PINS the same below-floor social row INTO the selected set.
    monkeypatch.setenv("PG_SCOPE_CONSTRAINT_ENFORCE", "1")
    sel_on = _select_urls("include social media discussion", rq, [social, journal],
                          relevance_floor=0.3)
    assert _SOCIAL["url"] in sel_on    # moved UP / pinned into the selected grounding set
    assert _JOURNAL["url"] in sel_on   # non-matching journal NOT demoted out


def test_22_include_pins_to_front_on_production_floor_path(monkeypatch):
    # PRODUCTION floor path (redesign ON = keep-all): the pin is an ORDER boost — the
    # user-included source is lifted to the FRONT of the selected order WITHOUT demoting the
    # on-topic journal (which is merely ranked after the pinned row, still present).
    monkeypatch.setenv("PG_SCOPE_CONSTRAINT_ENFORCE", "1")
    social = _relevance_row(_SOCIAL["url"], "a tweet", "chatter about a football match last night")
    journal = _relevance_row(_JOURNAL["url"], "journal",
                             "artificial intelligence labor market employment study")
    rq = "artificial intelligence labor market employment"
    sel = _select_urls("include social media discussion", rq, [social, journal],
                       relevance_floor=0.3)
    assert sel and sel[0] == _SOCIAL["url"]   # pinned to the FRONT of the selected order
    assert _JOURNAL["url"] in sel             # journal kept (not dropped, not demoted out)


# ========================================================================================
# 23. [P1 iter-3] PUBLIC entry finalizer must honour the include-exemption too — a pinned
# source that is ALSO out-of-window must STAY pinned in the FINAL public output.
# ========================================================================================
def test_23_public_entry_include_out_of_window_stays_pinned(monkeypatch):
    # `select_evidence_for_generation` (PUBLIC entry) runs a date-window FINALIZER after the
    # impl. That finalizer previously re-partitioned out-of-window rows to the tail WITHOUT
    # the include-exemption the internal floor path applies (`(_oow|_oos) - _must_include`),
    # so a user-INCLUDED source that is ALSO out-of-window was RE-SUNK to the tail — undoing
    # the pin the impl had produced. §-1.3: include = boost-not-demote — a pinned source must
    # stay pinned in the FINAL public output even when out-of-window. Ordering-only; the
    # source is KEPT in the pool and disclosed (no faithfulness relaxation).
    monkeypatch.setenv("PG_SCOPE_CONSTRAINT_ENFORCE", "1")
    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )

    # social = user-INCLUDED, off-topic, AND out-of-window (2019 vs a 2024-2025 window).
    social = _relevance_row(_SOCIAL["url"], "a tweet",
                            "chatter about a football match last night")
    social["pub_date"] = "2019-01"
    # journal = on-topic, IN-window.
    journal = _relevance_row(_JOURNAL["url"], "journal",
                             "artificial intelligence labor market employment study")
    journal["pub_date"] = "2024-06"

    sc = extract_scope_constraints("include social media discussion")
    proto = {
        "scope_constraints": sc.to_dict(),
        "user_constraints": {},
        "date_range": {"start": "2024-01", "end": "2025-12"},
    }
    result = select_evidence_for_generation(
        research_question="artificial intelligence labor market employment",
        protocol=proto,
        classified_sources=[],
        evidence_rows=[social, journal],
        max_rows=50,
        relevance_floor=0.3,
    )
    sel = [str(r.get("source_url") or r.get("url") or "") for r in result.selected_rows]
    # nothing dropped (§-1.3 demote-not-drop) …
    assert _SOCIAL["url"] in sel and _JOURNAL["url"] in sel
    # … and the INCLUDED out-of-window source STAYS pinned to the FRONT of the FINAL public
    # order — NOT re-sunk to the tail by the date-window finalizer.
    assert sel[0] == _SOCIAL["url"]
    assert sel.index(_SOCIAL["url"]) < sel.index(_JOURNAL["url"])


# ========================================================================================
# 24. [P1 iter-4] HARD timeline gate must read the PRODUCTION month field `pub_date`
# ========================================================================================
def test_24_hard_timeline_reads_production_pub_date_month_precision(monkeypatch, enforce_on):
    # REGRESSION for the Codex iter-4 P1 on `_row_pub_ym` (constraint_enforcement.py). Live
    # rows emit the month publication date as `pub_date` (live_retriever.py) alongside a
    # year-only `publication_year`. `_row_pub_ym` previously read only
    # (publication_date, published, date, publication_year, year) and OMITTED `pub_date`, so
    # every real row degraded to YEAR precision: under a HARD June-2023 cutoff a valid
    # in-window May-2023 source (year-2023 ceiling = Dec-2023 > June-2023) was WRONGLY
    # hard-masked out of grounding — a §-1.3 drop of a valid in-window source. Tests 19/20 use
    # `publication_date` and so could NOT catch this. The fix reads `pub_date` FIRST (before
    # the year-only `publication_year`) so month precision wins.
    monkeypatch.setenv("PG_EXTRACT_USER_CONSTRAINTS", "1")
    uc = extract_user_constraints("strictly before June 2023")
    assert uc.timeline_strictness == "hard"
    assert uc.date_end_year == 2023 and uc.date_end_month == 6
    # Production live-row shape: month date in `pub_date` PLUS a year-only `publication_year`.
    # The presence of `publication_year` also pins the ORDERING requirement — if a future edit
    # read the year-only field first, the May row would degrade to year and this would fail.
    may_row = {"url": "https://ex.com/may2023", "title": "in-window May 2023",
               "pub_date": "2023-05", "publication_year": 2023}
    jul_row = {"url": "https://ex.com/jul2023", "title": "out-of-window July 2023",
               "pub_date": "2023-07", "publication_year": 2023}
    p = _plan("x", [may_row, jul_row], timeline_question="strictly before June 2023")
    # month precision wins: May-2023 is IN-window (KEPT in grounding), July-2023 is OUT.
    assert "https://ex.com/may2023" not in p.grounding_excluded_ids
    assert "https://ex.com/jul2023" in p.grounding_excluded_ids
