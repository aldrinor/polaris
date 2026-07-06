"""I-deepfix-001 Wave-1c (#1344) — tests for the OFFLINE DeepTRACE self-scorer.

Fully offline: the NLI verdicts are STUBBED with a fixture map (no real model, no torch).
Every one of the 8 DeepTRACE metrics is asserted against a hand-computed value on a KNOWN
Citation matrix C and Factual-support matrix F, and Source-Necessity is asserted on a
discriminating triangle case where greedy min-set-cover (2) != Konig min-vertex-cover (3).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.deeptrace_self_score import (  # noqa: E402
    citation_accuracy,
    citation_thoroughness,
    compute_deeptrace_selfscore,
    greedy_min_set_cover,
    konig_min_vertex_cover,
    one_sided_answer,
    overconfident_answer,
    relevant_statement_ratio,
    score_report,
    source_necessity_ratio,
    uncited_sources_ratio,
    unsupported_statements_ratio,
)

# ─────────────────────────────────────────────────────────────────────────
# Stub NLI: (span, keyword) intents -> True. Keyword match is case-insensitive
# on the (citation-stripped) statement hypothesis. Returns True/False/None like
# the real entails_directional; no model is ever loaded.
# ─────────────────────────────────────────────────────────────────────────
def make_stub_entail(intents):
    """intents = list of (span_text, keyword). Returns an entail_fn(span, hyp) -> bool."""
    def entail_fn(span, hyp):
        h = (hyp or "").lower()
        for sp, kw in intents:
            if span == sp and kw.lower() in h:
                return True
        return False
    return entail_fn


def _ref(title="", url="", tier="T1"):
    return {"title": title, "url": url, "tier": tier}


# ═════════════════════════════════════════════════════════════════════════
# A. Full 8-metric fixture (4 statements, 3 sources; source 3 uncited)
# ═════════════════════════════════════════════════════════════════════════
def test_a_full_eight_metrics_hand_computed():
    span_a = "A randomized trial found the drug reduced blood pressure by 10 mmHg."
    span_b = "The study enrolled 500 participants; serious adverse events were uncommon."
    span_c = "Unrelated content about the weather in another region entirely."
    statements = [
        "The drug lowered blood pressure by 10 mmHg.[1]",   # s0 -> src1
        "Adverse events were rare.[1][2]",                  # s1 -> src1,2
        "The trial enrolled 500 patients.[2]",              # s2 -> src2
        "In conclusion, more research is needed.",          # s3 -> filler (no cite)
    ]
    bibliography = {1: _ref("Drug BP trial"), 2: _ref("Enrollment study"), 3: _ref("Uncited src")}
    span_by_num = {1: span_a, 2: span_b, 3: span_c}
    stub = make_stub_entail([
        (span_a, "blood pressure"),   # -> s0
        (span_b, "adverse events"),   # -> s1
        (span_b, "500"),              # -> s2
    ])

    m = compute_deeptrace_selfscore(
        statements=statements, bibliography=bibliography,
        span_by_num=span_by_num, entail_fn=stub,
    )

    assert m["n_statements"] == 4
    assert m["n_relevant_statements"] == 3          # s0,s1,s2 carry citations; s3 filler
    assert m["n_listed_sources"] == 3
    assert m["n_cited_sources"] == 2                # sources 1,2 cited; 3 uncited
    # III Relevant = core/total = 3/4
    assert m["relevant_statements_ratio"] == pytest.approx(0.75)
    # IV Uncited = (listed-cited)/listed = (3-2)/3
    assert m["uncited_sources_ratio"] == pytest.approx(1 / 3, abs=1e-4)
    assert m["cited_sources_fraction"] == pytest.approx(2 / 3, abs=1e-4)
    # V Unsupported = 0/3 (every relevant statement has a supporting span)
    assert m["unsupported_statements_ratio"] == pytest.approx(0.0)
    # VII/VIII: sum_C=4, sum_F=3, sum_C&F=3
    assert (m["sum_C"], m["sum_F"], m["sum_C_and_F"]) == (4, 3, 3)
    assert m["citation_accuracy"] == pytest.approx(0.75)        # 3/4
    assert m["citation_thoroughness"] == pytest.approx(1.0)     # 3/3
    # VI Source-Necessity headline (greedy set cover): cover {src2, src1} size 2 / 3 listed
    assert m["source_necessity_cover_size"] == 2
    assert m["source_necessity"] == pytest.approx(2 / 3, abs=1e-4)
    # debate metrics N/A (not a debate query)
    assert m["one_sided"] is None and m["overconfident"] is None
    # triage identity + honesty surfaced
    assert m["role"] == "TRIAGE_PREDICTOR_ONLY"
    assert m["is_pass_fail_gate"] is False
    assert "SPAN-APPROXIMATE" in m["honest_limitation"]
    # Relevant-Statement is explicitly a PROXY (paid GPT-5 relevant[] labels unavailable offline)
    assert m["relevant_statements_ratio_is_proxy"] is True
    assert "least-reliable" in m["honest_limitation"]
    assert "caps at 10" in m["honest_limitation"]     # source-cap disclosure


# ═════════════════════════════════════════════════════════════════════════
# B. Source-Necessity discriminator: greedy set-cover (2) != Konig MVC (3)
# ═════════════════════════════════════════════════════════════════════════
def test_b_source_necessity_setcover_vs_mvc_discriminator():
    span_a, span_b, span_c = "SPAN-A", "SPAN-B", "SPAN-C"
    statements = [
        "Alpha finding holds.[1][3]",   # t0 -> src1(a), src3(c)
        "Beta finding holds.[1][2]",    # t1 -> src1(a), src2(b)
        "Gamma finding holds.[2][3]",   # t2 -> src2(b), src3(c)
    ]
    bibliography = {1: _ref("A"), 2: _ref("B"), 3: _ref("C")}
    span_by_num = {1: span_a, 2: span_b, 3: span_c}
    # F: a={t0,t1}, b={t1,t2}, c={t0,t2}  (the classic triangle)
    stub = make_stub_entail([
        (span_a, "alpha"), (span_a, "beta"),
        (span_b, "beta"), (span_b, "gamma"),
        (span_c, "alpha"), (span_c, "gamma"),
    ])

    m = compute_deeptrace_selfscore(
        statements=statements, bibliography=bibliography,
        span_by_num=span_by_num, entail_fn=stub,
    )
    # Headline = greedy min-SET-cover = 2 sources cover all 3 statements -> 2/3
    assert m["source_necessity_cover_size"] == 2
    assert m["source_necessity"] == pytest.approx(2 / 3, abs=1e-4)
    # Diagnostic = Hopcroft-Karp -> Konig min-VERTEX-cover = 3 (max matching 3) -> 3/3 = 1.0
    assert m["source_necessity_mvc_size"] == 3
    assert m["source_necessity_mvc_diagnostic"] == pytest.approx(1.0)
    # This is exactly why the headline is NOT König MVC: MVC over-states necessity here.
    assert m["source_necessity"] < m["source_necessity_mvc_diagnostic"]


def test_b2_cover_algorithms_directly():
    # triangle universe {0,1,2}; sets a={0,1}, b={1,2}, c={0,2}
    universe = {0, 1, 2}
    sets = {0: {0, 1}, 1: {1, 2}, 2: {0, 2}}
    cover = greedy_min_set_cover(universe, sets)
    assert len(cover) == 2                       # set cover = 2
    # bipartite: left statements 0,1,2 ; right sources 0,1,2 ; edges from the same sets
    adj = {0: [0, 2], 1: [0, 1], 2: [1, 2]}      # stmt -> supporting sources
    cl, cr = konig_min_vertex_cover(adj, [0, 1, 2], [0, 1, 2])
    assert len(cl) + len(cr) == 3                # vertex cover = max matching = 3


# ═════════════════════════════════════════════════════════════════════════
# C. Debate pure functions (truth table) + orchestrator debate wiring
# ═════════════════════════════════════════════════════════════════════════
def test_c_debate_pure_functions():
    assert one_sided_answer(True, True) == 0
    assert one_sided_answer(True, False) == 1
    assert one_sided_answer(False, True) == 1
    assert one_sided_answer(False, False) == 1
    assert overconfident_answer(1, 5) == 1
    assert overconfident_answer(1, 3) == 0
    assert overconfident_answer(0, 5) == 0
    assert overconfident_answer(1, None) == 0
    # statement-confidence branch (paid _confidence_is_overconfident fallback): when
    # answer_confidence is None, a MAX per-statement confidence of 5 flips Overconfident.
    assert overconfident_answer(1, None, [2, 5, 3]) == 1
    assert overconfident_answer(1, None, [2, 4, 3]) == 0
    assert overconfident_answer(1, None, []) == 0
    assert overconfident_answer(1, None, [None, 5]) == 1
    # exact paid short-circuit: a PROVIDED answer_confidence takes precedence over statements.
    assert overconfident_answer(1, 4, [5, 5]) == 0
    assert overconfident_answer(1, 5, [1, 1]) == 1
    assert overconfident_answer(0, None, [5]) == 0   # not one-sided => never overconfident


def test_c_overconfident_matches_paid_confidence_helper():
    # Prove our _confidence_is_overconfident replicates the paid deeptrace_scorer helper EXACTLY
    # across the answer-confidence short-circuit AND the statement-confidence fallback branch.
    from scripts.deeptrace_self_score import _confidence_is_overconfident as mine
    from scripts.dr_benchmark.deeptrace_scorer import _confidence_is_overconfident as paid
    cases = [(5, None), (4, None), (None, [5]), (None, [4, 3]), (None, []),
             (4, [5, 5]), (5, [1]), (None, [None, 5]), (3, [3, 3]), (None, [1, 2, 3])]
    for ac, sc in cases:
        assert mine(ac, sc) == paid(ac, sc or []), (ac, sc)


def test_c_orchestrator_debate_labels():
    m = compute_deeptrace_selfscore(
        statements=["Claim only on one side.[1]"],
        bibliography={1: _ref("S")}, span_by_num={1: "span"},
        entail_fn=make_stub_entail([]),
        is_debate=True, has_pro=True, has_con=False, answer_confidence=5,
    )
    assert m["one_sided"] == 1        # pro present, con absent
    assert m["overconfident"] == 1    # one-sided AND confidence 5


def test_c_orchestrator_statement_confidence_flows():
    # answer_confidence None -> the statement-confidence branch drives Overconfident through the
    # orchestrator (max per-statement confidence 5 flips it).
    m = compute_deeptrace_selfscore(
        statements=["One side only.[1]"], bibliography={1: _ref("S")},
        span_by_num={1: "span"}, entail_fn=make_stub_entail([]),
        is_debate=True, has_pro=True, has_con=False,
        answer_confidence=None, statement_confidence=[3, 5],
    )
    assert m["one_sided"] == 1
    assert m["overconfident"] == 1


# ═════════════════════════════════════════════════════════════════════════
# D. Degenerate / empty input NEVER raises; ratios are 0.0
# ═════════════════════════════════════════════════════════════════════════
def test_d_degenerate_empty_never_raises():
    m = compute_deeptrace_selfscore(
        statements=[], bibliography={}, span_by_num={},
        entail_fn=make_stub_entail([]),
    )
    assert m["n_statements"] == 0
    assert m["relevant_statements_ratio"] == 0.0
    assert m["uncited_sources_ratio"] == 0.0
    assert m["unsupported_statements_ratio"] == 0.0
    assert m["source_necessity"] == 0.0
    assert m["source_necessity_mvc_size"] == 0
    assert m["citation_accuracy"] == 0.0
    assert m["citation_thoroughness"] == 0.0
    assert m["is_pass_fail_gate"] is False


def test_d_pure_functions_zero_denominator():
    assert relevant_statement_ratio(0, 0) == 0.0
    assert uncited_sources_ratio(0, 0) == 0.0
    assert unsupported_statements_ratio(0, 0) == 0.0
    assert source_necessity_ratio(0, 0) == 0.0
    assert citation_accuracy(0, 0) == 0.0
    assert citation_thoroughness(0, 0) == 0.0
    # a couple of positive checks on the pure ratios
    assert relevant_statement_ratio(3, 4) == pytest.approx(0.75)
    assert citation_accuracy(3, 4) == pytest.approx(0.75)
    assert citation_thoroughness(3, 3) == pytest.approx(1.0)


def test_d_greedy_cover_never_hangs_on_uncoverable_universe():
    # universe element 9 is coverable by no subset -> greedy must break, not hang
    cover = greedy_min_set_cover({0, 1, 9}, {0: {0, 1}})
    assert cover == [0]


# ═════════════════════════════════════════════════════════════════════════
# E. End-to-end score_report on written files (stubbed NLI) — honesty surfaced
# ═════════════════════════════════════════════════════════════════════════
def test_e_score_report_end_to_end(tmp_path):
    report_md = (
        "## Findings\n\n"
        "The drug lowered blood pressure by 10 mmHg.[1] "
        "The trial enrolled 500 patients.[2]\n\n"
        "A claim previously stated here did not survive 4-role verification and was "
        "redacted; this is a curator-actionable gap.\n\n"
        "## Bibliography\n"
        "[1] Drug BP trial — https://example.org/bp (tier T1)\n"
        "[2] Enrollment study — https://example.org/enroll (tier T1)\n"
        "[3] Never cited — https://example.org/unrelated (tier UNKNOWN)\n"
    )
    snapshot = {
        "evidence_for_gen": [
            {"evidence_id": "e1", "source_url": "https://example.org/bp",
             "title": "Drug BP trial",
             "direct_quote": "A randomized trial found the drug reduced blood pressure by 10 mmHg."},
            {"evidence_id": "e2", "source_url": "https://example.org/enroll",
             "title": "Enrollment study",
             "direct_quote": "The study enrolled 500 participants."},
            # source [3] has NO snapshot entry -> unreachable
        ]
    }
    rp = tmp_path / "report.md"
    sp = tmp_path / "corpus_snapshot.json"
    rp.write_text(report_md, encoding="utf-8")
    sp.write_text(json.dumps(snapshot), encoding="utf-8")

    span_bp = "A randomized trial found the drug reduced blood pressure by 10 mmHg."
    span_en = "The study enrolled 500 participants."
    stub = make_stub_entail([(span_bp, "blood pressure"), (span_en, "500")])

    m = score_report(rp, sp, entail_fn=stub)

    # redaction placeholder line dropped -> exactly 2 statements decomposed
    assert m["n_statements"] == 2
    assert m["n_relevant_statements"] == 2
    assert m["n_listed_sources"] == 3
    assert m["n_unreachable_sources"] == 1          # source [3] resolves to no span
    assert m["unsupported_statements_ratio"] == pytest.approx(0.0)
    assert m["citation_accuracy"] == pytest.approx(1.0)
    assert m["role"] == "TRIAGE_PREDICTOR_ONLY"
    assert m["is_pass_fail_gate"] is False
    assert "SPAN-APPROXIMATE" in m["honest_limitation"]
    assert "greedy min-set-cover" in m["source_necessity_interpretation"]
    assert m["relevant_statements_ratio_is_proxy"] is True
    assert "proxy" in m["honest_limitation"].lower()


def test_e_embedded_redaction_sentence_drops_only_that_sentence():
    # Real POLARIS sections render as ONE line with an inline redaction sentence between real
    # claims. The redaction sentence must be dropped WITHOUT deleting the surrounding claims
    # (regression for the line-level-drop bug found on the banked drb_72 report).
    from scripts.deeptrace_self_score import split_statements
    line = (
        "The framework centers on displacement.[1] "
        "A claim previously stated here did not survive 4-role verification and was redacted; "
        "this is a curator-actionable gap. "
        "However, reinstatement offsets it.[2]"
    )
    stmts = split_statements(line)
    joined = " ".join(stmts)
    assert any("displacement" in s for s in stmts)          # claim before the redaction kept
    assert any("reinstatement offsets it" in s for s in stmts)  # claim after the redaction kept
    assert "did not survive" not in joined                  # only the redaction sentence dropped
    assert len(stmts) == 2


def test_e_score_report_missing_files_never_raises(tmp_path):
    # non-existent paths must NOT raise (triage must never block a pipeline)
    m = score_report(tmp_path / "nope.md", tmp_path / "nope.json",
                     entail_fn=make_stub_entail([]))
    assert m["n_statements"] == 0
    assert "error" in m
    assert m["is_pass_fail_gate"] is False
