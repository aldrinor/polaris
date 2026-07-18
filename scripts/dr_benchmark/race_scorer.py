#!/usr/bin/env python3
"""RACE scorer — POLARIS re-implementation of the DeepResearch-Bench RACE metric.

WHAT THIS IS
------------
RACE (Reference-based Adaptive Criteria-driven Evaluation) is the report-quality half of
DeepResearch-Bench (Du et al., "DeepResearch Bench: A Comprehensive Benchmark for Deep
Research Agents", arXiv:2506.11763; github.com/Ayanami0730/deep_research_bench). It scores a
research report on FOUR dimensions — Comprehensiveness, Insight, Instruction-Following,
Readability — using per-task ADAPTIVE criteria (weights sum to 1.0 per dimension) plus
per-task dimension weights, and grades RELATIVE TO A REFERENCE report:

    overall_score      = target_total / (target_total + reference_total)
    per-dim normalized = target_dim   / (target_dim   + reference_dim)

so 0.5 == parity with the reference; >0.5 beats it. Because the reference is a COMMON
baseline shared by every candidate, POLARIS-vs-competitor comparisons are valid regardless
of which reference is chosen (the reference cancels in a cross-system comparison).

FAITHFULNESS / DISCLOSURE (honesty rules)
-----------------------------------------
  * Algorithm & prompts: the comparative-scoring prompt (race_prompts.GENERATE_MERGED_SCORE_PROMPT)
    is VERBATIM from the official harness; the weighted-score aggregation ports
    utils/score_calculator.calculate_weighted_scores exactly (fuzzy criterion matching,
    average-weight fallback, dimension weighting). The dimension-weight and per-dimension
    criteria-generation prompts reproduce the official INSTRUCTION bodies verbatim; their
    long illustrative EXAMPLE blocks are abbreviated (does not change the scoring math).
  * Judge SUBSTITUTION: the paper's RACE judge is Gemini-2.5-Pro. We substitute
    moonshotai/kimi-k2.6 — the SAME operator-signed judge lock used by the DeepTRACE scorer
    (config/benchmark/deeptrace_judge_lock.yaml, comparability policy = self_rescore). So this
    is a SELF_RESCORE run: POLARIS and every competitor are scored by the SAME judge on the
    SAME task/criteria/reference. Absolute numbers are NOT the paper's published numbers.
  * Reference SUBSTITUTION: the candidates all answer a Generative-AI-focused variant of
    DeepResearch-Bench English task id 72 ("...restructuring impact of AI on the labor
    market..."). We use the official DRB task-72 REFERENCE report as the common reference
    anchor (--reference). It is topic-matched (AI x labor market) but the shared prompt the
    candidates answered differs in framing (Generative AI; positive/negative/challenges/
    opportunities sections; pre-June-2023; a required summary table). DISCLOSED, not hidden.
  * Adaptive criteria are generated from the ACTUAL shared prompt the candidates answered
    (--task-prompt / --task-prompt-file), not the official-72 prompt, so instruction-following
    is judged against the instructions the candidates were actually given.

This module makes ~ (5 criteria-gen + N_candidates scoring) paid OpenRouter calls. It is a
re-implementation ESTIMATE, disclosed as such; it never claims the paper's official numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import race_prompts  # noqa: E402

DIMENSIONS = ["comprehensiveness", "insight", "instruction_following", "readability"]
DEFAULT_LOCK = "config/benchmark/deeptrace_judge_lock.yaml"


# --------------------------------------------------------------------------- judge lock
def load_judge_from_lock(lock_path: str) -> dict:
    """Read the operator-signed benchmark-judge lock. Fail loud if unsigned or missing model."""
    import yaml

    with open(lock_path, "r", encoding="utf-8") as fh:
        lock = yaml.safe_load(fh)
    sig = (lock.get("signature") or {})
    if not bool(sig.get("signed")):
        raise SystemExit(f"[race] BLOCKED: judge lock {lock_path} is UNSIGNED — no RACE number is claimable.")
    bj = (lock.get("benchmark_judge") or {})
    model = bj.get("model_slug")
    if not model:
        raise SystemExit(f"[race] BLOCKED: judge lock {lock_path} has no benchmark_judge.model_slug.")
    policy = (lock.get("comparability") or {}).get("policy")
    return {"model": model, "policy": policy}


# --------------------------------------------------------------------------- OpenRouter call
class RateLimit429(RuntimeError):
    pass


def call_judge(model: str, prompt: str, *, max_tokens: int = 16000, temperature: float = 0.0,
               timeout: float = 600.0, max_retries: int = 4) -> str:
    """One chat/completions call to the locked judge via OpenRouter. Raises RateLimit429 on HTTP 429
    (surfaced to the operator, never silently retried forever). Reads OPENROUTER_API_KEY from env."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("[race] BLOCKED: OPENROUTER_API_KEY unset — cannot reach the judge.")
    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    endpoint = base + "/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(body).encode("utf-8")
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            endpoint, data=data,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read())
            choices = payload.get("choices") or []
            if not choices:
                raise RuntimeError(f"empty choices: {str(payload)[:300]}")
            return choices[0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:  # noqa: PERF203
            if e.code == 429:
                raise RateLimit429("OpenRouter HTTP 429 (rate limit / shared-account headroom exhausted).")
            last_err = e
            time.sleep(2.0 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"[race] judge call failed after {max_retries} attempts: {last_err}")


# --------------------------------------------------------------------------- article cleaning
_DATA_URI_IMG = re.compile(r"!\[[^\]]*\]\(data:[^)]+\)")
_BARE_DATA_URI = re.compile(r"data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=\s]{200,}")


def clean_article(text: str) -> str:
    """Deterministic, offline article normalisation (DISCLOSED substitute for the official LLM
    ArticleCleaner). Strips base64 data-URI images (pure token bloat, zero textual content) and
    collapses runaway blank lines. Applied IDENTICALLY to every candidate and the reference, so it
    is fair. It removes NO prose."""
    text = _DATA_URI_IMG.sub("", text)
    text = _BARE_DATA_URI.sub("", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------- JSON extraction
def extract_json(text: str) -> Optional[Any]:
    """Extract the outermost JSON object/array from a possibly-markdown-wrapped LLM reply."""
    if not isinstance(text, str):
        return None
    s = text.strip()
    for loader in (s,):
        try:
            return json.loads(loader)
        except Exception:  # noqa: BLE001
            pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:  # noqa: BLE001
            pass
    # outermost {...} or [...]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        level = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                level += 1
            elif text[i] == closer:
                level -= 1
                if level == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:  # noqa: BLE001
                        break
    return None


# --------------------------------------------------------------------------- criteria generation
def _extract_weight_json(reply: str) -> dict:
    obj = extract_json(reply)
    if isinstance(obj, dict):
        return obj
    # pull the <json_output> block if present
    m = re.search(r"<json_output>\s*([\s\S]*?)\s*</json_output>", reply)
    if m:
        obj = extract_json(m.group(1))
        if isinstance(obj, dict):
            return obj
    raise RuntimeError(f"could not parse dimension-weight JSON from judge reply: {reply[:300]}")


def _extract_criteria_list(reply: str) -> list:
    m = re.search(r"<json_output>\s*([\s\S]*?)\s*</json_output>", reply)
    if m:
        obj = extract_json(m.group(1))
        if isinstance(obj, list):
            return obj
    obj = extract_json(reply)
    if isinstance(obj, list):
        return obj
    raise RuntimeError(f"could not parse criteria list from judge reply: {reply[:300]}")


def generate_criteria(model: str, task_prompt: str, verbose: bool = True) -> dict:
    """Run the RACE criteria-generation phase: adaptive dimension weights + per-dimension criteria.
    Returns a criteria_data dict shaped exactly like the official criteria.jsonl entries:
      {"dimension_weight": {...}, "criterions": {dim: [{criterion, explanation, weight}, ...]}}
    """
    if verbose:
        print("[race] generating adaptive dimension weights...", file=sys.stderr)
    dw_reply = call_judge(model, race_prompts.GENERATE_DIMENSION_WEIGHT_PROMPT.format(task_prompt=task_prompt))
    dim_weight = _extract_weight_json(dw_reply)
    dim_weight = {k: float(v) for k, v in dim_weight.items() if k in DIMENSIONS}
    total = sum(dim_weight.values()) or 1.0
    dim_weight = {k: v / total for k, v in dim_weight.items()}  # renormalize to 1.0

    prompts = {
        "comprehensiveness": race_prompts.GENERATE_CRITERIA_PROMPT_COMPREHENSIVENESS,
        "insight": race_prompts.GENERATE_CRITERIA_PROMPT_INSIGHT,
        "instruction_following": race_prompts.GENERATE_CRITERIA_PROMPT_INSTRUCTION,
        "readability": race_prompts.GENERATE_CRITERIA_PROMPT_READABILITY,
    }
    criterions: dict[str, list] = {}
    for dim, tmpl in prompts.items():
        if verbose:
            print(f"[race] generating criteria: {dim}...", file=sys.stderr)
        reply = call_judge(model, tmpl.format(task_prompt=task_prompt))
        items = _extract_criteria_list(reply)
        clean_items = []
        for it in items:
            if isinstance(it, dict) and "criterion" in it and "weight" in it:
                clean_items.append({
                    "criterion": str(it["criterion"]).strip(),
                    "explanation": str(it.get("explanation", "")).strip(),
                    "weight": float(it["weight"]),
                })
        wsum = sum(c["weight"] for c in clean_items) or 1.0
        for c in clean_items:
            c["weight"] = c["weight"] / wsum  # renormalize per-dim to 1.0
        criterions[dim] = clean_items
    return {"dimension_weight": dim_weight, "criterions": criterions}


def format_criteria_list(criteria_data: dict) -> str:
    """JSON string of criteria (criterion + explanation, NO weights) for the scoring prompt —
    matches the official format_criteria_list."""
    out = {}
    for dim, items in criteria_data.get("criterions", {}).items():
        out[dim] = [{"criterion": c["criterion"], "explanation": c["explanation"]} for c in items]
    return json.dumps(out, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- weighted scoring (port)
def calculate_weighted_scores(llm_output_json: dict, criteria_data: dict) -> dict:
    """Port of utils/score_calculator.calculate_weighted_scores (exact matching / fallback logic)."""
    results = {"target": {"dims": {}, "total": 0.0}, "reference": {"dims": {}, "total": 0.0}}
    total_target = 0.0
    total_reference = 0.0
    dimension_weights = criteria_data.get("dimension_weight", {})

    criterion_weights: dict[str, dict[str, float]] = {}
    for dim, crits in criteria_data.get("criterions", {}).items():
        criterion_weights[dim] = {c["criterion"]: c["weight"] for c in crits}

    for dim, scores_list in llm_output_json.items():
        if not isinstance(scores_list, list) or dim not in dimension_weights or dim not in criterion_weights:
            continue
        dim_map = criterion_weights.get(dim, {})
        if not dim_map:
            continue
        dim_t = 0.0
        dim_r = 0.0
        dim_w = 0.0
        last_a2 = None
        for item in scores_list:
            if not isinstance(item, dict):
                continue
            ctext = item.get("criterion")
            ctext = ctext.strip() if isinstance(ctext, str) else None
            a1 = item.get("article_1_score")
            a2 = item.get("article_2_score")
            tgt = item.get("target_score")
            if tgt is not None and a1 is None:
                a1 = tgt
            try:
                a1 = float(a1) if a1 is not None else None
                a2 = float(a2) if a2 is not None else None
            except (ValueError, TypeError):
                continue
            last_a2 = a2
            if not (ctext and a1 is not None):
                continue
            weight = dim_map.get(ctext)
            if weight is None:
                cl = ctext.lower()
                for k, v in dim_map.items():
                    if k.lower() == cl:
                        weight = v
                        break
                if weight is None:
                    for k, v in dim_map.items():
                        if cl in k.lower() or k.lower() in cl:
                            weight = v
                            break
                if weight is None:
                    weight = sum(dim_map.values()) / len(dim_map)
            dim_t += a1 * weight
            dim_w += weight
            if a2 is not None:
                dim_r += a2 * weight
        if dim_w > 0:
            dim_t_avg = dim_t / dim_w
            dim_r_avg = dim_r / dim_w if last_a2 is not None else 0.0
        else:
            dim_t_avg = dim_r_avg = 0.0
        results["target"]["dims"][f"{dim}_weighted_avg"] = dim_t_avg
        results["reference"]["dims"][f"{dim}_weighted_avg"] = dim_r_avg
        dw = dimension_weights.get(dim, 0)
        total_target += dim_t_avg * dw
        total_reference += dim_r_avg * dw
    results["target"]["total"] = total_target
    results["reference"]["total"] = total_reference
    return results


def score_candidate(model: str, task_prompt: str, candidate_article: str, reference_article: str,
                    criteria_data: dict, *, max_retries: int = 6) -> dict:
    """Comparative-score one candidate (article_1) vs the reference (article_2). Returns per-dim
    normalized scores + overall_score = target/(target+ref)."""
    criteria_list_str = format_criteria_list(criteria_data)
    prompt = race_prompts.GENERATE_MERGED_SCORE_PROMPT.format(
        task_prompt=task_prompt, article_1=candidate_article,
        article_2=reference_article, criteria_list=criteria_list_str,
    )
    llm_json = None
    for attempt in range(max_retries):
        reply = call_judge(model, prompt)
        obj = extract_json(reply)
        if isinstance(obj, dict) and all(d in obj for d in DIMENSIONS):
            llm_json = obj
            break
        time.sleep(1.5 * (attempt + 1))
    if llm_json is None:
        raise RuntimeError("judge did not return valid 4-dimension scoring JSON after retries.")

    scores = calculate_weighted_scores(llm_json, criteria_data)
    t_total = scores["target"]["total"]
    r_total = scores["reference"]["total"]
    overall = t_total / (t_total + r_total) if (t_total + r_total) > 0 else 0.0
    norm = {}
    for dim in DIMENSIONS:
        tk = scores["target"]["dims"].get(f"{dim}_weighted_avg", 0.0)
        rk = scores["reference"]["dims"].get(f"{dim}_weighted_avg", 0.0)
        norm[dim] = tk / (tk + rk) if (tk + rk) > 0 else 0.0
    return {
        "overall_score": overall,
        "dims_normalized": norm,
        "target_total": t_total,
        "reference_total": r_total,
        "target_dims_raw": scores["target"]["dims"],
        "reference_dims_raw": scores["reference"]["dims"],
        "raw_llm_scores": llm_json,
    }


# --------------------------------------------------------------------------- CLI
def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="RACE scorer (DeepResearch-Bench re-implementation).")
    ap.add_argument("--lock", default=DEFAULT_LOCK, help="benchmark-judge lock YAML")
    ap.add_argument("--task-prompt", help="the shared task prompt the candidates answered")
    ap.add_argument("--task-prompt-file", help="file containing the task prompt")
    ap.add_argument("--reference", required=True, help="reference article file (common baseline)")
    ap.add_argument("--candidate", action="append", default=[], metavar="NAME=PATH",
                    help="a candidate report as NAME=PATH (repeatable)")
    ap.add_argument("--criteria-out", help="write generated criteria JSON here")
    ap.add_argument("--criteria-in", help="reuse pre-generated criteria JSON (skip criteria-gen)")
    ap.add_argument("--out", help="write full results JSON here")
    args = ap.parse_args(argv)

    if args.task_prompt_file:
        task_prompt = _read(args.task_prompt_file).strip()
    elif args.task_prompt:
        task_prompt = args.task_prompt.strip()
    else:
        raise SystemExit("[race] need --task-prompt or --task-prompt-file")

    judge = load_judge_from_lock(args.lock)
    model = judge["model"]
    print(f"[race] judge={model} comparability={judge['policy']} (self_rescore: same judge for all systems)",
          file=sys.stderr)

    reference_article = clean_article(_read(args.reference))
    candidates = {}
    for spec in args.candidate:
        if "=" not in spec:
            raise SystemExit(f"[race] bad --candidate {spec!r}; use NAME=PATH")
        name, path = spec.split("=", 1)
        candidates[name] = clean_article(_read(path))
    if not candidates:
        raise SystemExit("[race] no --candidate given")

    if args.criteria_in:
        criteria_data = json.loads(_read(args.criteria_in))
    else:
        criteria_data = generate_criteria(model, task_prompt)
        if args.criteria_out:
            with open(args.criteria_out, "w", encoding="utf-8") as fh:
                json.dump(criteria_data, fh, ensure_ascii=False, indent=2)
            print(f"[race] wrote criteria -> {args.criteria_out}", file=sys.stderr)

    print("[race] dimension weights:", criteria_data["dimension_weight"], file=sys.stderr)

    results = {}
    try:
        for name, art in candidates.items():
            print(f"[race] scoring candidate: {name} ...", file=sys.stderr)
            results[name] = score_candidate(model, task_prompt, art, reference_article, criteria_data)
            r = results[name]
            print(f"[race]   {name}: overall={r['overall_score']:.4f} "
                  + " ".join(f"{d[:4]}={r['dims_normalized'][d]:.3f}" for d in DIMENSIONS), file=sys.stderr)
    except RateLimit429 as e:
        print(f"[race] BLOCKED by rate limit: {e}", file=sys.stderr)
        print("[race] partial results so far:", json.dumps({k: v['overall_score'] for k, v in results.items()}),
              file=sys.stderr)
        return 5

    out = {
        "metric": "RACE (DeepResearch-Bench re-implementation, ESTIMATE)",
        "judge_model": model,
        "comparability_policy": judge["policy"],
        "reference_disclosure": "official DRB English task-72 reference report (topic-matched anchor); "
                                "shared candidate prompt is a Generative-AI variant of task 72 (DISCLOSED).",
        "judge_disclosure": "paper RACE judge is Gemini-2.5-Pro; substituted kimi-k2.6 per operator lock.",
        "task_prompt": task_prompt,
        "dimension_weights": criteria_data["dimension_weight"],
        "criteria_counts": {d: len(criteria_data["criterions"].get(d, [])) for d in DIMENSIONS},
        "results": results,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
