#!/usr/bin/env python3
"""Deep-thinking gate mind = openai/gpt-5.6-sol via OpenRouter (replaces Fable at gate points).
Opus orchestrates; this is called ONLY at deep-think/gate decisions to bound cost ($5/$30 per M tok).
Usage:  echo "<prompt>" | python3 sol_think.py [--system "<sys>"] [--max N] [--model M]
Reads OPENROUTER_API_KEY from env (source .env first). Prints content to stdout, usage to stderr.
"""
import os, sys, json, time, urllib.request, argparse

def sol(prompt, system=None, max_tokens=6000, model=None):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise SystemExit("sol_think: no OPENROUTER_API_KEY in env (source .env first)")
    model = model or os.environ.get("SOL_MODEL", "openai/gpt-5.6-sol")
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": msgs, "max_tokens": max_tokens}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(str(d["error"])[:200])
            m = d["choices"][0]["message"]
            return {"content": m.get("content") or "", "reasoning": m.get("reasoning") or "",
                    "usage": d.get("usage", {}), "model": d.get("model", model)}
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"sol_think: failed after 3 tries: {last}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default=None)
    ap.add_argument("--max", type=int, default=6000)
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    out = sol(sys.stdin.read(), system=a.system, max_tokens=a.max, model=a.model)
    print(out["content"])
    u = out["usage"]
    sys.stderr.write(f"[sol {out['model']}] in={u.get('prompt_tokens')} out={u.get('completion_tokens')} "
                     f"reason_chars={len(out['reasoning'])}\n")
