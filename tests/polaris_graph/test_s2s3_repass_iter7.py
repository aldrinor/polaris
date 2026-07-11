"""S2/S3 re-pass iter-7 (Fable full fix-list) — pure-function offline tests.

Covers: Fix 1a (line-prompt junk/non-claim class naming), Fix 1b (no-claim basket-founding
pool), Fix 1c (single-sentence error-page whole-drop), Fix 2a (whole-source OFF-TOPIC
tie-break re-judge), Fix 3 (consolidation soft numeric-set prior), Fix 4 (parity-safe
cross-host title-union content verdict). No GPU / no live LLM (deterministic stubs).
"""
from __future__ import annotations

import os

from src.polaris_graph.retrieval import line_screen as L
from src.polaris_graph.synthesis import finding_dedup as F
from src.polaris_graph.synthesis import consolidation_nli as C

_Q = "What are the labor-market impacts of generative AI on paralegals and data-entry clerks?"
_REAL = (
    "Generative artificial intelligence is projected to expose roughly forty six percent of "
    "current job tasks to some degree of automation over the coming decade across occupations."
)


# ── Fix 1a: line prompt names the new NON_CLAIM / JUNK classes ────────────────
def test_fix1a_prompt_names_new_boilerplate_classes():
    p = L.build_line_prompt(_Q, "", "", [(0, "line")])
    assert "CATALOGUING" in p and "ISSN" in p
    assert "CORRESPONDENCE" in p
    assert "PERCENTAGE SALAD" in p
    assert "try again" in p.lower()  # JUNK error/retry class
    assert "reported statistic" in p and "KEEP" in p  # numeric fail-open preserved


# ── Fix 1c: single-sentence error / challenge page ───────────────────────────
def test_fix1c_error_page_detection_and_failopen():
    assert L._body_is_single_sentence_error("Wait a moment and try again.")
    assert L._body_is_single_sentence_error("Something went wrong. Please try again.")
    assert not L._body_is_single_sentence_error(_REAL)   # real prose fail-open
    assert not L._body_is_single_sentence_error("")
    assert L._row_is_error_page({"direct_quote": "Wait a moment and try again."})
    assert not L._row_is_error_page({"direct_quote": _REAL})
    assert L._body_is_shell("Wait a moment and try again.")


def test_fix1c_error_page_kill_switch():
    os.environ["PG_LINE_SCREEN_ERROR_PAGE"] = "0"
    try:
        assert not L._row_is_error_page({"direct_quote": "Wait a moment and try again."})
    finally:
        os.environ.pop("PG_LINE_SCREEN_ERROR_PAGE", None)


# ── Fix 2a: whole-source OFF-TOPIC tie-break ─────────────────────────────────
def test_fix2a_tiebreak_prompt_and_parser():
    prompt = L.build_offtopic_tiebreak_prompt(_Q, "This paper studies a murine stress model.")
    assert _Q in prompt  # FULL question passed untruncated
    assert "VERDICT: OFF_TOPIC" in prompt and "VERDICT: KEEP" in prompt
    assert L._whole_source_offtopic_tiebreak(_Q, "x", lambda _p: "VERDICT: OFF_TOPIC") is True
    assert L._whole_source_offtopic_tiebreak(_Q, "x", lambda _p: "VERDICT: KEEP") is False
    assert L._whole_source_offtopic_tiebreak(_Q, "x", lambda _p: "???") is None

    def _boom(_p):
        raise RuntimeError("down")

    assert L._whole_source_offtopic_tiebreak(_Q, "x", _boom) is None


def _stub_llm(tiebreak_verdict):
    def _llm(prompt):
        if "TIE-BREAK topic judge" in prompt:
            return "VERDICT: " + tiebreak_verdict
        out = []
        for line in prompt.splitlines():
            s = line.strip()
            if s and s[0].isdigit() and ":" in s:
                idx = s.split(":", 1)[0].strip()
                if idx.isdigit():
                    out.append(f"{idx}: OFF_TOPIC")
        return "\n".join(out)
    return _llm


def test_fix2a_screen_source_tiebreak_integration():
    body = ("Climate risks in equity markets are rising.\n"
            "Stranded assets threaten oil majors.\n"
            "Carbon pricing reshapes portfolios.")
    row = {"evidence_id": "ev_x", "direct_quote": body, "source_url": "https://ex.org/climate"}
    res_drop = L.screen_source(row, _Q, _stub_llm("OFF_TOPIC"))
    assert res_drop.whole_dropped and res_drop.n_kept == 0
    assert "tiebreak" in (res_drop.whole_drop_reason or "")
    res_keep = L.screen_source(row, _Q, _stub_llm("KEEP"))
    assert not res_keep.whole_dropped and res_keep.n_kept == 3 and res_keep.disagreement


