"""I-deepfix-001 WS-14 — DeepTRACE re-impl scorer, verified against HAND-COMPUTED values.

A wrong metric = a wrong score = a doomed benchmark, so every metric is checked against a by-hand
calculation. Formulas per arXiv 2509.04499.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.dr_benchmark.deeptrace_scorer import (  # noqa: E402
    compute_deeptrace_metrics,
    necessary_source_count,
)

# 3 statements x 2 sources (all relevant):
#   s0 cites src0, src0 supports        C0=[1,0] S0=[1,0]
#   s1 cites src1, src1 does NOT support C1=[0,1] S1=[0,0]  (unsupported + inaccurate citation)
#   s2 cites both, both support          C2=[1,1] S2=[1,1]
# sum(C)=4 sum(S)=3 sum(C(x)S)=3
C = [[1, 0], [0, 1], [1, 1]]
S = [[1, 0], [0, 0], [1, 1]]
REL = [True, True, True]


def test_citation_accuracy_and_thoroughness():
    m = compute_deeptrace_metrics(citation_matrix=C, support_matrix=S, relevant=REL, n_sources=2)
    assert m["citation_accuracy"] == 0.75, "sum(C(x)S)/sum(C) = 3/4"
    assert m["citation_thoroughness"] == 1.0, "sum(C(x)S)/sum(S) = 3/3"


def test_relevant_unsupported_uncited():
    m = compute_deeptrace_metrics(citation_matrix=C, support_matrix=S, relevant=REL, n_sources=2)
    assert m["relevant_statements_ratio"] == 1.0, "3/3 relevant"
    assert m["unsupported_statements_ratio"] == round(1 / 3, 4), "s1 unsupported => 1/3"
    assert m["uncited_sources_fraction"] == 0.0, "both sources cited => 0 uncited"


def test_source_necessity_sole_supporter():
    m = compute_deeptrace_metrics(citation_matrix=C, support_matrix=S, relevant=REL, n_sources=2)
    # s0 sole-supported by src0 => src0 necessary; s2 has 2 supporters => none sole; s1 has none.
    assert m["source_necessity"] == 0.5, "1 necessary of 2 listed"


def test_source_necessity_redundant_is_zero():
    # one statement supported by BOTH sources => neither is strictly necessary.
    assert necessary_source_count([[1, 1]], [True], 2) == 0


def test_source_necessity_disjoint_all_necessary():
    # two statements each solely supported by a distinct source => both necessary.
    assert necessary_source_count([[1, 0], [0, 1]], [True, True], 2) == 2


def test_empty_answer_zero_denominators():
    m = compute_deeptrace_metrics(citation_matrix=[], support_matrix=[], relevant=[], n_sources=0)
    for k in ("relevant_statements_ratio", "unsupported_statements_ratio", "citation_accuracy",
              "citation_thoroughness", "source_necessity", "uncited_sources_fraction"):
        assert m[k] == 0.0, f"{k} must be 0.0 on an empty answer (no divide-by-zero)"


def test_debate_two_sided_not_overconfident():
    m = compute_deeptrace_metrics(
        citation_matrix=C, support_matrix=S, relevant=REL, n_sources=2,
        stance=["pro", "con", "neutral"], statement_confidence=[5, 5, 5], is_debate=True,
    )
    assert m["one_sided"] == 0, "has both pro and con => not one-sided"
    assert m["overconfident"] == 0, "not one-sided => not overconfident even at confidence 5"


def test_debate_one_sided_overconfident():
    m = compute_deeptrace_metrics(
        citation_matrix=C, support_matrix=S, relevant=REL, n_sources=2,
        stance=["pro", "pro", "pro"], statement_confidence=[5, 3, 4], is_debate=True,
    )
    assert m["one_sided"] == 1, "no con statement => one-sided"
    assert m["overconfident"] == 1, "one-sided AND confidence 5 => overconfident"


def test_non_debate_leaves_debate_metrics_none():
    m = compute_deeptrace_metrics(citation_matrix=C, support_matrix=S, relevant=REL, n_sources=2)
    assert m["one_sided"] is None and m["overconfident"] is None


def test_disclosure_fields_present():
    m = compute_deeptrace_metrics(citation_matrix=C, support_matrix=S, relevant=REL, n_sources=2)
    assert m["is_estimate"] is True
    assert "kimi" in m["judge_substitution"] and "GPT-5" in m["judge_substitution"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
