"""Cross-section fact-dedup pass — GH#423 I-gen-002.

After all multi_section generation completes (parallel asyncio.gather)
but BEFORE strict_verify drops bad sentences, this module:

  1. Extracts a numeric-token signature per sentence (percentages,
     dollar amounts bucketed by ±5%, years).
  2. Groups sentences across sections by signature.
  3. For each group with len > 1: marks the FIRST section's instance
     as PRIMARY, all others as REDUNDANT.
  4. Issues a SINGLE batched LLM call to rewrite REDUNDANT sentences
     as cross-references (e.g., "as noted under Efficacy [ev_X]").
  5. Returns updated sections with redundant sentences replaced.

Failure handling: if the rewrite LLM call fails or returns malformed
output, fall back to keeping the PRIMARY only and DROPPING all
REDUNDANTS. This is the safe degradation per Codex review
(GH#423 quality analysis, .codex/I-gen-002/codex_path_quality_output.txt
strict_verify_interaction=8/10, failure_modes=8/10).

Section ordering for PRIMARY selection: the order returned by the
caller (typically the outline-defined order: Efficacy → Comparative
→ Regulatory → Population Subgroups → Long-term Outcomes for policy
templates; Efficacy → Safety → Comparative → Mechanism → Regulatory
for clinical). The first-section-in-order wins for any duplicate
fact.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.fact_dedup")


# ─────────────────────────────────────────────────────────────────────────
# Numeric-token extraction
# ─────────────────────────────────────────────────────────────────────────

# Percentages: "8.7%", "8.7 percent", "8.7 per cent"
_PERCENT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|per[ \-]?cent\b|percent\b)",
    re.IGNORECASE,
)

# Dollar amounts: "$200", "$1.4 billion", "CAD $700 million", "USD 299M"
_DOLLAR_RE = re.compile(
    r"(?:\$|\bUSD\s*|\bCAD\s*)\s*"
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(billion|million|thousand|B|M|K|bn|mn)?\b",
    re.IGNORECASE,
)

_DOLLAR_UNIT_SCALE = {
    "billion": 1_000_000_000, "bn": 1_000_000_000, "b": 1_000_000_000,
    "million": 1_000_000, "mn": 1_000_000, "m": 1_000_000,
    "thousand": 1_000, "k": 1_000,
    None: 1, "": 1,
}

# Years: 4-digit 19xx or 20xx
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _round_dollar_to_bucket(amount: float, tolerance: float = 0.05) -> int:
    """Round a dollar amount to a ±5% bucket for signature comparison.

    Example: $11.2B and $11.4B both round to the same bucket (~$11B).
              $11.2B and $13.4B fall in different buckets (gap > 5%).
    """
    if amount <= 0:
        return 0
    # log-space bucketing: round to nearest 5% step
    import math
    log_amount = math.log10(amount)
    step = math.log10(1 + tolerance)
    bucket_idx = round(log_amount / step)
    # Return the bucket as an int (representative midpoint)
    return int(round(10 ** (bucket_idx * step)))


@dataclass(frozen=True)
class FactSignature:
    """Canonical signature for a sentence's quantitative content.

    Two sentences with the SAME signature are candidates for being
    duplicate-fact instances. Empty signature (no decimals/dollars/years)
    means the sentence has no quantitative content and is NOT a dedup
    candidate.
    """
    decimals: frozenset[float] = field(default_factory=frozenset)
    dollar_buckets: frozenset[int] = field(default_factory=frozenset)
    years: frozenset[int] = field(default_factory=frozenset)

    def is_empty(self) -> bool:
        return not (self.decimals or self.dollar_buckets or self.years)


def extract_signature(sentence: str) -> FactSignature:
    """Extract a FactSignature from a sentence.

    Decimals: floats from percentages.
    Dollar buckets: dollar amounts bucketed by ±5% (after unit normalization).
    Years: 4-digit 19xx/20xx integers.
    """
    decimals: set[float] = set()
    for match in _PERCENT_RE.finditer(sentence):
        try:
            decimals.add(round(float(match.group(1)), 2))
        except (ValueError, TypeError):
            continue

    dollar_buckets: set[int] = set()
    for match in _DOLLAR_RE.finditer(sentence):
        try:
            amount = float(match.group(1).replace(",", ""))
        except (ValueError, TypeError):
            continue
        unit = (match.group(2) or "").lower()
        scale = _DOLLAR_UNIT_SCALE.get(unit, 1)
        normalized = amount * scale
        dollar_buckets.add(_round_dollar_to_bucket(normalized))

    years: set[int] = set()
    for match in _YEAR_RE.finditer(sentence):
        try:
            years.add(int(match.group(1)))
        except (ValueError, TypeError):
            continue

    return FactSignature(
        decimals=frozenset(decimals),
        dollar_buckets=frozenset(dollar_buckets),
        years=frozenset(years),
    )


# ─────────────────────────────────────────────────────────────────────────
# PROSE-repetition clustering — I-beatboth-011 §3.3 (#1289)
# ─────────────────────────────────────────────────────────────────────────
#
# Coverage-map finding (.codex/I-beatboth-010/full_coverage.md §3.3): build_groups SKIPS any sentence
# whose numeric FactSignature .is_empty() (the ~498-499 `continue`). So PURE-PROSE restatements (no
# %/$/year token — e.g. report.md L39/L43's 10-15x Autor/Acemoglu sentences) NEVER cluster and the
# audited prose repetition is structurally invisible. Worse, the L39/L43 case is INTRA-section, which
# the numeric path's ≥2-distinct-section gate also excludes.
#
# Fix: a deterministic, offline, pure-python PROSE pass (NO new deps, NO embeddings) that clusters the
# empty-signature sentences by content-word n-gram SHINGLE-SET EXACT JACCARD with a HIGH threshold
# (default 0.82) so ONLY near-identical restatements cluster — conservative: it must NEVER merge
# distinct claims. (MinHash+LSH is the scalable APPROXIMATION for trillion-token corpora; plain exact
# Jaccard is correct at our hundreds-of-sentences scale.) A prose cluster with ≥2 OCCURRENCES (intra
# OR cross section) becomes a RedundancyGroup that flows through the SAME keep-all cross-ref rewrite as
# the numeric path — never dropping a source or a citation (§-1.3 consolidate-keep-all).
#
# GATED behind PG_FACT_DEDUP_PROSE (default OFF => build_groups is byte-identical to today; the
# benchmark slate forces it ON). FAITHFULNESS: strict_verify / NLI / 4-role / span-grounding untouched.
PROSE_DEDUP_ENV = "PG_FACT_DEDUP_PROSE"
PROSE_JACCARD_ENV = "PG_FACT_DEDUP_PROSE_JACCARD"
_PROSE_JACCARD_DEFAULT = "0.82"
# A prose sentence must carry at least this many content words to be a clustering candidate (a very
# short sentence shingle-overlaps too easily — false-positive risk).
_PROSE_MIN_CONTENT_WORDS = 4

# Citation tokens stripped before shingling: `[#ev:id:a-b]`, `[ev_id]`, `[12]`, etc. (the surface
# citation markers are NOT content — only the prose words decide redundancy).
_CITATION_TOKEN_RE = re.compile(r"\[(?:#ev:[^\]]*|ev_[^\]]*|\d+)\]")
_WORD_RE = re.compile(r"[a-z0-9]+")

# I-wire-014 (#1335) FIX-D faithfulness guard for the NLI prose-dedup path. The benchmarked
# SAFE winner (mutual-entailment + these two guards) held distinct_claims_preserved_rate = 1.0;
# the bare mutual-entailment in-tree path lacked them and could merge two claims that happen to
# entail but cite DIFFERENT sources or carry a DISTINCT number. So a redundant joins a primary
# only when it shares the SAME citation SET and introduces NO new number (its numbers ⊆ primary's).
_BARE_NUM_RE = re.compile(r"\d[\d,.]*")


def _nli_cite_set(sentence: str) -> frozenset:
    """Order-independent set of citation markers in a sentence ([#ev:..]/[ev_..]/[N])."""
    return frozenset(_CITATION_TOKEN_RE.findall(sentence or ""))


def _nli_num_set(sentence: str) -> frozenset:
    """Bare numbers in a sentence AFTER stripping citation markers (so [8] is not a number)."""
    stripped = _CITATION_TOKEN_RE.sub(" ", sentence or "")
    return frozenset(_BARE_NUM_RE.findall(stripped))

# A small, conservative English stopword set (deterministic; no external dep). Dropping stopwords keeps
# the shingle set focused on CONTENT words so "the/and/of" padding does not inflate Jaccard.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from", "had", "has",
    "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their", "them",
    "they", "this", "to", "was", "were", "which", "with", "their", "these", "those", "than",
})

