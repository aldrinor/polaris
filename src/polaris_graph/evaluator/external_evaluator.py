"""
External non-same-family evaluator — HONEST-REBUILD Phase 5.

Runs quality checks on a completed report using a DIFFERENT model
family than the one that generated the report. Combined with rule-
based PRISMA-trAIce compliance checks that run without any LLM at all.

ADDRESSES the self-grading problem documented across FIX-QM7 /
FIX-043A / REMEDIATE-LOOP and quantified in PG_LB_SA_02_CONTENT_AUDIT:
any evaluator in the same training lineage as the generator shares
the generator's blind spots (Play Favorites arXiv:2508.06709,
DeepHalluBench arXiv:2601.22984).

ARCHITECTURE
------------
Two complementary channels:

1. RULE-BASED CHECKS (deterministic, no LLM)
   - Citation-span exact match: every [#ev:...] token must verify
     against the stored evidence pool (reuses Phase 4 verifier).
   - Tier-distribution arithmetic: actual corpus tier fractions
     match the numbers reported in the methods section.
   - Contradiction disclosure: every ContradictionRecord from
     Phase 3 must have at least one mention in the report text.
   - PRISMA-trAIce compliance checklist (26 items, see PRISMA_TRAICE).
   - Word-count + citation-count floors.

2. LLM-JUDGE (non-same-family)
   - Uses PG_EVALUATOR_MODEL (default google/gemma-4-31b-it) against
     PG_GENERATOR_MODEL (default deepseek/deepseek-v4-pro).
   - check_family_segregation() FAILS FAST if both are in the
     same family.
   - Only judges NUANCE items the rule-based checks can't cover:
     tone consistency, hedging appropriateness, paragraph flow.
   - The LLM does NOT produce a single faithfulness % — its output
     is a structured profile (per-axis verdict) so we can avoid
     the collapse to a single cooked number.

CRITICAL: Phase 5 emits `evaluator_output` (structured dict), NOT
`faithfulness_score` (single float). Phase 1a removed the single-float
from the UI to prevent the next wave of cooking.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.external_evaluator")


# ─────────────────────────────────────────────────────────────────────────────
# PRISMA-trAIce compliance checklist (abbreviated for machine checks)
# ─────────────────────────────────────────────────────────────────────────────
#
# PRISMA-trAIce is a documented extension of PRISMA 2020 for AI-
# generated systematic reviews. Reference: Cochrane AI Methods Group
# guidance, 2025. The full 26-item list requires manual attestation;
# below are the subset of items that can be verified machine-side.

# ─────────────────────────────────────────────────────────────────────────────
# M-30 (2026-04-20): abbreviation-aware sentence boundary detection for PT11.
#
# V19 aborted on PT11 because the prior regex treated `vs.` as a sentence
# terminator. A well-cited sentence like
#   "diarrhea (10.7% vs. 4.8%), nausea (8.1% vs. 2.7%),
#    and vomiting (5.7% vs. 1.2%).[7]"
# was scored as 4 uncited decimals because the lookahead from 4.8, 8.1, 2.7,
# 5.7 stopped at the nearest "vs. " and never reached "[7]" at the real
# sentence end.
#
# The abbreviation list below is generalizable English orthography — NOT a
# clinical-domain hard-code. Every domain that uses standard English prose
# (policy, materials, energy, due-diligence) benefits from the same list.
# ─────────────────────────────────────────────────────────────────────────────

# M-30 pass-3 (addressing Codex pass-2 blocker): `etc.`, `U.S.`,
# `et al.` and other multi-segment acronyms also have sentence-final
# vs mid-sentence ambiguity. Previous pass-2 design treated them as
# ALWAYS non-boundary, which let `4.2%, 5.3%, 6.4%, 7.5% in the U.S. A
# separate claim.[1]` falsely pass PT11. Pass-3 restricts
# ALWAYS_NONBOUNDARY to only tokens that are virtually never
# sentence-final in practice; everything else routes through
# context-dependent next-char disambiguation.
#
# ALWAYS_NONBOUNDARY (virtually never ends a sentence):
#   - comparatives `vs.`, `v.`
#   - Latin connectives `cf.`, `viz.`
#   - titles `Dr.`, `Mr.`, `Mrs.`, `Ms.`, `Prof.`, `Sr.`, `Jr.`, `Rev.`
#     (practically always followed by a proper-noun name; the very
#     rare "She is a Dr." sentence-final usage is an accepted
#     false-negative since decimals don't usually precede titles).
#
# CONTEXT_DEPENDENT (resolved by next non-whitespace char — digit/
# paren/lowercase → non-boundary; uppercase/EOL → boundary):
#   - end-of-list `etc`
#   - document references (Fig, Ref, No, pp, Vol, Ch, Sec, App, ...)
#   - organisations (Inc, Ltd, Co, Corp, Gov, Dept)
#   - months (Jan-Dec)
#   - multi-segment acronyms (e.g, i.e, U.S, U.K, E.U) — routed via
#     the multi-segment detector in `_is_abbreviation_period`.
#   - `et al` — routed via the special-case detector.
_PT11_ALWAYS_NONBOUNDARY = frozenset([
    # Comparatives — never end a sentence
    "vs", "v",
    # Latin connectives that always introduce content after them
    "cf", "viz",
    # Titles — followed by proper-noun, treated as non-boundary.
    # Edge case: "She is a Dr." sentence-final; accepted false-negative
    # (decimals rarely precede sentence-final titles in research prose).
    "Dr", "Mr", "Mrs", "Ms", "Prof", "Sr", "Jr", "Rev",
])

_PT11_CONTEXT_DEPENDENT = frozenset([
    # End-of-list marker — can be sentence-final ("items, etc. We then...")
    # or mid-sentence ("items, etc. and other things")
    "etc",
    # Document references — usually followed by a number
    "Fig", "Figs", "Ref", "Refs", "Eq", "Eqs",
    "No", "Nos", "pp", "Vol", "Ch", "Sec", "App",
    # Organisations — can be sentence-final ("Eli Lilly Inc. We...") or
    # mid-sentence ("Eli Lilly Inc. reported")
    "Inc", "Ltd", "Co", "Corp", "Gov", "Dept",
    # Months — can be sentence-final ("in Jan. We...") or followed by
    # a day number ("Jan. 15, 2020")
    "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug",
    "Sep", "Sept", "Oct", "Nov", "Dec",
])


# M-30 pass-5 (addressing Codex pass-4 blocker): ALL-CAPS after a
# context-dependent abbreviation can be either an acronym chain
# ("U.S. FDA database", mid-sentence) or a new-sentence subject
# ("U.S. FDA approved the summary", boundary). Disambiguate by
# looking at the WORD AFTER the acronym:
#   - If next-next word is a verb form (modal/auxiliary or -ed/-ing
#     past-tense/gerund) → new sentence (boundary).
#   - Otherwise → acronym chain continuation (non-boundary).
_PT11_VERB_INDICATORS = frozenset([
    # BE forms
    "is", "was", "are", "were", "be", "been", "being",
    # HAVE forms
    "has", "had", "have", "having",
    # DO forms
    "does", "did", "do", "done", "doing",
    # Modal auxiliaries
    "can", "may", "might", "will", "would",
    "could", "should", "must", "shall", "ought",
    # Common present-tense reporting verbs (-s suffix) that frequently
    # follow an acronym subject in research prose
    "reports", "issues", "approves", "states", "notes",
    "finds", "observes", "concludes", "recommends", "announces",
    "demonstrates", "publishes", "releases", "confirms",
    "establishes", "shows", "suggests",
])


# Title-case words that STRONGLY signal a sentence boundary when they
# follow a context-dependent abbreviation (Codex pass-3 addition).
# This list lets the boundary rule correctly split cases like
# "U.S. The trial..." (boundary) while keeping "U.S. FDA database..."
# (mid-sentence continuation, an all-caps acronym follows an acronym).
# Generalizable English discourse markers — no domain-specific terms.
_PT11_SENTENCE_STARTER_WORDS = frozenset([
    # Articles and demonstratives
    "The", "This", "That", "These", "Those", "An",
    # Pronouns that commonly open sentences
    "He", "She", "It", "They", "We", "You",
    # Discourse markers / transitional adverbs
    "However", "Moreover", "Furthermore", "Thus", "Therefore",
    "Nonetheless", "Nevertheless", "Conversely", "Meanwhile",
    "Subsequently", "Previously", "Historically", "Recently",
    "Currently", "Ultimately", "Overall", "Finally",
    "Similarly", "Alternatively", "Separately", "Additionally",
    "Notably", "Importantly", "Specifically", "Generally",
    "Indeed", "Also",
    # Conjunctions at sentence start
    "And", "But", "Or",
    # Prepositional / conditional openers
    "In", "On", "At", "When", "While", "Where",
    "If", "Though", "Although", "After", "Before", "During",
    # Sequential openers
    "First", "Second", "Third", "Next",
])


def _is_abbreviation_period(text: str, period_pos: int) -> bool:
    """True if text[period_pos] == '.' and the period is an abbreviation
    terminator (NOT a sentence boundary).

    Disambiguation:
      1. ALWAYS_NONBOUNDARY tokens (vs, cf, viz, titles) are
         non-boundary unconditionally.
      2. CONTEXT_DEPENDENT tokens (etc, months, orgs, doc-refs),
         multi-segment acronyms (e.g, i.e, U.S, U.K, E.U), and the
         `et al.` special-case all resolve by the next
         non-whitespace character:
           - digit / `(` / `-` / `+` → non-boundary
           - lowercase letter        → non-boundary
           - uppercase letter        → boundary (new sentence starts)
           - end-of-string           → boundary
    """
    if period_pos < 0 or period_pos >= len(text) or text[period_pos] != ".":
        return False
    # Walk back over alphabetic characters + embedded periods to find
    # the token that ends at period_pos.
    start = period_pos - 1
    while start >= 0 and (text[start].isalpha() or text[start] == "."):
        start -= 1
    token = text[start + 1:period_pos]
    if not token:
        return False

    # Bucket 1: always non-boundary (short-circuit).
    if token in _PT11_ALWAYS_NONBOUNDARY:
        return True

    # Determine whether this is a context-dependent abbreviation:
    # explicit list, multi-segment acronym, or "et al.".
    is_context_dependent = token in _PT11_CONTEXT_DEPENDENT

    if not is_context_dependent and "." in token:
        parts = [p for p in token.split(".") if p]
        if parts and all(len(p) <= 2 and p.isalpha() for p in parts):
            is_context_dependent = True  # e.g, i.e, U.S, U.K, E.U

    if not is_context_dependent and token == "al":
        pre_start = max(0, start + 1 - 3)
        if text[pre_start:start + 1].endswith("et "):
            is_context_dependent = True  # "et al."

    if not is_context_dependent:
        return False

    # Resolve by the next non-whitespace character AND the shape of
    # the next word.
    after = period_pos + 1
    while after < len(text) and text[after] in " \t":
        after += 1
    if after >= len(text):
        return False  # end-of-input → real boundary
    nxt = text[after]
    if nxt.isdigit() or nxt in "(-+":
        return True  # "Fig. 3", "Jan. 15", "U.S. 2023 report"
    if nxt.islower():
        return True  # "Inc. reported", "etc. and more", "U.S. market"

    # Uppercase next char — inspect the whole next word.
    word_end = after
    while word_end < len(text) and (text[word_end].isalpha() or text[word_end] in "-'"):
        word_end += 1
    next_word = text[after:word_end]
    alpha_only = "".join(c for c in next_word if c.isalpha())

    # 1-char uppercase word: article "A" or pronoun "I" at sentence start.
    if len(alpha_only) == 1:
        return False

    # Capture the word immediately after `next_word` (same-structure
    # lookahead — used to disambiguate both ALL-CAPS acronym chains and
    # Title-case proper nouns).
    nnext_start = word_end
    while nnext_start < len(text) and text[nnext_start] in " \t":
        nnext_start += 1
    nnext_end = nnext_start
    while nnext_end < len(text) and (text[nnext_end].isalpha() or text[nnext_end] in "-'"):
        nnext_end += 1
    nnext_word = text[nnext_start:nnext_end]
    nnext_lc = nnext_word.lower()

    # ALL-CAPS multi-char word — usually an acronym. Distinguish by
    # looking at the next-next word:
    #   "U.S. FDA database"  → database is not a verb  → non-boundary
    #   "U.S. FDA approved"  → approved ends in -ed    → boundary
    #   "U.S. CDC reported"  → reported ends in -ed    → boundary
    #   "U.S. EPA reports"   → reports in verb list    → boundary
    #   "U.S. FDA is"        → is is a modal           → boundary
    if alpha_only.isupper():
        if _looks_like_verb_form(nnext_lc):
            return False  # ACRONYM + verb → new sentence
        return True  # ACRONYM + non-verb → acronym chain continuation

    # Explicit sentence-starter discourse markers and articles →
    # sentence boundary. Catches "U.S. The trial...",
    # "Inc. Separately reports...", "et al. However it was...".
    if next_word in _PT11_SENTENCE_STARTER_WORDS:
        return False

    # Title-case word (not in starter list) — likely a proper noun.
    # Further disambiguate by looking at the next-next word. If that
    # word starts with a lowercase letter, the Title-case word is
    # probably part of an ongoing noun phrase ("U.K. Biobank data",
    # "U.S. Pfizer reported"). If the next-next word is uppercase or
    # absent, default to boundary (safer).
    if nnext_start < len(text):
        nn = text[nnext_start]
        if nn.islower():
            return True  # proper-noun continuation — mid-sentence
    # No lowercase continuation → treat as sentence boundary.
    return False


def _looks_like_verb_form(word_lowercase: str) -> bool:
    """Heuristic verb-form detector on a lowercased word. True if
    the word is a common modal/auxiliary, a -ed past-tense form, or
    an -ing gerund/participle. Accepts occasional noun false-positives
    (e.g. "offering", "meeting") since the consequence is a PT11
    false-FAIL — recoverable by re-running — while the alternative
    is a false-PASS that lets fabrication through the audit gate."""
    if not word_lowercase:
        return False
    if word_lowercase in _PT11_VERB_INDICATORS:
        return True
    if len(word_lowercase) >= 4 and word_lowercase.endswith("ed"):
        return True
    if len(word_lowercase) >= 5 and word_lowercase.endswith("ing"):
        return True
    return False


# Sentence-terminator regex. Matches `.`, `!`, `?` when followed by
# whitespace, end-of-string, or an inline citation `[N]` / `[#ev:...]`
# (reports commonly write `sentence.[7] Next sentence...`).
_SENTENCE_END_REGEX = re.compile(r"[.!?](?=\s|$|\[)")


def _skip_trailing_citation_brackets(text: str, pos: int) -> int:
    """Advance `pos` past any `[...]` citation brackets that immediately
    follow. So `sentence.[7][#ev:x]` with `pos` at the `.` advances past
    both brackets. Returns the position after the last closing `]`.

    This is needed because PT11 treats `.[7]` as one sentence-end unit:
    the `[7]` cites the PRIOR sentence, so it should be part of that
    sentence's "end" — not the start of the next sentence.
    """
    while pos < len(text) and text[pos] == "[":
        close = text.find("]", pos)
        if close < 0:
            break
        pos = close + 1
    return pos


def _next_real_sentence_end(text: str) -> int | None:
    """Return the position just past the first real sentence terminator
    in `text`, INCLUDING any trailing `[N]` / `[#ev:...]` citations. So
    for `sentence.[7] Next` the return value points at the space after
    `]`, letting lookahead snippets include the citation.

    Returns None if no real terminator is found. Skips
    abbreviation-period false positives."""
    for m in _SENTENCE_END_REGEX.finditer(text):
        period_pos = m.start()
        if text[period_pos] == "." and _is_abbreviation_period(text, period_pos):
            continue
        return _skip_trailing_citation_brackets(text, period_pos + 1)
    return None


def _prev_real_sentence_end(text: str) -> int:
    """Return the index of the last char of the last real sentence
    (the terminator char or, if the terminator is followed by citation
    brackets, the closing `]` of the last trailing bracket).

    So for `First sentence.[1] Current claim`, the return value points
    at the `]` of `[1]` — caller's `back_text[last_end+1:]` then starts
    cleanly in the new sentence and does NOT see `[1]`, which correctly
    belongs to the prior sentence.

    Returns -1 if no terminator is found. Skips abbreviation-period
    false positives."""
    last = -1
    for m in _SENTENCE_END_REGEX.finditer(text):
        period_pos = m.start()
        if text[period_pos] == "." and _is_abbreviation_period(text, period_pos):
            continue
        # Advance past trailing citation brackets so they end this sentence.
        end_pos = _skip_trailing_citation_brackets(text, period_pos + 1)
        # `end_pos` is the position AFTER the last `]` (or after the `.`
        # when no brackets follow). Return that position minus 1 so the
        # caller's `back_text[last + 1:]` starts on the next char.
        last = end_pos - 1
    return last


_PRISMA_TRAICE_MACHINE_ITEMS = [
    # (item_id, human_name, required_in_section)
    ("PT01", "Pre-registered protocol reference present", "methods"),
    ("PT02", "Generator model name disclosed", "methods"),
    ("PT03", "Evaluator model name disclosed (separate family)", "methods"),
    ("PT04", "Retrieval date/time disclosed", "methods"),
    ("PT05", "Inclusion / exclusion criteria listed", "methods"),
    ("PT06", "Tier taxonomy referenced (T1-T7)", "methods"),
    ("PT07", "Expected-vs-actual tier distribution reported", "methods"),
    ("PT08", "Contradiction detector invoked — disclosure if any found", "results"),
    ("PT09", "Sponsor / conflict-of-interest filter applied", "methods"),
    ("PT10", "Prompt-injection sanitization enabled", "methods"),
    ("PT11", "Every numeric claim has a [CITE] or [#ev:] token", "results"),
    ("PT12", "No citation markers attached to unverified sentences", "results"),
    ("PT13", "Superlative / comparative claims are hedged", "results"),
    # PT14-PT26: mode label, limitations, reproducibility, manual
    # attestations — checked by UI, not by this module.
]


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RuleCheckResult:
    item_id: str
    name: str
    passed: bool
    details: str = ""


@dataclass
class LLMJudgmentAxis:
    """Structured per-axis LLM judgment. NOT collapsed to a single %."""
    axis: str             # "tone" / "hedging" / "flow" / "citation_tightness"
    verdict: str          # "good" / "acceptable" / "needs_revision"
    notes: str = ""


@dataclass
class EvaluatorOutput:
    """Structured evaluator output — emitted to output JSON as
    `evaluator_output`. Phase 1a replaced `faithfulness_score` with this.
    """
    generator_model: str
    evaluator_model: str
    generator_family: str
    evaluator_family: str
    rule_checks: list[RuleCheckResult] = field(default_factory=list)
    llm_judgments: list[LLMJudgmentAxis] = field(default_factory=list)
    contradictions_disclosed: int = 0
    contradictions_missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def rule_check_pass_count(self) -> int:
        return sum(1 for r in self.rule_checks if r.passed)

    @property
    def rule_check_fail_count(self) -> int:
        return sum(1 for r in self.rule_checks if not r.passed)


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based check implementations
# ─────────────────────────────────────────────────────────────────────────────


def _check_methods_mentions(report_text: str, keywords: list[str]) -> bool:
    """Return True if ANY keyword appears in the methods section.

    We treat "Methods" / "Methodology" / "Materials and Methods"
    headings as the start of the methods section. If no heading is
    found, we scan the whole text.
    """
    lower = report_text.lower()
    # Find methods section
    methods_idx = -1
    for header in ("\nmethods", "\nmethodology", "\nmaterials and methods"):
        idx = lower.find(header)
        if idx != -1:
            methods_idx = idx
            break
    if methods_idx == -1:
        # Scan whole text as fallback
        search_space = lower
    else:
        # Take methods section to next top-level heading
        rest = lower[methods_idx:]
        # Next \n# or \n## heading after the methods header
        next_hdr = re.search(r"\n##?\s+\w", rest[50:])  # skip the methods heading itself
        if next_hdr:
            search_space = rest[: 50 + next_hdr.start()]
        else:
            search_space = rest
    return any(k.lower() in search_space for k in keywords)


def run_rule_checks(
    *,
    report_text: str,
    protocol: dict[str, Any],
    tier_distribution_report: Optional[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    evidence_pool: dict[str, dict[str, Any]],
    generator_model: str,
    evaluator_model: str,
) -> tuple[list[RuleCheckResult], int, list[str]]:
    """Run the 12 machine-verifiable PRISMA-trAIce items.

    Returns (results, num_contradictions_disclosed, missing_contradiction_ids).
    """
    results: list[RuleCheckResult] = []

    # PT01 — pre-registered protocol reference present
    pt01 = (
        "protocol.json" in report_text.lower()
        or "pre-register" in report_text.lower()
        or "pre register" in report_text.lower()
    )
    results.append(RuleCheckResult(
        "PT01", "Pre-registered protocol reference present", pt01,
        "Report must reference the protocol.json artifact."
        if not pt01 else "",
    ))

    # PT02 — generator model disclosed
    pt02 = generator_model and generator_model.lower() in report_text.lower()
    results.append(RuleCheckResult(
        "PT02", "Generator model disclosed", bool(pt02),
        f"Expected generator_model={generator_model!r} in report text."
        if not pt02 else "",
    ))

    # PT03 — evaluator model disclosed
    pt03 = evaluator_model and evaluator_model.lower() in report_text.lower()
    results.append(RuleCheckResult(
        "PT03", "Evaluator model disclosed (separate family)", bool(pt03),
        f"Expected evaluator_model={evaluator_model!r} in report text."
        if not pt03 else "",
    ))

    # PT04 — retrieval date
    pt04 = bool(
        re.search(r"retriev(al|ed)[^.]{0,60}(202[0-9]|\d{4}-\d{2}-\d{2})",
                  report_text, re.IGNORECASE)
    )
    results.append(RuleCheckResult(
        "PT04", "Retrieval date disclosed", pt04,
        "Expected phrase like 'retrieved on 2026-04-17' in report."
        if not pt04 else "",
    ))

    # PT05 — inclusion / exclusion criteria
    inc = _check_methods_mentions(report_text, ["inclusion", "included"])
    exc = _check_methods_mentions(report_text, ["exclusion", "excluded"])
    pt05 = inc and exc
    results.append(RuleCheckResult(
        "PT05", "Inclusion / exclusion criteria listed", pt05,
        "Report methods must list both inclusion AND exclusion criteria."
        if not pt05 else "",
    ))

    # PT06 — tier taxonomy
    pt06 = bool(re.search(r"\bT[1-7]\b", report_text))
    results.append(RuleCheckResult(
        "PT06", "Tier taxonomy (T1-T7) referenced", pt06,
        "Expected at least one T1..T7 reference in the report."
        if not pt06 else "",
    ))

    # PT07 — expected-vs-actual tier distribution
    pt07 = bool(
        tier_distribution_report
        and "tier_fractions" in tier_distribution_report
        and "expected" in report_text.lower()
        and "actual" in report_text.lower()
    )
    results.append(RuleCheckResult(
        "PT07", "Expected-vs-actual tier distribution reported", pt07,
        "Report must show both expected and actual tier percentages."
        if not pt07 else "",
    ))

    # PT08 — contradiction disclosure
    missing_contradictions: list[str] = []
    for c in contradictions:
        # Look for subject + predicate mention + disclosure keyword
        subj = (c.get("subject") or "").lower()
        pred = (c.get("predicate") or "").lower()
        if not subj or not pred:
            continue
        if subj in report_text.lower() and pred in report_text.lower():
            continue
        missing_contradictions.append(f"{subj}/{pred}")
    num_disclosed = max(0, len(contradictions) - len(missing_contradictions))
    pt08 = len(missing_contradictions) == 0
    results.append(RuleCheckResult(
        "PT08", "All detected contradictions disclosed in report", pt08,
        f"Missing disclosures for: {missing_contradictions}"
        if not pt08 else "",
    ))

    # PT09 — sponsor filter applied
    pt09 = _check_methods_mentions(
        report_text, ["sponsor", "conflict of interest", "coi", "funding"],
    )
    results.append(RuleCheckResult(
        "PT09", "Sponsor / COI filter applied", pt09,
        "Report methods must mention sponsor or COI handling."
        if not pt09 else "",
    ))

    # PT10 — prompt-injection sanitization enabled
    pt10 = (
        "injection" in report_text.lower()
        or "sanitiz" in report_text.lower()
    )
    results.append(RuleCheckResult(
        "PT10", "Prompt-injection sanitization enabled", pt10,
        "Report must mention prompt-injection defense in methods."
        if not pt10 else "",
    ))

    # PT11 — every numeric claim has a citation token.
    # Only check the PROSE portion of the report (everything before the
    # "## Methods" heading). The methods and bibliography sections
    # contain protocol numbers (tier bounds like "30-60%", retrieval
    # dates, model names with version numbers) that are specifications,
    # not empirical claims needing citations.
    methods_idx = report_text.lower().find("\n## methods")
    if methods_idx > 0:
        prose_only = report_text[:methods_idx]
    else:
        prose_only = report_text
    text_stripped = re.sub(r"\[#ev:[^\]]+\]", "", prose_only)
    # Only check DECIMAL numbers (the empirical claims) — integers like
    # study-ID "STEP 1" or "week 68" are study markers, not claims.
    #
    # Look-ahead is to the end of the current sentence (up to `.!?`),
    # not a fixed 80-char window — decimals early in a long sentence
    # should get credit for a citation attached at the sentence end.
    #
    # M-30 (2026-04-20): use abbreviation-aware sentence boundary
    # detection. `vs.`, `e.g.`, `etc.`, `Fig.`, etc. must NOT split a
    # sentence — otherwise "10.7% vs. 4.8%, 8.1% vs. 2.7% ... [7]"
    # is incorrectly scored as having uncited decimals.
    numeric_matches = list(re.finditer(
        r"(?<![A-Za-z0-9.])(-?\d+\.\d+)",
        text_stripped,
    ))
    uncited = 0
    # M-34 (2026-04-21): widen lookahead so the abbreviation-aware
    # sentence-end helper can actually find the terminator. Long
    # regulatory/clinical sentences (300-450 chars) are legitimate —
    # V23 had three sentences where the citation was at char 350-450
    # but the helper only saw the first 200 chars, returned None, and
    # fell back to 150. Slice now caps at 1000 chars; None-fallback
    # returns the full slice instead of narrowing to 150.
    for m in numeric_matches:
        after_text = text_stripped[m.end():m.end() + 1000]
        lookahead_end = _next_real_sentence_end(after_text)
        if lookahead_end is None:
            lookahead_end = len(after_text)
        snippet_after = after_text[:lookahead_end]
        if not re.search(r"\[\d+\]|\[#ev:", snippet_after):
            # Fallback: allow markers BEFORE the number. Walk back to
            # the previous real sentence boundary (abbreviation-aware).
            # Same widening applies to the back-lookup.
            back_text = text_stripped[max(0, m.start() - 1000):m.start()]
            prev_end = _prev_real_sentence_end(back_text)
            snippet_before = back_text[prev_end + 1:] if prev_end >= 0 else back_text
            if not re.search(r"\[\d+\]|\[#ev:", snippet_before):
                uncited += 1
    pt11 = uncited < max(3, len(numeric_matches) // 10)  # allow <=10% uncited
    results.append(RuleCheckResult(
        "PT11", "Numeric claims have citation markers", pt11,
        f"{uncited} numeric claims without adjacent citation marker "
        f"(out of {len(numeric_matches)} decimals in prose)."
        if not pt11 else "",
    ))

    # PT12 — no citations on unverified sentences
    # Heuristic: find sentences containing [n] markers, check that the
    # evidence pool has at least one entry referenced. We can't do full
    # provenance verification without the token data, but we can check
    # that markers [1]..[N] don't exceed the bibliography size.
    # M-5 (Codex pass 5): scan only the pre-bibliography portion.
    # Bibliography entries legitimately include bracketed years in
    # source titles (e.g., "Best Guide on RAG Pipeline [2025]") that
    # must not be misread as citation markers into the evidence pool.
    biblio_idx = report_text.lower().find("\n## bibliography")
    prose_for_markers = (
        report_text[:biblio_idx] if biblio_idx > 0 else report_text
    )
    max_marker = 0
    for m in re.finditer(r"\[(\d+)\]", prose_for_markers):
        try:
            n = int(m.group(1))
            if n > max_marker:
                max_marker = n
        except ValueError:
            continue
    pt12 = max_marker <= len(evidence_pool) if evidence_pool else True
    results.append(RuleCheckResult(
        "PT12", "Citation markers don't exceed bibliography size", pt12,
        f"max_marker={max_marker} but evidence_pool has {len(evidence_pool)}."
        if not pt12 else "",
    ))

    # PT13 — Gap-2: hedging on superlative / comparative claims.
    # Scans the prose portion of the report for unhedged superlatives
    # ("largest", "best", "better than X") that are NOT anchored to a
    # source verb ("reported", "described as", "one review found").
    # This is a SOFT check — passes if <=1 unhedged claim remains
    # (the evaluator treats this as a quality hint, not a blocker).
    # M-6 (Codex pass 5 follow-up): exempt (i) the first "# " title
    # line (it's inherited from the research question, not a generator
    # assertion) and (ii) superlative words that appear in the
    # research_question itself. Example: question "best practices for
    # RAG" — the title echoes "best" and the generator may echo it
    # back in prose; neither is a generator superlative claim.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
        _detect_unhedged_superlative,
        split_into_sentences,
    )
    methods_idx_pt13 = report_text.lower().find("\n## methods")
    prose_for_hedging = (
        report_text[:methods_idx_pt13] if methods_idx_pt13 > 0 else report_text
    )
    # Strip the first H1 title line from the scan window (belongs to
    # the question, not the generator's prose).
    lines_pt13 = prose_for_hedging.splitlines()
    if lines_pt13 and lines_pt13[0].lstrip().startswith("# "):
        prose_for_hedging = "\n".join(lines_pt13[1:])

    # Build a set of superlative-family words present in the research
    # question so we don't flag the generator for echoing them.
    question_text = (protocol.get("research_question") or "").lower()
    question_superlatives: set[str] = set()
    if question_text:
        for m in re.finditer(
            r"\b(largest|highest|greatest|best|leading|superior|top|"
            r"unparalleled|unmatched|unprecedented)\b",
            question_text,
        ):
            question_superlatives.add(m.group(0))

    # M-6 refinement (Codex pass 6 + 7): require the prose sentence to
    # share N content words with the research question before we exempt
    # a single-word superlative, where N is DYNAMIC:
    #
    # - `len(question_superlatives) >= 2` → N=2 (strict). A question
    #   stuffed with multiple superlative words is adversarial-shaped;
    #   the full lexical-echo test applies.
    # - `len(question_superlatives) <= 1` → N=1 (loose). A normal
    #   question with one superlative gets the benefit of paraphrase:
    #   e.g., "best RAG practices?" → prose "Hybrid retrieval is the
    #   best approach" only shares `{best}` (the superlative itself) but
    #   is a legitimate direct answer.
    #
    # This dynamic threshold scales defense with attack surface. Codex
    # pass 7 flagged 4 over-strict cases under a hard N=2; the dynamic
    # rule handles them while preserving the pass-6 adversarial test.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
        _content_words,
    )
    question_content_words = (
        _content_words(question_text) if question_text else set()
    )
    if len(question_superlatives) >= 2:
        echo_min_content_words = 2
    else:
        echo_min_content_words = 1

    unhedged_examples: list[str] = []
    for sent in split_into_sentences(prose_for_hedging):
        found = _detect_unhedged_superlative(sent)
        if not found:
            continue
        # Exempt if (a) the matched phrase is a single question-
        # inherited word AND (b) the prose sentence shares ≥2 content
        # words with the question (lexical echo — means the sentence
        # is quoting or paraphrasing the question topic, not asserting
        # an independent superlative claim).
        if found.lower().strip() in question_superlatives:
            sent_content = _content_words(sent)
            echo_overlap = sent_content & question_content_words
            if len(echo_overlap) >= echo_min_content_words:
                continue
        unhedged_examples.append(f"{found!r} in: {sent[:90]!r}")
    pt13 = len(unhedged_examples) <= 1
    results.append(RuleCheckResult(
        "PT13", "Superlative / comparative claims are hedged to sources", pt13,
        f"{len(unhedged_examples)} unhedged: {unhedged_examples[:3]}"
        if not pt13 else "",
    ))

    return results, num_disclosed, missing_contradictions


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


def run_external_evaluation(
    *,
    report_text: str,
    protocol: dict[str, Any],
    tier_distribution_report: Optional[dict[str, Any]] = None,
    contradictions: Optional[list[dict[str, Any]]] = None,
    evidence_pool: Optional[dict[str, dict[str, Any]]] = None,
    enable_llm_judge: bool = False,
) -> EvaluatorOutput:
    """Run Phase 5 evaluator and return structured output.

    Args:
        report_text: Final generated report text (with [n] citations).
        protocol: Dict form of protocol.json.
        tier_distribution_report: Dict from Phase 2g compute_tier_distribution.
        contradictions: List of ContradictionRecord dicts from Phase 3.
        evidence_pool: Evidence_id -> evidence dict.
        enable_llm_judge: If True and the environment is configured,
            call the LLM judge. Defaults to False so the rule-based
            checks can run in offline / test mode.

    Raises RuntimeError if generator and evaluator are in the same family.
    """
    from src.polaris_graph.llm.openrouter_client import (  # noqa: E402
        PG_EVALUATOR_MODEL,
        PG_GENERATOR_MODEL,
        check_family_segregation,
    )

    gen_family, eval_family = check_family_segregation()

    contradictions = contradictions or []
    evidence_pool = evidence_pool or {}

    # Rule-based checks
    rule_results, n_disclosed, missing = run_rule_checks(
        report_text=report_text,
        protocol=protocol,
        tier_distribution_report=tier_distribution_report,
        contradictions=contradictions,
        evidence_pool=evidence_pool,
        generator_model=PG_GENERATOR_MODEL,
        evaluator_model=PG_EVALUATOR_MODEL,
    )

    llm_judgments: list[LLMJudgmentAxis] = []
    notes: list[str] = []
    if enable_llm_judge:
        # Placeholder for the actual LLM call. In full deployment this
        # hits PG_EVALUATOR_MODEL via OpenRouter with a fixed prompt
        # that asks for per-axis verdicts. Kept as a stub here because
        # unit tests should not perform network I/O.
        notes.append(
            "LLM-judge mode requested but not executed in offline "
            "evaluation context."
        )

    return EvaluatorOutput(
        generator_model=PG_GENERATOR_MODEL,
        evaluator_model=PG_EVALUATOR_MODEL,
        generator_family=gen_family,
        evaluator_family=eval_family,
        rule_checks=rule_results,
        llm_judgments=llm_judgments,
        contradictions_disclosed=n_disclosed,
        contradictions_missing=missing,
        notes=notes,
    )
