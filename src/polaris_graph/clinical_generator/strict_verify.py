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


def _min_overlap_threshold() -> int:
    raw = os.environ.get("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "")
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MIN_CONTENT_OVERLAP


def _content_words(text: str) -> set[str]:
    """Lowercase content words (>=3 chars, not stopwords) from `text`."""
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if len(m.group(0)) >= 3 and m.group(0).lower() not in _STOPWORDS
    }


def _decimals(text: str) -> set[str]:
    """Numeric tokens (integers + decimals) from `text`."""
    return {m.group(0) for m in _DECIMAL_RE.finditer(text)}


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
            logger.warning(
                "entailment judge_error (mode=%s): sentence=%r reason=%r — failing closed",
                mode, sentence_clean, reason,
            )
            if mode == "enforce":
                return False, "entailment_judge_error_fail_closed"
        if verdict in ("NEUTRAL", "CONTRADICTED"):
            logger.warning(
                "entailment %s (mode=%s): sentence=%r reason=%r",
                verdict, mode, sentence_clean, reason,
            )
            if mode == "enforce":
                return False, "entailment_failed"

    return True, None


def verify_sentence_to_record(
    sentence_text: str,
    section_id: str,
    pool: EvidencePool,
    min_content_overlap: int | None = None,
    is_synthesis_claim: bool = False,
) -> VerifiedSentence:
    """Convenience: wrap verify_sentence into a VerifiedSentence record.

    Used by the generator orchestrator to build Section.verified_sentences.
    """
    passed, reason = verify_sentence(
        sentence_text,
        pool,
        min_content_overlap=min_content_overlap,
        is_synthesis_claim=is_synthesis_claim,
    )
    tokens = [t.raw for t in extract_tokens(sentence_text)]
    return VerifiedSentence(
        section_id=section_id,
        sentence_text=sentence_text,
        provenance_tokens=tokens,
        verifier_pass=passed,
        drop_reason=reason,
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