# Sentinel shingle frozenset for sentences too short to cluster — it shares nothing with anything
# (a fresh object each call would still be empty; using a module-level empty frozenset is fine because
# Jaccard against an empty set is 0, so it can never match).
_PROSE_NO_MATCH: frozenset = frozenset()


def _prose_dedup_enabled() -> bool:
    """PG_FACT_DEDUP_PROSE gate. B15 (#1359) FLIP-ON: DEFAULT-ON now — the in-tree Jaccard prose
    path is the deterministic, dep-free fallback consolidation winner (clusters the empty-numeric-
    signature sentences that the numeric path skips, killing the degenerate one-fact-~10x repetition).
    It routes through the UNCHANGED keep-all cross-ref rewrite (every citation of every clustered
    sentence is preserved — §-1.3 consolidate-keep-all) and is re-verified by strict_verify at the
    rewrite seam, so faithfulness is untouched. LAW VI kill-switch: set PG_FACT_DEDUP_PROSE=0 to
    restore the byte-identical legacy (prose pass skipped)."""
    return os.getenv(PROSE_DEDUP_ENV, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _read_prose_jaccard() -> float:
    """Read PG_FACT_DEDUP_PROSE_JACCARD as a float in (0, 1]. Malformed/out-of-range => default 0.82
    (logged once at WARNING, never raised — a typo must not crash a paid run)."""
    raw = os.environ.get(PROSE_JACCARD_ENV, "").strip() or _PROSE_JACCARD_DEFAULT
    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[fact_dedup] %s=%r is not a float; using default %s",
            PROSE_JACCARD_ENV, raw, _PROSE_JACCARD_DEFAULT,
        )
        return float(_PROSE_JACCARD_DEFAULT)
    if not (0.0 < value <= 1.0):
        logger.warning(
            "[fact_dedup] %s=%s out of (0,1]; using default %s",
            PROSE_JACCARD_ENV, value, _PROSE_JACCARD_DEFAULT,
        )
        return float(_PROSE_JACCARD_DEFAULT)
    return value


def _prose_shingles(sentence: str) -> frozenset:
    """Normalize a sentence to a content-word shingle set for prose-redundancy Jaccard.

    Steps: lowercase -> strip the [#ev:...]/[ev_id]/[N] citation tokens -> word-tokenize (alnum) ->
    drop stopwords -> take word-UNIGRAMS AND word-BIGRAMS (bigrams give order-sensitivity so
    "AI raised productivity" != "productivity raised AI"). Returns a frozenset of shingle strings.
    A sentence with fewer than `_PROSE_MIN_CONTENT_WORDS` content words returns the never-matching
    sentinel `_PROSE_NO_MATCH` (so trivially-short prose is NOT clustered)."""
    text = _CITATION_TOKEN_RE.sub(" ", sentence.lower())
    words = [w for w in _WORD_RE.findall(text) if w not in _STOPWORDS]
    if len(words) < _PROSE_MIN_CONTENT_WORDS:
        return _PROSE_NO_MATCH
    shingles: set[str] = set(words)  # unigrams
    for i in range(len(words) - 1):  # bigrams
        shingles.add(words[i] + " " + words[i + 1])
    return frozenset(shingles)


