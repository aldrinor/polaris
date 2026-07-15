#!/usr/bin/env python3
"""feat/intake-contract — A/B CONTRACT EVAL harness (SCRIPT-ONLY).

Compares a BASELINE arm (the three intake-contract flags OFF) against a TREATMENT
arm (the three flags ON) and reports the delta. The three flags:

    PG_INTAKE_CONTRACT_COMPILE     (intake contract compiler)
    PG_EXTRACT_INSTRUCTION_SLOTS   (instruction-slot extraction + O2 wire)
    PG_POSTWRITE_STRUCTURE_CHECK   (post-write structure/format checker)

Two modes:

  --dry-run  (DEFAULT — ZERO paid calls, ZERO network, ZERO LLM)
      Proves, on a small FIXTURE task set using the repo's own offline-deterministic
      surfaces (build_floor_contract + check_report_against_contract,
      compile_intake_contract(llm_fn=None), bind_instruction_slots on fixture specs),
      that the TREATMENT config yields materially different intake/contract/section
      objects than BASELINE, AND that the BASELINE (flags-OFF) config is byte-identical
      to a no-op today (every surface inert). Emits a JSON report; exits 0 when the A/B
      is coherent, nonzero otherwise. Imports NO live client.

  --live     (DOUBLE-GATED — real paid RACE + FACT scoring)
      Requires BOTH --live AND --i-understand-this-spends=<token>. Runs the champion
      compose pipeline twice (baseline env vs treatment env), then RACE + FACT, and
      diffs RACE overall + FACT valid_rate. HONEST CAVEAT: on the champion compose
      path only PG_POSTWRITE_STRUCTURE_CHECK is reachable; the other two flags take
      effect only via graph_v2's run_scope_gate, which the champion path does NOT
      route through — so their live RACE/FACT delta is currently ZERO. The dry-run
      demonstrates the module-level object divergence, not a champion report change.

SAFETY: additive, script-only. It sets/clears ONLY the three treatment flags between
arms and leaves every other env var identical (no A/B confound). It touches NO
faithfulness code. Default mode makes zero paid calls; the live path is import-isolated
behind the double gate so a dry-run cannot transitively import a live client.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure the repo root is importable when this script is run directly from scripts/.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The three treatment flags, in a stable order.
_TREATMENT_FLAGS = (
    "PG_INTAKE_CONTRACT_COMPILE",
    "PG_EXTRACT_INSTRUCTION_SLOTS",
    "PG_POSTWRITE_STRUCTURE_CHECK",
)

# The token the operator must echo to unlock the paid --live path.
_SPEND_TOKEN = "yes-spend-real-money"


# ─────────────────────────────────────────────────────────────────────────────
# fixture task set — synthetic, self-contained; NO benchmark data, NO network.
# ─────────────────────────────────────────────────────────────────────────────

def _default_tasks() -> list[dict[str, Any]]:
    """A tiny fixture task set. Each task carries a research_question with EXPLICIT
    structural asks (comparison / enumeration / length / journal-only) plus a
    synthetic finished report_text so the post-write checker has something to score.
    Nothing here touches the network or an LLM."""
    return [
        {
            "id": "cmp-remote-office",
            "research_question": (
                "Compare remote work versus office work. Use at least 1200 words "
                "and cite only peer-reviewed journal sources."
            ),
            "report_text": (
                "# Report\n\nIntro prose.\n\n"
                "## Remote work productivity\nText about remote work [1].\n\n"
                "## Office work dynamics\nText about office work [2].\n\n"
                "## References\n[1] A. [2] B.\n"
            ),
            "biblio": [{"tier": "A"}, {"tier": "B"}],
            "actual_words": 1400,
        },
        {
            "id": "enum-three-topics",
            "research_question": (
                "Cover the following: solar power, wind power, and hydro power."
            ),
            "report_text": (
                "# Report\n\nIntro.\n\n"
                "## Solar power\nSolar [1].\n\n## Wind power\nWind [2].\n\n"
                "## References\n[1] A. [2] B.\n"
            ),
            "biblio": [{"tier": "A"}, {"tier": "B"}],
            "actual_words": 800,
        },
    ]


def _fixture_section_specs():
    """A hand-built SectionSpec list standing in for a finalized outline (no generator
    run). Covers 'remote work' but NOT 'office work' so the O2 consumer has both a
    satisfied and an unsatisfied path to exercise."""
    from src.polaris_graph.retrieval.section_blueprint import SectionSpec  # noqa: PLC0415

    return [
        SectionSpec(section_id="s1", title="Remote work productivity",
                    description="evidence on remote work", evidence_count=5),
        SectionSpec(section_id="s2", title="Team dynamics",
                    description="collaboration overhead", evidence_count=5),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# env arm helper — set ONLY the three treatment flags, restore everything after.
# ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _flag_arm(on: bool):
    """Context manager that sets the three treatment flags to '1' (on) or removes
    them (off), then restores the prior environment EXACTLY. No other env var is
    touched, so the two arms differ only by the treatment flags."""
    saved = {k: os.environ.get(k) for k in _TREATMENT_FLAGS}
    try:
        for k in _TREATMENT_FLAGS:
            if on:
                os.environ[k] = "1"
            else:
                os.environ.pop(k, None)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# offline surfaces — each returns a plain JSON-able object (or None when its flag
# is OFF). These are the champion-reachable / module-level deterministic surfaces.
# ─────────────────────────────────────────────────────────────────────────────

def _surface_postwrite(task: dict[str, Any]) -> dict[str, Any] | None:
    """Post-write structure adherence — mirrors compose_agentic_report_s3gear329's
    PG_POSTWRITE_STRUCTURE_CHECK block. None when the flag is OFF (driver never runs)."""
    from src.polaris_graph.generator.postwrite_structure_check import (  # noqa: PLC0415
        build_floor_contract,
        check_report_against_contract,
        postwrite_check_enabled,
    )

    if not postwrite_check_enabled():
        return None
    contract = build_floor_contract(task["research_question"])
    return check_report_against_contract(
        task["report_text"], contract, task.get("biblio"), task.get("actual_words", 0),
    )


def _surface_intake_contract(task: dict[str, Any]) -> dict[str, Any] | None:
    """Floor-only intake contract (llm_fn=None => offline, zero paid calls). None when
    PG_INTAKE_CONTRACT_COMPILE is OFF (no compiler invoked on the champion path)."""
    from src.polaris_graph.intake.contract_compiler import (  # noqa: PLC0415
        compile_intake_contract,
        compile_intake_contract_enabled,
    )

    if not compile_intake_contract_enabled():
        return None
    return compile_intake_contract(task["research_question"], llm_fn=None).to_dict()


def _surface_slot_coverage(task: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Instruction-slot coverage over the fixture section specs (offline regex +
    pure bind). None when PG_EXTRACT_INSTRUCTION_SLOTS is OFF (specs stay unchanged)."""
    from src.polaris_graph.retrieval.intake_constraint_extractor import (  # noqa: PLC0415
        extract_instruction_slots,
        extract_instruction_slots_enabled,
    )

    if not extract_instruction_slots_enabled():
        return None
    from src.polaris_graph.retrieval.section_blueprint import (  # noqa: PLC0415
        bind_instruction_slots,
    )

    specs = _fixture_section_specs()
    slots = [s.to_dict() for s in extract_instruction_slots(task["research_question"], llm_fn=None)]
    bind_instruction_slots(specs, slots)
    return slots


