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
    *,
    threshold: float = 0.25,
) -> dict[str, Any]:
    """Score each (span ⊨ sentence) pair with the NLI model; return an ADVISORY annotation dict.

    Raises ``NliUnavailableError`` if the model cannot load OR exposes neither ``.score`` (MiniCheck)
    nor ``.infer`` (FaithLens) — NEVER returns a silent empty pass. Returns
    ``{nli_status:"ok", model, sentences_checked, disputed_count, disputed:[…], min_prob, mean_prob,
    threshold, advisory:True}``.
    """
    # Lazy import: keeps torch/minicheck off the module-import path (offline tests mock this).
    from src.polaris_graph.agents.nli_verifier import PG_NLI_MODEL, load_nli_model

    if not pairs:
        return {
            "nli_status": "ok", "model": PG_NLI_MODEL, "sentences_checked": 0,
            "disputed_count": 0, "disputed": [], "min_prob": None, "mean_prob": None,
            "threshold": threshold, "advisory": True,
        }

    scorer = await load_nli_model()
    if scorer is None:
        raise NliUnavailableError(
            f"NLI model '{PG_NLI_MODEL}' unavailable (deps missing or load failed) — "
            f"refusing to report a silent clean pass"
        )

    docs = [p["span"] for p in pairs]
    claims = [p["sentence"] for p in pairs]

    # Codex brief-gate P2.3: MiniCheck exposes .score(); FaithLens exposes .infer(). Support both so an
    # otherwise-available model is not mislabeled nli_status:error.
    if hasattr(scorer, "score"):
        _labels, raw_probs, _chunks, _chunk_probs = scorer.score(docs=docs, claims=claims)
        probs = [float(p) for p in raw_probs]
    elif hasattr(scorer, "infer"):
        results = scorer.infer(docs=docs, claims=claims)
        probs = [1.0 if (r.get("prediction", 0) == 1) else 0.0 for r in results]
    else:
        raise NliUnavailableError(
            f"NLI scorer for '{PG_NLI_MODEL}' exposes neither .score nor .infer"
        )

    disputed = []
    for pair, prob in zip(pairs, probs):
        if prob < threshold:
            disputed.append({
                "section": pair.get("section", ""),
                "evidence_id": pair.get("evidence_id", ""),
                "prob": round(prob, 4),
                "sentence": pair["sentence"],
            })
    return {
        "nli_status": "ok",
        "model": PG_NLI_MODEL,
        "sentences_checked": len(pairs),
        "disputed_count": len(disputed),
        "disputed": disputed,
        "min_prob": round(min(probs), 4) if probs else None,
        "mean_prob": round(sum(probs) / len(probs), 4) if probs else None,
        "threshold": threshold,
        "advisory": True,
    }
