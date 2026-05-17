#!/usr/bin/env python3
"""I-rdy-018 (#514) — OpenRouter V4 Pro non-sovereign rehearsal runner.

Phase-4 rehearsal: point the LLM endpoint at OpenRouter V4 Pro + Gemma
(test-only, non-confidential prompts) and exercise the full v6 journey.

Subcommands:
  check-models   GET OpenRouter /models; confirm the generator (V4 Pro) and
                 evaluator (Gemma) model ids are available. No token spend.
  run            Run the fixed non-confidential prompt set
                 (tests/v6/fixtures/rehearsal_prompts.yaml) through the real
                 v6 actor path. `--dry-run` validates wiring with no spend.

The live `run` path calls `enqueue_research_run.fn(...)` — the undecorated
v6 actor function — so the rehearsal exercises the genuine actor q-dict
(unique artifact dir + synthesized v30_contract_patch), not a shortcut.

Usage:
    python scripts/v6/run_rehearsal.py check-models [--generator ID] [--evaluator ID]
    python scripts/v6/run_rehearsal.py run [--dry-run] [--only TEMPLATE]
        [--max-cost N] [--out-root DIR] [--generator ID] [--evaluator ID]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# The actor module decorates @dramatiq.actor at import; force the StubBroker
# so importing it never needs a live Redis. The runner uses `.fn()`, never
# the broker, so this is inert beyond import-time.
os.environ.setdefault("POLARIS_V6_QUEUE_USE_STUB", "1")

import yaml  # noqa: E402  (third-party; project dependency)

DEFAULT_GENERATOR = "deepseek/deepseek-v4-pro"
DEFAULT_EVALUATOR = "google/gemma-4-31b-it"
DEFAULT_MAX_COST = "5.00"
PROMPTS_PATH = Path(__file__).resolve().parents[2] / "tests" / "v6" / "fixtures" / "rehearsal_prompts.yaml"


def _fail(msg: str) -> None:
    """Fail loud: stderr + non-zero exit (CLAUDE.md LAW II)."""
    raise SystemExit(f"[run_rehearsal] ERROR: {msg}")


def _openrouter_base() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")


def _load_prompts() -> list[dict]:
    if not PROMPTS_PATH.is_file():
        _fail(f"prompt set not found: {PROMPTS_PATH}")
    data = yaml.safe_load(PROMPTS_PATH.read_text(encoding="utf-8"))
    prompts = data.get("prompts") if isinstance(data, dict) else None
    if not prompts:
        _fail(f"{PROMPTS_PATH.name} has no `prompts` list")
    for entry in prompts:
        if "template" not in entry or "question" not in entry:
            _fail(f"prompt entry missing template/question: {entry!r}")
    return prompts


def cmd_check_models(args: argparse.Namespace) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        _fail("OPENROUTER_API_KEY is unset — the rehearsal cannot run without it")

    url = f"{_openrouter_base()}/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            catalogue = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        _fail(f"OpenRouter /models request failed: {exc}")

    available = {m.get("id") for m in catalogue.get("data", []) if isinstance(m, dict)}
    wanted = {"generator": args.generator, "evaluator": args.evaluator}
    print(f"OpenRouter /models — {len(available)} models in catalogue")
    missing = []
    for role, model_id in wanted.items():
        present = model_id in available
        print(f"  [{'OK ' if present else 'MISSING'}] {role}: {model_id}")
        if not present:
            missing.append(model_id)
    if missing:
        _fail(f"configured model(s) not available on OpenRouter: {', '.join(missing)}")
    print("check-models: PASS — generator + evaluator both available")


def cmd_run(args: argparse.Namespace) -> None:
    from polaris_v6.queue.actors import TEMPLATE_TO_SCOPE_DOMAIN

    prompts = _load_prompts()
    if args.only:
        prompts = [p for p in prompts if p["template"] == args.only]
        if not prompts:
            _fail(f"--only {args.only!r} matched no prompt in the set")
    for entry in prompts:
        if entry["template"] not in TEMPLATE_TO_SCOPE_DOMAIN:
            _fail(
                f"prompt template {entry['template']!r} is not one of the "
                f"canonical templates {sorted(TEMPLATE_TO_SCOPE_DOMAIN)}"
            )

    key_present = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    print("=" * 64)
    print("POLARIS v6 non-sovereign rehearsal" + ("  [DRY RUN]" if args.dry_run else ""))
    print("=" * 64)
    print(f"  generator        : {args.generator}")
    print(f"  evaluator        : {args.evaluator}")
    print(f"  backend          : openrouter ({_openrouter_base()})")
    print(f"  OPENROUTER_API_KEY: {'present' if key_present else 'ABSENT'}")
    print(f"  PG_MAX_COST_PER_RUN: {args.max_cost}")
    print(f"  prompts          : {len(prompts)}")
    for entry in prompts:
        print(f"    - {entry['template']}: {entry['question']}")
    print("-" * 64)

    if args.dry_run:
        print("DRY RUN: wiring validated — no LLM call, no run-store write, "
              "no spend. Re-run without --dry-run to execute the billed rehearsal.")
        return

    if not key_present:
        _fail("OPENROUTER_API_KEY is unset — cannot execute a live rehearsal run")

    # Wire the LLM endpoint as env vars (Phase-4: point at V4 Pro + Gemma).
    os.environ["PG_GENERATOR_MODEL"] = args.generator
    os.environ["PG_EVALUATOR_MODEL"] = args.evaluator
    os.environ["PG_MAX_COST_PER_RUN"] = str(args.max_cost)
    if args.out_root:
        os.environ["POLARIS_V6_OUTPUT_ROOT"] = str(args.out_root)

    from polaris_v6.queue import run_store
    from polaris_v6.queue.actors import enqueue_research_run

    results: list[dict] = []
    for entry in prompts:
        template, question = entry["template"], entry["question"]
        run_id = f"rehearsal_{template}_{uuid.uuid4().hex[:8]}"
        run_store.insert_run(run_id, template, question)
        print(f"[run] {template} ({run_id}) ...")
        status = {"template": template, "run_id": run_id}
        try:
            enqueue_research_run.fn(run_id, {"template": template, "question": question})
        except Exception as exc:  # noqa: BLE001 — record any pipeline crash, continue
            print(f"  EXCEPTION: {type(exc).__name__}: {exc}")
        row = run_store.get_run(run_id, path=None)
        status["pipeline_status"] = getattr(row, "pipeline_status", None)
        status["cost_usd"] = getattr(row, "cost_usd", None)
        results.append(status)
        print(f"  pipeline_status={status['pipeline_status']} cost_usd={status['cost_usd']}")

    # A run "passes start-to-finish" if the pipeline reached a terminal
    # verdict — success / abort_* / partial_* all count (CLAUDE.md §9.3:
    # abort_* are pipeline verdicts, not errors). Only error_* / a missing
    # status (crash before any verdict) fails the rehearsal.
    failed = [
        r for r in results
        if not r["pipeline_status"] or str(r["pipeline_status"]).startswith("error_")
    ]
    total_cost = sum(r["cost_usd"] or 0.0 for r in results)
    print("-" * 64)
    print(f"rehearsal: {len(results) - len(failed)}/{len(results)} prompts "
          f"reached a terminal verdict; total cost_usd={total_cost:.4f}")
    if failed:
        print(f"RESULT: FAIL — {len(failed)} prompt(s) did not pass: "
              f"{[r['template'] for r in failed]}")
        raise SystemExit(1)
    print("RESULT: PASS — the full non-sovereign rehearsal path passed start-to-finish")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="POLARIS v6 OpenRouter rehearsal runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check-models", help="confirm V4 Pro + Gemma are available on OpenRouter")
    check.add_argument("--generator", default=DEFAULT_GENERATOR)
    check.add_argument("--evaluator", default=DEFAULT_EVALUATOR)
    check.set_defaults(func=cmd_check_models)

    run = sub.add_parser("run", help="run the fixed non-confidential prompt set")
    run.add_argument("--dry-run", action="store_true",
                     help="validate wiring only — no LLM call, no spend")
    run.add_argument("--only", default=None, help="run a single template")
    run.add_argument("--max-cost", default=DEFAULT_MAX_COST,
                     help="PG_MAX_COST_PER_RUN per run (default 5.00)")
    run.add_argument("--out-root", default=None, help="override POLARIS_V6_OUTPUT_ROOT")
    run.add_argument("--generator", default=DEFAULT_GENERATOR)
    run.add_argument("--evaluator", default=DEFAULT_EVALUATOR)
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
