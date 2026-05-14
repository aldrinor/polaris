"""I-sov-001 G2 — dual-backend response-shape test.

Sends an identical chat-completion request to:
  1. real OpenRouter (US, current transitional backend)
  2. a self-hosted OpenAI-compatible endpoint (Ollama qwen2.5:7b — stands in
     for the OVH H200 vLLM endpoint; vLLM and Ollama both implement the
     plain OpenAI /v1/chat/completions contract)

Then runs BOTH raw responses through POLARIS's actual parsers:
  - generator2/real_completion.py::_extract_text
  - llm/openrouter_client.py response handling (via a focused replica of
    its _call() parse path)

Goal: prove whether POLARIS's OpenRouter-shaped parsing assumptions break
on a plain-OpenAI self-hosted response. Codex G2 flagged this as a P0.

Run:  set -a && source .env && set +a && python .codex/I-sov-001/dual_backend_test.py
"""

from __future__ import annotations

import json
import os
import sys

import httpx

sys.path.insert(0, "src")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SELFHOST_URL = "http://localhost:11434/v1/chat/completions"  # Ollama OpenAI-compat

# Identical request body to both backends.
MESSAGES = [
    {"role": "system", "content": "You are a precise assistant. Answer in one short sentence."},
    {"role": "user", "content": "What is the capital of Canada?"},
]


def call_backend(url: str, model: str, api_key: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        # OpenRouter-recommended routing headers (vLLM/Ollama ignore these):
        headers["HTTP-Referer"] = "https://polaris-canada.local"
        headers["X-Title"] = "POLARIS I-sov-001 dual-backend test"
    body = {
        "model": model,
        "messages": MESSAGES,
        "temperature": 0.2,
        "max_tokens": 100,
    }
    with httpx.Client(timeout=120.0) as c:
        r = c.post(url, json=body, headers=headers)
        r.raise_for_status()
        return r.json()


def shape_report(label: str, data: dict) -> None:
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    print("top-level keys:", sorted(data.keys()))
    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        print("choices[0] keys:", sorted(choices[0].keys()))
        print("message keys:", sorted(msg.keys()))
        print("message.content type:", type(msg.get("content")).__name__)
        print("message.content value:", repr(msg.get("content"))[:200])
        print("message.reasoning present:", "reasoning" in msg)
    usage = data.get("usage") or {}
    print("usage keys:", sorted(usage.keys()))
    print("usage.cost present:", "cost" in usage)
    # OpenRouter-specific top-level fields:
    for f in ("provider", "id", "model", "system_fingerprint"):
        if f in data:
            print(f"  has '{f}': {data[f]!r}"[:120])


def run_polaris_parsers(label: str, data: dict) -> None:
    print(f"\n--- POLARIS parsers vs {label} ---")
    # Parser 1: generator2/real_completion._extract_text
    try:
        from polaris_graph.generator2.real_completion import _extract_text
        text = _extract_text(data)
        print(f"  _extract_text  -> OK ({len(text)} chars): {text[:80]!r}")
    except Exception as e:
        print(f"  _extract_text  -> FAIL: {type(e).__name__}: {e}")

    # Parser 2: openrouter_client content+reasoning extraction.
    # Replicate the parse path _call() uses without constructing the full client.
    try:
        choices = data.get("choices") or []
        msg = choices[0].get("message") or {} if choices else {}
        content = msg.get("content")
        reasoning = msg.get("reasoning")
        usage = data.get("usage") or {}
        input_tok = int(usage.get("prompt_tokens", 0) or 0)
        output_tok = int(usage.get("completion_tokens", 0) or 0)
        api_cost = float(usage.get("cost", 0) or 0)
        ok_content = isinstance(content, str) and bool(content.strip())
        print(
            f"  openrouter_client path -> content_ok={ok_content} "
            f"reasoning_present={reasoning is not None} "
            f"input_tok={input_tok} output_tok={output_tok} "
            f"api_cost={api_cost} (cost imputed from tokens if 0)"
        )
    except Exception as e:
        print(f"  openrouter_client path -> FAIL: {type(e).__name__}: {e}")


def main() -> int:
    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not or_key:
        print("FATAL: OPENROUTER_API_KEY not in env. Run: set -a && source .env && set +a")
        return 1

    # OpenRouter model: use the cheap fast one for a shape test.
    or_model = os.environ.get("OPENROUTER_DEFAULT_MODEL", "qwen/qwen-2.5-7b-instruct")
    selfhost_model = "qwen2.5:7b"  # Ollama local

    results: dict[str, dict] = {}

    print("Calling OpenRouter (real, US)...")
    try:
        results["openrouter"] = call_backend(OPENROUTER_URL, or_model, or_key)
        print("  OK")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

    print("Calling self-hosted OpenAI-compat endpoint (Ollama, vLLM-equivalent)...")
    try:
        results["selfhost"] = call_backend(SELFHOST_URL, selfhost_model, None)
        print("  OK")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

    for label, data in results.items():
        shape_report(label.upper(), data)
        run_polaris_parsers(label.upper(), data)

    # Persist raw responses for the brief.
    out = ".codex/I-sov-001/dual_backend_raw_responses.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw responses saved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
