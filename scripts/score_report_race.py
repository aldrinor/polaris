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


def assert_legacy_scorer_lineage(report_path: str, prompt: str, task_id: "str | int") -> int:
    """STAGE-0 LINEAGE SEAM (scorer guard): refuse to score a split-brained legacy run BEFORE spend.

    On the legacy lineage the scored report ANSWERED the LEGACY (RACE task) question, so before any
    RACE spend this ASSERTS no split brain: the question the run actually answered (read from the
    run's ``corpus_snapshot`` lineage record) must equal the legacy canonical (``query.jsonl`` id ==
    ``--task-id``) the RACE harness packs. Returns ``0`` to proceed, ``2`` (BLOCKED) if the answered
    evidence is missing/unverifiable, and RAISES ``GateZeroLineageError`` on a hard packed/answered/
    canonical mismatch (raw AND sha). DEFAULT lineage (``drb_ii_idx`` / unset) => a no-op ``0`` —
    byte-identical to HEAD. Pure + hermetic (no network / no spend), so it is unit-testable.
    """
    from scripts.dr_benchmark.gate0_lineage import (
        LINEAGE_LEGACY_RACE_TASK as _GATE0_LINEAGE_LEGACY,
        assert_no_split_brain as _gate0_assert_no_split_brain,
        lineage_from_env as _gate0_lineage_from_env,
    )
    if _gate0_lineage_from_env() != _GATE0_LINEAGE_LEGACY:
        return 0
    run_dir = Path(report_path).resolve().parent
    snap_path = run_dir / "corpus_snapshot.json"
    if not snap_path.is_file():
        print(
            f"BLOCKED: legacy_race_task scoring requires the run's answered-question record but "
            f"no corpus_snapshot.json found at {snap_path} — cannot verify the report answered the "
            f"legacy question (refusing to score a possibly split-brained run).",
            file=sys.stderr,
        )
        return 2
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    answered_question = snap.get("question")
    answered_slug = snap.get("slug")
    stored_lineage = snap.get("lineage")
    if not answered_question or not answered_slug:
        print(
            f"BLOCKED: corpus_snapshot at {snap_path} is missing the answered question/slug — "
            f"cannot verify the legacy lineage (refusing to score).",
            file=sys.stderr,
        )
        return 2
    if stored_lineage != _GATE0_LINEAGE_LEGACY:
        print(
            f"BLOCKED: legacy_race_task scoring but the run snapshot lineage is "
            f"{stored_lineage!r} (expected {_GATE0_LINEAGE_LEGACY!r}) — the run did NOT answer the "
            f"legacy question (refusing to score a split-brained run).",
            file=sys.stderr,
        )
        return 2
    # packed == the RACE-harness prompt (query.jsonl id==task-id); answered == the run snapshot.
    # Both must equal the legacy canonical for the slug (raw AND sha), or the score is meaningless.
    _gate0_assert_no_split_brain(
        answered_slug, prompt, answered_question, lineage=_GATE0_LINEAGE_LEGACY,
    )
    print(
        f"[race] legacy_race_task split-brain guard PASSED: slug {answered_slug!r} answered "
        f"== packed (query.jsonl id {task_id}) == legacy canonical."
    )
    return 0


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

    # STAGE-0 LINEAGE SEAM: on the legacy lineage, refuse to score a split-brained run BEFORE spend.
    _guard_rc = assert_legacy_scorer_lineage(args.report, prompt, args.task_id)
    if _guard_rc != 0:
        return _guard_rc

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

    # FIX 1: purge stale cleaned cache. deepresearch_bench_race.py scores
    # cleaned_data/{model}.jsonl; --force only bypasses the eval-results cache, never the
    # clean cache. clean_article.py dedups by task-id, so an aborted stub under this id would
    # permanently shadow the real report. The wrapper writes exactly one raw record, so
    # purging the whole per-model cleaned file is exact.
    cleaned = DRB / "data/test_data/cleaned_data" / f"{args.model_name}.jsonl"
    if cleaned.exists():
        cleaned.unlink()
        print(f"[race] purged stale cleaned cache {cleaned.name} (forces re-clean)")

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

    # FIX 1 (2b): scored-artifact assertion. The cleaned file is what RACE actually scores.
    # Assert it holds exactly one record for THIS task with an article long enough to be the
    # real report (not an aborted stub or the {"id","error"} failure-record poisoning vector
    # that clean_article.py leaves and _load_processed_ids counts as processed).
    if not cleaned.exists():
        print("BLOCKED: cleaned/raw divergence", file=sys.stderr)
        print(f"[race] cleaned file {cleaned} not produced by harness", file=sys.stderr)
        return 3
    cleaned_records = [
        json.loads(cl) for cl in cleaned.read_text(encoding="utf-8").splitlines() if cl.strip()
    ]
    if len(cleaned_records) != 1:
        print("BLOCKED: cleaned/raw divergence", file=sys.stderr)
        print(f"[race] expected exactly 1 cleaned record, found {len(cleaned_records)}",
              file=sys.stderr)
        return 3
    rec = cleaned_records[0]
    if str(rec.get("id")) != str(task["id"]):
        print("BLOCKED: cleaned/raw divergence", file=sys.stderr)
        print(f"[race] cleaned record id={rec.get('id')!r} != task id={task['id']!r}",
              file=sys.stderr)
        return 3
    cleaned_article = rec.get("article", "")
    if len(cleaned_article) < 0.5 * len(report_text):
        print("BLOCKED: cleaned/raw divergence", file=sys.stderr)
        print(f"[race] cleaned article_chars={len(cleaned_article)} < 0.5 * "
              f"report_chars={len(report_text)} (aborted stub / error record?)", file=sys.stderr)
        return 3

    res_file = out_dir / "race_result.txt"
    if res_file.exists():
        print("\n===== RACE RESULT =====")
        print(res_file.read_text())
    else:
        print("[race] NO race_result.txt produced (see harness log above)", file=sys.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
