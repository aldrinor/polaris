#!/usr/bin/env python3
"""Repoint the card-audit judge transport from `claude -p --model opus` to OpenRouter glm-5.2.

WHY THIS EXISTS
    `card_audit.harness` was built for a `claude -p --model opus --effort max` transport
    (`subprocess_opus_runner`), which would take ~12-24h for 5,759 cards. The operator wants the
    SAME audit — same prompts, same dimensions, same disposition logic — pointed at the fast
    OpenRouter glm-5.2 model the miner already uses, run in parallel with the compose job.

WHAT IS SWAPPED (only the transport, never the judgement):
  1. THE SEMANTIC RUNNER. `make_glm_runner()` returns a callable(prompt, schema) -> envelope that
     mirrors the `claude -p --output-format json` envelope harness expects (keys: result, modelUsage,
     model, is_error, total_cost_usd). It reuses `OpenRouterClient(model='z-ai/glm-5.2')` exactly as
     `evidence_miner.llm()` / `cellcog_composer.llm()` do, with a LARGE max_tokens (default 18000) so
     the reasoning-first model does not truncate its verdict mid-plan (the I-bug-089 lesson).

  2. THE "PROVE IT WAS OPUS" GATE. `harness.model_is_opus` (and the combine step that reads
     `model_verified`) exists to reject a cheaper model masquerading as opus. We are INTENTIONALLY
     using glm-5.2, so `install_glm_model_gate()` monkeypatches `harness.model_is_opus` to instead
     prove the response came from the INTENDED judge model (glm-5.2) and was not silently downgraded
     to some OTHER model. It is a relaxation of the opus-specific check, not a removal of the
     "no silent downgrade" invariant.

  3. THE ENTAILMENT (faithfulness) JUDGE. `report_ast.entailed_by_span` is authoritative and is NOT
     edited. Its default judge (`report_ast._llm_entailment_judge`) already calls the glm-5.2 model
     via `cellcog_composer.llm(prompt, max_tokens=300)` with the exact strict-entailment prompt — but
     300 tokens truncates a reasoning-first model before it can answer, which would fail EVERY card
     closed (a systemic false-negative). `install_glm_entailment_judge()` floors that token budget to
     a large value (I-bug-089) WITHOUT touching the prompt, then wraps the judge in the error-sentinel
     guard (`judge_guard.install_guarded_judge`). Prompt and semantics are untouched; only the token
     budget and model-proof are.

Nothing here hardcodes a subject/DOI/venue — it is a pure transport shim.
"""
from __future__ import annotations

import asyncio
import json
import threading

JUDGE_MODEL = 'z-ai/glm-5.2'
# LARGE max_tokens so the reasoning-first judge does not truncate its structured verdict (I-bug-089).
SEMANTIC_MAX_TOKENS = 18000
# The entailment (faithfulness) judge asks for a tiny JSON, but glm-5.2 emits a reasoning prelude
# first; a 300-token budget starves it. Floor it well above the reasoning prelude.
ENTAILMENT_MIN_TOKENS = 16000