def _jaccard(a: frozenset, b: frozenset) -> float:
    """Exact Jaccard similarity |a∩b| / |a∪b|. Empty-either side => 0.0 (never a match)."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


# Polarity / negation guard for the prose-Jaccard pass (Codex #1289 iter-1 P1). Content-word shingle
# Jaccard is polarity-BLIND: "X raised wages" vs "X lowered wages", or a long claim differing only by an
# inserted "not", share almost all shingles and clear 0.82 — yet assert OPPOSITE claims. Clustering them
# would cross-ref one real, opposing claim away (a silent claim drop). Two prose sentences may cluster
# ONLY when their polarity signature matches exactly. Deterministic token sets; no external dep, no LLM.
_NEGATION_CUES = frozenset({
    "not", "no", "never", "none", "without", "cannot", "cant", "nor", "neither",
    "lack", "lacks", "lacking", "absent", "fail", "fails", "failed", "failing", "nothing",
})
_DIRECTION_DOWN = frozenset({
    "decline", "declined", "declines", "decrease", "decreased", "decreases", "reduce", "reduced",
    "reduces", "reduction", "fell", "fall", "falls", "fallen", "drop", "dropped", "drops", "lower",
    "lowered", "lowers", "fewer", "less", "loss", "losses", "lost", "shrink", "shrank", "shrunk",
    "worsen", "worsened", "weaken", "weakened", "negative", "down", "slower", "slowed", "depress",
    "depressed", "suppressed", "contracted", "contraction",
})
_DIRECTION_UP = frozenset({
    "increase", "increased", "increases", "rise", "rose", "risen", "rises", "grew", "grow", "grows",
    "growth", "higher", "more", "greater", "gain", "gained", "gains", "raise", "raised", "raises",
    "expand", "expanded", "expands", "boost", "boosted", "improve", "improved", "improves",
    "improvement", "positive", "up", "faster", "accelerate", "accelerated", "surged", "surge",
})


def _polarity_signature(sentence: str) -> tuple:
    """A deterministic polarity fingerprint: (sorted negation cues present, has_contraction_negation,
    has_DOWN-direction, has_UP-direction). Two prose sentences may cluster ONLY when their signatures
    are equal, so a single inserted ``not`` / ``n't`` or a ``raised``↔``lowered`` antonym flip blocks
    the merge even at Jaccard ~1.0. Pure guard (never a relax): it can only PREVENT a merge, never force
    one — so it can only KEEP more sources, never drop one (§-1.3)."""
    text = _CITATION_TOKEN_RE.sub(" ", (sentence or "").lower())
    has_nt = "n't" in text or "n’t" in text
    words = set(_WORD_RE.findall(text))
    return (
        tuple(sorted(words & _NEGATION_CUES)),
        has_nt,
        bool(words & _DIRECTION_DOWN),
        bool(words & _DIRECTION_UP),
    )


def _build_prose_groups(
    sections: dict[str, list[str]],
    section_order: list[str],
    threshold: float,
) -> list["RedundancyGroup"]:
    """Cluster the EMPTY-numeric-signature sentences (the ones build_groups currently skips) by
    content-word shingle Jaccard >= threshold. A cluster with >=2 OCCURRENCES (intra OR cross section)
    becomes a RedundancyGroup: primary = first occurrence in section_order, the rest redundants.

    Reuses the SAME RedundancyGroup / SentenceLocation shapes the numeric path uses, so the downstream
    rewrite (keep-all cross-ref) is unchanged. Deterministic greedy single-pass clustering: each
    candidate joins the FIRST existing cluster whose representative shingle set is within threshold,
    else opens a new cluster — correct at our scale and order-stable.

    I-deepfix-001 D1 (#1344): this prose pass is the SENTENCE-layer counterpart of the §-1.3
    "CONSOLIDATE qualitative claims too" guarantee. The SOURCE-basket layer (synthesis/finding_dedup.py
    ``_build_qualitative_groups``) forms the matching NON-NUMERIC corroboration basket the D1 diced dice
    asserts. Both layers share the SAME conservative predicate (high content-word shingle Jaccard + the
    polarity guard below) so neither merges two DIFFERENT qualitative claims, and both KEEP-ALL.
    """
    # Collect every empty-numeric-signature location (the prose candidates) in section_order.
    prose_locs: list[SentenceLocation] = []
    for section_title in section_order:
        if section_title not in sections:
            continue
        for idx, sentence in enumerate(sections[section_title]):
            sig = extract_signature(sentence)
            if not sig.is_empty():
                continue  # numeric sentences belong to the numeric path, NOT the prose path
            prose_locs.append(SentenceLocation(
                section=section_title, index=idx, sentence=sentence, signature=sig,
            ))

    # Greedy clustering by prose Jaccard. Each cluster is (representative_shingles, [locations]).
    clusters: list[tuple[frozenset, list[SentenceLocation]]] = []
    for loc in prose_locs:
        sh = _prose_shingles(loc.sentence)
        if sh is _PROSE_NO_MATCH or not sh:
            continue  # too short to cluster — never a redundancy candidate
        placed = False
        loc_polarity = _polarity_signature(loc.sentence)
        for rep, members in clusters:
            # Polarity must match the cluster primary (Codex #1289 P1): NEVER merge an opposite-polarity
            # claim ("raised" vs "lowered", or a "not" flip) even at high shingle-Jaccard, or a real
            # opposing claim would be cross-reffed away. Guard-only: it can only keep claims separate.
            if _polarity_signature(members[0].sentence) != loc_polarity:
                continue
            if _jaccard(sh, rep) >= threshold:
                members.append(loc)
                placed = True
                break
        if not placed:
            clusters.append((sh, [loc]))

    groups: list[RedundancyGroup] = []
    for _rep, members in clusters:
        if len(members) < 2:  # >=2 OCCURRENCES (intra OR cross section) — NOT a distinct-section gate
            continue
        primary = members[0]
        redundants = members[1:]
        groups.append(RedundancyGroup(
            signature=primary.signature, primary=primary, redundants=redundants,
        ))
    return groups


# ─────────────────────────────────────────────────────────────────────────
# Consolidation-NLI companion seam (I-wire-001 W1, #1306) — flag-gated default-OFF
# ─────────────────────────────────────────────────────────────────────────
def _consolidation_nli_enabled_factdedup() -> bool:
    """Gate for the COMPANION prose seam in ``build_groups``.

    Requires BOTH the master flag ``PG_CONSOLIDATION_NLI`` AND a dedicated opt-in sub-flag
    ``PG_CONSOLIDATION_NLI_PROSE`` (default-OFF). The companion seam clusters prose
    sentences and routes them through the cross-ref REWRITE — a CONTENT-LOSSY path
    (opposite direction to multi-citation) and currently UNVALIDATED by the §-1.4
    fire-test. The dedicated sub-flag prevents the master flag (which activates the
    faithful finding_dedup consolidation) from SILENTLY also activating this prose
    path on a future flag-flip.

    B15 (#1359) FLIP-ON: the sub-flag ``PG_CONSOLIDATION_NLI_PROSE`` now DEFAULTS-ON, so when the
    master ``PG_CONSOLIDATION_NLI`` cross-encoder winner is active the bidirectional-NLI prose path
    fires too (it is the primary same-claim consolidation that the Jaccard floor leaves separate —
    killing the degenerate one-fact-~10x repetition). The I-wire-014 (#1335) FIX-D guards
    (DIRECT mutual-entailment edge + same section + same citation SET + numbers ⊆ primary) held
    distinct_claims_preserved_rate = 1.0, so this path is no longer "unvalidated/lossy": it routes
    through the UNCHANGED keep-all cross-ref rewrite (every citation preserved, §-1.3 consolidate)
    and is re-verified by strict_verify. The MASTER flag still gates it: if ``PG_CONSOLIDATION_NLI``
    is OFF this stays OFF (no cross-encoder ever loaded). LAW VI kill-switch:
    PG_CONSOLIDATION_NLI_PROSE=0 restores the byte-identical legacy. Single source of truth for the
    master gate lives in ``consolidation_nli``; imported LAZILY so fact_dedup never pulls the
    cross-encoder when the sub-flag/master is off."""
    if resolve("PG_CONSOLIDATION_NLI_PROSE").strip().lower() in ("", "0", "false", "off", "no"):
        return False
    from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
        consolidation_nli_enabled,
    )

    return consolidation_nli_enabled()


def _read_nli_max_sentences() -> int:
    """`PG_CONSOLIDATION_NLI_MAX_SENTENCES` (default 200) — bounds the prose-path O(n^2)
    pairwise NLI. Malformed/out-of-range => default (logged, never raised)."""
    raw = os.environ.get("PG_CONSOLIDATION_NLI_MAX_SENTENCES", "").strip() or "200"
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning("[fact_dedup] PG_CONSOLIDATION_NLI_MAX_SENTENCES=%r not an int; using 200", raw)
        return 200
    return max(2, min(2000, value))


def _build_nli_prose_groups(
    sections: dict[str, list[str]],
    section_order: list[str],
) -> list["RedundancyGroup"]:
    """Cluster the EMPTY-numeric-signature sentences by BIDIRECTIONAL NLI (same-claim),
    mirroring ``_build_prose_groups`` but using the cross-encoder winner instead of the
    Jaccard floor. A cluster with >=2 occurrences becomes a RedundancyGroup (primary =
    first in section_order). Routes through the UNCHANGED keep-all cross-ref rewrite.
    Faithfulness-neutral (§-1.3): groups sentences only; relaxes no verify gate."""
    from src.polaris_graph.synthesis.consolidation_nli import group_clusters  # noqa: PLC0415

    prose_locs: list[SentenceLocation] = []
    for section_title in section_order:
        if section_title not in sections:
            continue
        for idx, sentence in enumerate(sections[section_title]):
            sig = extract_signature(sentence)
            if not sig.is_empty():
                continue
            prose_locs.append(SentenceLocation(
                section=section_title, index=idx, sentence=sentence, signature=sig,
            ))
    if len(prose_locs) < 2:
        return []

    # Bound the O(n^2) pairwise NLI on the prose path (no numeric value to bucket on here):
    # cap the candidate-sentence count via PG_CONSOLIDATION_NLI_MAX_SENTENCES (default 200 =>
    # <=19,900 pairs, under the default PG_CONSOLIDATION_NLI_MAX_PAIRS=20,000). Over the cap,
    # skip the prose NLI block (it is a companion seam; the primary effect is in
    # finding_dedup) rather than raise on a long report. Logged once, never silent-wrong.
    max_sentences = _read_nli_max_sentences()
    if len(prose_locs) > max_sentences:
        logger.warning(
            "[fact_dedup] consolidation-NLI prose block skipped: %d candidate sentences "
            "exceeds PG_CONSOLIDATION_NLI_MAX_SENTENCES=%d (companion seam; primary effect "
            "is finding_dedup.dedup_by_finding)", len(prose_locs), max_sentences,
        )
        return []

    # Strip citation tokens before NLI so the model scores the CLAIM, not the markers.
    texts = [_CITATION_TOKEN_RE.sub(" ", loc.sentence or "") for loc in prose_locs]

    # I-wire-014 (#1335) FIX-D: use DIRECT pairwise bidirectional-entailment edges (score_pairs),
    # NOT group_clusters' TRANSITIVE union-find. The dedup bake-off proved the transitive root
    # over-merges: A↔B and B↔C union A,B,C even when A and C do NOT directly entail, so a
    # distinct claim that entails only a sibling gets dropped (preserved fell to 0.976). The
    # validated-SAFE winner is keep-first over DIRECT edges + two guards: a redundant joins a
    # primary ONLY when it (a) DIRECTLY bidirectionally-entails the primary, (b) is in the SAME
    # section, (c) shares the SAME citation SET, and (d) introduces NO new number (its numbers ⊆
    # the primary's). Held distinct_claims_preserved_rate = 1.0. Faithfulness-neutral (§-1.3 — the
    # keep-all cross-ref rewrite preserves every citation of the merged members).
    from src.polaris_graph.synthesis.consolidation_nli import score_pairs  # noqa: PLC0415

    edges = score_pairs(texts)  # sorted (i, j), i < j, that bidirectionally entail
    entails: dict[int, set[int]] = {}
    for i, j in edges:
        entails.setdefault(i, set()).add(j)
        entails.setdefault(j, set()).add(i)

    groups: list[RedundancyGroup] = []
    consumed = [False] * len(prose_locs)
    for i in range(len(prose_locs)):
        if consumed[i]:
            continue
        primary = prose_locs[i]
        p_cites = _nli_cite_set(primary.sentence)
        p_nums = _nli_num_set(primary.sentence)
        direct = entails.get(i, set())
        redundants: list[SentenceLocation] = []
        for j in range(i + 1, len(prose_locs)):
            if consumed[j] or j not in direct:
                continue  # require a DIRECT mutual-entailment edge with the primary
            m = prose_locs[j]
            if (
                m.section == primary.section
                and _nli_cite_set(m.sentence) == p_cites
                and _nli_num_set(m.sentence) <= p_nums
            ):
                redundants.append(m)
                consumed[j] = True
        if redundants:
            consumed[i] = True
            groups.append(RedundancyGroup(
                signature=primary.signature, primary=primary, redundants=redundants,
            ))
    # I-wire-014 (#1335): FIRING SIGNAL so the prose-NLI dedup is verifiable in the run log
    # (per "verify the feature fired in OUTPUT, not config"). Logs even on a zero result.
    _n_redundant = sum(len(g.redundants) for g in groups)
    logger.info(
        "[fact_dedup] consolidation-NLI prose dedup FIRED: %d candidate sentence(s) -> %d group(s), "
        "%d redundant paraphrase(s) consolidated (direct-pairwise + same-section + cite-set + "
        "number guards; keep-all preserves every citation)",
        len(prose_locs), len(groups), _n_redundant,
    )
    return groups


# ─────────────────────────────────────────────────────────────────────────
# Grouping + redundancy identification
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class SentenceLocation:
    """Pointer to a sentence within section drafts."""
    section: str
    index: int  # position within the section's sentences list
    sentence: str
    signature: FactSignature


@dataclass
class RedundancyGroup:
    """A group of sentences that share a fact signature."""
    signature: FactSignature
    primary: SentenceLocation
    redundants: list[SentenceLocation]


def _signatures_overlap(
    a: FactSignature, b: FactSignature, min_decimal_overlap: int = 2,
) -> bool:
    """Overlap-based signature matcher — per Codex Phase 3 diagnosis.

    Two signatures are considered the same fact unit if they share
    EITHER:
      - At least `min_decimal_overlap` decimal values (e.g., 9.2% and
        13.9% appearing in both → semantic match even if years differ),
      - OR they share the COMPLETE decimal set AND have supporting
        year/dollar overlap (so a "3.7% in 2016" sentence does NOT match
        a "3.7% in 2014" sentence — different timepoints, different
        facts),
      - OR they share ≥2 dollar buckets.

    Strict pure-decimal match is allowed ONLY when both signatures have
    no years and no dollars (so the equality is truly about decimals
    alone, not coincidentally-same decimals in different contexts).

    Empty signatures never match.

    Codex iter-1 P1 fix: previously, pure-decimal equality matched even
    when years differed → false-positive deduplication risk on facts
    that share the same decimal across different timepoints/contexts.
    """
    if a.is_empty() or b.is_empty():
        return False
    # Path 0: exact-signature equality (legacy behavior preserved).
    # Codex iter-2 P1 regression fix: when two sentences carry the
    # IDENTICAL full FactSignature (e.g., both extract as
    # FactSignature(dollar_buckets={204}, decimals={}, years={}) for
    # "$200 more per person"), they ARE the same fact. The stricter
    # iter-1 fix accidentally regressed this case.
    if a == b:
        return True
    # Codex iter-4 P1 fix: populated-axis conflicts must block ALL
    # heuristic paths (Path 1/Path 2/Path 3), not just Path 2. Previously
    # the guard lived inside Path 2 only, so e.g. "3.0%/1.6% of $40K/$80K
    # in 2014" vs "3.0%/1.6% of $200K/$300K in 2014" could still match via
    # Path 1's ≥2-decimal shortcut (decimals shared, dollar buckets
    # disjoint while years overlap). Lift the guard to a top-level
    # precondition so any disjoint populated-axis disqualifies a match.
    years_conflict = (a.years and b.years) and not (a.years & b.years)
    dollars_conflict = (
        (a.dollar_buckets and b.dollar_buckets)
        and not (a.dollar_buckets & b.dollar_buckets)
    )
    if years_conflict or dollars_conflict:
        return False
    # Path 1: shared salient percentages (≥2 decimals in common)
    shared_decimals = a.decimals & b.decimals
    if len(shared_decimals) >= min_decimal_overlap:
        return True
    # Path 2: full decimal-set equality
    if a.decimals == b.decimals and a.decimals:
        # At least one supporting overlap → match
        if a.dollar_buckets & b.dollar_buckets or a.years & b.years:
            return True
        # Pure decimal-only match: allowed ONLY when both sides have NO
        # contextual years AND NO contextual dollars.
        if (not a.years and not b.years
                and not a.dollar_buckets and not b.dollar_buckets):
            return True
        return False
    # Path 3: shared dollar buckets (≥2 distinct amounts in common)
    shared_dollars = a.dollar_buckets & b.dollar_buckets
    if len(shared_dollars) >= 2:
        return True
    return False


def _signatures_conflict(a: FactSignature, b: FactSignature) -> bool:
    """True iff a populated context axis (years OR dollar_buckets) is
    populated on BOTH sides AND has zero intersection.

    Codex brief-iter-1 P1 fix: this is the same populated-axis-conflict
    check used by `_signatures_overlap` top-level guard, lifted into a
    helper so cluster-membership logic can reject contextless-bridge
    merges (e.g. A={2014} and C={2016} merged via B={} bridge).
    """
    if a.is_empty() or b.is_empty():
        return False
    years_conflict = (a.years and b.years) and not (a.years & b.years)
    dollars_conflict = (
        (a.dollar_buckets and b.dollar_buckets)
        and not (a.dollar_buckets & b.dollar_buckets)
    )
    return years_conflict or dollars_conflict


def _cluster_is_compatible(
    candidate: SentenceLocation, cluster: list[SentenceLocation],
) -> bool:
    """True iff candidate overlaps with AT LEAST ONE cluster member AND
    does NOT conflict with ANY cluster member.

    Phase 3 P1-2 fix (Codex review): previous greedy implementation
    compared candidate only against cluster[0]. Comparing against ALL
    members captures transitive chains (A↔B↔C where A↛C directly).

    Codex brief-iter-1 P1 fix: requiring "no conflict with any member"
    blocks the contextless-bridge merge — e.g. A={9.2%,13.9%,2014} and
    C={9.2%,13.9%,2016} would otherwise be merged via B={9.2%,13.9%}
    (which overlaps with both and conflicts with neither).
    """
    has_overlap = False
    for member in cluster:
        if _signatures_conflict(candidate.signature, member.signature):
            return False
        if _signatures_overlap(candidate.signature, member.signature):
            has_overlap = True
    return has_overlap


def _clusters_pairwise_compatible(
    cluster_a: list[SentenceLocation], cluster_b: list[SentenceLocation],
) -> bool:
    """True iff no member of cluster_a conflicts with any member of
    cluster_b.

    Codex brief-iter-1 P1 fix: when a candidate bridges two existing
    clusters X and Y, the candidate may be individually compatible with
    both (`_cluster_is_compatible` True for each) while X and Y
    themselves contain mutually-conflicting members. Without this
    pairwise check, the candidate would silently fuse incompatible
    clusters through its contextless overlap.
    """
    for a in cluster_a:
        for b in cluster_b:
            if _signatures_conflict(a.signature, b.signature):
                return False
    return True


_ENV_FACT_DEDUP_EXACT_INTRASECTION = "PG_FACT_DEDUP_EXACT_INTRASECTION"
_EXACT_DUP_WS_RE = re.compile(r"\s+")


def _fact_dedup_exact_intrasection_enabled() -> bool:
    """I-deepfix-001 tail-B1 (#1344, finding #10): kill-switch for the EXACT-duplicate intra-section
    consolidation (default ON). OFF => the pre-fix >=2-distinct-section gate is byte-identical."""
    return os.environ.get(_ENV_FACT_DEDUP_EXACT_INTRASECTION, "1").strip().lower() not in (
        "", "0", "false", "no", "off",
    )


def _exact_dup_norm(sentence: str) -> str:
    """Normalize a sentence for EXACT-duplicate detection: strip a leaked contract-field label
    prefix (so a claim differing from its twin ONLY by an echoed "Effect estimate with uncertainty:"
    label compares equal), then lowercase + collapse whitespace. PURE. The prefix stripper is
    imported lazily to keep this generator module free of a top-level roles import."""
    try:
        from src.polaris_graph.roles.contract_field_prefix import (  # noqa: PLC0415
            strip_contract_field_prefix,
        )
        base = strip_contract_field_prefix(sentence or "")
    except Exception:  # noqa: BLE001 — normalization must never break dedup; fall back to raw text
        base = sentence or ""
    return _EXACT_DUP_WS_RE.sub(" ", base.lower()).strip()


def build_groups(
    sections: dict[str, list[str]],
    section_order: Optional[list[str]] = None,
) -> list[RedundancyGroup]:
    """Group sentences across sections by overlap-matched FactSignature.

    Per Codex Phase 3 diagnosis (`.codex/I-gen-002-phase3/`): the
    earlier exact-FactSignature grouping was too strict — incidental
    years/dollars added in one section but not another broke the match.
    Now uses `_signatures_overlap` core-fact matcher to group
    semantically equivalent sentences even when contextual numerics
    differ.

    Args:
        sections: dict mapping section_title -> list of sentence strings.
        section_order: optional explicit ordering for PRIMARY selection.
            If None, falls back to insertion order of `sections` keys.

    Returns:
        List of RedundancyGroup, one per overlap-cluster appearing in
        2+ section-distinct sentences. Empty signatures are excluded.
        Sentences within the same section that share a signature are
        NOT counted as redundancy.
    """
    if section_order is None:
        section_order = list(sections.keys())

    # Collect all locations with their signatures
    all_locations: list[SentenceLocation] = []
    for section_title in section_order:
        if section_title not in sections:
            continue
        for idx, sentence in enumerate(sections[section_title]):
            sig = extract_signature(sentence)
            if sig.is_empty():
                continue
            all_locations.append(SentenceLocation(
                section=section_title, index=idx,
                sentence=sentence, signature=sig,
            ))

    # Transitive clustering by compatibility (overlap + no-conflict):
    # each location is compared against ALL members of each existing
    # cluster. The candidate joins a cluster iff it has at least one
    # overlapping member AND no conflicting member. When the candidate is
    # compatible with multiple clusters, those clusters are merged into
    # the lowest-index target ONLY IF the clusters themselves are
    # pairwise-compatible (no cross-cluster member conflict). This
    # prevents contextless-bridge merges (Codex brief-iter-1 P1 fix).
    clusters: list[list[SentenceLocation]] = []
    for loc in all_locations:
        compat_idx = [
            i for i, cluster in enumerate(clusters)
            if _cluster_is_compatible(loc, cluster)
        ]
        if not compat_idx:
            clusters.append([loc])
            continue
        target = clusters[compat_idx[0]]
        target.append(loc)
        # Codex brief-iter-2 P1 fix: check compatibility against the
        # GROWING target (not the original), so two non-target clusters
        # that conflict with each other cannot both be folded in via the
        # same candidate bridge. Iteration order is the natural compat_idx
        # order; for each follow-on candidate, the test is against the
        # target's CURRENT membership.
        merged_idx: list[int] = []
        for j in compat_idx[1:]:
            if _clusters_pairwise_compatible(target, clusters[j]):
                target.extend(clusters[j])
                merged_idx.append(j)
        for j in sorted(merged_idx, reverse=True):
            del clusters[j]

    groups: list[RedundancyGroup] = []
    _exact_relax = _fact_dedup_exact_intrasection_enabled()
    for cluster in clusters:
        # Filter: at least 2 distinct sections must share this cluster
        distinct_sections = {loc.section for loc in cluster}
        if len(distinct_sections) < 2:
            # I-deepfix-001 tail-B1 (#1344, finding #10): the >=2-distinct-section gate excludes an
            # INTRA-section duplicate — the exact drb_72 case where the identical Acemoglu-Restrepo
            # figure appears twice in ONE section (one twin carrying a leaked contract-field label
            # prefix). Consolidate EXACT duplicates (identical text after prefix-strip + normalize)
            # even within one section, so the twins collapse to one representative + cross-references.
            # SCOPED to exact dups only (a mere overlap-signature match within a section is NOT
            # consolidated — that would over-collapse distinct-but-related sentences). Kill-switch OFF
            # => byte-identical to the pre-fix >=2-section gate.
            if not _exact_relax:
                continue
            by_norm: dict[str, list[SentenceLocation]] = {}
            for loc in cluster:
                by_norm.setdefault(_exact_dup_norm(loc.sentence), []).append(loc)
            for _norm, members in by_norm.items():
                if _norm and len(members) >= 2:
                    groups.append(RedundancyGroup(
                        signature=members[0].signature,
                        primary=members[0],
                        redundants=members[1:],
                    ))
            continue
        # Within the cluster, primary = first location in section_order;
        # redundants = all other locations (even same section as primary,
        # if they appear after — but typically these will be from
        # different sections).
        primary = cluster[0]
        redundants = cluster[1:]
        groups.append(RedundancyGroup(
            signature=primary.signature,
            primary=primary,
            redundants=redundants,
        ))

    # I-beatboth-011 §3.3 (#1289): PROSE-repetition pass — clusters the EMPTY-numeric-signature
    # sentences (skipped above at the `sig.is_empty(): continue`) by content-word shingle Jaccard.
    # GATED behind PG_FACT_DEDUP_PROSE (default OFF => this block is a no-op and `groups` is exactly
    # the numeric-path result, byte-identical to today). Prose groups append to the SAME `groups` list
    # so they route through the UNCHANGED keep-all cross-ref rewrite downstream (§-1.3 consolidate).
    if _prose_dedup_enabled():
        groups.extend(_build_prose_groups(
            sections, section_order, _read_prose_jaccard(),
        ))

    # I-wire-001 W1 (#1306): CONSOLIDATION-NLI winner — clusters the SAME empty-numeric
    # sentences by BIDIRECTIONAL NLI (same-claim paraphrases the literal/Jaccard floor
    # leaves separate). GATED behind PG_CONSOLIDATION_NLI (default OFF => no-op, byte-
    # identical). Appends to the SAME `groups` list so it routes through the UNCHANGED
    # keep-all cross-ref rewrite downstream (§-1.3 consolidate; faithfulness FROZEN).
    # NOTE: the primary behavioral seam for this winner is `finding_dedup.dedup_by_finding`
    # (the source-basket corroboration path the §-1.4 canary asserts on); this block is the
    # plan-listed companion seam in the SENTENCE-redundancy path.
    if _consolidation_nli_enabled_factdedup():
        groups.extend(_build_nli_prose_groups(sections, section_order))

    return groups


def count_redundancy(groups: list[RedundancyGroup]) -> int:
    """Total redundant sentences across all groups."""
    return sum(len(g.redundants) for g in groups)


# ─────────────────────────────────────────────────────────────────────────
# Rewrite — LLM call
# ─────────────────────────────────────────────────────────────────────────


REWRITE_SYSTEM_PROMPT = """You are rewriting redundant sentences from a multi-section research report so each redundant sentence becomes a brief CROSS-REFERENCE back to the section where the fact was first established (the PRIMARY section).

INPUT: A list of (REDUNDANT sentence, PRIMARY section name) pairs. The redundant sentence currently restates a fact that already appears in the PRIMARY section.

OUTPUT: A JSON object {"rewrites": [...]} with one rewrite per input. Each rewrite is the new sentence to replace the redundant one.

RULES:
1. Keep at least ONE evidence-ID citation marker `[ev_XXX]` from the original sentence in the rewrite.
2. Rewrites should be ONE sentence, 6-20 words.
3. Use the natural cross-reference idiom: "as noted under {PRIMARY_SECTION} [ev_X]", "see the {PRIMARY_SECTION} section [ev_X]", "the same finding is detailed in {PRIMARY_SECTION} [ev_X]", etc.
4. PRESERVE the topical anchor in the rewrite — what the fact is ABOUT — even though the decimals/amounts move to the PRIMARY section. Example: a redundant sentence about regressivity-by-income gets rewritten as "Regressivity by income is detailed under {PRIMARY_SECTION} [ev_X]" — readers still see what the cross-ref points to.
5. Do NOT invent new claims. Do NOT cite evidence-IDs that weren't in the original sentence.
6. If you cannot construct a valid cross-reference (e.g., the sentence has no [ev_XXX] markers, or the topical anchor is unclear), return null for that rewrite.

OUTPUT FORMAT (strict JSON):
{"rewrites": ["new sentence 1", "new sentence 2", null, "new sentence 4"]}
"""


def _build_rewrite_prompt(
    redundancy_groups: list[RedundancyGroup],
) -> tuple[str, list[tuple[RedundancyGroup, SentenceLocation]]]:
    """Build the user prompt + a flat list of (group, redundant_loc) for
    aligning the rewrite outputs back to source.

    Returns:
        (prompt_text, flat_list_of_input_locations_in_output_order)
    """
    lines = ["INPUTS (redundant sentence, primary section name):", ""]
    flat: list[tuple[RedundancyGroup, SentenceLocation]] = []
    counter = 0
    for group in redundancy_groups:
        for redundant in group.redundants:
            counter += 1
            lines.append(f"{counter}. REDUNDANT: {redundant.sentence}")
            lines.append(f"   PRIMARY_SECTION: {group.primary.section}")
            lines.append("")
            flat.append((group, redundant))
    lines.append(
        f"Return JSON {{\"rewrites\": [...]}} with exactly "
        f"{counter} entries in the same order as INPUTS."
    )
    return "\n".join(lines), flat


# ─────────────────────────────────────────────────────────────────────────
# I-deepfix-001 V6 (#1344): provenance-token carry-through for the rewrite.
# ─────────────────────────────────────────────────────────────────────────
# ROOT (grounded in drb_72_ai_labor/reasoning_trace.jsonl _fact_dedup call): the
# anti-restatement rewrite LLM DELIBERATELY converts the span-bearing canonical
# provenance token `[#ev:ev_109:839-961]` into a BARE `[ev_109]` marker — its own
# reasoning: "the original uses [#ev:ev_109:839-961]. The rule says keep at least one
# [ev_XXX] citation marker. Let me use ... [ev_X]." The re-verify strict_verify then
# parses provenance tokens from the rewrite, finds NO valid `[#ev:id:start-end]` token,
# and DROPS every rewrite with `no_provenance_token` (manifest fact_dedup:
# n_rewrites_strict_verify_pass=0 / n_rewrites_strict_verify_drop=3).
#
# FIX: carry the ORIGINAL redundant sentence's REAL span-bearing tokens through the
# rewrite so the UNCHANGED strict_verify can re-check it (shell / numeric / content /
# entailment) instead of auto-failing on a stripped token. Faithfulness-NEUTRAL
# (§-1.3): we only restore the sentence's OWN real grounding that the LLM stripped —
# never fabricate a token, never relax a gate. A genuinely ungroundable rewrite (junk
# shell span, no content overlap) STILL drops in strict_verify. LAW VI kill-switch:
# PG_FACT_DEDUP_CARRY_PROVENANCE=0 restores the byte-identical pre-fix behaviour.
_PROVENANCE_TOKEN_RE_FACTDEDUP = re.compile(
    r"\[#ev:(?P<ev_id>[A-Za-z0-9_]+):(?P<start>\d+)-(?P<end>\d+)\]"
)


def _carry_provenance_enabled() -> bool:
    """PG_FACT_DEDUP_CARRY_PROVENANCE gate (default ON)."""
    return resolve("PG_FACT_DEDUP_CARRY_PROVENANCE").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _restore_provenance_tokens(rewrite_text: str, original_sentence: str) -> str:
    """Carry the ORIGINAL sentence's span-bearing `[#ev:id:start-end]` tokens onto the
    LLM rewrite so strict_verify can re-verify it.

    For each canonical token id present in ``original_sentence``: if the rewrite already
    carries that exact canonical token, leave it; else, if the rewrite carries a BARE /
    span-less marker for the SAME id (``[ev_id]`` / ``[#ev:id]`` / ``[ev_id:s-e]``),
    replace it with the canonical token(s); else APPEND the canonical token(s)
    (KEEP-ALL, §-1.3 — a corroborating source is never dropped). Ids never in the
    original are left untouched (strict_verify still polices them). Deterministic,
    stdlib-only; returns ``rewrite_text`` unchanged when the original carries no
    canonical token."""
    original_tokens = list(_PROVENANCE_TOKEN_RE_FACTDEDUP.finditer(original_sentence or ""))
    if not original_tokens:
        return rewrite_text
    # ev_id -> ordered, de-duplicated list of its canonical span-bearing tokens.
    canonical_by_id: dict[str, list[str]] = {}
    for m in original_tokens:
        toks = canonical_by_id.setdefault(m.group("ev_id"), [])
        if m.group(0) not in toks:
            toks.append(m.group(0))

    text = rewrite_text
    for ev_id, toks in canonical_by_id.items():
        canonical = "".join(toks)  # all spans for this id (KEEP-ALL)
        if canonical in text:
            continue  # rewrite already carries the exact span-bearing grounding
        # A bare / span-less marker for THIS specific id (matched literally, never a
        # different id or a numeric `[12]` marker).
        bare_re = re.compile(r"\[(?:#ev:)?" + re.escape(ev_id) + r"(?::\d+-\d+)?\]")
        if bare_re.search(text):
            _state = {"done": False}

            def _sub(_m: "re.Match[str]") -> str:
                if _state["done"]:
                    return ""  # collapse duplicate bare markers for the same id
                _state["done"] = True
                return canonical

            text = bare_re.sub(_sub, text)
        else:
            # No marker for this id at all -> append the canonical token(s) (KEEP-ALL),
            # keeping any trailing sentence period after the citation.
            stripped = text.rstrip()
            if stripped.endswith("."):
                text = stripped[:-1].rstrip() + " " + canonical + "."
            else:
                text = stripped + " " + canonical
    return text


async def rewrite_redundant_sentences(
    redundancy_groups: list[RedundancyGroup],
    llm_callable: Callable[[str, str], Any],
) -> dict[tuple[str, int], Optional[str]]:
    """Issue a single LLM call to rewrite all redundant sentences as
    cross-references.

    Args:
        redundancy_groups: from build_groups().
        llm_callable: async callable(system, prompt) -> response object
            with .content attribute. Decoupled from openrouter_client
            to keep this module test-friendly.

    Returns:
        dict mapping (section, index) -> merged multi-citation sentence string.
        A redundant whose rewrite FAILED or came back null/empty is OMITTED from
        the dict (no key) so apply_rewrites keeps its ORIGINAL cited sentence —
        consolidate-keep-all (§-1.3): a failed merge never deletes a corroborating
        source. (The None value is still honored as an explicit drop by
        apply_rewrites, but the failure/null fallbacks no longer emit it.)
    """
    import json

    if not redundancy_groups:
        return {}

    prompt, flat = _build_rewrite_prompt(redundancy_groups)
    try:
        response = await llm_callable(REWRITE_SYSTEM_PROMPT, prompt)
        content = getattr(response, "content", None) or response
        # Parse JSON; tolerate code fences
        text = str(content).strip()
        if text.startswith("```"):
            # strip ```json … ``` or ``` … ```
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )
        parsed = json.loads(text)
        rewrites = parsed.get("rewrites", [])
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e:
        logger.warning(
            "[fact_dedup] rewrite call failed (%s); falling back to "
            "KEEP-redundants (consolidate-keep-all, §-1.3)", e,
        )
        # Safe fallback (§-1.3 CONSOLIDATE-DON'T-DROP): the anti-restatement rewrite is an
        # OPTIMIZATION (merge corroborating sentences into one multi-citation sentence). When it
        # fails we must NOT delete the corroborating cited sentences — emit NO drop keys so
        # apply_rewrites keeps every original sentence verbatim (repetition = corroboration).
        return {}

    if not isinstance(rewrites, list) or len(rewrites) != len(flat):
        logger.warning(
            "[fact_dedup] rewrite response shape mismatch "
            "(expected %d items, got %r); falling back to KEEP (consolidate-keep-all)",
            len(flat), type(rewrites).__name__,
        )
        return {}

    out: dict[tuple[str, int], Optional[str]] = {}
    for (_group, loc), rewrite in zip(flat, rewrites):
        if isinstance(rewrite, str) and rewrite.strip():
            rewrite_text = rewrite.strip()
            # I-deepfix-001 V6 (#1344): carry the ORIGINAL sentence's span-bearing
            # `[#ev:id:start-end]` provenance token(s) through the rewrite BEFORE the
            # KEEP-ALL check + return, so the re-verify strict_verify can re-check the
            # rewrite instead of auto-dropping it on the LLM-stripped bare `[ev_id]`
            # marker (`no_provenance_token`). Faithfulness-NEUTRAL: restores the
            # sentence's OWN real grounding; never fabricates, never relaxes a gate.
            if _carry_provenance_enabled():
                rewrite_text = _restore_provenance_tokens(rewrite_text, loc.sentence)
            # KEEP-ALL ENFORCEMENT (§-1.3; Codex #1289 iter-1 NOVEL-P0): a *successful* rewrite must NOT
            # silently DROP a corroborating source. Keep-all is a GROUP-GLOBAL invariant: the redundant
            # is cross-reffed to the PRIMARY (which is kept verbatim and carries ALL its own citations),
            # so the redundant may safely shed a token it SHARES with the primary — but every source
            # UNIQUE to this redundant (a citation token NOT in the primary) MUST survive the rewrite, or
            # it vanishes from the report entirely. Require those unique-vs-primary tokens to be present;
            # if any is missing, DISCARD the rewrite and KEEP the original cited sentence (emit no key —
            # the absent-key branch in apply_rewrites preserves it). A false reject only forgoes an
            # optimization; it can never drop a source. (The numeric path shares this guard, harmlessly.)
            original_cites = set(_CITATION_TOKEN_RE.findall(loc.sentence or ""))
            primary_cites = set(_CITATION_TOKEN_RE.findall(getattr(_group.primary, "sentence", "") or ""))
            must_survive = original_cites - primary_cites  # sources unique to this redundant
            rewrite_cites = set(_CITATION_TOKEN_RE.findall(rewrite_text))
            if must_survive and not must_survive <= rewrite_cites:
                logger.warning(
                    "[fact_dedup] rewrite at (%s,%d) dropped redundant-unique citation token(s) %s "
                    "(not carried by the primary); KEEPing the original cited sentence "
                    "(consolidate-keep-all, §-1.3)",
                    loc.section, loc.index, sorted(must_survive - rewrite_cites),
                )
                continue
            out[(loc.section, loc.index)] = rewrite_text
        # else: a null/empty rewrite for THIS item means the merge produced nothing — KEEP the
        # original cited sentence (consolidate-keep-all, §-1.3) by emitting NO key for it, so
        # apply_rewrites' absent-key branch preserves the corroborating sentence rather than
        # dropping it. Never delete a corroborating source on a failed rewrite.
    return out


def apply_rewrites(
    sections: dict[str, list[str]],
    rewrites: dict[tuple[str, int], Optional[str]],
) -> dict[str, list[str]]:
    """Apply rewrites in-place-equivalent (returns new dict).

    None rewrites = drop the sentence from its section.
    String rewrites = replace the sentence at that (section, index).
    """
    new_sections: dict[str, list[str]] = {}
    for section_title, sentences in sections.items():
        new_sentences: list[str] = []
        for idx, sentence in enumerate(sentences):
            key = (section_title, idx)
            if key in rewrites:
                replacement = rewrites[key]
                if replacement is None:
                    # Drop redundant entirely
                    continue
                new_sentences.append(replacement)
            else:
                new_sentences.append(sentence)
        new_sections[section_title] = new_sentences
    return new_sections


# ─────────────────────────────────────────────────────────────────────────
# Top-level entry point
# ─────────────────────────────────────────────────────────────────────────


async def dedup_pass(
    sections: dict[str, list[str]],
    llm_callable: Callable[[str, str], Any],
    section_order: Optional[list[str]] = None,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """End-to-end dedup pass.

    Args:
        sections: dict mapping section_title -> list of sentence strings.
            Typically the verified sentences from each section after
            multi_section generation.
        llm_callable: async callable(system, prompt) -> response.
        section_order: explicit PRIMARY ordering; defaults to insertion.

    Returns:
        (new_sections, telemetry) where telemetry includes:
            - n_groups: number of duplicate-fact groups detected
            - n_redundants: total redundant sentences flagged
            - n_rewrites_applied: successful rewrites
            - n_drops: sentences dropped because rewrite returned None
    """
    groups = build_groups(sections, section_order=section_order)
    n_redundants = count_redundancy(groups)
    telemetry: dict[str, Any] = {
        "n_groups": len(groups),
        "n_redundants": n_redundants,
        "n_rewrites_applied": 0,
        "n_drops": 0,
    }
    if not groups:
        return sections, telemetry

    logger.info(
        "[fact_dedup] %d duplicate-fact groups detected, "
        "%d redundant sentences to rewrite",
        len(groups), n_redundants,
    )
    rewrites = await rewrite_redundant_sentences(groups, llm_callable)
    for _k, v in rewrites.items():
        if v is None:
            telemetry["n_drops"] += 1
        else:
            telemetry["n_rewrites_applied"] += 1

    new_sections = apply_rewrites(sections, rewrites)
    logger.info(
        "[fact_dedup] applied=%d, dropped=%d",
        telemetry["n_rewrites_applied"], telemetry["n_drops"],
    )
    return new_sections, telemetry
