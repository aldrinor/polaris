"""I-arch-011 entailment-judge CALL-SHAPE bake-off (blank-rate AND verdict-correctness).

The credibility-pass micro-test proved there is NO concurrency deadlock; the real chokepoint is a
GLM-5.1 BLANK-200 storm (empty-content 200s) when the entailment judge fires at
``reasoning:{effort:"high"}`` + ``response_format:{json_object}`` + max_tokens=131072. The yaml's own
2026-06-14 bake-off found the NUMERIC reasoning cap (``reasoning.max_tokens``), not effort=high, is
what makes GLM-5.1 return clean content.

This bake-off A/Bs the exact prod call shape against the numeric-cap fix, on the REAL entailment
prompt, and gates on the RIGHT thing (advisor): a shape must be BOTH low-blank AND get all three
labeled pairs (ENTAILED / CONTRADICTED / NEUTRAL) correct — a shape that returns content but
rubber-stamps ENTAILED is strictly WORSE than the current blank->advisory-keep (it would relax the
NLI gate). Winner = lowest blank rate AND 3/3 labels correct on every sample.

Run on a VM (z-ai-led mirror routing already deployed):
  cd /root/polaris_v2 && /root/run_env/bin/python -m scripts.diagnostics.entailment_shape_bakeoff
"""
import concurrent.futures
import json
import os
import sys
import time

sys.path.insert(0, "/root/polaris_v2")

try:
    from dotenv import load_dotenv

    load_dotenv("/root/polaris_v2/.env")
except Exception:  # noqa: BLE001
    pass

import httpx  # noqa: E402

from src.polaris_graph.llm.entailment_judge import _ENTAILMENT_PROMPT  # noqa: E402

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
BASE = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
ENDPOINT = BASE + "/chat/completions"
MODEL = "z-ai/glm-5.1"

# Three UNAMBIGUOUS labeled pairs (a correct NLI judge MUST get these right).
PAIRS = [
    # ENTAILED: conservative paraphrase, every assertion supported by the span.
    (
        "ENTAILED",
        "In a randomized controlled trial, deep brain stimulation of the subthalamic nucleus "
        "significantly improved motor function as measured by UPDRS-III compared with best medical "
        "therapy in patients with advanced Parkinson disease over 24 months of follow-up.",
        "Deep brain stimulation improved motor function in advanced Parkinson's disease.",
    ),
    # CONTRADICTED: span says improved, sentence says worsened.
    (
        "CONTRADICTED",
        "In the trial, deep brain stimulation significantly improved motor function compared with "
        "best medical therapy.",
        "Deep brain stimulation worsened motor function compared with best medical therapy.",
    ),
    # NEUTRAL: sentence introduces a new outcome (mortality) absent from the span.
    (
        "NEUTRAL",
        "Deep brain stimulation improved motor function in patients with advanced Parkinson disease.",
        "Deep brain stimulation reduced the risk of death in patients with advanced Parkinson "
        "disease.",
    ),
]

# Call shapes. provider pinned to z-ai (allow_fallbacks:False) = prod single-provider behavior.
PROVIDER_BLOCK = {"order": [os.environ.get("PG_BAKEOFF_PROVIDER", "z-ai")],
                  "allow_fallbacks": False, "require_parameters": True}
SHAPES = {
    # S0 = current prod default (the blank-prone shape under test).
    "S0_effort_high_json": {"reasoning": {"effort": "high"},
                            "response_format": {"type": "json_object"}, "max_tokens": 131072},
    # S1 = LEAD FIX: numeric reasoning cap (matches the proven 2026-06-14 bake-off) + json_object ON.
    "S1_rcap100k_json": {"reasoning": {"max_tokens": 100000},
                         "response_format": {"type": "json_object"}, "max_tokens": 131072},
    # S2 = localize the json_object confound: numeric cap, json_object OFF.
    "S2_rcap100k_nojson": {"reasoning": {"max_tokens": 100000}, "max_tokens": 131072},
    # S3 = proven fallback: medium effort + json_object ON.
    "S3_effort_medium_json": {"reasoning": {"effort": "medium"},
                              "response_format": {"type": "json_object"}, "max_tokens": 131072},
    # S4 = tighter reasoning cap (more content headroom) + json_object ON.
    "S4_rcap8k_json": {"reasoning": {"max_tokens": 8000},
                       "response_format": {"type": "json_object"}, "max_tokens": 16000},
}

SAMPLES_PER_PAIR = int(os.environ.get("PG_BAKEOFF_SAMPLES", "6"))
CALL_TIMEOUT_S = 150.0


def _extract_verdict(content: str):
    """Tolerant: pull the first {...} JSON object's `verdict`. Returns (verdict|None, why)."""
    s = (content or "").strip()
    if not s:
        return None, "BLANK"
    # strip code fences
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        s = s.lstrip("json").strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "NO_JSON:" + s[:40]
    try:
        obj = json.loads(s[start:end + 1])
    except Exception as e:  # noqa: BLE001
        return None, "PARSE:" + str(e)[:40]
    v = str(obj.get("verdict", "")).strip().upper()
    if v not in ("ENTAILED", "NEUTRAL", "CONTRADICTED"):
        return None, "BADVERDICT:" + v[:24]
    return v, "ok"


