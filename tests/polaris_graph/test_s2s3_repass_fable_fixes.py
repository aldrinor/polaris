"""S2/S3 re-pass — Fable full-list fixes (offline, no GPU/LLM).

Covers the general, question-agnostic deltas of the Fable re-pass:
  Fix 1(a) rung-0 exact-duplicate collapse (byte-identical claim = same claim, no judge)
  Fix 1(b) __unknown__ clusters POOLED for NLI (pool != merge; default ON)
  Fix 3    RePEc handle work-identity leg (cross-mirror ideas <-> econpapers)
  Fix 2    NON_CLAIM claim-bearing line verdict (S2 line screen), gated default ON
  Fix 2/8  claim-bearing complete-sentence representative (S3)
  Fix 4    scope-aware authoritative-reference ON-topic instruction (topic judge)

All fixes are behind LAW-VI kill switches; each test also asserts the OFF path is
byte-identical to the legacy behaviour.
"""
import os

from src.polaris_graph.synthesis import finding_dedup as fd
from src.polaris_graph.retrieval import line_screen as ls
from src.polaris_graph.retrieval import topic_relevance_gate as tg


# ── Fix 1(a): rung-0 exact-duplicate collapse ──────────────────────────────
def test_rung0_default_on():
    assert fd._rung0_exact_collapse_enabled() is True


def test_rung0_signature_folds_citation_ws_case():
    a = fd._rung0_signature("AI will displace 300 million jobs. [#ev:s1:0-40]")
    b = fd._rung0_signature("ai   will DISPLACE 300 million jobs.  [#ev:s9:5-99]")
    assert a == b and a != ""
    # punctuation / chrome-only line yields an empty signature -> never groups
    assert fd._rung0_signature("--- [#ev:x] ---") == ""


def test_rung0_collapses_identical_text_unknowns():
    rows = [
        {"evidence_id": "e1", "direct_quote": "AI will displace 300 million jobs. [#ev:e1:0-30]",
         "authority_score": 0.9},
        {"evidence_id": "e2", "direct_quote": "ai will displace 300 million jobs.  [#ev:e2:0-30]",
         "authority_score": 0.8},
        {"evidence_id": "e3", "direct_quote": "Interest rates are expected to fall next year.",
         "authority_score": 0.7},
    ]
    groups = {
        ("__unknown__", "e1", 0): [0],
        ("__unknown__", "e2", 0): [1],
        ("__unknown__", "e3", 0): [2],
    }
    merged, collapsed = fd._apply_rung0_exact_collapse(groups, rows, lambda ri: (0.0, -ri))
    sets = sorted(sorted(v) for v in merged.values())
    assert collapsed == 1
    assert [0, 1] in sets and [2] in sets


def test_rung0_off_is_noop():
    os.environ["PG_FINDING_RUNG0_EXACT"] = "0"
    try:
        assert fd._rung0_exact_collapse_enabled() is False
    finally:
        os.environ.pop("PG_FINDING_RUNG0_EXACT", None)


# ── Fix 1(b): unknown pooled for NLI ───────────────────────────────────────
def test_unknown_pool_default_on_and_shared_bucket():
    assert fd._unknown_nli_pool_enabled() is True
    b1 = fd._cluster_value_bucket(("__unknown__", "a", 0), [], [])
    b2 = fd._cluster_value_bucket(("__unknown__", "b", 0), [], [])
    assert b1 == b2 == ("__unk_qual__",)


# ── Fix 3: RePEc handle work-identity leg ──────────────────────────────────
def test_repec_handle_cross_mirror():
    ideas = fd._url_work_identifier({"source_url": "https://ideas.repec.org/p/nbr/nberwo/34174.html"})
    econ = fd._url_work_identifier({"source_url": "https://econpapers.repec.org/p/nbr/nberwo/34174.html"})
    assert ideas.startswith("repec:") and "34174" in ideas
    assert ideas == econ
    assert fd._url_work_identifier({"source_url": "RePEc:nbr:nberwo:34174"}) == ideas


def test_repec_different_handles_distinct():
    a = fd._url_work_identifier({"source_url": "https://ideas.repec.org/p/nbr/nberwo/34174.html"})
    b = fd._url_work_identifier({"source_url": "https://ideas.repec.org/p/nbr/nberwo/99999.html"})
    assert a != b


def test_arxiv_on_repec_still_merges_arxiv_org():
    a = fd._url_work_identifier({"source_url": "https://ideas.repec.org/p/arx/papers/2303.10130.html"})
    b = fd._url_work_identifier({"source_url": "https://arxiv.org/abs/2303.10130"})
    assert a == b == "arxiv:2303.10130"


# ── Fix 2: NON_CLAIM line verdict ──────────────────────────────────────────
def test_non_claim_default_on_and_offered():
    assert ls.claim_bearing_gate_enabled() is True
    prompt = ls.build_line_prompt("q?", "", "", [(0, "Table of contents")])
    assert "NON_CLAIM" in prompt


def test_non_claim_parsed_and_span_drops():
    parsed = ls.parse_line_verdicts("0: NON_CLAIM\n1: KEEP", [0, 1], scope_offered=False)
    assert parsed == {0: ls.NON_CLAIM, 1: ls.KEEP}


def test_non_claim_off_is_byte_identical():
    os.environ["PG_LINE_SCREEN_CLAIM_GATE"] = "0"
    try:
        prompt = ls.build_line_prompt("q?", "", "", [(0, "x")])
        assert "NON_CLAIM" not in prompt
        # with the gate off, a NON_CLAIM token is unrecognised -> count mismatch -> fail-open None
        assert ls.parse_line_verdicts("0: NON_CLAIM\n1: KEEP", [0, 1], scope_offered=False) is None
    finally:
        os.environ.pop("PG_LINE_SCREEN_CLAIM_GATE", None)


# ── Fix 2/8: claim-bearing complete-sentence representative ─────────────────
def test_claim_bearing_complete_detector():
    assert fd._is_claim_bearing_complete(
        {"direct_quote": "Generative AI could automate 25 percent of work tasks by 2030."}
    ) is True
    assert fd._is_claim_bearing_complete({"direct_quote": "[...] automate 25 percent of [...]"}) is False


def test_representative_prefers_complete_sentence():
    rows = [
        {"evidence_id": "t", "direct_quote": "[...] automate 25 percent of [...]"},
        {"evidence_id": "c", "direct_quote": "Generative AI could automate 25 percent of work tasks."},
    ]
    # rank the truncated fragment (index 0) HIGHER; the claim-bearing gate must still pick index 1
    rep = fd._choose_clean_representative([0, 1], lambda ri: (1.0 if ri == 0 else 0.0), rows)
    assert rep == 1


# ── Fix 4: authoritative-reference ON-topic instruction ────────────────────
def test_authoritative_reference_default_on_in_prompt():
    assert tg._authoritative_reference_ontopic_enabled() is True
    p = tg._build_batch_prompt("Which occupations are most exposed to AI?",
                               [(0, "BLS OES Paralegals", "wage table")])
    assert "AUTHORITATIVE REFERENCE PAGES ARE ON-TOPIC" in p


def test_authoritative_reference_off_is_byte_identical():
    os.environ["PG_TOPIC_AUTHORITATIVE_REFERENCE_ONTOPIC"] = "0"
    try:
        p = tg._build_batch_prompt("q", [(0, "t", "s")])
        assert "AUTHORITATIVE REFERENCE PAGES" not in p
    finally:
        os.environ.pop("PG_TOPIC_AUTHORITATIVE_REFERENCE_ONTOPIC", None)