# ── Fix 1b: no-claim basket-founding pool ────────────────────────────────────
def test_fix1b_pure_boilerplate_gate():
    assert F._row_is_pure_boilerplate({"direct_quote": "ISSN 1972-4942. All rights reserved."})
    assert not F._row_is_pure_boilerplate(
        {"direct_quote": "Generative AI could expose 46% of jobs to automation by 2035."})
    assert not F._row_is_pure_boilerplate({"direct_quote": "Unemployment rose 2%."})  # fail-open
    assert "no_claim_basket_pooled_count" in F.FindingDedupResult.__dataclass_fields__


def test_fix1b_kill_switch():
    os.environ["PG_FINDING_NOCLAIM_BASKET_POOL"] = "0"
    try:
        assert F._noclaim_basket_pool_enabled() is False
    finally:
        os.environ.pop("PG_FINDING_NOCLAIM_BASKET_POOL", None)
    assert F._noclaim_basket_pool_enabled() is True


# ── Fix 4: parity-safe cross-host title-union content verdict ────────────────
def test_fix4_title_key_stays_host_agnostic():
    lt = "The Projected Impact of Generative Artificial Intelligence on the United States Labor Market"
    ka = F._title_alone_key({"title": lt, "source_url": "https://a.org/x.pdf"})
    kb = F._title_alone_key({"title": lt, "source_url": "https://b.org/y.pdf"})
    assert ka == kb and ka.startswith("titlealone:")          # render parity preserved
    assert F._title_alone_key({"title": "Paralegal"}) == ""    # short title never signs


def test_fix4_content_verdict_tristate():
    rows = [
        {"direct_quote": "Generative AI could automate 46 percent of paralegal tasks within a decade."},
        {"direct_quote": "Nearly half of paralegal tasks, about 46 percent, are exposed to AI automation."},
        {"direct_quote": "The best sourdough starter needs equal parts flour and water fed daily."},
    ]
    assert F._group_content_verdict([0], [1], rows, entail_fn=lambda a, b: True) is True
    assert F._group_content_verdict([0], [2], rows, entail_fn=lambda a, b: ("46" in a and "46" in b)) is False
    assert F._group_content_verdict([0], [1], rows, entail_fn=lambda a, b: None) is None
    os.environ["PG_SAMEWORK_CONTENT_CONFIRM"] = "0"
    try:
        assert F._group_content_verdict([0], [1], rows, entail_fn=lambda a, b: True) is None
    finally:
        os.environ.pop("PG_SAMEWORK_CONTENT_CONFIRM", None)


# ── Fix 3: consolidation soft numeric-set prior ──────────────────────────────
def test_fix3_value_set_reads_text_numbers():
    row = [{"direct_quote": "AI raises GDP by 1.5% in the low case and 3.7% in the high case."}]
    vs = F._cluster_value_set(("ai", "raise", 1.5), row, [0])
    assert 1.5 in vs and 3.7 in vs
    # year-like bare integers are excluded from the prior
    vs2 = F._cluster_value_set(("x", "y", 5.5), [{"direct_quote": "In 2024 the rate was 5.5%."}], [0])
    assert 5.5 in vs2 and 2024.0 not in vs2


def test_fix3_soft_prior_bridges_multi_anchor(monkeypatch):
    rows = [
        {"evidence_id": "eA", "source_url": "https://a.org",
         "direct_quote": "Generative AI could raise US GDP by 1.5% in the low case and 3.7% in the high case."},
        {"evidence_id": "eB", "source_url": "https://b.org",
         "direct_quote": "In the high case generative AI lifts GDP by 3.7%, with 1.5% in the conservative scenario."},
    ]
    groups = {("ai", "raise_gdp", 1.5): [0], ("ai", "raise_gdp", 3.7): [1]}
    rank = lambda ri: (0.0, 0.0, -ri)
    seen = {}

    def _stub(texts, **kw):
        seen["n"] = len(texts)
        return {i: 0 for i in range(len(texts))}

    monkeypatch.setattr(C, "group_clusters", _stub)
    os.environ["PG_CONSOLIDATION_SOFT_PRIOR"] = "1"
    try:
        merged, n = F._apply_consolidation_nli(dict(groups), rows, rank)
        assert n == 1 and len(merged) == 1 and seen.get("n") == 2
        os.environ["PG_CONSOLIDATION_SOFT_PRIOR"] = "0"
        merged2, n2 = F._apply_consolidation_nli(dict(groups), rows, rank)
        assert n2 == 0 and len(merged2) == 2   # legacy single-value bucket keeps them split
    finally:
        os.environ.pop("PG_CONSOLIDATION_SOFT_PRIOR", None)
