#!/usr/bin/env python3
"""Score a composed POLARIS report with RACE (DeepResearch Bench) against a benchmark task.

RACE (third_party/deep_research_bench/deepresearch_bench_race.py) is REFERENCE-BASED: it matches
the target article, the reference article, and the per-task criteria by EXACT prompt string, then
an LLM judge (openai/gpt-5.5 via OpenRouter) scores both target and reference on the task's
dynamic-weighted dimensions. Overall = target/(target+reference) (0.5 == parity with reference).

This wrapper: (1) reads a report.md, (2) writes it as the target jsonl under the benchmark task's
EXACT prompt (so ref+criteria align), (3) invokes the official RACE harness limited to that task,
(4) prints results/race/<model>/race_result.txt.

Usage:
    set -a && . ./.env && set +a
    python scripts/score_report_race.py --report outputs/live_compose/run2/report.md \
        --task-id 72 --model-name polaris_task72
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRB = ROOT / "third_party" / "deep_research_bench"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", required=True, help="path to report.md")
    ap.add_argument("--task-id", default="72")
    ap.add_argument("--model-name", default="polaris_task72")
    ap.add_argument("--race-model", default=os.getenv("RACE_MODEL", "openai/gpt-5.5"))
    ap.add_argument("--max-workers", type=int, default=4)
    args = ap.parse_args()

    if not os.getenv("OPENROUTER_API_KEY"):
        print("BLOCKED: OPENROUTER_API_KEY not set — source .env first", file=sys.stderr)
        return 2

    report_text = Path(args.report).read_text(encoding="utf-8")
    # Find the benchmark task's EXACT prompt (target/ref/criteria all key on it).
    task = None
    for line in (DRB / "data/prompt_data/query.jsonl").read_text().splitlines():
        o = json.loads(line)
        if str(o["id"]) == str(args.task_id):
            task = o
            break
    if task is None:
        print(f"BLOCKED: task id {args.task_id} not in query.jsonl", file=sys.stderr)
        return 2
    prompt = task["prompt"]
    lang = task.get("language", "en")

    # Single-task query file so ONLY this task is scored.
    q_path = DRB / f"data/prompt_data/query_task{args.task_id}.jsonl"
    q_path.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")

    # Target article jsonl (raw). Article carries the benchmark prompt so RACE aligns it with the
    # reference+criteria. This is an apples-to-apples score ONLY when the report was composed to
    # answer THIS prompt.
    target = {"id": task["id"], "prompt": prompt, "article": report_text}
    raw_dir = DRB / "data/test_data/raw_data"
    (raw_dir / f"{args.model_name}.jsonl").write_text(
        json.dumps(target, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[race] target={args.model_name}.jsonl  article_chars={len(report_text)}  "
          f"prompt_task={args.task_id} lang={lang}")

    out_dir = DRB / f"results/race/{args.model_name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["LLM_BACKEND"] = "openrouter"
    env["RACE_MODEL"] = args.race_model
    lang_flag = "--only_en" if lang == "en" else "--only_zh"
    cmd = [
        sys.executable, "-u", "deepresearch_bench_race.py", args.model_name,
        "--raw_data_dir", "data/test_data/raw_data",
        "--cleaned_data_dir", "data/test_data/cleaned_data",
        "--query_file", str(q_path.relative_to(DRB)),
        "--output_dir", str(out_dir.relative_to(DRB)),
        "--max_workers", str(args.max_workers),
        lang_flag, "--force",
    ]
    print("[race] running:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(DRB), env=env)
    res_file = out_dir / "race_result.txt"
    if res_file.exists():
        print("\n===== RACE RESULT =====")
        print(res_file.read_text())
    else:
        print("[race] NO race_result.txt produced (see harness log above)", file=sys.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
