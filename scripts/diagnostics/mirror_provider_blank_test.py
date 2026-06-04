#!/usr/bin/env python3
"""I-run11-005 root-cause confirm: is the Mirror blank an OpenRouter PROVIDER-routing issue, not the
model? GLM-5.1 has 19 providers (2 degraded: Phala status -5/49% uptime, Together -2/83%). Our
transport does NOT restrict the provider, so a Mirror call can land on a flaky one that returns empty
content (finish_reason:error, 0 tokens) -> BlankVerdictError. This forces GLM onto specific providers
(allow_fallbacks=false) on the SAME hard claim + realistic payload + reasoning ON, and reports which
return empty. If the degraded providers blank and the healthy ones don't, provider routing is the
cause and the fix is provider preferences (exclude flaky / fallback-on-empty), NOT a model swap.

Reads OPENROUTER_API_KEY from .env (never printed). Run from repo root. ~6 live calls.
"""
from __future__ import annotations
import json, os, sys, urllib.request, urllib.error

key = os.getenv("OPENROUTER_API_KEY")
if not key:
    for line in open(".env", encoding="utf-8"):
        if line.startswith("OPENROUTER_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'"); break

e = json.load(open("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json", encoding="utf-8"))
docs = [(x["evidence_id"], x["direct_quote"]) for x in e
        if len(x.get("direct_quote") or "") > 200 and x.get("evidence_id")][:5]
DOC_BLOCK = "\n\n".join(f"[doc {i}: {d}]\n{q[:2000]}" for i, (d, q) in enumerate(docs))
CLAIM = ("Across these studies automation displaced workers from routine tasks, depressed relative "
         "wages for the middle of the skill distribution, complemented high-skill labor, and netted "
         "out to no collapse in aggregate labor demand over the period studied.")
PROMPT = (f"Documents:\n{DOC_BLOCK}\n\nClaim:\n{CLAIM}\n\nQuote the exact supporting spans from the "
          "documents using <co>covered text</co:doc_id> citation tags, then judge the claim.")

# degraded providers first, then a healthy control set
PROVIDERS = ["Phala", "Together", "Chutes", "Fireworks", "Baidu", "DeepInfra"]


def call(provider: str) -> str:
    body = {
        "model": "z-ai/glm-5.1",
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 16384,
        "reasoning": {"enabled": True, "effort": "high"},
        "provider": {"order": [provider], "allow_fallbacks": False},
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=90).read())
    except urllib.error.HTTPError as ex:
        return f"HTTP {ex.code}: {ex.read()[:140].decode(errors='ignore')}"
    except Exception as ex:  # noqa: BLE001
        return f"{type(ex).__name__}: {str(ex)[:120]}"
    ch = (r.get("choices") or [{}])[0]
    msg = ch.get("message", {}) or {}
    content = (msg.get("content") or "")
    reasoning = (msg.get("reasoning") or "")
    served = (r.get("provider") or "?")
    fr = ch.get("finish_reason")
    err = r.get("error")
    return (f"served={served} content_len={len(content)} reasoning_len={len(reasoning)} "
            f"finish={fr} blank={len(content.strip()) == 0}" + (f" ERROR={err}" if err else ""))


def main():
    print("forcing GLM-5.1 onto each provider (allow_fallbacks=False), hard claim, reasoning ON\n",
          flush=True)
    for p in PROVIDERS:
        print(f"[{p:10}] {call(p)}", flush=True)


if __name__ == "__main__":
    main()