def _one_call(shape_body: dict, span: str, sentence: str):
    prompt = _ENTAILMENT_PROMPT.format(span=span, sentence=sentence)
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "provider": PROVIDER_BLOCK,
        **shape_body,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    t0 = time.time()
    try:
        with httpx.Client(timeout=httpx.Timeout(CALL_TIMEOUT_S, connect=15.0, read=120.0)) as c:
            r = c.post(ENDPOINT, headers=headers, json=body)
        dt = round(time.time() - t0, 1)
        if r.status_code != 200:
            return ("HTTP%d" % r.status_code, None, dt)
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        verdict, why = _extract_verdict(content)
        return (why if verdict is None else "ok", verdict, dt)
    except Exception as e:  # noqa: BLE001
        return ("EXC:" + str(e)[:40], None, round(time.time() - t0, 1))


def run_shape(name: str, shape_body: dict) -> dict:
    tasks = []
    for label, span, sentence in PAIRS:
        for _ in range(SAMPLES_PER_PAIR):
            tasks.append((label, span, sentence))
    results = [None] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_one_call, shape_body, sp, se): i
                for i, (lb, sp, se) in enumerate(tasks)}
        for fut in concurrent.futures.as_completed(futs):
            results[futs[fut]] = fut.result()
    # aggregate
    n = len(tasks)
    blanks = sum(1 for (why, v, _dt) in results if why == "BLANK")
    nonans = sum(1 for (why, v, _dt) in results if v is None)  # blank OR parse-fail OR http
    durs = sorted(dt for (_w, _v, dt) in results)
    median = durs[len(durs) // 2] if durs else 0.0
    per_label = {}
    for (label, _sp, _se), (why, verdict, _dt) in zip(tasks, results):
        d = per_label.setdefault(label, {"n": 0, "correct": 0, "nonans": 0})
        d["n"] += 1
        if verdict is None:
            d["nonans"] += 1
        elif verdict == label:
            d["correct"] += 1
    all_correct = all(d["correct"] == d["n"] for d in per_label.values())
    return {
        "name": name, "n": n, "blank_pct": round(100 * blanks / n, 0),
        "nonans_pct": round(100 * nonans / n, 0), "median_s": median,
        "per_label": per_label, "all_correct": all_correct,
        "sample_fails": [why for (why, v, _dt) in results if v is None][:6],
    }


if __name__ == "__main__":
    if not API_KEY:
        print("FATAL: OPENROUTER_API_KEY not set", flush=True)
        sys.exit(2)
    print(f"=== entailment call-shape bake-off | provider={PROVIDER_BLOCK['order'][0]} | "
          f"{SAMPLES_PER_PAIR} samples/pair x 3 labels ===", flush=True)
    rows = []
    for name, body in SHAPES.items():
        print(f"\n--- running {name} ---", flush=True)
        row = run_shape(name, body)
        rows.append(row)
        pl = row["per_label"]
        print(
            f"{name}: blank={row['blank_pct']:.0f}% nonans={row['nonans_pct']:.0f}% "
            f"median={row['median_s']}s | "
            f"E={pl.get('ENTAILED',{}).get('correct',0)}/{pl.get('ENTAILED',{}).get('n',0)} "
            f"C={pl.get('CONTRADICTED',{}).get('correct',0)}/{pl.get('CONTRADICTED',{}).get('n',0)} "
            f"N={pl.get('NEUTRAL',{}).get('correct',0)}/{pl.get('NEUTRAL',{}).get('n',0)} | "
            f"ALL_CORRECT={row['all_correct']} | fails={row['sample_fails']}",
            flush=True,
        )
    # winner = 3/3 labels perfect AND lowest non-answer rate
    clean = [r for r in rows if r["all_correct"] and r["nonans_pct"] == 0]
    clean.sort(key=lambda r: (r["nonans_pct"], r["median_s"]))
    print("\n=== SUMMARY ===", flush=True)
    for r in sorted(rows, key=lambda r: (r["nonans_pct"], not r["all_correct"], r["median_s"])):
        print(f"  {r['name']:<24} nonans={r['nonans_pct']:>3.0f}% blank={r['blank_pct']:>3.0f}% "
              f"median={r['median_s']:>5}s all_correct={r['all_correct']}", flush=True)
    if clean:
        print(f"WINNER={clean[0]['name']}", flush=True)
    else:
        passced = [r for r in rows if r["all_correct"]]
        if passced:
            passced.sort(key=lambda r: (r["nonans_pct"], r["median_s"]))
            print(f"NO_ZERO_BLANK_WINNER — best all-correct: {passced[0]['name']} "
                  f"(nonans={passced[0]['nonans_pct']:.0f}%)", flush=True)
        else:
            print("NO_WINNER — no shape got all 3 labels correct (investigate before any fix)", flush=True)
