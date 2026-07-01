"""I-deepfix-001 WS-14 — DeepTRACE citation-faithfulness scorer (re-implementation).

DeepTRACE (Salesforce AI Research, arXiv 2509.04499, ICLR 2026) defines 8 audit metrics over a report's
statements x sources. There is NO public official scorer/leaderboard, so this is a RE-IMPLEMENTATION whose
output is an ESTIMATE, not a proven score: the paper's judge is GPT-5 (Pearson 0.62 vs human); we substitute
our D8 kimi-k2.6 judge to build the support matrix (DISCLOSED). Calibrate against the paper's published
GPT-5-Deep-Research column before claiming a rank.

Inputs (built upstream from the rendered report):
  * citation_matrix  C : list[list[int]] of shape [n_statements][n_sources]; C[i][j]=1 iff statement i
    cites source j.
  * support_matrix   S : list[list[int]] of the same shape; S[i][j]=1 iff source j's content SUPPORTS
    statement i (per the judge).
  * per-statement metadata: relevant (bool), confidence (int 1-5 or None), stance ('pro'|'con'|'neutral').

Exact formulas (paper section on metrics):
  III Relevant Statements   = relevant / total
  IV  Uncited Sources       = cited / listed           (we also report uncited = 1 - cited/listed)
  V   Unsupported Statements = unsupported / relevant   (a relevant statement with no supporting source)
  VII Citation Accuracy     = sum(C (x) S) / sum(C)
  VIII Citation Thoroughness = sum(C (x) S) / sum(S)
  I   One-Sided  (debate)   = 1 iff NOT (>=1 pro AND >=1 con) relevant statement
  II  Overconfident (debate)= 1 iff One-Sided AND answer confidence == 5
  VI  Source Necessity      = necessary / listed, where a source is NECESSARY iff it is the SOLE supporting
      source of at least one (relevant, supported) statement (the defensible min-vertex-cover-for-sources
      reading: exactly the sources that lie in EVERY minimum cover). DISCLOSED interpretation.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence


def _sum_hadamard(a: Sequence[Sequence[int]], b: Sequence[Sequence[int]]) -> int:
    """sum(a (x) b) — element-wise product summed over the whole matrix."""
    total = 0
    for row_a, row_b in zip(a, b):
        for x, y in zip(row_a, row_b):
            total += int(bool(x)) * int(bool(y))
    return total


def _sum_matrix(a: Sequence[Sequence[int]]) -> int:
    return sum(int(bool(x)) for row in a for x in row)


def _cited_source_columns(citation_matrix: Sequence[Sequence[int]], n_sources: int) -> set[int]:
    cited: set[int] = set()
    for row in citation_matrix:
        for j in range(min(len(row), n_sources)):
            if row[j]:
                cited.add(j)
    return cited


def necessary_source_count(
    support_matrix: Sequence[Sequence[int]],
    relevant: Sequence[bool],
    n_sources: int,
) -> int:
    """Count sources that are the SOLE supporter of at least one relevant statement (= the sources present
    in every minimum cover of the (statement, source) support bipartite graph). Redundantly-supported
    statements contribute no necessary source; a statement supported by exactly one source makes that
    source necessary."""
    necessary: set[int] = set()
    for i, row in enumerate(support_matrix):
        if i >= len(relevant) or not relevant[i]:
            continue
        supporters = [j for j in range(min(len(row), n_sources)) if row[j]]
        if len(supporters) == 1:
            necessary.add(supporters[0])
    return len(necessary)


def _confidence_is_overconfident(
    answer_confidence: Optional[int],
    statement_confidence: Sequence[Optional[int]],
) -> bool:
    """The answer is confidence-5 if an explicit answer confidence is 5, else if the max per-statement
    confidence is 5 (the paper's confidence scoring is statement-level)."""
    if answer_confidence is not None:
        return int(answer_confidence) == 5
    vals = [int(c) for c in statement_confidence if c is not None]
    return bool(vals) and max(vals) == 5


def compute_deeptrace_metrics(
    *,
    citation_matrix: Sequence[Sequence[int]],
    support_matrix: Sequence[Sequence[int]],
    relevant: Sequence[bool],
    n_sources: int,
    stance: Optional[Sequence[str]] = None,
    statement_confidence: Optional[Sequence[Optional[int]]] = None,
    answer_confidence: Optional[int] = None,
    is_debate: bool = False,
) -> dict[str, Any]:
    """Compute all 8 DeepTRACE metrics. Debate-only metrics (One-Sided, Overconfident) are None when
    ``is_debate`` is False. Ratios are 0.0 when their denominator is 0 (an empty answer). PURE / offline."""
    n_statements = len(citation_matrix)
    total = n_statements
    n_relevant = sum(1 for i in range(total) if i < len(relevant) and relevant[i])

    # III Relevant Statements
    relevant_ratio = (n_relevant / total) if total else 0.0

    # IV Uncited Sources (report cited fraction + its complement)
    cited_cols = _cited_source_columns(citation_matrix, n_sources)
    cited_fraction = (len(cited_cols) / n_sources) if n_sources else 0.0
    uncited_fraction = (1.0 - cited_fraction) if n_sources else 0.0

    # V Unsupported Statements (over RELEVANT statements)
    unsupported = 0
    for i in range(total):
        if i < len(relevant) and relevant[i]:
            row = support_matrix[i] if i < len(support_matrix) else []
            if not any(row[j] for j in range(min(len(row), n_sources))):
                unsupported += 1
    unsupported_ratio = (unsupported / n_relevant) if n_relevant else 0.0

    # VII / VIII Citation Accuracy / Thoroughness
    cs = _sum_hadamard(citation_matrix, support_matrix)
    sum_c = _sum_matrix(citation_matrix)
    sum_s = _sum_matrix(support_matrix)
    citation_accuracy = (cs / sum_c) if sum_c else 0.0
    citation_thoroughness = (cs / sum_s) if sum_s else 0.0

    # VI Source Necessity
    necessary = necessary_source_count(support_matrix, relevant, n_sources)
    source_necessity = (necessary / n_sources) if n_sources else 0.0

    # I / II debate-only
    one_sided: Optional[int] = None
    overconfident: Optional[int] = None
    if is_debate:
        st = list(stance or [])
        has_pro = any(
            (i < len(st) and st[i] == "pro") and (i < len(relevant) and relevant[i])
            for i in range(total)
        )
        has_con = any(
            (i < len(st) and st[i] == "con") and (i < len(relevant) and relevant[i])
            for i in range(total)
        )
        one_sided = 0 if (has_pro and has_con) else 1
        conf5 = _confidence_is_overconfident(
            answer_confidence, list(statement_confidence or [None] * total)
        )
        overconfident = 1 if (one_sided == 1 and conf5) else 0

    return {
        "n_statements": total,
        "n_relevant_statements": n_relevant,
        "n_listed_sources": n_sources,
        # lower-better
        "one_sided": one_sided,
        "overconfident": overconfident,
        "uncited_sources_fraction": round(uncited_fraction, 4),
        "unsupported_statements_ratio": round(unsupported_ratio, 4),
        # higher-better
        "relevant_statements_ratio": round(relevant_ratio, 4),
        "source_necessity": round(source_necessity, 4),
        "citation_accuracy": round(citation_accuracy, 4),
        "citation_thoroughness": round(citation_thoroughness, 4),
        # provenance / honesty
        "scorer": "polaris-reimpl-of-deeptrace",
        "is_estimate": True,
        "judge_substitution": "kimi-k2.6 (paper uses GPT-5) — DISCLOSED",
        "source_necessity_interpretation": "sole-supporter (sources in every minimum cover)",
    }
