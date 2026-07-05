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
  VI  Source Necessity      = size_of_minimum_source_cover / listed, where the minimum source cover is the
      FEWEST sources whose union still SUPPORTS every supported relevant statement (paper 2509.04499
      "minimum vertex cover for source nodes"; the official answer-engine-eval reference uses greedy set
      cover, which we match — no exact Hopcroft-Karp needed). A statement supported by 2 sources therefore
      contributes cover-size 1 (necessity 0.5 of 2 listed), NOT 0. The old SOLE-supporter count (a source
      that is the only supporter of some supported relevant statement) is retained as a SECONDARY
      disclosure field ``n_sole_supporter`` — it is a lower bound on the cover size, nothing is lost.
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
    """SECONDARY disclosure (NOT the DeepTRACE VI numerator anymore): count sources that are the SOLE
    supporter of at least one relevant statement. Such a source must appear in every cover, so this count
    is a LOWER BOUND on the minimum source cover size (see ``minimum_source_cover_size``). Redundantly-
    supported statements contribute no sole supporter; a statement supported by exactly one source makes
    that source a sole supporter. Retained so nothing is lost after the min-cover fix."""
    necessary: set[int] = set()
    for i, row in enumerate(support_matrix):
        if i >= len(relevant) or not relevant[i]:
            continue
        supporters = [j for j in range(min(len(row), n_sources)) if row[j]]
        if len(supporters) == 1:
            necessary.add(supporters[0])
    return len(necessary)


def minimum_source_cover_size(
    support_matrix: Sequence[Sequence[int]],
    relevant: Sequence[bool],
    n_sources: int,
) -> int:
    """DeepTRACE VI numerator: the size of the MINIMUM source cover over the supported relevant statements.

    universe = indices of relevant statements that have >= 1 supporting source (i.e. supported).
    sets     = for each listed source j, the set of supported relevant statements it supports (S[i][j]==1).
    The cover = the fewest sources whose union covers the whole universe. Computed by greedy set cover
    (repeatedly take the source covering the most still-uncovered statements), which is the standard
    reference implementation used by the official answer-engine-eval code — exact Hopcroft-Karp is not
    required. Deterministic tie-break: lowest source index. A statement supported by 2 sources yields a
    cover of size 1 (not 0), fixing the sole-supporter divergence. Returns 0 for an empty universe."""
    universe: set[int] = set()
    source_sets: dict[int, set[int]] = {j: set() for j in range(n_sources)}
    for i, row in enumerate(support_matrix):
        if i >= len(relevant) or not relevant[i]:
            continue
        supporters = [j for j in range(min(len(row), n_sources)) if row[j]]
        if not supporters:  # unsupported relevant statement is not in the cover universe
            continue
        universe.add(i)
        for j in supporters:
            source_sets[j].add(i)

    uncovered = set(universe)
    cover_size = 0
    while uncovered:
        best_j: Optional[int] = None
        best_cov = 0
        for j in range(n_sources):
            cov = len(source_sets[j] & uncovered)
            if cov > best_cov:
                best_cov = cov
                best_j = j
        if best_j is None:  # no source covers a remaining statement (unreachable: each has a supporter)
            break
        uncovered -= source_sets[best_j]
        cover_size += 1
    return cover_size


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

    # VI Source Necessity = min-source-cover size / listed (paper "minimum vertex cover for source nodes").
    cover_size = minimum_source_cover_size(support_matrix, relevant, n_sources)
    source_necessity = (cover_size / n_sources) if n_sources else 0.0
    # SECONDARY disclosure retained so nothing is lost: the old sole-supporter count (lower bound on cover).
    n_sole_supporter = necessary_source_count(support_matrix, relevant, n_sources)

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
        "source_necessity_cover_size": cover_size,
        "n_sole_supporter": n_sole_supporter,
        "citation_accuracy": round(citation_accuracy, 4),
        "citation_thoroughness": round(citation_thoroughness, 4),
        # provenance / honesty
        "scorer": "polaris-reimpl-of-deeptrace",
        "is_estimate": True,
        "judge_substitution": "kimi-k2.6 (paper uses GPT-5) — DISCLOSED",
        "source_necessity_interpretation": (
            "min-source-cover (greedy set cover over supported relevant statements) / n_listed_sources; "
            "n_sole_supporter is the retained sole-supporter lower bound"
        ),
    }
