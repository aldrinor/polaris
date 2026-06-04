"""I-cap-002 feature 4/4 (#1060): NLI entailment as an ADDITIVE, advisory benchmark annotation.

strict_verify is regex/numeric — it can pass a qualitative-negation hallucination ("drug X did NOT
reduce mortality") whose numbers/content-words still match the cited span. NLI is the **second validator
path**: for each delivered sentence it scores whether the CITED evidence span entails the sentence; a low
entailment prob is a hallucination the regex missed. This is ADVISORY only — it annotates the manifest, it
never changes ``release_allowed``/``status`` (the 4-role D8 seam remains the single binding gate).

**No silent degrade (LAW II + operator no-downgrade directive):** ``annotate_nli_entailment`` raises
``NliUnavailableError`` when the model/deps cannot load — it NEVER returns an empty "clean" result that
reads as "NLI verified". The caller records ``nli_status:"unavailable"`` LOUDLY in the manifest. (This is
the deliberate difference from ``nli_verifier.verify_evidence_nli``, which returns ``[]`` on a missing model.)

Heavy deps (``torch`` / ``transformers`` / ``minicheck``) are imported LAZILY inside the async function, so
importing this module pulls nothing heavy; offline tests mock the scorer (no torch). The live model runs on
the VM (CLAUDE.md §8.4).
"""

from __future__ import annotations

import os
import re
from typing import Any

from src.polaris_graph.clinical_generator.provenance import strip_tokens

# Codex diff-gate iter-1 P2.1: the benchmark's provenance offsets index into the row's
# ``direct_quote`` / ``statement`` (the field strict_verify validates against), so those MUST be tried
# FIRST — slicing ``full_text`` for a row that carries both would pick the wrong byte range.
_SPAN_TEXT_FIELDS = ("direct_quote", "statement", "full_text", "snippet", "text", "source_text")

# Codex diff-gate iter-1 P2.3: strip_tokens removes only ``[#ev:...]``; a pre-resolve sentence can still
# carry ``[#calc:model:hash:field]`` calc tokens and ``(atom_NNN)`` markers that are cleaned from the
# final delivered prose elsewhere. Strip those too, or they create advisory false NLI disputes.
_RESIDUAL_ARTIFACT_RE = re.compile(r"\[#calc:[^\]]*\]|\(?\batom_\d+\b\)?")


class NliUnavailableError(RuntimeError):
    """The NLI model/deps could not be loaded. Raised (never silently swallowed) so the caller can
    surface ``nli_status:"unavailable"`` rather than report a false clean pass."""


def _resolve_span_text(row: dict[str, Any], start: int, end: int) -> str:
    """Slice the cited [start:end] span out of an evidence row's text (get_span_text semantics)."""
    text = ""
    for field in _SPAN_TEXT_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value:
            text = value
            break
    if not text or start < 0 or end > len(text) or start > end:
        return ""
    return text[start:end]


