#!/usr/bin/env python3
"""Mirror-reliability spot-check (I-run11-005): does a candidate Mirror model EMIT a non-blank
grounding verdict via OpenRouter, or blank like GLM-5.1? Fast offline test on ONE real (claim, span)
pair so we don't burn a 50-min full run to learn a model blanks. NO pipeline import — a raw
chat-completions call mirroring the Mirror pass-1 (grounded judgment, no forced reasoning).

Reads OPENROUTER_API_KEY from the env/.env (never printed). Run from repo root.
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error

KEY = os.getenv("OPENROUTER_API_KEY")
if not KEY:
    # minimal .env loader (key=value), no third-party dep
    try:
        for line in open(".env", encoding="utf-8"):
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    except Exception:
        pass
if not KEY:
    print("NO OPENROUTER_API_KEY"); sys.exit(2)

CLAIM = ("In the last few decades, one noticeable change has been a 'polarization' of the labor "
         "market, in which wage gains went disproportionately to those at the top and at the bottom "
         "of the income and skill distribution, not to those in the middle.")
SPAN = ("In this essay, I begin by identifying the reasons that automation has not wiped out a "
        "majority of jobs over the decades and centuries. Automation does indeed substitute for "
        "labor. However, automation also complements labor, raises output in ways that leads to "
        "higher demand for labor, and interacts with adjustments in labor supply.")
PROMPT = (f"SPAN of source text:\n{SPAN}\n\nCLAIM that cites ONLY that span:\n{CLAIM}\n\n"
          "In ONE short paragraph, judge whether every factual assertion in the CLAIM is supported "
          "by the SPAN alone, and state SUPPORTED or NOT SUPPORTED.")


def catalog_slugs():
    req = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                 headers={"Authorization": f"Bearer {KEY}"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]
    ids = {m["id"] for m in data}
    # pick the newest-looking candidate per distinct family (NOT deepseek/minimax/qwen)
    def pick(prefix, contains=()):
        cands = sorted([i for i in ids if i.startswith(prefix)
                        and all(c in i for c in contains)], reverse=True)
        return cands[:3]
    return {
        "glm(z-ai)": pick("z-ai/", ("glm",)),
        "mistral": pick("mistralai/"),
        "llama(meta)": pick("meta-llama/", ("llama",)),
        "kimi(moonshot)": pick("moonshotai/"),
    }


def call(model, reasoning_off=True):
    body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 2000}
    if not reasoning_off:
        body["reasoning"] = {"effort": "high"}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=180).read())
    except urllib.error.HTTPError as e:
        return {"err": f"HTTP {e.code}: {e.read()[:120].decode(errors='ignore')}", "dt": time.time()-t0}
    except Exception as e:
        return {"err": str(e)[:120], "dt": time.time()-t0}
    ch = (r.get("choices") or [{}])[0]
    msg = ch.get("message", {})
    content = (msg.get("content") or "")
    reasoning = (msg.get("reasoning") or "")
    return {"content_len": len(content), "reasoning_len": len(reasoning),
            "blank": len(content.strip()) == 0, "dt": round(time.time()-t0, 1),
            "head": content[:80].replace("\n", " ")}


def main():
    cands = catalog_slugs()
    print("=== candidate slugs from live OpenRouter catalog ===")
    for fam, slugs in cands.items():
        print(f"  {fam}: {slugs}")
    print("\n=== reliability test (reasoning OFF; blank=True means UNUSABLE as Mirror) ===")
    # Explicit STRONG open-weight candidates (distinct families) + the actual locked Mirror glm-5.1.
    avail = {s for slugs in cands.values() for s in slugs}
    explicit = [
        ("glm-5.1 (locked Mirror, reasoning-OFF)", "z-ai/glm-5.1"),
        ("mistral-small-3.2 (Apache-2)", "mistralai/mistral-small-3.2-24b-instruct"),
        ("magistral-medium (Mistral reasoning)", "mistralai/magistral-medium-2509"),
        ("llama-4-maverick (Meta)", "meta-llama/llama-4-maverick"),
        ("llama-4-scout (Meta)", "meta-llama/llama-4-scout"),
        ("kimi-k2.6 (Moonshot, paid)", "moonshotai/kimi-k2.6"),
    ]
    for label, slug in explicit:
        res = call(slug, reasoning_off=True)
        tag = "" if slug in avail else " [not in catalog top-list — trying anyway]"
        print(f"  [{label}] {slug}{tag}")
        print(f"      {res}")


if __name__ == "__main__":
    main()
