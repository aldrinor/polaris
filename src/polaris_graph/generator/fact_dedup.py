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
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

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
    for cluster in clusters:
        # Filter: at least 2 distinct sections must share this cluster
        distinct_sections = {loc.section for loc in cluster}
        if len(distinct_sections) < 2:
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
        dict mapping (section, index) -> new sentence string OR None if
        rewrite failed/null. Caller decides how to handle None
        (typically: drop the sentence entirely, keeping only PRIMARY).
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
            "DROP-redundants behavior", e,
        )
        # Safe fallback: drop all redundants (return None for each)
        return {(loc.section, loc.index): None for _g, loc in flat}

    if not isinstance(rewrites, list) or len(rewrites) != len(flat):
        logger.warning(
            "[fact_dedup] rewrite response shape mismatch "
            "(expected %d items, got %r); falling back to DROP",
            len(flat), type(rewrites).__name__,
        )
        return {(loc.section, loc.index): None for _g, loc in flat}

    out: dict[tuple[str, int], Optional[str]] = {}
    for (_group, loc), rewrite in zip(flat, rewrites):
        if isinstance(rewrite, str) and rewrite.strip():
            out[(loc.section, loc.index)] = rewrite.strip()
        else:
            # null/empty rewrite → drop
            out[(loc.section, loc.index)] = None
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
