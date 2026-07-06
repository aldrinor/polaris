#!/usr/bin/env python3
"""Offline DeepTRACE self-scorer — I-deepfix-001 Wave-1c (#1344), TRIAGE PREDICTOR ONLY.

================================  READ THIS FIRST  ================================
This script ESTIMATES a POLARIS rendered report's DeepTRACE citation-faithfulness score
OFFLINE, before spending on the paid GPT-5 / kimi-k2.6 judge. It is a **TRIAGE PREDICTOR,
NOT a pass/fail gate.** It never aborts, raises on bad input, blocks, or decides anything by
a hardcoded threshold (LAW VI). Its numbers are ESTIMATES, not a proven score. Per operator
directive ("prove our own scorer correct then trust it") the point of this module is
formula-fidelity: every metric below is a small pure function whose docstring quotes the exact
DeepTRACE formula so a reviewer can verify it. It does NOT replace the official paid harness —
it predicts it, cheaply, so a shallow/broken report can be caught before paid judging.

DeepTRACE = Salesforce AI Research, arXiv 2509.04499. The 8 metrics are computed over a
report's statements × sources via a Citation matrix C and a Factual-support matrix F.

HONEST LIMITATION — THE F-MATRIX IS SPAN-APPROXIMATE BY CONSTRUCTION
-------------------------------------------------------------------
DeepTRACE judges F over each source's FULL fetched text. We only have the banked
`corpus_snapshot.json` EXTRACTED SPANS (`direct_quote`) — median ~2.8K of ~14.7K chars,
~550/694 sources truncated (per REAL_PLAN_2026). So a statement that IS truly supported by a
source whose supporting sentence was not captured in the span reads as UNSUPPORTED here.
Net direction: this scorer UNDER-estimates support → OVER-estimates Unsupported-Statements,
UNDER-estimates Citation-Thoroughness. Sources whose bibliography URL/title resolves to no
snapshot span are `n_unreachable` (like DeepTRACE dropping ~15% un-scrapeable URLs) and can
never contribute F-support; they only DEFLATE Source-Necessity. Confidence ranking of the
predictions (stated so the reader weights them correctly):
  * BEST predicted (still span-approximate): Citation-Accuracy, Citation-Thoroughness,
    Unsupported-Statements, Uncited-Sources.
  * WEAK / PROXY: Relevant-Statement — core = an offline citation-presence PROXY for the paid
    GPT-5 core/filler `relevant[]` labels (unavailable offline); it WILL diverge from the paid
    Relevant-Statement and is the least-reliable estimate (flagged relevant_statements_ratio_is_proxy).
  * WEAKEST / usually N/A offline: One-Sided, Overconfident (need a stance + 1-5 confidence
    judge we do not run offline; None unless the caller supplies the labels).

SOURCE-NECESSITY — FORMULA-FIDELITY CONFLICT (flagged for the Codex+Fable gate)
------------------------------------------------------------------------------
The Wave-1c task text names "Hopcroft-Karp → König min-VERTEX-cover". The primary sources use
min-SET-cover, and a triage predictor MUST compute the same quantity the paid path computes:
  * `scripts/dr_benchmark/deeptrace_scorer.py` (POLARIS paid path) = greedy min-SET-cover.
  * `third_party/answer-engine-eval/.../utils_coverage.greedy_set_cover` (official reference) =
    greedy set cover.
König two-sided min-vertex-cover (= max-matching size) OVER-states necessity on redundant
reports (statements {s1,s2,s3}; sources a={s1,s2}, b={s2,s3}, c={s1,s3}: set cover 2 → 2/3
correct, but max matching 3 → König 3 → 1.0 wrong). So the HEADLINE `source_necessity` uses
greedy min-set-cover (valid predictor), and Hopcroft-Karp→König min-vertex-cover is kept as the
LABELED diagnostic `source_necessity_mvc_diagnostic` (the algorithm the task names, implemented
+ tested). See `.codex/I-deepfix-001/wave1c_brief.md`.

Fully disjoint: this script imports nothing from POLARIS except the NLI engine
`entails_directional` (imported LAZILY inside the default entailment wrapper, so importing this
module and `--help` never load torch / sentence-transformers). It modifies NO existing module.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

# An entailment verdict function: (premise_span, hypothesis_statement) -> True / False / None.
# None = verdict unavailable (model/infra degrade) — counted as F=0 for scoring but tallied.
EntailFn = Callable[[str, str], Optional[bool]]

# ─────────────────────────────────────────────────────────────────────────
# Parsing regexes (mirror scripts/dr_benchmark/pack_deeptrace.py conventions)
# ─────────────────────────────────────────────────────────────────────────
_CITE_RE = re.compile(r"\[([\d,\s]+)\]")           # [N] / [N, M] numbered citations
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")       # POLARIS-internal provenance tokens (stripped)
_INTRA_LINE_SENT_RE = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z0-9])")  # intra-line sentence boundary
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")      # markdown ATX heading line
# Appendix boundary: the answer body is everything BEFORE the first of these (mirrors
# pack_drb2.answer_body). `---` is a horizontal rule that in POLARIS reports precedes the
# V30 disclosure appendix.
_APPENDIX_BOUNDARY_RE = re.compile(
    r"^\s{0,3}(##+\s*(bibliography|references|methods?|contradiction|"
    r"evidence[- ]support|v30\b)|-{3,}\s*$)",
    re.IGNORECASE,
)
# The exact redaction placeholder POLARIS emits where a claim failed 4-role verification. It is
# NOT an answer statement (it is a curator gap marker) and must be dropped from the statement set.
_REDACTION_MARKER = "did not survive"  # substring of the placeholder line; robust to wording drift
_BIB_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s+(.*)$")  # a `## Bibliography` entry line
_BIB_TIER_RE = re.compile(r"\(tier\s+([^)]*)\)\s*$", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")


# ═════════════════════════════════════════════════════════════════════════
# THE 8 DEEPTRACE METRICS — pure functions, each docstring quotes the formula
# (BESTPRACTICE_2026_BRIEF DEEP PACK 1 / arXiv 2509.04499). C=citation matrix,
# F=factual-support matrix, ⊙=element-wise product, Σ=sum over all cells.
# ═════════════════════════════════════════════════════════════════════════
def one_sided_answer(has_pro: bool, has_con: bool) -> int:
    """Metric I — One-Sided (binary, debate queries only). LOWER better.

    Formula: 0 if BOTH a pro AND a con statement are present, else 1.
    Offline we have no stance classifier; the caller supplies has_pro / has_con (else the
    orchestrator reports None = N/A)."""
    return 0 if (has_pro and has_con) else 1


def _confidence_is_overconfident(
    answer_confidence: Optional[int],
    statement_confidence: Optional[Sequence[Optional[int]]] = None,
) -> bool:
    """Whole-answer confidence==5 test — replicated EXACTLY from the paid path
    `scripts/dr_benchmark/deeptrace_scorer.py:_confidence_is_overconfident` (lines 122-131) so the
    triage Overconfident prediction matches the paid metric. If an explicit whole-answer
    confidence is provided it is AUTHORITATIVE (==5); OTHERWISE fall back to whether the MAX
    per-statement 1-5 confidence is 5 (the paper scores confidence statement-level). Exact
    short-circuit: a PROVIDED answer_confidence takes precedence and the statement branch is only
    consulted when answer_confidence is None (verified against the paid helper in the test)."""
    if answer_confidence is not None:
        return int(answer_confidence) == 5
    vals = [int(c) for c in (statement_confidence or []) if c is not None]
    return bool(vals) and max(vals) == 5


def overconfident_answer(
    one_sided: int,
    answer_confidence: Optional[int],
    statement_confidence: Optional[Sequence[Optional[int]]] = None,
) -> int:
    """Metric II — Overconfident (binary, debate queries only). LOWER better.

    Formula: 1 if (One-Sided==1 AND whole-answer Confidence==5) else 0, where the confidence-5
    test is the paid path's `_confidence_is_overconfident` (answer_confidence==5, else max
    per-statement confidence==5). Confidence is a 1-5 Likert from a separate judge pass; None
    offline unless the caller supplies it."""
    return 1 if (one_sided == 1 and _confidence_is_overconfident(
        answer_confidence, statement_confidence)) else 0


def relevant_statement_ratio(n_core: int, n_total: int) -> float:
    """Metric III — Relevant Statement (ratio). HIGHER better.

    Formula: (# relevant/core statements) / (total statements). 0.0 on empty."""
    return (n_core / n_total) if n_total else 0.0


def uncited_sources_ratio(n_cited: int, n_listed: int) -> float:
    """Metric IV — Uncited Sources (ratio, reported as %uncited). LOWER better.

    Formula: (# listed − # cited) / (# listed) — the fraction of listed sources that NO
    statement cites. (The complement, cited/listed, is reported alongside.) 0.0 on empty."""
    return ((n_listed - n_cited) / n_listed) if n_listed else 0.0


def unsupported_statements_ratio(n_unsupported: int, n_relevant: int) -> float:
    """Metric V — Unsupported Statements (ratio). LOWER better.

    Formula: (# unsupported statements) / (# relevant statements), where a relevant statement is
    unsupported iff NO listed source supports it in F (its F row is all-zero). 0.0 on empty."""
    return (n_unsupported / n_relevant) if n_relevant else 0.0


def source_necessity_ratio(cover_size: int, n_listed: int) -> float:
    """Metric VI — Source Necessity (ratio). HIGHER better.

    Formula: (# necessary sources = |minimum source cover|) / (# listed sources). The HEADLINE
    cover is the greedy min-SET-cover over supported relevant statements (matches the paid
    `deeptrace_scorer.py` and the official `utils_coverage.greedy_set_cover`). A Hopcroft-Karp →
    König min-VERTEX-cover value is reported separately as a labeled diagnostic. 0.0 on empty."""
    return (cover_size / n_listed) if n_listed else 0.0


def citation_accuracy(sum_c_and_f: int, sum_c: int) -> float:
    """Metric VII — Citation Accuracy (= precision). HIGHER better.

    Formula: Σ(C ⊙ F) / Σ(C). Of every citation the report makes, the fraction landing on a
    source that genuinely supports that statement. 0.0 when the report cites nothing."""
    return (sum_c_and_f / sum_c) if sum_c else 0.0


def citation_thoroughness(sum_c_and_f: int, sum_f: int) -> float:
    """Metric VIII — Citation Thoroughness (= recall). HIGHER better.

    Formula: Σ(C ⊙ F) / Σ(F). Of every true (statement, source) support pair, the fraction the
    report actually cited. 0.0 when F has no support pair."""
    return (sum_c_and_f / sum_f) if sum_f else 0.0


# ═════════════════════════════════════════════════════════════════════════
# Source-cover algorithms
# ═════════════════════════════════════════════════════════════════════════
def greedy_min_set_cover(universe: set[int], source_sets: dict[int, set[int]]) -> list[int]:
    """Greedy minimum SET cover — the DeepTRACE Source-Necessity numerator (HEADLINE).

    Mirrors `third_party/answer-engine-eval/.../utils_coverage.greedy_set_cover` and the paid
    `scripts/dr_benchmark/deeptrace_scorer.minimum_source_cover_size`: repeatedly take the source
    covering the most still-uncovered universe elements. Deterministic tie-break: highest new
    coverage, then LOWEST source index. Returns the chosen source indices (cover size = len).
    Guards against a non-coverable universe element (breaks on zero gain) so it never hangs."""
    covered: set[int] = set()
    cover: list[int] = []
    while covered != universe:
        best_idx: Optional[int] = None
        best_gain = 0
        for idx in sorted(source_sets):  # sorted => LOWEST-index tie-break is deterministic
            gain = len(source_sets[idx] - covered)
            if gain > best_gain:
                best_gain = gain
                best_idx = idx
        if best_idx is None or best_gain == 0:
            break  # no source covers a remaining element (unreachable when universe is covered)
        cover.append(best_idx)
        covered |= source_sets[best_idx]
    return cover


def _hopcroft_karp(adj: dict[int, list[int]], left: list[int], right: list[int]) -> dict[int, int]:
    """Hopcroft-Karp maximum bipartite matching. Returns match_right {right_vertex: left_vertex}.

    `adj[u]` = list of right vertices adjacent to left vertex u. `left`/`right` = vertex id lists.
    Standard BFS-layered / DFS-augment implementation; O(E·sqrt(V))."""
    import collections

    INF = float("inf")
    match_left: dict[int, Optional[int]] = {u: None for u in left}
    match_right: dict[int, Optional[int]] = {v: None for v in right}
    dist: dict[int, float] = {}

    def bfs() -> bool:
        queue: "collections.deque[int]" = collections.deque()
        for u in left:
            if match_left[u] is None:
                dist[u] = 0
                queue.append(u)
            else:
                dist[u] = INF
        found = False
        while queue:
            u = queue.popleft()
            for v in adj.get(u, []):
                w = match_right[v]
                if w is None:
                    found = True
                elif dist[w] == INF:
                    dist[w] = dist[u] + 1
                    queue.append(w)
        return found

    def dfs(u: int) -> bool:
        for v in adj.get(u, []):
            w = match_right[v]
            if w is None or (dist[w] == dist[u] + 1 and dfs(w)):
                match_left[u] = v
                match_right[v] = u
                return True
        dist[u] = INF
        return False

    while bfs():
        for u in left:
            if match_left[u] is None:
                dfs(u)
    return {v: u for v, u in match_right.items() if u is not None}


def konig_min_vertex_cover(
    adj: dict[int, list[int]], left: list[int], right: list[int]
) -> tuple[set[int], set[int]]:
    """König's theorem: minimum VERTEX cover of a bipartite graph from a max matching.

    DIAGNOSTIC ONLY (not the headline Source-Necessity — see the module docstring). Returns
    (cover_left, cover_right): a minimum vertex cover whose total size == max-matching size.
    Construction: let U = unmatched left vertices; alternating-walk (unmatched edges L→R, matched
    edges R→L) marks reachable Z; cover = (left − Z_left) ∪ (right ∩ Z_right)."""
    match_right = _hopcroft_karp(adj, left, right)          # {right: left}
    match_left = {u: v for v, u in match_right.items()}      # {left: right}

    z_left: set[int] = set()
    z_right: set[int] = set()
    stack = [u for u in left if u not in match_left]         # unmatched left vertices
    z_left.update(stack)
    while stack:
        u = stack.pop()
        for v in adj.get(u, []):
            if v in z_right:
                continue
            # traverse an edge NOT in the matching (L→R)
            if match_left.get(u) == v:
                continue
            z_right.add(v)
            w = match_right.get(v)  # follow the matched edge R→L
            if w is not None and w not in z_left:
                z_left.add(w)
                stack.append(w)
    cover_left = {u for u in left if u not in z_left}
    cover_right = {v for v in right if v in z_right}
    return cover_left, cover_right


# ═════════════════════════════════════════════════════════════════════════
# Report / snapshot parsing (deterministic, offline)
# ═════════════════════════════════════════════════════════════════════════
def strip_provenance_tokens(text: str) -> str:
    """Remove POLARIS-internal `[#ev:...]` provenance tokens (DeepTRACE ignores markup)."""
    return _EV_TOKEN_RE.sub("", text)


def strip_citation_markup(text: str) -> str:
    """Remove `[N]` citation markers — the entailment hypothesis is the bare claim text
    (DeepTRACE's factual-support judge is told to ignore citations)."""
    return _CITE_RE.sub("", strip_provenance_tokens(text)).strip()


def extract_answer_body(report_md: str) -> str:
    """Everything BEFORE the first appendix boundary (## Bibliography / Methods / Contradiction /
    References / V30 / horizontal rule). Mirrors pack_drb2.answer_body; local so this is
    standalone. Provenance tokens stripped."""
    lines = report_md.splitlines()
    for i, line in enumerate(lines):
        if _APPENDIX_BOUNDARY_RE.match(line):
            lines = lines[:i]
            break
    return strip_provenance_tokens("\n".join(lines)).strip()


def split_statements(body: str) -> list[str]:
    """Decompose the answer body into the finest citation-bearing units (mirrors
    pack_deeptrace._split_statements): per markdown line → table cells (split on `|`) → prose
    sentences (terminal-punctuation boundary). Heading lines and the redaction placeholder are
    dropped. Real DeepTRACE uses a GPT-5 decomposition pass; this deterministic split is the
    disclosed triage approximation."""
    statements: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or _HEADING_RE.match(line):
            continue
        # NOTE: the redaction placeholder is dropped at the SENTENCE level below, NOT the line
        # level — real POLARIS sections render as ONE multi-sentence line that carries an inline
        # redaction sentence, so a line-level drop would delete the whole section's real claims.
        units = [c for c in line.split("|") if c.strip()] if line.startswith("|") else [line]
        for unit in units:
            for seg in _INTRA_LINE_SENT_RE.split(unit):
                seg = seg.strip()
                if seg and _REDACTION_MARKER not in seg.lower():
                    statements.append(seg)
    return statements


def parse_bibliography(report_md: str) -> dict[int, dict[str, str]]:
    """Parse the `## Bibliography` section: {num: {'title', 'url', 'tier'}}. A bibliography entry
    line looks like `[N] Title — https://url (tier T1)`. URL/tier are optional (some entries have
    an empty URL). Only lines inside the Bibliography section are read."""
    refs: dict[int, dict[str, str]] = {}
    in_bib = False
    for line in report_md.splitlines():
        stripped = line.strip()
        if _HEADING_RE.match(line):
            in_bib = bool(re.match(r"^\s{0,3}##+\s*bibliography\b", line, re.IGNORECASE))
            continue
        if not in_bib:
            continue
        m = _BIB_LINE_RE.match(stripped)
        if not m:
            continue
        num = int(m.group(1))
        rest = m.group(2).strip()
        tier = ""
        tm = _BIB_TIER_RE.search(rest)
        if tm:
            tier = tm.group(1).strip()
            rest = rest[: tm.start()].strip()
        url_m = _URL_RE.search(rest)
        url = url_m.group(0).rstrip(").,") if url_m else ""
        title = rest
        if url:
            title = rest[: url_m.start()].strip()
        title = title.rstrip("—-–:").strip()
        refs[num] = {"title": title, "url": url, "tier": tier}
    return refs


def _normalize_url(url: str) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def _normalize_title(title: str) -> str:
    t = (title or "").strip().lower().rstrip("….")
    return re.sub(r"\s+", " ", t)


def link_sources_to_spans(
    bibliography: dict[int, dict[str, str]], evidence: Sequence[dict]
) -> dict[int, Optional[str]]:
    """Resolve each bibliography number to its snapshot `direct_quote` span via normalized URL
    match first, then normalized title match. Unresolved → None (an `n_unreachable` source that
    can never contribute F-support). Purely deterministic."""
    by_url: dict[str, str] = {}
    by_title: dict[str, str] = {}
    for ev in evidence:
        span = (ev.get("direct_quote") or "").strip()
        if not span:
            continue
        u = _normalize_url(ev.get("source_url") or "")
        if u and u not in by_url:
            by_url[u] = span
        t = _normalize_title(ev.get("title") or ev.get("statement") or "")
        if t and t not in by_title:
            by_title[t] = span
    span_by_num: dict[int, Optional[str]] = {}
    for num, ref in bibliography.items():
        span = None
        u = _normalize_url(ref.get("url") or "")
        if u and u in by_url:
            span = by_url[u]
        if span is None:
            t = _normalize_title(ref.get("title") or "")
            if t and t in by_title:
                span = by_title[t]
        span_by_num[num] = span
    return span_by_num


def citation_columns(statements: Sequence[str]) -> list[set[int]]:
    """Per statement, the SET of source numbers it cites (parsed from `[N]` / `[N, M]`)."""
    out: list[set[int]] = []
    for s in statements:
        nums: set[int] = set()
        for grp in _CITE_RE.findall(s):
            for tok in grp.split(","):
                tok = tok.strip()
                if tok.isdigit():
                    nums.add(int(tok))
        out.append(nums)
    return out


# ═════════════════════════════════════════════════════════════════════════
# Default entailment wrapper — reuses the POLARIS NLI engine (lazy import)
# ═════════════════════════════════════════════════════════════════════════
def _default_entail_fn(premise_span: str, hypothesis_statement: str) -> Optional[bool]:
    """Production F-matrix verdict: does the source SPAN entail the STATEMENT? Reuses
    `src.polaris_graph.synthesis.consolidation_nli.entails_directional` (the ALCE / DeepTRACE
    citation direction — span→claim SUPPORT, forward logits only). Imported LAZILY so importing
    this script / running `--help` never loads torch. Returns True / False / None (None on any
    infra fault; the caller counts it as F=0 and tallies n_unknown_entailment)."""
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from src.polaris_graph.synthesis.consolidation_nli import entails_directional
    except Exception as exc:  # noqa: BLE001 — engine unavailable => UNKNOWN verdict, never crash
        print(f"[deeptrace_self_score] NLI engine unavailable ({exc}); F verdicts = UNKNOWN.",
              file=sys.stderr)
        return None
    try:
        return entails_directional(premise_span, hypothesis_statement)
    except Exception as exc:  # noqa: BLE001 — a verdict failure is UNKNOWN, never fatal (triage)
        print(f"[deeptrace_self_score] entailment failed ({exc}); verdict = UNKNOWN.",
              file=sys.stderr)
        return None


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator — build C, F, compute all 8 metrics. Pure, never raises.
# ═════════════════════════════════════════════════════════════════════════
def compute_deeptrace_selfscore(
    *,
    statements: Sequence[str],
    bibliography: dict[int, dict[str, str]],
    span_by_num: dict[int, Optional[str]],
    entail_fn: EntailFn,
    is_debate: bool = False,
    has_pro: Optional[bool] = None,
    has_con: Optional[bool] = None,
    answer_confidence: Optional[int] = None,
    statement_confidence: Optional[Sequence[Optional[int]]] = None,
) -> dict[str, Any]:
    """Build the Citation matrix C and Factual-support matrix F from parsed inputs, then compute
    all 8 DeepTRACE metrics. PURE and offline; NEVER raises on degenerate/empty input (returns
    zero-filled metrics). `entail_fn(span, statement)` supplies each F verdict (stubbed in tests).
    """
    listed_nums = sorted(bibliography)
    n_listed = len(listed_nums)
    col_of = {num: k for k, num in enumerate(listed_nums)}
    n_stmt = len(statements)

    cite_sets = citation_columns(statements)
    # Core/relevant heuristic: a statement is core iff it carries ≥1 citation to a LISTED source.
    relevant = [bool(cs & set(listed_nums)) for cs in cite_sets]
    n_relevant = sum(relevant)

    # Citation matrix C (only citations to listed sources).
    C = [[0] * n_listed for _ in range(n_stmt)]
    for i, cs in enumerate(cite_sets):
        for num in cs:
            if num in col_of:
                C[i][col_of[num]] = 1

    # Factual-support matrix F — F[i][j]=1 iff span j entails statement i (citation markup
    # stripped from the hypothesis). Computed over EVERY span-resolvable listed source, not just
    # cited ones (DeepTRACE judges support independent of citation).
    F = [[0] * n_listed for _ in range(n_stmt)]
    n_unknown_entailment = 0
    hypotheses = [strip_citation_markup(s) for s in statements]
    for j, num in enumerate(listed_nums):
        span = span_by_num.get(num)
        if not span:
            continue  # unreachable source: no span => contributes no F-support
        for i in range(n_stmt):
            hyp = hypotheses[i]
            if not hyp:
                continue
            verdict = entail_fn(span, hyp)
            if verdict is None:
                n_unknown_entailment += 1
            elif verdict:
                F[i][j] = 1

    n_unreachable = sum(1 for num in listed_nums if not span_by_num.get(num))

    # ── Metric III: Relevant Statement ────────────────────────────────────
    m_relevant = relevant_statement_ratio(n_relevant, n_stmt)

    # ── Metric IV: Uncited Sources ────────────────────────────────────────
    cited_cols = {col_of[num] for cs in cite_sets for num in cs if num in col_of}
    n_cited = len(cited_cols)
    m_uncited = uncited_sources_ratio(n_cited, n_listed)
    cited_fraction = (n_cited / n_listed) if n_listed else 0.0

    # ── Metric V: Unsupported Statements (over relevant statements) ────────
    n_unsupported = 0
    for i in range(n_stmt):
        if relevant[i] and not any(F[i]):
            n_unsupported += 1
    m_unsupported = unsupported_statements_ratio(n_unsupported, n_relevant)

    # ── Metrics VII / VIII: Citation Accuracy / Thoroughness ──────────────
    sum_c = sum(sum(row) for row in C)
    sum_f = sum(sum(row) for row in F)
    sum_cf = sum(C[i][j] & F[i][j] for i in range(n_stmt) for j in range(n_listed))
    m_accuracy = citation_accuracy(sum_cf, sum_c)
    m_thoroughness = citation_thoroughness(sum_cf, sum_f)

    # ── Metric VI: Source Necessity ───────────────────────────────────────
    # Universe = supported relevant statements; source_sets[j] = supported relevant statements j
    # supports. HEADLINE = greedy min-set-cover; DIAGNOSTIC = Hopcroft-Karp→König min-vertex-cover.
    universe: set[int] = set()
    source_sets: dict[int, set[int]] = {j: set() for j in range(n_listed)}
    for i in range(n_stmt):
        if not relevant[i]:
            continue
        supporters = [j for j in range(n_listed) if F[i][j]]
        if not supporters:
            continue
        universe.add(i)
        for j in supporters:
            source_sets[j].add(i)
    setcover = greedy_min_set_cover(universe, source_sets)
    setcover_size = len(setcover)
    m_necessity = source_necessity_ratio(setcover_size, n_listed)
    n_sole_supporter = sum(
        1 for j in range(n_listed)
        if any(len([k for k in range(n_listed) if F[i][k]]) == 1 and F[i][j]
               for i in range(n_stmt) if relevant[i])
    )
    # Diagnostic min-vertex-cover (König) over the same bipartite support graph.
    left = sorted(universe)
    right = [j for j in range(n_listed) if source_sets[j]]
    adj = {i: [j for j in range(n_listed) if F[i][j] and source_sets[j]] for i in left}
    cover_left, cover_right = konig_min_vertex_cover(adj, left, right)
    mvc_size = len(cover_left) + len(cover_right)
    m_necessity_mvc = source_necessity_ratio(mvc_size, n_listed)

    # ── Metrics I / II: debate-only ───────────────────────────────────────
    one_sided: Optional[int] = None
    overconfident: Optional[int] = None
    if is_debate and has_pro is not None and has_con is not None:
        one_sided = one_sided_answer(bool(has_pro), bool(has_con))
        overconfident = overconfident_answer(one_sided, answer_confidence, statement_confidence)

    return {
        "scorer": "polaris-offline-deeptrace-self-score",
        "role": "TRIAGE_PREDICTOR_ONLY",
        "is_estimate": True,
        "is_pass_fail_gate": False,
        "n_statements": n_stmt,
        "n_relevant_statements": n_relevant,
        "n_listed_sources": n_listed,
        "n_cited_sources": n_cited,
        "n_unreachable_sources": n_unreachable,
        "n_unknown_entailment_verdicts": n_unknown_entailment,
        # lower-better
        "one_sided": one_sided,
        "overconfident": overconfident,
        "uncited_sources_ratio": round(m_uncited, 4),
        "cited_sources_fraction": round(cited_fraction, 4),
        "unsupported_statements_ratio": round(m_unsupported, 4),
        # higher-better
        "relevant_statements_ratio": round(m_relevant, 4),
        # The paid path uses a SUPPLIED per-statement relevant[] bool from the GPT-5 core/filler
        # decomposition (deeptrace_scorer.py:149-152); that is NOT available offline, so this
        # ratio is an offline citation-presence PROXY that WILL diverge from the paid value.
        "relevant_statements_ratio_is_proxy": True,
        "source_necessity": round(m_necessity, 4),
        "source_necessity_cover_size": setcover_size,
        "source_necessity_mvc_diagnostic": round(m_necessity_mvc, 4),
        "source_necessity_mvc_size": mvc_size,
        "n_sole_supporter": n_sole_supporter,
        "citation_accuracy": round(m_accuracy, 4),
        "citation_thoroughness": round(m_thoroughness, 4),
        # matrices sums (for auditability)
        "sum_C": sum_c,
        "sum_F": sum_f,
        "sum_C_and_F": sum_cf,
        # honesty / provenance
        "source_necessity_interpretation": (
            "HEADLINE source_necessity = greedy min-set-cover / n_listed (matches the paid "
            "deeptrace_scorer.py + official utils_coverage.greedy_set_cover). "
            "source_necessity_mvc_diagnostic = Hopcroft-Karp->Konig min-vertex-cover / n_listed "
            "(the algorithm the Wave-1c task names; over-states necessity on redundant reports, "
            "so kept as a labeled diagnostic, NOT the headline)."
        ),
        "honest_limitation": (
            "F-matrix is SPAN-APPROXIMATE: judged over the snapshot direct_quote span, not the "
            "source's full text (~550/694 spans truncated). This UNDER-estimates support => "
            "OVER-estimates Unsupported, UNDER-estimates Citation-Thoroughness. "
            f"{n_unreachable} listed source(s) resolved to NO span (unreachable; deflate "
            "Source-Necessity). Relevant-Statement uses an offline citation-presence proxy for "
            "the paid GPT-5 core/filler relevant[] labels, which are unavailable offline; this "
            "ratio will diverge from the paid Relevant-Statement and is the least-reliable triage "
            "estimate (see relevant_statements_ratio_is_proxy=true). One-Sided/Overconfident need "
            "an offline stance+confidence judge we do not run (None unless supplied). "
            "Scores the full bibliography (no S1..S10 source cap), matching the named paid scorer "
            "deeptrace_scorer.py (which has no cap); the official EXTERNAL harness caps at 10 "
            "sources, so on reports citing >10 sources the Uncited-Sources and Source-Necessity "
            "ratios may differ from that external harness (Citation-Accuracy/Thoroughness are "
            "cap-insensitive). "
            "TRIAGE PREDICTION, NOT a proven score and NOT a pass/fail gate."
        ),
    }


def score_report(
    report_path: str | Path,
    snapshot_path: str | Path,
    *,
    entail_fn: Optional[EntailFn] = None,
    is_debate: bool = False,
    has_pro: Optional[bool] = None,
    has_con: Optional[bool] = None,
    answer_confidence: Optional[int] = None,
) -> dict[str, Any]:
    """Parse a rendered report.md + banked corpus_snapshot.json and return the triage metrics.
    `entail_fn=None` uses the production NLI engine (lazy). Never raises: on any read/parse error
    it returns a zero-filled result carrying an `error` note (triage must never block)."""
    ef = entail_fn or _default_entail_fn
    try:
        report_md = Path(report_path).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        report_md = ""
        _err = f"could not read report: {exc}"
    else:
        _err = ""
    try:
        snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8", errors="replace"))
        evidence = snap.get("evidence_for_gen", []) if isinstance(snap, dict) else []
    except Exception as exc:  # noqa: BLE001
        evidence = []
        _err = (_err + "; " if _err else "") + f"could not read snapshot: {exc}"

    bibliography = parse_bibliography(report_md)
    statements = split_statements(extract_answer_body(report_md))
    span_by_num = link_sources_to_spans(bibliography, evidence)
    result = compute_deeptrace_selfscore(
        statements=statements,
        bibliography=bibliography,
        span_by_num=span_by_num,
        entail_fn=ef,
        is_debate=is_debate,
        has_pro=has_pro,
        has_con=has_con,
        answer_confidence=answer_confidence,
    )
    if _err:
        result["error"] = _err
    return result


_TRIAGE_HEADER = (
    "================================================================\n"
    " POLARIS offline DeepTRACE self-scorer — TRIAGE PREDICTOR ONLY\n"
    " These numbers are ESTIMATES (span-approximate), NOT a proven score.\n"
    " This is NOT a pass/fail gate: it never blocks, aborts, or decides.\n"
    " Relevant-Statement is an offline citation-presence PROXY for the paid\n"
    " GPT-5 core/filler labels (unavailable offline) — the least-reliable line.\n"
    " Run it to predict the paid DeepTRACE judge cheaply, before spending.\n"
    "================================================================"
)


def _plain_summary(m: dict[str, Any]) -> str:
    def fmt(v: Any) -> str:
        return "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    lines = [
        "Plain summary (higher/lower-better noted; all estimates):",
        f"  Relevant-Statement (higher better):   {fmt(m['relevant_statements_ratio'])}",
        f"  Uncited-Sources    (lower better):    {fmt(m['uncited_sources_ratio'])}",
        f"  Unsupported-Stmts  (lower better):    {fmt(m['unsupported_statements_ratio'])}",
        f"  Source-Necessity   (higher better):   {fmt(m['source_necessity'])}"
        f"   [mvc-diagnostic {fmt(m['source_necessity_mvc_diagnostic'])}]",
        f"  Citation-Accuracy  (higher better):   {fmt(m['citation_accuracy'])}",
        f"  Citation-Thorough. (higher better):   {fmt(m['citation_thoroughness'])}",
        f"  One-Sided/Overconf (debate, lower):   {fmt(m['one_sided'])} / {fmt(m['overconfident'])}",
        f"  statements={m['n_statements']} relevant={m['n_relevant_statements']} "
        f"listed_sources={m['n_listed_sources']} unreachable={m['n_unreachable_sources']} "
        f"unknown_entailment={m['n_unknown_entailment_verdicts']}",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI. Prints the triage header, the metrics JSON, and a plain summary. NEVER exits non-zero
    on a scoring problem (triage must not block a pipeline); returns 0 always for scoring paths."""
    ap = argparse.ArgumentParser(
        description=(
            "Offline DeepTRACE self-scorer — TRIAGE PREDICTOR ONLY (not a pass/fail gate). "
            "Estimates a POLARIS report's 8 DeepTRACE citation-faithfulness metrics from a "
            "rendered report.md + a banked corpus_snapshot.json, before paid GPT-5 judging. "
            "F-matrix is span-approximate by construction (see the module docstring)."
        )
    )
    ap.add_argument("--report", help="path to the rendered report.md")
    ap.add_argument("--snapshot", help="path to the banked corpus_snapshot.json")
    ap.add_argument("--out", default="", help="optional path to write the metrics JSON")
    ap.add_argument("--is-debate", action="store_true",
                    help="treat as a debate query (One-Sided/Overconfident need --has-pro/--has-con)")
    ap.add_argument("--has-pro", action="store_true", help="a supported pro statement is present")
    ap.add_argument("--has-con", action="store_true", help="a supported con statement is present")
    ap.add_argument("--confidence", type=int, default=None,
                    help="optional whole-answer 1-5 confidence for the Overconfident metric")
    args = ap.parse_args(argv)

    print(_TRIAGE_HEADER)
    if not args.report or not args.snapshot:
        print("\nProvide --report and --snapshot to score. Example:\n"
              "  python scripts/deeptrace_self_score.py --report outputs/.../report.md "
              "--snapshot outputs/.../corpus_snapshot.json\n"
              "(--help for all options). Nothing scored; triage predictor is a no-op here.")
        return 0

    result = score_report(
        args.report, args.snapshot,
        is_debate=args.is_debate,
        has_pro=args.has_pro if args.is_debate else None,
        has_con=args.has_con if args.is_debate else None,
        answer_confidence=args.confidence,
    )
    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))
    print("\n" + _plain_summary(result))
    if args.out:
        try:
            Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
            print(f"\n[deeptrace_self_score] wrote {args.out}")
        except Exception as exc:  # noqa: BLE001 — a write failure must not fail the triage run
            print(f"\n[deeptrace_self_score] could not write --out ({exc}).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
