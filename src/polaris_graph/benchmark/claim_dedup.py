"""I-perm-024 (#1216) — Claimify-style claim-atom dedup for the beat-both scorer.

Anti-inflation pass: BEFORE the extended metrics roll up over the per-claim audit
ledger, collapse near-duplicate claim atoms so that N restatements of one obvious
fact count ONCE. Without this, a verbose report could inflate
``faithfulness_precision`` / ``citation_support_rate`` / ``diversity_score`` simply
by repeating the same easy claim — a §-1.1-banned "more text = better" loophole.

Pure text + deterministic. Operates on the claim TEXT only and returns index
groups; the caller (``extended_metrics``) joins the kept indices back to its
``ClaimRow``s. Applied IDENTICALLY to every system (no POLARIS bias).

Merge rule (conservative — under-merge is safe, over-merge is the risk):
  two claims merge iff
    (a) their numeric signatures are COMPATIBLE (equal, or at least one empty, and
        no populated-axis conflict — reuses the ``fact_dedup`` populated-axis lesson
        so "3.7% in 2014" never merges with "3.7% in 2016"), AND
    (b) their content-token Jaccard >= ``min_jaccard`` (default 0.80).
The dedup is REPORTED (n_raw / n_kept / groups), never silent.

SOTA framing: Claimify (arXiv 2407.03572) decomposes + deduplicates claims before
scoring; here we only need the dedup half over already-extracted atoms.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.polaris_graph.generator.fact_dedup import (
    FactSignature,
    extract_signature,
)

# A frozen, env-overridable default. Higher = more conservative (fewer merges).
_DEFAULT_MIN_JACCARD = 0.80

# Content-token extraction: lowercase alphanumeric tokens of length >= 3, minus a
# tiny closed-class stoplist. Numbers stay (they also feed the signature) so that
# "20%" vs "37%" lowers Jaccard too — defense in depth with the signature check.
# Hyphen/slash-preserving tokens (Codex diff-gate iter-3 P1): keep biomedical entity
# tokens INTACT — "IL-6" / "IL-10" / "CD4/CD8" are ONE token each, not split into a
# dropped "il" + a bare digit. Without this, "IL-6 ... 20%" tokenized to just {6} and
# merged with "TNF ... 20%" / "IL-10 ... 20%".
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)*")
_STOPWORDS = frozenset(
    "the a an and or of to in for with on at by from as is are was were be been "
    "that this these those it its their his her our your they we he she than then "
    "which who whom whose into over under between among within without".split()
)


def _content_tokens(text: str) -> frozenset[str]:
    """Tokens for the Jaccard similarity (noise-reduced: length >= 3, non-stopword)."""
    toks = {
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) >= 3 and t not in _STOPWORDS
    }
    return frozenset(toks)


# Surrounding sentence/grouping punctuation stripped from a subject token's EDGES only;
# every other character (sign +/-, slash, Greek α/β, %, internal hyphen, digits) is kept
# VERBATIM so it can distinguish entities. (Codex diff-gate iter-4 P1.)
_SUBJECT_EDGE_STRIP = ".,;:!?()[]{}\"'`…«»‹›—–"


def _subject_tokens(text: str) -> frozenset[str]:
    """Entity/subject tokens for the SWAP guard, extracted ROBUSTLY (Codex diff-gate
    iter-2/3/4 P1 class). Split on whitespace, lowercase, strip ONLY surrounding
    sentence/grouping punctuation, and keep the token BODY verbatim. This preserves
    EVERY clinically-distinguishing character — sign suffixes (`CD4+` vs `CD4-`, `pks+`
    vs `pks-`), Greek variants (`IL-1α` vs `IL-1β`), hyphens (`IL-6` vs `IL-10`),
    alphanumerics (`SGLT2` vs `DPP4`), and short symbols (`Zn` vs `Cu`) — so any two
    DISTINCT entities produce DIFFERENT subject tokens and trigger the mutual-swap
    block. A token with NO letter (pure number/punctuation) is excluded (numeric
    differences are the signature-conflict guard's job); stopwords are dropped. Being
    maximally character-preserving here only makes the dedup MORE conservative
    (under-merge = §-1.1-safe; over-merge is the lethal direction we forbid)."""
    out: set[str] = set()
    for raw in text.lower().split():
        t = raw.strip(_SUBJECT_EDGE_STRIP)
        if t and t not in _STOPWORDS and any(c.isalpha() for c in t):
            out.add(t)
    return frozenset(out)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _subjects_differ(a_subjects: frozenset[str], b_subjects: frozenset[str]) -> bool:
    """True iff the two claims have ANY subject-token difference (in EITHER direction).

    Codex diff-gate iter-1..5 found that a token heuristic cannot tell a non-distinguishing
    elaboration ("fiber" vs "dietary fiber") from a clinically-distinct SUBGROUP narrowing
    ("breast cancer" vs "HER2+ breast cancer", "T cells" vs "CD4+ T cells", "aspirin" vs
    "low-dose aspirin") — both are one-sided subset modifiers. Since over-merging two
    distinct clinical facts is the §-1.1 LETHAL direction and under-merging is safe, the
    dedup requires IDENTICAL subject-token sets to merge: ANY subject difference (mutual
    swap OR one-sided subset) blocks the merge. Only verbatim repeats / pure reorderings
    (identical subjects) collapse — exactly the inflation vector the dedup must stop —
    while every subject/modifier difference is preserved as a distinct claim."""
    return a_subjects != b_subjects


def _signatures_conflict(a: FactSignature, b: FactSignature) -> bool:
    """True iff a populated context axis (percent-decimals OR years OR dollars) is
    populated on BOTH sides AND has zero intersection — i.e. the two claims carry
    DIFFERENT numbers and must NOT be merged. Mirrors
    ``fact_dedup._signatures_conflict`` (the populated-axis lesson) but also guards
    the decimal axis, since for claim atoms a different percentage IS a different
    fact."""
    if a.is_empty() or b.is_empty():
        return False
    decimals_conflict = (a.decimals and b.decimals) and not (a.decimals & b.decimals)
    years_conflict = (a.years and b.years) and not (a.years & b.years)
    dollars_conflict = (
        (a.dollar_buckets and b.dollar_buckets)
        and not (a.dollar_buckets & b.dollar_buckets)
    )
    return bool(decimals_conflict or years_conflict or dollars_conflict)


@dataclass
class DedupResult:
    """Result of a dedup pass over a list of claim texts.

    ``groups`` is a list of clusters, each a list of original indices with the
    REPRESENTATIVE (lowest original index) first. ``representatives`` is the list
    of representative indices (one per group), in ascending order — the caller
    keeps exactly these.
    """
    groups: list[list[int]] = field(default_factory=list)

    @property
    def representatives(self) -> list[int]:
        return sorted(g[0] for g in self.groups)

    @property
    def n_raw(self) -> int:
        return sum(len(g) for g in self.groups)

    @property
    def n_kept(self) -> int:
        return len(self.groups)

    @property
    def n_collapsed(self) -> int:
        return self.n_raw - self.n_kept

    def collapsed_groups(self) -> list[list[int]]:
        """Only the groups that actually merged >1 claim (for the audit trail)."""
        return [g for g in self.groups if len(g) > 1]


def dedup_claims(
    texts: list[str], *, min_jaccard: float = _DEFAULT_MIN_JACCARD,
) -> DedupResult:
    """Greedy deterministic claim dedup.

    Each claim joins the FIRST existing cluster it is compatible with (compatible =
    no numeric-signature conflict AND no mutual subject/entity SWAP against ANY member
    AND Jaccard >= min_jaccard against the cluster representative); otherwise it starts
    a new cluster. Deterministic: input order is preserved, representative = lowest
    index, no RNG.
    """
    sigs = [extract_signature(t) for t in texts]
    toks = [_content_tokens(t) for t in texts]   # for Jaccard
    stoks = [_subject_tokens(t) for t in texts]  # for the entity-swap guard
    clusters: list[list[int]] = []
    cluster_rep_tokens: list[frozenset[str]] = []
    for i in range(len(texts)):
        placed = False
        for ci, cluster in enumerate(clusters):
            # no numeric conflict AND IDENTICAL subject-token sets (any subject
            # difference — swap OR one-sided subset — blocks the merge; §-1.1-safe)
            if any(_signatures_conflict(sigs[i], sigs[m]) for m in cluster):
                continue
            if any(_subjects_differ(stoks[i], stoks[m]) for m in cluster):
                continue
            if _jaccard(toks[i], cluster_rep_tokens[ci]) >= min_jaccard:
                cluster.append(i)
                placed = True
                break
        if not placed:
            clusters.append([i])
            cluster_rep_tokens.append(toks[i])
    return DedupResult(groups=clusters)
