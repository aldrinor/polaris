"""Oracle Layer 2 (partial): wire the cassette around the async LLM boundary.

Monkeypatches ``OpenRouterClient.generate`` to route through a :class:`Cassette`:
  * ``mode="record"`` — call the real client and record ``(request -> response)``,
  * ``mode="replay"`` — serve the recorded response with NO network call.

Request identity = the deterministic call arguments (model + prompt + system + sampling knobs).
The stable ``call_id`` is an ordinal per identical request, assigned in call order. This is correct
for a **sequential** LLM decision loop (record and replay issue the same requests in the same order);
concurrent identical ``generate`` calls would need a context-derived id (a documented follow-up).

Only the behaviour-relevant, deterministic response fields are frozen (content, reasoning, token
counts, model, finish_reason). The non-deterministic fields are normalized on replay:
``duration_ms=0.0`` (timing), ``raw_response=None`` and ``trace_call_id=None`` (provider ids) — so a
refactor cannot "regress" merely because a timestamp or provider id differed.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

from tests.oracle.cassette import Cassette, _canonical

_counter: dict[str, int] = {}
_counter_lock = threading.Lock()


def _reset_counter() -> None:
    with _counter_lock:
        _counter.clear()


def _call_id(method: str, req: dict) -> str:
    base = _canonical(method, req)
    with _counter_lock:
        n = _counter.get(base, 0)
        _counter[base] = n + 1
    return str(n)


def _request(model: str, prompt: str, system: str, max_tokens: int, temperature: float,
             reasoning_max_tokens, reasoning_exclude, response_format) -> dict:
    return {
        "model": model, "prompt": prompt, "system": system,
        "max_tokens": max_tokens, "temperature": temperature,
        "reasoning_max_tokens": reasoning_max_tokens,
        "reasoning_exclude": reasoning_exclude,
        "response_format": response_format,
    }


def _response_to_dict(r) -> dict:
    return {
        "content": r.content,
        "reasoning": r.reasoning,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "reasoning_tokens": r.reasoning_tokens,
        "model": r.model,
        "finish_reason": r.finish_reason,
    }


def _dict_to_response(d: dict):
    from src.polaris_graph.llm.openrouter_client import LLMResponse
    return LLMResponse(
        content=d["content"], reasoning=d["reasoning"],
        input_tokens=d["input_tokens"], output_tokens=d["output_tokens"],
        reasoning_tokens=d["reasoning_tokens"], model=d["model"],
        duration_ms=0.0, raw_response=None, trace_call_id=None,  # normalized non-determinism
        finish_reason=d["finish_reason"],
    )


@contextlib.contextmanager
def llm_cassette(path: str | Path, mode: str):
    """Patch OpenRouterClient.generate to record/replay through a cassette for the block's duration."""
    from src.polaris_graph.llm import openrouter_client as oc

    cas = Cassette(path, mode)
    _reset_counter()
    original = oc.OpenRouterClient.generate

    async def _wrapped(self, prompt, system="", max_tokens=4096, temperature=0.7, timeout=None,
                       reasoning_max_tokens=None, reasoning_exclude=None, response_format=None):
        req = _request(self.model, prompt, system, max_tokens, temperature,
                       reasoning_max_tokens, reasoning_exclude, response_format)
        cid = _call_id("generate", req)
        if mode == "record":
            key, args_snap = cas.record_begin("generate", req, cid)  # reserve BEFORE the live await
            resp = await original(
                self, prompt, system=system, max_tokens=max_tokens, temperature=temperature,
                timeout=timeout, reasoning_max_tokens=reasoning_max_tokens,
                reasoning_exclude=reasoning_exclude, response_format=response_format,
            )
            cas.record_end(key, "generate", args_snap, cid, _response_to_dict(resp))
            return resp
        return _dict_to_response(cas.replay("generate", req, cid))

    oc.OpenRouterClient.generate = _wrapped
    try:
        yield cas
    finally:
        oc.OpenRouterClient.generate = original
        cas.finalize()