# =================================================================================================
# 1. The semantic runner — a claude-p-shaped envelope produced by an OpenRouter glm-5.2 call
# =================================================================================================
def _glm_generate(prompt: str, *, model: str, max_tokens: int, timeout_s: float):
    """One synchronous glm-5.2 call. Mirrors evidence_miner.llm(): a fresh OpenRouterClient in its own
    event loop (thread-safe — each ThreadPoolExecutor worker owns its loop). Returns the LLMResponse."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    async def _run():
        c = OpenRouterClient(model=model)
        try:
            return await c.generate(prompt=prompt, max_tokens=max_tokens, temperature=0.0,
                                    timeout=timeout_s)
        finally:
            cl = getattr(c, 'close', None)
            if cl:
                try:
                    res = cl()
                    if hasattr(res, '__await__'):
                        await res
                except Exception:
                    pass

    return asyncio.run(_run())


def make_glm_runner(*, model: str = JUDGE_MODEL, max_tokens: int = SEMANTIC_MAX_TOKENS,
                    timeout_s: float = 600.0, max_retries: int = 3):
    """Build the injectable OpusRunner replacement. Signature/return shape match
    `harness.subprocess_opus_runner`: callable(prompt, schema) -> the parsed `claude -p` JSON envelope
    (result / modelUsage / model / is_error / total_cost_usd). `schema` is accepted for signature
    compatibility (harness also embeds the schema in the prompt text); glm has no server-side
    json-schema mode here, so we rely on the prompt's schema instruction + harness's own validator."""

    def runner(prompt: str, schema: dict) -> dict:
        last_err = ''
        for _attempt in range(max(1, max_retries)):
            try:
                r = _glm_generate(prompt, model=model, max_tokens=max_tokens, timeout_s=timeout_s)
            except Exception as e:  # noqa: BLE001 — a transport fault retries the SAME model, then fails closed
                last_err = f'{type(e).__name__}: {e}'
                continue
            content = getattr(r, 'content', None)
            if content is None and isinstance(r, dict):
                content = r.get('content')
            content = content if isinstance(content, str) else (str(r) if r is not None else '')
            if not content.strip():
                last_err = 'empty content from glm (possible truncation)'
                continue
            model_name = getattr(r, 'model', '') or model
            out_tok = int(getattr(r, 'output_tokens', 0) or 0) + int(getattr(r, 'reasoning_tokens', 0) or 0)
            in_tok = int(getattr(r, 'input_tokens', 0) or 0)
            # Envelope shaped like `claude -p --output-format json`, with modelUsage keyed by the model
            # id actually billed so the (patched) model gate can prove the intended judge answered.
            return {
                'result': content,
                'model': model_name,
                'modelUsage': {model_name: {'outputTokens': out_tok, 'inputTokens': in_tok}},
                'is_error': False,
                'total_cost_usd': 0.0,  # OpenRouterClient tracks cost in its own ledger; not needed here
            }
        # Fail closed exactly like the opus transport: raise OpusUnavailable so the caller quarantines.
        from card_audit import harness
        raise harness.OpusUnavailable(f'glm transport failed after {max_retries} retries: {last_err}')

    return runner


# =================================================================================================
# 2. The model-proof gate — prove it was glm-5.2 (the intended judge), not a silent downgrade
# =================================================================================================
def install_glm_model_gate(model: str = JUDGE_MODEL) -> None:
    """Monkeypatch `harness.model_is_opus` so the audit accepts the INTENDED glm-5.2 judge instead of
    demanding opus. Still fail-closed against a silent downgrade: the substantive answer's dominant
    output-token model must be the intended judge family, and must not be some OTHER cheap model."""
    from card_audit import harness

    family = model.split('/')[0].lower() if '/' in model else model.lower()
    short = model.split('/')[-1].lower()  # e.g. 'glm-5.2'

    def model_is_intended_judge(result: dict) -> bool:
        usage = result.get('modelUsage') or {}
        hay = ' '.join(list(usage.keys()) + [str(result.get('model') or '')]).lower()
        # The intended judge must appear somewhere in the billed models / primary model.
        if short not in hay and family not in hay and model.lower() not in hay:
            return False

        def _out(v):
            return (v.get('outputTokens') or v.get('output_tokens') or 0) if isinstance(v, dict) else 0

        outs = {k.lower(): _out(v) for k, v in usage.items()}
        if outs and any(outs.values()):
            dominant = max(outs, key=lambda k: outs[k])
            return short in dominant or family in dominant or model.lower() in dominant
        primary = str(result.get('model') or '').lower()
        return short in primary or family in primary or model.lower() in primary

    harness.model_is_opus = model_is_intended_judge  # type: ignore[assignment]


# =================================================================================================
# 3. The entailment (faithfulness) judge — same prompt, glm-5.2, LARGE token budget, guarded
# =================================================================================================
_orig_cellcog_llm = None
_llm_patch_lock = threading.Lock()


def install_glm_entailment_judge(min_tokens: int = ENTAILMENT_MIN_TOKENS) -> None:
    """Keep `report_ast._llm_entailment_judge` and its verbatim strict-entailment PROMPT, but ensure
    its glm-5.2 transport (`cellcog_composer.llm`) gets a LARGE token budget so the reasoning-first
    model does not truncate before emitting its JSON verdict (I-bug-089). Then wrap the judge in the
    error-sentinel guard so an ENTAILED-with-error reply is downgraded to UNCERTAIN (fail closed).

    We do NOT edit report_ast.py or cellcog_composer.py on disk — this floors the token budget by
    wrapping `cellcog_composer.llm` in-process only."""
    global _orig_cellcog_llm
    import cellcog_composer as CC
    from card_audit import judge_guard

    with _llm_patch_lock:
        if _orig_cellcog_llm is None:
            _orig_cellcog_llm = CC.llm

            def llm_large_tokens(prompt: str, max_tokens: int = 8192) -> str:
                return _orig_cellcog_llm(prompt, max_tokens=max(max_tokens, min_tokens))

            CC.llm = llm_large_tokens  # type: ignore[assignment]

    # Wrap whatever entailment judge is currently wired (default: _llm_entailment_judge) in the guard.
    judge_guard.install_guarded_judge()


def install_all() -> dict:
    """Install every glm-5.2 transport swap and return a small manifest for the run report."""
    install_glm_model_gate(JUDGE_MODEL)
    install_glm_entailment_judge(ENTAILMENT_MIN_TOKENS)
    return {
        'judge_model': JUDGE_MODEL,
        'semantic_max_tokens': SEMANTIC_MAX_TOKENS,
        'entailment_min_tokens': ENTAILMENT_MIN_TOKENS,
        'model_gate': 'harness.model_is_opus -> prove intended glm-5.2 (no silent downgrade)',
        'entailment_judge': 'report_ast default judge (prompt intact) + large token floor + error-sentinel guard',
    }
