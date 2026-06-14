#!/usr/bin/env python3
"""I-arch-003 (#1253): Mirror (z-ai/glm-5.1) provider bake-off.

WHY: the OpenRouter endpoints read (2026-06-14) showed the Mirror's pinned provider
DeepInfra is fp4 + max_out=32768 — violating the operator's "fp8 better quality" AND
"max max tokens" directives. We must re-pin to a fp8 HIGH-CAP provider that is ALSO
blank-clean (the GLM empty-content-200 defect that demoted Parasail/SiliconFlow).

This tests each fp8 candidate with the EXACT Mirror transport request shape
(reasoning.max_tokens cap + generous total max_tokens + provider pin +
require_parameters) and a real claim-vs-evidence verdict prompt, measuring blank
rate, finish_reason, latency, and the provider actually served. EMPIRICAL, not guessed.

Run: python scripts/diagnostics/mirror_glm_provider_bakeoff.py
"""
import json
import os
import time
import urllib.request

MODEL = "z-ai/glm-5.1"
# fp8, max_out >= 131072, NOT in the Mirror blank-ignore list. AtlasCloud advertises
# the highest fp8 output (202752); Z.AI is first-party; Baidu/Novita/GMICloud back them.
CANDIDATES = ["atlas-cloud", "z-ai", "baidu", "novita", "gmicloud"]
PROVIDER_ALIAS = {
    "atlas-cloud": "AtlasCloud",
    "z-ai": "Z.AI",
    "baidu": "Baidu",
    "novita": "Novita",
    "gmicloud": "GMICloud",
}
REASONING_CAP = int(os.getenv("PG_MIRROR_REASONING_MAX_TOKENS", "100000"))
MAX_TOKENS = int(os.getenv("PG_MIRROR_MAX_TOKENS", "131072"))
CALLS_PER = 3

EVIDENCE = (
    "In the SURMOUNT-1 trial, tirzepatide 15 mg produced a mean weight reduction of "
    "20.9% from baseline at week 72 versus 3.1% with placebo (p<0.001)."
)
CLAIM = "Tirzepatide 15 mg reduced body weight by about 21% at 72 weeks in SURMOUNT-1."
PROMPT = (
    "You are a strict claim-vs-evidence verifier. Decide whether the EVIDENCE entails "
    "the CLAIM. Return ONLY a JSON object: {\"verdict\": \"SUPPORTED|UNSUPPORTED\", "
    "\"reason\": \"<one sentence>\"}.\n\n"
    f"EVIDENCE: {EVIDENCE}\n\nCLAIM: {CLAIM}\n"
)


def _key():
    for line in open(".env", encoding="utf-8", errors="ignore"):
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.getenv("OPENROUTER_API_KEY")


def call(key, provider_slug):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "reasoning": {"max_tokens": REASONING_CAP},
        "max_tokens": MAX_TOKENS,
        "provider": {
            "order": [PROVIDER_ALIAS[provider_slug]],
            "allow_fallbacks": False,
            "require_parameters": True,
        },
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        d = json.load(urllib.request.urlopen(req, timeout=300))
    except Exception as e:
        return {"err": str(e)[:160], "dt": round(time.time() - t0, 1)}
    dt = round(time.time() - t0, 1)
    ch = (d.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    content = (msg.get("content") or "").strip()
    reasoning = (msg.get("reasoning") or "")
    usage = d.get("usage") or {}
    return {
        "dt": dt,
        "served": d.get("provider"),
        "finish": ch.get("finish_reason"),
        "content_len": len(content),
        "blank": len(content) == 0,
        "reasoning_len": len(reasoning),
        "completion_tokens": usage.get("completion_tokens"),
        "content_head": content[:80],
    }


def main():
    key = _key()
    if not key:
        raise SystemExit("no OPENROUTER_API_KEY")
    print(f"model={MODEL} reasoning_cap={REASONING_CAP} max_tokens={MAX_TOKENS} calls={CALLS_PER}/provider\n")
    summary = {}
    for prov in CANDIDATES:
        print(f"=== {prov} ({PROVIDER_ALIAS[prov]}) ===")
        blanks = oks = errs = 0
        for i in range(CALLS_PER):
            r = call(key, prov)
            if r.get("err"):
                errs += 1
                print(f"  call{i+1} ({r['dt']}s): ERR {r['err']}")
            elif r["blank"]:
                blanks += 1
                print(f"  call{i+1} ({r['dt']}s): BLANK finish={r['finish']} reasoning_len={r['reasoning_len']} served={r['served']}")
            else:
                oks += 1
                print(f"  call{i+1} ({r['dt']}s): OK finish={r['finish']} content_len={r['content_len']} served={r['served']} :: {r['content_head']!r}")
        summary[prov] = {"ok": oks, "blank": blanks, "err": errs}
        print()
    print("=== SUMMARY (clean = ok=3, blank=0, err=0) ===")
    for prov, s in summary.items():
        verdict = "CLEAN" if s["ok"] == CALLS_PER else "REJECT"
        print(f"  {prov:<14} ok={s['ok']} blank={s['blank']} err={s['err']}  -> {verdict}")


if __name__ == "__main__":
    main()
