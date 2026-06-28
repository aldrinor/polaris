"""I-bug-108 — Verifier-driven sentence repair loop.

Per Codex strategic-review iter 1 path B + I-bug-108 brief APPROVE:
when strict_verify drops a sentence due to "drift" failures (entailment,
number, trial-name, content overlap), feed (sentence, cited spans,
failure reason) back to the generator and ask for a single rewrite that
makes the cited span actually entail the claim.

Key design points:

1. **Loop runs AFTER strict_verify** — does not modify the verifier;
   the verifier remains the source of truth. Repair is a downstream
   recovery layer that re-presents repaired candidates to the same
   verification chain.

2. **Targets drift failures only** — no_provenance_token, invalid_token,
   span_out_of_range are NOT repairable (the sentence has no anchor or
   its anchor is invalid; rewriting won't help). See REPAIRABLE_REASONS.

3. **Token-set preservation (Codex iter-1 P0)** — repaired output MUST
   carry exactly the same [#ev:id:start-end] markers as the original,
   in any order. Any change → treated as repair failure (preserves the
   audit invariant: kept prose never references evidence the original
   draft didn't cite).

4. **Bounded** — 1 retry per sentence, cap MAX_PER_SECTION repairs.
   Deterministic order (original drop order) so MAX_PER_SECTION cap
   doesn't make runs noisy.

5. **Drop accounting honest** — recovered sentences move from dropped
   to kept; failed-repair sentences stay dropped (no double-counting).

6. **Off by default in tests, on by default in production** — gated by
   PG_REPAIR_LOOP_ENABLED env var. Tests autouse-fixture set =false to
   keep CI free of accidental network calls.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from src.polaris_graph.generator.provenance_generator import (
    SentenceVerification,
    parse_provenance_tokens,
    verify_sentence_provenance,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

MAX_RETRIES_PER_SENTENCE = 1  # Codex iter-1 brief: bounded; cost discipline
MAX_PER_SECTION_DEFAULT = 10  # Codex iter-1 brief
NULL_DROP_SENTINEL = "NULL_DROP"

# I-deepfix-001 B17 (#1361): marker-PRUNE — a repair may DROP a co-cited [#ev:...] marker IFF its span
# does not support the claim (a SUBSET of the original markers), never ADD a marker, never empty the
# set. The legacy contract forced marker-set EQUALITY, so when the repair reasoning itself concluded a
# co-cited span does NOT support the claim it could not drop that marker — it degraded the sentence into
# a vague multi-citation umbrella that "fits" every span, implying corroboration the reasoning denied
# (forensic Repair #23/#35). A marker must mean "this span supports this sentence"; allowing the
# unsupported one to be pruned (then CONFIRMED dropped via the entailment judge, fail-closed to KEEP)
# STRENGTHENS basket faithfulness (§-1.3). LAW VI kill-switch PG_REPAIR_MARKER_PRUNE_ENABLED (default
# ON) => the legacy equality contract is restored byte-for-byte.
_ENV_MARKER_PRUNE_ENABLED = "PG_REPAIR_MARKER_PRUNE_ENABLED"


def _marker_prune_enabled() -> bool:
    """True iff the default-ON B17 marker-prune (subset-accept + per-dropped-marker entailment confirm)
    is active. ``PG_REPAIR_MARKER_PRUNE_ENABLED=0/off/false/no`` => the legacy marker-set EQUALITY
    contract is restored byte-for-byte."""
    return os.environ.get(_ENV_MARKER_PRUNE_ENABLED, "1").strip().lower() in (
        "1", "true", "yes", "on", "enabled",
    )

# Failures that benefit from rewriting. See module docstring point 2.
REPAIRABLE_REASON_PREFIXES: frozenset[str] = frozenset({
    "entailment_failed",
    "number_not_in_any_cited_span",
    "no_integer_overlap_any_cited_span",
    "trial_name_mismatch",
    "no_content_word_overlap_any_cited_span",
    "overlap_too_low",
})


REPAIR_SYSTEM_PROMPT = """You are repairing a single sentence that a strict verifier dropped because the cited span does NOT support the sentence's specific claims. Your job is to rewrite the sentence so the cited span actually entails it — drop unsupported specifics, keep the [#ev:...] markers EXACTLY as they appear in the original, output exactly one rewritten sentence (no preamble, no sign-off).