def build_nli_pairs(
    kept_sentences: list[dict[str, Any]],
    ev_pool: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build ``[{sentence, span, section, evidence_id}]`` NLI pairs from delivered kept sentences.

    Per Codex brief-gate P2: (1) the sentence is CLEANED of ``[#ev:...]`` / atom artifacts via
    ``strip_tokens`` so citation tokens don't create false NLI disputes; (2) ALL cited spans of the
    sentence are concatenated as the premise (not first-token-only), so a sentence grounded by multiple
    spans is not over-disputed. A sentence with no cleanable text or no resolvable span is skipped.

    ``kept_sentences``: ``[{"sentence": str, "tokens": [{"evidence_id","start","end"}], "section": str}]``.
    Pure (no model, no network).
    """
    pairs: list[dict[str, Any]] = []
    for ks in kept_sentences or []:
        raw = ks.get("sentence") or ""
        # P2.1: drop [#ev:...] tokens; P2.3: also drop [#calc:...] + (atom_NNN) residuals; collapse ws.
        claim = _RESIDUAL_ARTIFACT_RE.sub(" ", strip_tokens(raw))
        claim = re.sub(r"\s+", " ", claim).strip()
        if not claim:
            continue
        spans: list[str] = []
        first_ev_id = ""
        for tok in ks.get("tokens", []) or []:
            ev_id = tok.get("evidence_id") or ""
            row = ev_pool.get(ev_id)
            if not isinstance(row, dict):
                continue
            span = _resolve_span_text(row, int(tok.get("start", -1)), int(tok.get("end", -1)))
            if span:
                spans.append(span)
                if not first_ev_id:
                    first_ev_id = ev_id
        premise = " ".join(spans).strip()
        if not premise:
            continue  # no resolvable cited span -> nothing to entail against; skip
        pairs.append({
            "sentence": claim,
            "span": premise,
            "section": ks.get("section", ""),
            "evidence_id": first_ev_id,
        })
    return pairs


async def annotate_nli_entailment(
    pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score each (span ⊨ sentence) pair with the frontier LLM entailment judge; ADVISORY annotation.

    I-cap-003 (#1066): the scoring backend is now the project's LLM entailment judge
    (``src.polaris_graph.llm.entailment_judge``) — a frontier OPEN-weight model (default
    ``google/gemma-4-31b-it``) via OpenRouter, family-segregated from the generator, already used by
    strict_verify. This REPLACES the old flan-t5/minicheck path (an old/weak F1-62.1 encoder that was
    git-only and unavailable on the CPU VM → the previous ``nli_status:unavailable`` bug).

    Each pair yields a verdict ``ENTAILED | NEUTRAL | CONTRADICTED``. ``disputed`` = NEUTRAL ∪
    CONTRADICTED (strict_verify's contract is "no unsupported additions"; the per-sentence ``verdict``
    distinguishes them). Returns ``{nli_status:"ok", judge, model, sentences_checked, entailed_count,
    neutral_count, contradicted_count, disputed_count, disputed:[…], advisory:True}``.

    FAIL-LOUD only on a genuine config error: a missing ``OPENROUTER_API_KEY`` raises
    ``NliUnavailableError`` (surfaced as ``nli_status:"unavailable"``, never a silent pass). The judge is
    called SYNCHRONOUSLY (NOT offloaded to a thread) so its per-call cost accumulates in the run's
    ``_RUN_COST_CTX`` ContextVar and ``BudgetExceededError`` (re-raised inside ``judge.judge``) propagates
    out to abort the run on a cap breach. A family-segregation error from ``_get_judge()`` PROPAGATES
    (not masked as "unavailable").
    """
    if not pairs:                                   # fast path — needs no API key / no judge
        return {
            "nli_status": "ok", "judge": "llm_entailment", "sentences_checked": 0,
            "sentences_scored": 0, "entailed_count": 0, "neutral_count": 0, "contradicted_count": 0,
            "disputed_count": 0, "disputed": [], "judge_error_count": 0, "judge_errors": [],
            "advisory": True,
        }

    # Fail-loud on a genuine config error BEFORE constructing the judge (the judge __init__ raises a
    # RuntimeError for a missing key that is indistinguishable from a family-collision RuntimeError —
    # check the key here so only the real missing-key case maps to NliUnavailableError).
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        raise NliUnavailableError(
            "OPENROUTER_API_KEY missing — the NLI entailment judge cannot run"
        )

    from src.polaris_graph.llm.entailment_judge import _get_judge

    judge = _get_judge()   # family-segregation RuntimeError propagates (NOT masked as unavailable)
    entailed = neutral = contradicted = judge_errors = 0
    disputed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for pair in pairs:
        # SYNC call (no asyncio.to_thread): keeps _RUN_COST_CTX in-context so judge spend counts against
        # PG_MAX_COST_PER_RUN and BudgetExceededError propagates. Runs post-generation (last step), so
        # blocking the loop for N sequential entailment calls is fine.
        verdict, reason = judge.judge(pair["sentence"], pair["span"])
        # I-cap-005 (#1068): the judge FAILS OPEN to ("ENTAILED", "judge_error: ...") on an API/parse
        # error to keep the run alive. Counting that as a genuine ENTAILED would silently report a
        # DEGRADED judge as "NLI clean" — a silent downgrade (LAW II / operator no-downgrade directive).
        # Detect it, count it as an ERROR (NOT entailed), and surface it loudly in the annotation.
        if isinstance(reason, str) and reason.startswith("judge_error:"):
            judge_errors += 1
            errors.append({
                "section": pair.get("section", ""),
                "evidence_id": pair.get("evidence_id", ""),
                "reason": reason,
                "sentence": pair["sentence"],
            })
            continue
        if verdict == "ENTAILED":
            entailed += 1
            continue
        if verdict == "CONTRADICTED":
            contradicted += 1
        else:
            verdict = "NEUTRAL"   # normalize any unexpected verdict to NEUTRAL (still disputed)
            neutral += 1
        disputed.append({
            "section": pair.get("section", ""),
            "evidence_id": pair.get("evidence_id", ""),
            "verdict": verdict,
            "reason": reason,
            "sentence": pair["sentence"],
        })
    scored = len(pairs) - judge_errors
    # If EVERY call errored, nothing was actually entailment-checked — surface nli_status:"error" LOUDLY
    # (not "ok" with a misleading zero-dispute count). Partial errors keep "ok" but expose the count so
    # an audit sees the degradation. Errored sentences are excluded from entailed/neutral/contradicted.
    nli_status = "error" if (pairs and scored == 0) else "ok"
    return {
        "nli_status": nli_status,
        "judge": "llm_entailment",
        "model": judge._model,
        "sentences_checked": len(pairs),
        "sentences_scored": scored,
        "entailed_count": entailed,
        "neutral_count": neutral,
        "contradicted_count": contradicted,
        "disputed_count": len(disputed),
        "disputed": disputed,
        "judge_error_count": judge_errors,
        "judge_errors": errors,
        "advisory": True,
    }
