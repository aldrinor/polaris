"""Strict verifier per CLAUDE.md §9.1 invariant 3.

Per-sentence check enforcing:
  (a) at least one provenance token present
  (b) every token references an evidence_id in the pool
  (c) span bounds are valid (0 <= start <= end <= len(text))
  (d) every decimal in the sentence appears in the cited spans
  (e) sentence and span share >= MIN_CONTENT_OVERLAP content words
  (f) I-bug-092: span semantically ENTAILS the sentence's specific claims
      (gated behind PG_STRICT_VERIFY_ENTAILMENT, defaults off)

Checks (a)-(e) are mechanical "provenance hygiene" — they bound a claim to
the same TOPIC as its span. Check (f) is "provenance correctness" — it
verifies the span actually entails the sentence's specific facts. The
audit on 2026-05-09 found that a capable generator can pass (a)-(e) by
producing topically-overlapping prose that introduces unsourced specifics
(e.g. inserting "pancreatic β-cells", "lipid metabolism", "energy storage"
into a span that says only "synergistic actions on insulin secretion,
glucagon suppression, appetite regulation, and adipocyte metabolism").

Returns a (verifier_pass: bool, drop_reason: str | None) pair, or directly
constructs a VerifiedSentence for use by the generator orchestrator.

Tunables (read at call time so tests can override):
  PG_PROVENANCE_MIN_CONTENT_OVERLAP — minimum shared content words (default 2)
  PG_STRICT_VERIFY_ENTAILMENT       — "off" | "warn" | "enforce" (default)
                                       off:     skip check (f), pre-I-bug-092 behavior
                                                — operator override; production runs
                                                  ship without provenance-correctness
                                                  enforcement
                                       warn:    run check (f), log violations,
                                                do NOT drop (collect telemetry)
                                       enforce: run check (f), drop on
                                                NEUTRAL or CONTRADICTED verdict
                                                (default per I-bug-095, validated
                                                empirically by I-bug-094 live test)
  PG_ENTAILMENT_MODEL               — entailment judge model
                                       (default: google/gemma-4-31b-it,
                                        the two-family evaluator)
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re

from src.polaris_graph.clinical_generator.provenance import (
    ProvenanceToken,
    extract_tokens,
    get_span_text,
    strip_tokens,
    validate_token_against_pool,
)
# S6 UNFREEZE (operator 2026-07-10): DROP -> LABEL + REPAIR policy. Top-level import is
# cycle-safe — verify_label_repair imports NOTHING from this module at import time (its
# strict_verify uses are all lazy, inside functions).
from src.polaris_graph.clinical_generator import verify_label_repair as _label_repair
# I-deepfix-001 L4 (#1344): CJK / multilingual-aware content tokenization + the
# unsegmentable-script fail-closed guard for the strict_verify overlap floor.
from src.polaris_graph.generator.script_aware_grounding import (
    extra_script_tokens,
    has_unsegmentable_content,
)
from src.polaris_graph.clinical_generator.verified_report import (
    DropReason,
    VerifiedSentence,
)
from src.polaris_graph.clinical_retrieval.evidence_pool import EvidencePool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

DEFAULT_MIN_CONTENT_OVERLAP = 2

# Minimal English stopword list. Strict-verify's content-word overlap should
# count substantive vocabulary, not function words. This is intentionally
# small — the rule is conservative ("at least 2 shared content words")
# so even a short stoplist yields the right behavior.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "at",
    "to", "for", "with", "as", "by", "from", "into", "through", "during",
    "before", "after", "above", "below", "between", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "having", "do",
    "does", "did", "doing", "will", "would", "should", "could", "may",
    "might", "must", "can", "this", "that", "these", "those", "it",
    "its", "their", "there", "they", "them", "we", "us", "our", "you",
    "your", "i", "me", "my", "he", "she", "his", "her",
})

_DECIMAL_RE = re.compile(r"\d+(?:\.\d+)?")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")
# I-deepfix-001 (Wave-2) — PERCENT-role regex mirroring
# ``provenance_generator._INTEGER_PERCENT_RE``: capture the number immediately
# before "%" or "percent" so a claim's printed percent can be compared
# PERCENT-vs-PERCENT against a cited span (never the bare-number union).
_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.IGNORECASE)


def _min_overlap_threshold() -> int:
    raw = os.environ.get("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "")
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MIN_CONTENT_OVERLAP


def _content_words(text: str) -> set[str]:
    """Lowercase content words (>=3 chars, not stopwords) from `text`.

    I-deepfix-001 L4 (#1344): the Latin path below is byte-identical to the
    pre-L4 engine (English unchanged). It is UNIONED with script-aware tokens
    (CJK character bigrams + space-delimited non-Latin words) so the
    ``overlap_too_low`` floor counts real shared content on non-Latin claims
    instead of mis-counting ZERO. Reverts byte-identical under
    PG_STRICT_VERIFY_SCRIPT_AWARE=0.
    """
    latin = {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if len(m.group(0)) >= 3 and m.group(0).lower() not in _STOPWORDS
    }
    return latin | extra_script_tokens(text)


def _decimals(text: str) -> set[str]:
    """Numeric tokens (integers + decimals) from `text`."""
    return {m.group(0) for m in _DECIMAL_RE.finditer(text)}


def _percents(text: str) -> set[str]:
    """I-deepfix-001 (Wave-2): PERCENT VALUES printed in `text` — the number
    immediately before "%"/"percent" (`_PERCENT_RE` group 1). "15%" and
    "15 percent" both yield "15"; a bare "15" (page number / year / count)
    yields nothing. Used to require a claim's printed percent to appear AS A
    PERCENT in a cited span, not merely as a coincidental bare digit."""
    return {m.group(1) for m in _PERCENT_RE.finditer(text)}


def _percent_role_match_enabled() -> bool:
    """I-deepfix-001 (Wave-2). True (DEFAULT) => every PERCENT value printed in
    the sentence must also appear AS A PERCENT in at least one cited span;
    otherwise the sentence drops (`numeric_mismatch`-class `percent_not_in_cited_span`).
    Strictly faithfulness-TIGHTENING and strictly ADDITIVE — it can only ADD a
    drop, never relax the decimal/overlap/entailment checks. Kill-switch
    PG_PROVENANCE_PERCENT_ROLE_MATCH=0 reverts BYTE-IDENTICAL. Read at call time."""
    v = os.environ.get("PG_PROVENANCE_PERCENT_ROLE_MATCH", "1").strip().lower()
    return v in ("1", "true", "yes", "on", "enabled")


# ---------------------------------------------------------------------------
# P5 (I-deepfix-001) — epistemic-QUALIFIER RETENTION gate
# ---------------------------------------------------------------------------
#
# Mirrors the Wave-2 PERCENT-role machinery: a strictly ADDITIVE, default-ON gate
# with a byte-identical-OFF kill-switch (PG_STRICT_VERIFY_QUALIFIER_RETENTION=0).
# It can only ADD a ``binding_qualifier_dropped`` drop — it never relaxes an
# existing check, so it stacks ON TOP of the I-faith-001 incumbent engine (that
# freeze covered engine REPLACEMENT, not an additive strengthening gate).
#
# WHY: the composer copies a numeral's VALUE but can silently drop the epistemic /
# scope qualifier bound to it in the cited span ("some estimates suggest 46% of
# jobs ... under a complementary-software scenario" restated as a flat "46% of
# jobs"). That is a certainty distortion (From-May-to-Is, arXiv:2606.07951): a
# hedged / conditional figure re-stated as a settled fact. The decimal / percent /
# overlap legs all PASS the stripped restatement, and the NLI leg is systematically
# lenient to hedge-dropping (a "more general" statement is still entailed), so the
# defect needs its OWN completeness gate — exactly as the P1-3 numeric-completeness
# guard mirrors the numeric leg.
#
# CALIBRATION (the over-fire guard): the gate anchors on a SUBSTANTIVE numeral
# (a decimal with a fractional part, or a percent-expressed value) that is SHARED
# between the span and the sentence, and only fires when an epistemic marker sits
# within a proximity window of that numeral IN THE SPAN while the sentence carries
# NO marker at all. Bare integers (page numbers, years, sample counts like the
# box1 negative ``N=1879``) are NOT substantive, so a plain short finding such as
# ``HbA1c reduced 2.3 points`` — whose span carries the SAME flat value with no
# nearby marker — never fires. The window bounds a marker to the numeral it
# actually qualifies; the broad SENTENCE-side marker set means any surviving hedge
# lets the sentence pass (the safe under-drop direction).

DEFAULT_QUALIFIER_PROXIMITY_TOKENS = 12

# The four From-May-to-Is (arXiv:2606.07951) epistemic-marker families, curated
# for PRECISION (plain factual verbs like "reported"/"indicated"/"expected" are
# deliberately excluded from the default so the gate does not over-fire on flat
# clinical spans). LAW VI: fully overridable via PG_STRICT_VERIFY_QUALIFIER_LEXICON
# (comma-separated). Multi-word phrases are matched whitespace-flexibly.
_DEFAULT_QUALIFIER_LEXICON: tuple[str, ...] = (
    # family 1 — hedges / approximators
    "may", "might", "could", "would", "likely", "unlikely", "probably",
    "possibly", "possible", "potentially", "perhaps", "approximately",
    "about", "around", "roughly", "nearly", "almost", "some", "certain",
    "up to", "as many as", "as much as", "at least", "at most",
    "no more than", "no fewer than",
    # family 2 — non-factive / projection verbs
    "estimate", "estimates", "estimated", "suggest", "suggests", "suggested",
    "propose", "proposed", "hypothesize", "hypothesized", "predict",
    "predicted", "project", "projected", "forecast", "forecasts", "forecasted",
    "model", "modeled", "modelled", "assume", "assumed", "believe", "believed",
    "claim", "claimed", "appear", "appears", "seem", "seems",
    # family 3 — source attribution
    "according to", "reportedly", "allegedly", "purportedly", "so-called",
    # family 4 — scope / conditional restrictors
    "if", "when", "assuming", "provided", "conditional", "scenario",
    "hypothetically", "theoretically", "in theory",
)


def _qualifier_retention_enabled() -> bool:
    """I-deepfix-001 (P5). True (DEFAULT) => run the epistemic-qualifier RETENTION
    gate; False => skip it. Strictly faithfulness-TIGHTENING and strictly ADDITIVE
    (it can only ADD a ``binding_qualifier_dropped`` drop). Kill-switch
    PG_STRICT_VERIFY_QUALIFIER_RETENTION=0 reverts BYTE-IDENTICAL. Read at call
    time so tests can override."""
    v = os.environ.get("PG_STRICT_VERIFY_QUALIFIER_RETENTION", "1").strip().lower()
    return v in ("1", "true", "yes", "on", "enabled")


def _qualifier_proximity_tokens() -> int:
    """Proximity window (in whitespace tokens) within which a span marker is bound
    to a numeral. PG_STRICT_VERIFY_QUALIFIER_PROXIMITY_TOKENS (default 12). An
    unset / non-integer value falls back to the default; a negative value clamps to
    0 (the tightest window). 0 = same-token only."""
    raw = os.environ.get("PG_STRICT_VERIFY_QUALIFIER_PROXIMITY_TOKENS", "").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_QUALIFIER_PROXIMITY_TOKENS


def _qualifier_lexicon() -> tuple[str, ...]:
    """The active epistemic-marker lexicon. LAW VI: PG_STRICT_VERIFY_QUALIFIER_LEXICON
    (comma-separated) overrides the curated default; an empty / all-blank override
    falls back to the default rather than disabling the gate silently."""
    raw = os.environ.get("PG_STRICT_VERIFY_QUALIFIER_LEXICON", "").strip()
    if not raw:
        return _DEFAULT_QUALIFIER_LEXICON
    items = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return items or _DEFAULT_QUALIFIER_LEXICON


@functools.lru_cache(maxsize=8)
def _qualifier_marker_re(lexicon: tuple[str, ...]) -> "re.Pattern[str]":
    """A word-boundary-anchored alternation over `lexicon`, longest phrase first so
    a multi-word marker ("up to") wins over its prefix. Internal spaces match any
    run of whitespace. Cached per distinct lexicon tuple."""
    parts = sorted({m for m in lexicon if m}, key=len, reverse=True)
    if not parts:
        # An all-blank lexicon can never match — a pattern that matches nothing.
        return re.compile(r"(?!x)x")
    alts = [re.escape(p).replace(r"\ ", r"\s+").replace(" ", r"\s+") for p in parts]
    return re.compile(r"\b(?:" + "|".join(alts) + r")\b", re.IGNORECASE)


def _has_epistemic_marker(text: str, marker_re: "re.Pattern[str]") -> bool:
    """True iff any epistemic marker appears in `text`."""
    return marker_re.search(text) is not None


def _substantive_numerals(text: str) -> set[str]:
    """Numerals carrying a CLAIMED magnitude: decimals with a fractional part, plus
    percent-expressed values (`_percents`). Bare integers — page numbers, years,
    sample counts ("N=1879") — are EXCLUDED: they are not the epistemically-hedged
    magnitudes the gate protects, and including them would over-fire on plain
    findings (the box1 calibration negatives)."""
    decimals_with_fraction = {n for n in _decimals(text) if "." in n}
    return decimals_with_fraction | _percents(text)


def _marker_binds_numeral_in_span(
    span_text: str,
    numeral: str,
    window: int,
    marker_re: "re.Pattern[str]",
) -> bool:
    """True iff an epistemic marker sits within `window` whitespace tokens of an
    occurrence of `numeral` inside `span_text`. The numeral is matched as a WHOLE
    number within a token ("46" matches "46%," / "46" but not "460" / "46.5"), so a
    coincidental substring never binds a marker."""
    tokens = span_text.split()
    for i, tok in enumerate(tokens):
        if numeral not in _decimals(tok):
            continue
        lo = max(0, i - window)
        hi = min(len(tokens), i + window + 1)
        if _has_epistemic_marker(" ".join(tokens[lo:hi]), marker_re):
            return True
    return False


# ---------------------------------------------------------------------------
# Entailment judge (I-bug-092 — provenance correctness)
# ---------------------------------------------------------------------------
#
# Definitions extracted to `polaris_graph.llm.entailment_judge` per
# I-bug-099 so future call sites have a single canonical home for the
# judge class + lazy singleton + telemetry counters. Re-exported here
# for backwards compatibility with the existing test pattern that
# monkey-patches `strict_verify._get_judge`, `strict_verify._JUDGE_TELEMETRY`,
# etc. via `monkeypatch.setattr(strict_verify, ...)`. Both `verify_sentence`
# (in this module) and `provenance_generator.verify_sentence_provenance`
# (which lazy-imports `_get_judge` from this module) read the re-exported
# names — a single rebind on `strict_verify` propagates to both.

from src.polaris_graph.llm.entailment_judge import (  # noqa: E402  -- re-export
    _DEFAULT_ENTAILMENT_MODEL,
    _ENTAILMENT_PROMPT,
    _ENTAILMENT_TIMEOUT_S,
    _EntailmentJudge,
    _JUDGE_TELEMETRY,
    _get_judge,
    _record_judge_outcome,
    get_judge_telemetry,
    reset_judge_telemetry,
)

# Note: `_JUDGE_SINGLETON` is NOT re-exported here. The resolver state
# lives in `polaris_graph.llm.entailment_judge` and is updated via
# that module's `global _JUDGE_SINGLETON` declaration in `_get_judge()`.
# Tests that do `monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON",
# fake, raising=False)` create a vestigial attribute that the resolver
# never reads — but the same tests also patch `_get_judge`, which IS
# re-exported and DOES propagate (provenance_generator lazy-imports
# `_get_judge` from this module at call time, so it picks up the patched
# value). Test patch surface is preserved by the `_get_judge` rebind;
# the `_JUDGE_SINGLETON` rebind is incidental.


# I-bug-097: dedup unknown-mode warnings so a long-running process logs
# at most ONE WARNING per typo string. Operators sometimes set
# PG_STRICT_VERIFY_ENTAILMENT=ENFORCE (already lowercased fine) or
# =enforced (verb form, falls through to off). Without a warning, the
# typo silently disables the gate.
#
# KEPT here (not moved to entailment_judge.py per I-bug-099 iter-2
# brief): tests rebind via `monkeypatch.setattr(strict_verify,
# "_UNKNOWN_MODE_WARNED", set(), raising=False)` and `_entailment_mode()`
# reads it from this module's globals — preserving the rebind contract.
_UNKNOWN_MODE_WARNED: set[str] = set()


# I-bug-095: production default flipped from "off" to "enforce" per
# Codex APPROVE iter 1. Empirical evidence: I-bug-094 live test ran
# 4/4 audit-derived cases (M2/C2/C1 + positive control) against real
# OpenRouter Gemma 4 31B and got correct verdicts. The cage is
# structurally complete with I-bug-092..097 + I-cj-008; flipping the
# default closes the loop on the 2026-05-09 audit-revealed gap.
#
# Operator escape hatch: `PG_STRICT_VERIFY_ENTAILMENT=off` continues
# to disable the check explicitly. Documented per Codex iter-1 brief
# verdict.
_DEFAULT_MODE = "enforce"


def _entailment_mode() -> str:
    """Return one of 'off', 'warn', 'enforce'. Unknown values map to default.

    I-bug-097: emit a single WARNING per process per unrecognized typo
    string. Empty / unset env returns the default mode silently —
    that is the intended default, not a misconfiguration.

    I-bug-095: default mode is 'enforce' (was 'off' before this Issue).
    Operators who need the pre-graduation behavior can set
    PG_STRICT_VERIFY_ENTAILMENT=off explicitly.
    """
    raw = os.environ.get("PG_STRICT_VERIFY_ENTAILMENT", _DEFAULT_MODE).lower().strip()
    if raw and raw not in ("off", "warn", "enforce"):
        if raw not in _UNKNOWN_MODE_WARNED:
            _UNKNOWN_MODE_WARNED.add(raw)
            logger.warning(
                "PG_STRICT_VERIFY_ENTAILMENT=%r unrecognized; "
                "treating as %r (default). Valid: off, warn, enforce.",
                raw, _DEFAULT_MODE,
            )
        return _DEFAULT_MODE
    return raw or _DEFAULT_MODE


# ---------------------------------------------------------------------------
# Per-sentence verifier
# ---------------------------------------------------------------------------

def verify_sentence(
    sentence_text: str,
    pool: EvidencePool,
    min_content_overlap: int | None = None,
    is_synthesis_claim: bool = False,
) -> tuple[bool, DropReason | None]:
    """Return (verifier_pass, drop_reason) for `sentence_text` against `pool`.

    Pass: returns (True, None).
    Fail: returns (False, drop_reason) with reason from DropReason literal.

    Implements CLAUDE.md §9.1 invariant 3 in order:
      1. at least one well-formed token        → no_provenance_token
      2. every token references known source_id → invalid_token
      3. spans within source bounds            → span_out_of_range
      4. every decimal in sentence in spans    → numeric_mismatch
      5. >=N shared content words              → overlap_too_low
      6. (I-bug-092) span entails sentence     → entailment_failed
         (gated by PG_STRICT_VERIFY_ENTAILMENT, off by default)

    If `is_synthesis_claim=True` AND the sentence has no tokens, return
    (True, None) — synthesis claims pass without provenance by definition
    (I-f5-006). If a synthesis claim DOES carry tokens, that's a generator
    bug; we still run token checks so the underlying invariant holds.
    """
    threshold = (
        min_content_overlap
        if min_content_overlap is not None
        else _min_overlap_threshold()
    )

    tokens = extract_tokens(sentence_text)
    if not tokens:
        if is_synthesis_claim:
            return True, None
        return False, "no_provenance_token"

    # Validate each token against the pool. Collect span texts for
    # later numeric + overlap checks.
    span_texts: list[str] = []
    for token in tokens:
        reason = validate_token_against_pool(token, pool)
        if reason == "invalid_token":
            return False, "invalid_token"
        if reason == "span_out_of_range":
            return False, "span_out_of_range"
        # Token valid — fetch its span text
        span = get_span_text(token, pool)
        if span is None:
            # Belt-and-suspenders: token validated but get_span_text said no.
            return False, "span_out_of_range"
        span_texts.append(span)

    sentence_clean = strip_tokens(sentence_text)
    combined_span = " ".join(span_texts)

    # Decimal match: every decimal in sentence must appear in the combined
    # span text. Permits the spans to contain MORE decimals than the
    # sentence cites — that's fine; the constraint is one-way.
    sentence_decimals = _decimals(sentence_clean)
    span_decimals = _decimals(combined_span)
    if not sentence_decimals.issubset(span_decimals):
        return False, "numeric_mismatch"

    # I-deepfix-001 (Wave-2) PERCENT-ROLE re-check (parity with
    # provenance_generator.verify_sentence_provenance). A printed percent
    # ("15%", "15 percent") is a PERCENT claim: it must be carried by a cited
    # span AS A PERCENT, not merely as a bare digit that coincidentally equals
    # the value (a page number / year / count). The decimal check above passes a
    # bare "15" via the number union; this compares PERCENT-vs-PERCENT
    # (`_percents`, same regex both sides). Span percents are read PER cited span
    # text (not the joined string) so a "15" ending one span and a "%" starting
    # the next can never be glued into a spurious percent. STRICTLY ADDITIVE:
    # only ADDS a drop; nothing grounded by a genuine in-span percent is newly
    # dropped. Default-ON; PG_PROVENANCE_PERCENT_ROLE_MATCH=0 reverts byte-identical.
    if _percent_role_match_enabled():
        sentence_percents = _percents(sentence_clean)
        if sentence_percents:
            span_percents: set[str] = set()
            for _span in span_texts:
                span_percents |= _percents(_span)
            if not sentence_percents.issubset(span_percents):
                return False, "percent_not_in_cited_span"

    # I-deepfix-001 (P5) EPISTEMIC-QUALIFIER RETENTION re-check. The composer can
    # copy a numeral's VALUE but drop the hedge / scope qualifier the cited span
    # binds to it ("some estimates suggest 46% ... under a complementary-software
    # scenario" -> a flat "46%"). For each cited span, if a SUBSTANTIVE numeral in
    # the span (decimal / percent — never a bare count / year) also appears in the
    # sentence AND an epistemic marker sits within
    # PG_STRICT_VERIFY_QUALIFIER_PROXIMITY_TOKENS of THAT numeral IN THE SPAN, the
    # sentence must itself carry a marker; else it dropped a binding qualifier ->
    # (False, "binding_qualifier_dropped"). Span percents/decimals are read PER
    # cited span (not the joined string) so a marker in one span can never bind a
    # numeral in another. STRICTLY ADDITIVE: only ADDS a drop; the verbatim K-span
    # fallback retains the qualifier by construction, so a genuine hedged finding
    # still ships. Default-ON; PG_STRICT_VERIFY_QUALIFIER_RETENTION=0 reverts
    # byte-identical. Read at call time.
    if _qualifier_retention_enabled():
        marker_re = _qualifier_marker_re(_qualifier_lexicon())
        if not _has_epistemic_marker(sentence_clean, marker_re):
            window = _qualifier_proximity_tokens()
            sentence_numbers = _decimals(sentence_clean)
            for _span in span_texts:
                shared = _substantive_numerals(_span) & sentence_numbers
                for numeral in shared:
                    if _marker_binds_numeral_in_span(
                        _span, numeral, window, marker_re
                    ):
                        return False, "binding_qualifier_dropped"

    # I-deepfix-001 L4 (#1344): FAIL-CLOSED on unsegmentable script content. A
    # claim carrying a run of letters in a script we cannot segment
    # (Thai/Lao/Khmer/Myanmar/Tibetan) yields no content tokens; rather than let
    # it slip past the overlap floor on a coincidental decimal match, we drop it
    # — we cannot establish lexical grounding and MUST NOT guess a pass (the
    # lethal weakened-positive). CJK / Arabic / Cyrillic etc. tokenize correctly
    # via _content_words and never reach here. Reverts byte-identical under
    # PG_STRICT_VERIFY_SCRIPT_AWARE=0.
    if has_unsegmentable_content(sentence_clean):
        return False, "unsegmentable_script"

    # Content-word overlap
    sentence_words = _content_words(sentence_clean)
    span_words = _content_words(combined_span)
    # BUG-03 (FX-02, #1106): a truly contentless sentence — NO content words AND no decimals —
    # is dropped EXPLICITLY here (mirrors the provenance_generator floor). With the default
    # threshold=2 it would already fail as overlap_too_low, but this fail-closes the
    # PG_PROVENANCE_MIN_CONTENT_OVERLAP=0 edge (where overlap=0 is not < 0) and gives a precise
    # reason. Faithfulness-TIGHTENING: any content word OR decimal routes to the numeric/overlap
    # floors, so a real clinical sentence can never trip this.
    if not sentence_words and not sentence_decimals:
        return False, "empty_or_contentless_sentence"
    overlap = len(sentence_words & span_words)
    if overlap < threshold:
        return False, "overlap_too_low"

    # Check (f) — entailment judge (I-bug-092). Synthesis claims with no
    # tokens already short-circuited above; if a synthesis claim DOES
    # carry tokens it must clear the same content-correctness bar as
    # any other cited sentence.
    mode = _entailment_mode()
    if mode in ("warn", "enforce"):
        verdict, reason = _get_judge().judge(sentence_clean, combined_span)
        _record_judge_outcome(verdict, reason)
        # I-ready-002 (#1071) P0: the judge FAILS OPEN to ("ENTAILED","judge_error:...") on an API/parse
        # error. Counting that as a genuine ENTAILED ships an UNVERIFIED clinical claim as "verified" — a
        # silent downgrade of the binding faithfulness gate (LAW II / lethal-in-clinical). Detect it and
        # FAIL CLOSED in enforce mode (drop the sentence, like an unsupported one); warn-mode logs only.
        if isinstance(reason, str) and reason.startswith("judge_error:"):
            # I-deepfix-001 W11-section-verify-judge-error-degrade (#1344): a judge_error is
            # a TRANSPORT fault (the judge socket failed / returned unparseable), NOT a
            # genuine NEUTRAL/CONTRADICTED faithfulness verdict. The mechanical provenance
            # gates (a)-(e) ALREADY passed above (evidence-id, span-bounds, decimals, >=2
            # content-word overlap), so this is an otherwise span-grounded claim being
            # dropped purely because of a socket fault. Under a SUSTAINED judge outage the
            # enforce-drop can empty EVERY section -> abort_no_verified_sections despite real
            # span-grounded evidence. Per the operator-locked "verifier NEVER holds a report":
            # when PG_STRICT_VERIFY_JUDGE_ERROR_ALWAYS_RELEASE is ON, DEGRADE to KEEP-with-
            # disclosed-label (the per-claim 'entailment_unverified_judge_error' label IS the
            # faithfulness signal). This applies ONLY to judge_error (transport) — genuine
            # NEUTRAL/CONTRADICTED below stay DROPPED (faithfulness NOT relaxed). Default-OFF
            # preserves the byte-identical enforce-drop.
            logger.warning(
                "entailment judge_error (mode=%s): sentence=%r reason=%r — failing closed",
                mode, sentence_clean, reason,
            )
            if mode == "enforce":
                _je_release = os.environ.get(
                    "PG_STRICT_VERIFY_JUDGE_ERROR_ALWAYS_RELEASE", "0",
                ).strip().lower() in ("1", "true", "yes", "on")
                if _je_release:
                    logger.warning(
                        "entailment judge_error (mode=enforce): KEEPING span-grounded "
                        "sentence with disclosed label (always-release; transport fault, "
                        "not a NEUTRAL/CONTRADICTED verdict): %r", sentence_clean,
                    )
                    return True, "entailment_unverified_judge_error"
                return False, "entailment_judge_error_fail_closed"
        if verdict in ("NEUTRAL", "CONTRADICTED"):
            logger.warning(
                "entailment %s (mode=%s): sentence=%r reason=%r",
                verdict, mode, sentence_clean, reason,
            )
            if mode == "enforce":
                return False, "entailment_failed"

    return True, None


def _collect_span_texts(sentence_text: str, pool: EvidencePool) -> list[str]:
    """Best-effort collect the cited-span texts for a sentence (mirrors the span
    collection inside ``verify_sentence``). Used ONLY by the S6 LABEL+REPAIR qualifier
    repair; skips any invalid / out-of-range token rather than raising."""
    spans: list[str] = []
    for token in extract_tokens(sentence_text):
        if validate_token_against_pool(token, pool) is not None:
            continue
        span = get_span_text(token, pool)
        if span is not None:
            spans.append(span)
    return spans


def verify_sentence_to_record(
    sentence_text: str,
    section_id: str,
    pool: EvidencePool,
    min_content_overlap: int | None = None,
    is_synthesis_claim: bool = False,
    *,
    repair_fn=None,
) -> VerifiedSentence:
    """Convenience: wrap verify_sentence into a VerifiedSentence record.

    Used by the generator orchestrator to build Section.verified_sentences.

    S6 UNFREEZE (operator 2026-07-10): ``repair_fn`` is the optional live NLI
    re-grounder ``(sentence, span_texts, drop_reason) -> repaired_sentence`` for the
    ``nli`` repair mode; ``None`` (default) uses the deterministic hedge repair. See
    ``verify_label_repair`` for the full DROP->LABEL+REPAIR contract.
    """
    passed, reason = verify_sentence(
        sentence_text,
        pool,
        min_content_overlap=min_content_overlap,
        is_synthesis_claim=is_synthesis_claim,
    )

    # S6 UNFREEZE (operator 2026-07-10): DROP -> LABEL + REPAIR. When a sentence FAILED
    # strict_verify for a LABEL-ELIGIBLE (grounded-but-weak) reason AND the policy flag
    # is ON, KEEP it with a confidence label instead of silently dropping it — the
    # operator's "verifier labels weak claims weak, never holds a report" rule. FATAL
    # reasons (fabricated citation / unsupported number / contradicted / ungrounded)
    # still DROP: that is the policy's own clinical-safety boundary (§-1.1). Synthesis
    # claims are excluded — their no-token schema invariant conflicts with a token-bearing
    # label-keep. Default-OFF (PG_STRICT_VERIFY_LABEL_REPAIR unset) => byte-identical DROP.
    if (
        not passed
        and reason is not None
        and not is_synthesis_claim
        and _label_repair.label_repair_enabled()
    ):
        _decision = _label_repair.apply_label_repair_policy(
            sentence_text,
            reason,
            _collect_span_texts(sentence_text, pool),
            repair_fn=repair_fn,
        )
        if _decision.kept:
            _kept_text = _decision.sentence_text
            _kept_tokens = [t.raw for t in extract_tokens(_kept_text)]
            return VerifiedSentence(
                section_id=section_id,
                sentence_text=_kept_text,
                provenance_tokens=_kept_tokens,
                verifier_pass=True,
                drop_reason=None,
                # The confidence label IS the preserved grounding signal (D8 + the
                # §-1.1 auditor both read it). evaluator_agrees stays None (pending) —
                # the two-family evaluator has NOT confirmed a label-kept weak sentence.
                kept_disclosure_label=_decision.disclosure_label,
                evaluator_agrees=None,
                is_synthesis_claim=is_synthesis_claim,
            )

    tokens = [t.raw for t in extract_tokens(sentence_text)]
    # I-deepfix-001 (Codex e2e gate P1): verify_sentence can return (passed=True, reason=<label>)
    # for the judge-error always-release path (span-grounded sentence KEPT with a disclosed
    # caveat). The VerifiedSentence schema forbids a non-None drop_reason when verifier_pass=True,
    # so a KEPT-with-disclosure caveat MUST ride in release_disclosure, not drop_reason — else the
    # construction raises and the intended ship-with-label ABORTS. drop_reason stays the
    # DROPPED-only reason (passed is False). Faithfulness untouched: NEUTRAL/CONTRADICTED still
    # fail (passed=False) and carry drop_reason exactly as before.
    kept_disclosure_label = reason if (passed and reason is not None) else None
    drop_reason = None if passed else reason
    return VerifiedSentence(
        section_id=section_id,
        sentence_text=sentence_text,
        provenance_tokens=tokens,
        verifier_pass=passed,
        drop_reason=drop_reason,
        kept_disclosure_label=kept_disclosure_label,
        evaluator_agrees=passed,
        is_synthesis_claim=is_synthesis_claim,
    )


# ---------------------------------------------------------------------------
# Section-level rollup
# ---------------------------------------------------------------------------

def section_pass_rate(sentences: list[VerifiedSentence]) -> float:
    """Fraction of sentences that passed verify, in [0.0, 1.0].

    Empty list returns 0.0 (vacuously below any threshold).
    """
    if not sentences:
        return 0.0
    passed = sum(1 for s in sentences if s.verifier_pass)
    return passed / len(sentences)