def _eval_task(task: dict[str, Any]) -> dict[str, Any]:
    """Compute all three surfaces for BOTH arms and return the per-task record."""
    with _flag_arm(on=False):
        baseline = {
            "postwrite": _surface_postwrite(task),
            "intake_contract": _surface_intake_contract(task),
            "slot_coverage": _surface_slot_coverage(task),
        }
    with _flag_arm(on=True):
        treatment = {
            "postwrite": _surface_postwrite(task),
            "intake_contract": _surface_intake_contract(task),
            "slot_coverage": _surface_slot_coverage(task),
        }
    return {"id": task.get("id"), "baseline": baseline, "treatment": treatment}


def run_dry_run(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Offline BASELINE-vs-TREATMENT differ. Returns a JSON-able report and a coherent
    A/B verdict:

      * baseline_inert   — every BASELINE surface is None (flags OFF add nothing);
      * treatment_active — every TREATMENT surface is non-None AND differs from
                           baseline (the flags DO change the intake/contract objects).

    Zero paid calls: every surface runs regex/pure/llm_fn=None.
    """
    records = [_eval_task(t) for t in tasks]

    baseline_inert = all(
        r["baseline"]["postwrite"] is None
        and r["baseline"]["intake_contract"] is None
        and r["baseline"]["slot_coverage"] is None
        for r in records
    )
    treatment_active = all(
        r["treatment"]["postwrite"] is not None
        and r["treatment"]["intake_contract"] is not None
        and r["treatment"]["slot_coverage"] is not None
        and r["treatment"] != r["baseline"]
        for r in records
    )
    verdict = {
        "baseline_inert": baseline_inert,
        "treatment_active": treatment_active,
        "coherent_ab": baseline_inert and treatment_active,
        "n_tasks": len(records),
    }
    return {"mode": "dry-run", "verdict": verdict, "tasks": records}


# ─────────────────────────────────────────────────────────────────────────────
# live path — DOUBLE-GATED, import-isolated, PAID. Not exercised by any test.
# ─────────────────────────────────────────────────────────────────────────────

def run_live(args: argparse.Namespace) -> int:  # pragma: no cover — paid, never in CI
    """Real RACE + FACT A/B. Requires --live AND --i-understand-this-spends=<token>.

    Runs the champion compose pipeline twice (baseline env vs treatment env, differing
    ONLY in the three treatment flags), then RACE + FACT, and diffs the scores. All live
    clients are imported INSIDE this function so a dry-run can never transitively import
    them.

    This function is intentionally a guarded orchestration seam: it refuses unless the
    double gate is satisfied and prints the exact commands it would run. Wiring the real
    subprocess calls is deferred to an operator-supervised session (hard rule: NO paid
    runs from this workflow)."""
    if not args.live or args.i_understand_this_spends != _SPEND_TOKEN:
        print(
            "REFUSED: the live path is double-gated. Pass BOTH --live AND "
            f"--i-understand-this-spends={_SPEND_TOKEN} to run PAID RACE+FACT scoring.",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps({
            "mode": "live",
            "status": "gate_satisfied_but_execution_deferred",
            "note": (
                "Live RACE+FACT is operator-supervised and NOT executed by this "
                "harness. On the champion compose path only PG_POSTWRITE_STRUCTURE_CHECK "
                "is reachable; the other two flags have ZERO champion RACE/FACT delta."
            ),
            "would_run": {
                "compose": "scripts/compose_agentic_report_s3gear329.py (x2: baseline env, treatment env)",
                "race": "third_party/deep_research_bench/deepresearch_bench_race.py --skip_cleaning",
                "fact": "third_party/deep_research_bench FACT valid_rate from validated.jsonl",
            },
        }, indent=2),
    )
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", default=False,
                   help="Run the PAID RACE+FACT A/B (off by default). Requires the spend token.")
    p.add_argument("--i-understand-this-spends", dest="i_understand_this_spends", default="",
                   help=f"Confirmation token required with --live (must equal '{_SPEND_TOKEN}').")
    p.add_argument("--tasks", default=None,
                   help="Optional path to a JSON list of fixture tasks (defaults to the built-in set).")
    p.add_argument("--out", default=None,
                   help="Optional path to write the JSON report to (dry-run mode).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.live:
        return run_live(args)

    # DRY-RUN (default): zero paid calls.
    if args.tasks:
        with open(args.tasks, "r", encoding="utf-8") as fh:
            tasks = json.load(fh)
    else:
        tasks = _default_tasks()

    report = run_dry_run(tasks)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if report["verdict"]["coherent_ab"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