CONSTRAINTS (STRICT — non-compliance = repair failure):

1. **Preserve [#ev:...] markers EXACTLY**: same evidence_id, same start-end byte range. The number of markers and their content must match the original. Do NOT add new markers, do NOT remove existing markers, do NOT change the byte ranges.

2. **No new specifics not in the cited span**: do NOT introduce numbers, study names, jurisdictions, mechanism details, or comparators that aren't literally in the cited span text. The verifier will reject again if you do.

3. **Hedge generic where the original was specific**: if the original said "tirzepatide reduced HbA1c by 1.7%" and the span only says "tirzepatide reduced HbA1c", rewrite as "tirzepatide reduced HbA1c [#ev:...]" — the qualitative claim is in the span, the magnitude is not.

4. **If you cannot make the claim entailed by the span**: output exactly NULL_DROP (capital, no quotes, nothing else). The original drop will be preserved.

5. **Output format**: just the rewritten sentence on a single line, ending with the [#ev:...] markers preserved. No quotes, no preamble, no explanation."""


# I-deepfix-001 B17 (#1361): the marker-PRUNE variant of the repair prompt. Constraint #1 is relaxed
# from "keep every marker EXACTLY" to "keep every SUPPORTING marker, DROP a marker IFF its span does
# not support the claim, never ADD a marker" (a subset, never a superset, never empty). Used when
# PG_REPAIR_MARKER_PRUNE_ENABLED is ON; the dropped marker is independently CONFIRMED unsupported via
# the entailment judge before the prune is accepted (orchestrator), so the model cannot prune a
# genuinely-supporting span to dodge repair. STRENGTHENS faithfulness.
REPAIR_SYSTEM_PROMPT_MARKER_PRUNE = """You are repairing a single sentence that a strict verifier dropped because the cited span does NOT support the sentence's specific claims. Your job is to rewrite the sentence so every cited span actually entails it — drop unsupported specifics, output exactly one rewritten sentence (no preamble, no sign-off).

CONSTRAINTS (STRICT — non-compliance = repair failure):

1. **Markers must be a SUBSET of the original**: keep every [#ev:...] marker whose span SUPPORTS the rewritten claim, EXACTLY (same evidence_id, same start-end byte range). You MAY REMOVE a marker IF AND ONLY IF that span does NOT support the claim — do not keep a non-supporting marker by diluting the sentence into a vague umbrella that "fits" every span. NEVER ADD a new marker, NEVER change a byte range, and keep AT LEAST ONE marker. A marker means "this span supports this sentence."

2. **No new specifics not in a kept cited span**: do NOT introduce numbers, study names, jurisdictions, mechanism details, or comparators that aren't literally in a KEPT cited span text. The verifier will reject again if you do.

3. **Hedge generic where the original was specific**: if the original said "tirzepatide reduced HbA1c by 1.7%" and the span only says "tirzepatide reduced HbA1c", rewrite as "tirzepatide reduced HbA1c [#ev:...]" — the qualitative claim is in the span, the magnitude is not.

4. **If you cannot make the claim entailed by any remaining span**: output exactly NULL_DROP (capital, no quotes, nothing else). The original drop will be preserved.

5. **Output format**: just the rewritten sentence on a single line, ending with the kept [#ev:...] markers preserved. No quotes, no preamble, no explanation."""


# ---------------------------------------------------------------------------
# Repair invocation
# ---------------------------------------------------------------------------


def is_repairable(failure_reasons: list[str]) -> bool:
    """A SentenceVerification.failure_reasons is repairable if every
    reason has a prefix in REPAIRABLE_REASON_PREFIXES.

    Mixed-failure sentences (e.g. invalid_token + entailment_failed)
    are NOT repairable — the invalid_token side won't fix from a
    rewrite. SKIP per the brief.
    """
    if not failure_reasons:
        return False
    for reason in failure_reasons:
        prefix = reason.split(":", 1)[0]
        if prefix not in REPAIRABLE_REASON_PREFIXES:
            return False
    return True


def _extract_token_signature(sentence: str) -> tuple[str, ...]:
    """Return a stable, sorted signature of all [#ev:id:start-end]
    tokens in the sentence, used for the Codex iter-1 token-set
    preservation check.

    Order doesn't matter (a repair may rearrange tokens) but the SET
    must match exactly. Each token's full string form is the unit.
    """
    tokens = parse_provenance_tokens(sentence)
    return tuple(sorted(t.raw for t in tokens))


def _span_text_for_token(tok: Any, evidence_pool: dict[str, dict[str, Any]]) -> str:
    """The cited span text for ONE provenance token (``direct_quote`` first, then ``statement``).
    Returns ``""`` when the evidence row / span is unavailable. PURE."""
    ev = evidence_pool.get(tok.evidence_id)
    if ev is None:
        return ""
    direct = ev.get("direct_quote") or ev.get("statement") or ""
    return direct[tok.start:tok.end] if tok.end <= len(direct) else direct[tok.start:]


def _confirm_marker_droppable(
    claim_text: str, span_text: str, judge: "Any | None" = None,
) -> bool:
    """I-deepfix-001 B17: confirm a PRUNED marker's span genuinely does NOT support the claim, via the
    entailment judge — so the model cannot prune a genuinely-supporting span to dodge repair. Returns
    True (prune confirmed) ONLY on a clean NEUTRAL / CONTRADICTED verdict. FAIL-CLOSED: a judge_error
    (the ``(ENTAILED, "judge_error: ...")`` sentinel), an ENTAILED verdict, an empty span, OR any
    exception => False (KEEP the marker — the drop is rejected, never a faithfulness relaxation).

    ``judge`` is injectable for offline tests; None lazily builds the production ``_EntailmentJudge``.
    A missing/uninstantiable judge fail-CLOSES to False (keep the marker)."""
    if not span_text.strip():
        return False  # no span to test -> cannot confirm the drop -> KEEP (fail-closed)
    if judge is None:
        try:
            from src.polaris_graph.llm.entailment_judge import _EntailmentJudge
            judge = _EntailmentJudge()
        except Exception as exc:  # pragma: no cover — judge resolved at runtime on the paid path
            logger.warning("[sentence_repair] entailment judge unavailable (keep marker): %s", exc)
            return False
    try:
        verdict, reason = judge.judge(claim_text, span_text)
    except Exception as exc:
        logger.warning("[sentence_repair] entailment judge raised (keep marker, fail-closed): %s", exc)
        return False
    # The fail-closed transport sentinel is ('ENTAILED', 'judge_error: ...'); treat ANY judge_error as
    # KEEP. Prune ONLY on a genuine NEUTRAL / CONTRADICTED (the span does not support the claim).
    if str(reason or "").startswith("judge_error:"):
        return False
    return str(verdict).upper() in ("NEUTRAL", "CONTRADICTED")


def _build_cited_spans_block(
    tokens: list[Any],
    evidence_pool: dict[str, dict[str, Any]],
) -> str:
    """Render the cited spans the original sentence pointed to, so the
    repair model can read the actual text it must entail.
    """
    lines = []
    for tok in tokens:
        ev = evidence_pool.get(tok.evidence_id)
        direct = ""
        if ev is not None:
            direct = ev.get("direct_quote") or ev.get("statement") or ""
        span_text = direct[tok.start:tok.end] if tok.end <= len(direct) else direct[tok.start:]
        lines.append(
            f"  [#ev:{tok.evidence_id}:{tok.start}-{tok.end}]:\n"
            f"    {span_text!r}"
        )
    return "\n".join(lines)


async def repair_sentence(
    *,
    dropped: SentenceVerification,
    evidence_pool: dict[str, dict[str, Any]],
    model: str = "deepseek/deepseek-v4-pro",
    max_tokens: int = 400,
    temperature: float = 0.2,
) -> tuple[str, str | None, int, int]:
    """Single repair attempt on one dropped sentence.

    Returns (outcome, repaired_text, in_tokens, out_tokens). Iter-2 P1
    fix per Codex review: outcome is an explicit string, not inferred
    from token counts — reliable telemetry classification.

    outcome values:
      - "text": the LLM produced a candidate rewrite (in repaired_text);
                caller must re-verify before kept[].
      - "null_drop": the LLM responded NULL_DROP — accept the original drop.
      - "api_failure": exception / network error / no response from API.
      - "skipped": failure_reasons aren't repairable.
    """
    from src.polaris_graph.llm.openrouter_client import (
        OpenRouterClient,
        set_reasoning_call_context,
    )

    if not is_repairable(dropped.failure_reasons):
        return "skipped", None, 0, 0

    cited_block = _build_cited_spans_block(dropped.tokens, evidence_pool)
    reason_block = "\n".join(f"  - {r}" for r in dropped.failure_reasons)

    prompt = (
        f"ORIGINAL SENTENCE (was dropped by strict_verify):\n"
        f"{dropped.sentence}\n\n"
        f"CITED SPAN(S) FROM THE EVIDENCE:\n"
        f"{cited_block}\n\n"
        f"VERIFIER REASON FOR DROPPING:\n"
        f"{reason_block}\n\n"
        f"TASK: Rewrite the sentence per the rules. If the claim cannot be "
        f"made entailed by the cited span, output NULL_DROP."
    )

    client = OpenRouterClient(model=model)
    try:
        # I-gen-004 (#496): tag the sentence-repair call for the trace sink.
        set_reasoning_call_context(section="_repair", call_type="repair")
        response = await client.generate(
            prompt=prompt,
            # I-deepfix-001 B17: the marker-PRUNE prompt (subset-accept) when the flag is ON; the
            # legacy EQUALITY prompt otherwise (byte-identical legacy behaviour).
            system=(
                REPAIR_SYSTEM_PROMPT_MARKER_PRUNE
                if _marker_prune_enabled()
                else REPAIR_SYSTEM_PROMPT
            ),
            # I-wire-009 (#1323): the repair max_tokens defaults to 400 -> floored to
            # PG_GLM5_MIN_MAX_TOKENS=4096 on the GLM-5.2 _ALWAYS_REASON path. Bound the reasoning
            # pool and floor CONTENT so a single repaired sentence is never starved to empty by an
            # effort=high prelude (which would otherwise surface as a silent api_failure below).
            # LAW VI env-tunable; faithfulness-neutral (every repaired sentence is re-verified by
            # the UNCHANGED strict_verify downstream).
            max_tokens=max(
                max_tokens, int(os.getenv("PG_REPAIR_MIN_MAX_TOKENS", "4096"))
            ),
            temperature=temperature,
            reasoning_max_tokens=int(
                os.getenv("PG_REPAIR_REASONING_MAX_TOKENS", "2048")
            ),
        )
        text = (response.content or "").strip()
        in_tok = response.input_tokens
        out_tok = response.output_tokens
    except Exception as exc:
        logger.warning("[sentence_repair] LLM call failed: %s", exc)
        return "api_failure", None, 0, 0
    finally:
        try:
            await client.close()
        except Exception:
            pass

    # Strip any wrapping quotes the model may have added
    text = text.strip().strip('"').strip("'").strip()

    if not text or text.upper().startswith(NULL_DROP_SENTINEL):
        return "null_drop", None, in_tok, out_tok

    return "text", text, in_tok, out_tok


# ---------------------------------------------------------------------------
# Section orchestrator
# ---------------------------------------------------------------------------


@dataclass
class RepairTelemetry:
    attempts: int = 0
    successes: int = 0
    null_drops: int = 0           # model said NULL_DROP
    token_set_violations: int = 0  # repaired output changed token set (ADDED a marker / emptied the set)
    re_verify_failures: int = 0    # repaired output still failed verifier
    api_failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # I-deepfix-001 B17 (#1361): co-cited markers PRUNED because the repaired claim no longer cites
    # them AND the entailment judge confirmed (NEUTRAL/CONTRADICTED) the dropped span does not support
    # the claim. A legitimate subset-prune, never a token_set_violation. STRENGTHENS faithfulness.
    markers_pruned: int = 0

    @property
    def recovery_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0


def _repair_loop_enabled() -> bool:
    raw = os.environ.get("PG_REPAIR_LOOP_ENABLED", "true").lower().strip()
    return raw in ("true", "1", "yes", "on")


def _max_per_section() -> int:
    raw = os.environ.get(
        "PG_REPAIR_LOOP_MAX_PER_SECTION", str(MAX_PER_SECTION_DEFAULT),
    )
    try:
        return max(0, int(raw))
    except ValueError:
        return MAX_PER_SECTION_DEFAULT


async def repair_dropped_section_sentences(
    *,
    kept: list[SentenceVerification],
    dropped: list[SentenceVerification],
    evidence_pool: dict[str, dict[str, Any]],
    model: str = "deepseek/deepseek-v4-pro",
    max_tokens: int = 400,
    temperature: float = 0.2,
    # I-deepfix-001 B17 (#1361): injectable entailment judge for the per-dropped-marker prune confirm
    # (``(claim, span) -> (verdict, reason)``). None (default) => the production ``_EntailmentJudge`` is
    # lazily built per prune; a test injects a deterministic fake.
    marker_prune_judge: "Any | None" = None,
) -> tuple[list[SentenceVerification], list[SentenceVerification], RepairTelemetry]:
    """Repair-loop orchestrator: walk the dropped list in order, attempt
    repair on the first MAX_PER_SECTION repairable items, return
    augmented (kept, dropped) lists + telemetry.

    Per Codex iter-1 brief P0 #2: recovered sentences MOVE from dropped
    to kept (no double-count). Failed-repair sentences STAY in dropped.

    Per Codex iter-1 brief P0 #3: deterministic order (input list
    order). MAX_PER_SECTION cap applies to ATTEMPT count, not failure
    count, so a section with 30 drops and cap 10 attempts the first 10
    repairable drops in order.

    PT12 safety filter (added after I-bug-108 first-run abort): only
    attempt repair on dropped sentences whose evidence_ids are ALL
    already cited by some pre-repair kept sentence. Otherwise the
    recovered sentence can introduce evidence_ids that the post-section
    bibliography builder won't include, causing PT12
    rule_pt12_invalid_citation_marker to fire downstream.
    """
    tel = RepairTelemetry()

    if not _repair_loop_enabled():
        return list(kept), list(dropped), tel

    cap = _max_per_section()
    new_kept = list(kept)
    final_dropped: list[SentenceVerification] = []
    attempted = 0

    # PT12 safety: build set of evidence_ids cited by the original
    # kept sentences. Repaired sentences must reference only these.
    kept_ev_ids: set[str] = set()
    for sv in kept:
        for tok in sv.tokens:
            kept_ev_ids.add(tok.evidence_id)

    # Codex iter-1 P0: original-order iteration
    for sv in dropped:
        if attempted >= cap or not is_repairable(sv.failure_reasons):
            final_dropped.append(sv)
            continue
        # PT12 safety: skip if dropped sentence cites evidence the
        # original kept set doesn't reference.
        sv_ev_ids = {tok.evidence_id for tok in sv.tokens}
        if not sv_ev_ids.issubset(kept_ev_ids):
            final_dropped.append(sv)
            continue

        attempted += 1
        tel.attempts += 1

        original_tokens = _extract_token_signature(sv.sentence)
        if not original_tokens:
            # No tokens to preserve → cannot meaningfully repair
            final_dropped.append(sv)
            continue

        outcome, repaired_text, in_tok, out_tok = await repair_sentence(
            dropped=sv,
            evidence_pool=evidence_pool,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        tel.input_tokens += in_tok
        tel.output_tokens += out_tok

        # Iter-2 P1 fix per Codex review: explicit outcome classification
        # instead of inferring API failure vs NULL_DROP from token counts.
        if outcome == "api_failure":
            tel.api_failures += 1
            final_dropped.append(sv)
            continue
        if outcome == "null_drop":
            tel.null_drops += 1
            final_dropped.append(sv)
            continue
        # outcome == "text": fall through to token-set preservation check
        if repaired_text is None:
            # Defensive: should not happen given outcome="text" but keep dropped
            final_dropped.append(sv)
            continue

        # Token-set preservation check (Codex iter-1 P0 #1)
        repaired_tokens = _extract_token_signature(repaired_text)
        if _marker_prune_enabled():
            # I-deepfix-001 B17 (#1361): accept a non-empty SUBSET (a confirmed marker PRUNE), reject
            # an ADDITION (a marker not in the original) or an EMPTY set. A marker may only be dropped
            # when the entailment judge CONFIRMS its span does not support the claim (NEUTRAL /
            # CONTRADICTED); a judge_error / ENTAILED / judge-unavailable fail-CLOSES to KEEP the
            # marker (=> the prune is rejected as a token_set_violation), so the model can never prune a
            # genuinely-supporting span to dodge repair. STRENGTHENS faithfulness; never relaxes it.
            orig_set = set(original_tokens)
            repaired_set = set(repaired_tokens)
            added = repaired_set - orig_set
            dropped_markers = orig_set - repaired_set
            if added or not repaired_set:
                # ADDED a marker OR emptied the set — a real violation (never an honest prune).
                tel.token_set_violations += 1
                logger.warning(
                    "[sentence_repair] repaired output ADDED markers or emptied the set "
                    "(orig=%s, repaired=%s) — keeping original drop", original_tokens, repaired_tokens,
                )
                final_dropped.append(sv)
                continue
            if dropped_markers:
                # Confirm EACH dropped marker's span genuinely does not support the repaired claim.
                _orig_tok_by_raw = {t.raw: t for t in parse_provenance_tokens(sv.sentence)}
                # The claim text with provenance tokens stripped (the entailment judge tests the bare
                # claim against the dropped span). Reuses the SAME cleaner the verifier uses.
                from src.polaris_graph.generator.provenance_generator import _verifier_cleaned_text
                _claim_for_confirm = _verifier_cleaned_text(repaired_text)
                _all_confirmed = True
                for _raw in dropped_markers:
                    _tok = _orig_tok_by_raw.get(_raw)
                    _span = _span_text_for_token(_tok, evidence_pool) if _tok is not None else ""
                    if not _confirm_marker_droppable(
                        _claim_for_confirm, _span, judge=marker_prune_judge
                    ):
                        _all_confirmed = False
                        break
                if not _all_confirmed:
                    # A dropped marker could NOT be confirmed unsupported (or the judge fail-closed) —
                    # reject the prune (treat as a token-set violation), keep the original drop.
                    tel.token_set_violations += 1
                    logger.warning(
                        "[sentence_repair] marker prune NOT confirmed unsupported (orig=%s, "
                        "repaired=%s) — keeping original drop", original_tokens, repaired_tokens,
                    )
                    final_dropped.append(sv)
                    continue
                tel.markers_pruned += len(dropped_markers)
                logger.info(
                    "[sentence_repair] B17 confirmed-pruned %d non-supporting marker(s) "
                    "(orig=%s, repaired=%s)", len(dropped_markers), original_tokens, repaired_tokens,
                )
        elif repaired_tokens != original_tokens:
            tel.token_set_violations += 1
            logger.warning(
                "[sentence_repair] repaired output changed token set "
                "(orig=%s, repaired=%s) — keeping original drop",
                original_tokens, repaired_tokens,
            )
            final_dropped.append(sv)
            continue

        # Re-run the FULL verification chain (mechanical checks +
        # entailment if env-enabled). Codex iter-1 P0: yes.
        re_verify = verify_sentence_provenance(
            repaired_text, evidence_pool,
        )
        if re_verify.is_verified:
            tel.successes += 1
            new_kept.append(re_verify)
            # Recovered: do NOT add to final_dropped
        else:
            tel.re_verify_failures += 1
            final_dropped.append(sv)

    return new_kept, final_dropped, tel
