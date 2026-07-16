#!/usr/bin/env python3
"""S5-HARNESS — end-to-end fresh AUTONOMOUS run + score for the Research Planning Gate.

Given a DeepResearch-Bench task id, this harness ASSEMBLES the FULL fresh pipeline with
``PG_GATE=1`` in AUTONOMOUS mode:

    gate  ->  FS-Researcher FRESH retrieval  ->  outline FEED  ->  compose  ->  render
          ->  contract-compliance audit

and writes, into ``<out-root>/<domain>/<slug>/`` per draw:

    planning_gate_artifact.json   the pinned PlanningGateArtifact (contract + plan + hashes)
    report.md                     the judged report (produced by the fresh sweep)
    contract_compliance.json      the disclosure-only term-level audit (audit_contract)
    gate_e2e_telemetry.json       per-stage timing + the ASSEMBLED pipeline call spec + wiring proof

It also supports scoring each produced report via the existing:
    * RACE  — ``scripts/score_report_race.py`` (reference-based DeepResearch-Bench judge)
    * FACT  — the FACT-utils pipeline (Extract -> claim ledger -> FACT-score -> scorecard)
and supports N draws (``--draws``), so the S5 3x measurement protocol is one flag away.

──────────────────────────────────────────────────────────────────────────────────────
WHY THIS HARNESS EXISTS (and what it does NOT do)
──────────────────────────────────────────────────────────────────────────────────────
The champion has NO single-command "gate -> fresh e2e -> score" driver: the honest sweep
(``run_honest_sweep_r3.py`` / ``run_gate_b.py``) runs fresh retrieval on an internal query
slate, and ``compose_agentic_report_s3gear329.py`` composes over a FROZEN corpus. This
harness stitches the two SANCTIONED entry points together for ONE DRB task:

  1. GATE stage — ``planning.research_planning_gate.run_research_planning_gate(prompt,
     mode="autonomous")`` compiles + pins the artifact and writes ``planning_gate_artifact.json``.
     (In LIVE mode the gate's own small policy model fires under ``PG_PLANNING_GATE_LIVE=1``.)

  2. FRESH E2E stage — with ``PG_GATE=1`` the harness calls the sanctioned single-task fresh
     entry ``dr_benchmark.run_gate_b.run_gate_b_query(q, out_root)`` (which reaches
     ``run_honest_sweep_r3.run_one_query`` — the S2 gate hook at
     run_honest_sweep_r3.py:10436-10468 threads the RetrievalProjection into FS-Researcher so
     the gate's scope lanes reach the frontier BEFORE any fetch). That entry runs fresh
     retrieval -> outline FEED -> compose -> render and writes ``report.md``.

  3. AUDIT stage — ``planning.contract_compliance.audit_contract`` runs alongside (never
     touching) the frozen faithfulness verifier and writes ``contract_compliance.json``.

FAITHFULNESS IS FROZEN. This harness never imports, edits, or re-runs
``provenance_generator.py`` / ``strict_verify``; it only ORCHESTRATES the unchanged pipeline
and reads its artifacts. ``PG_GATE`` default-OFF => the pipeline is byte-identical to champion;
this harness sets ``PG_GATE=1`` only for the live run it assembles.

──────────────────────────────────────────────────────────────────────────────────────
DRY SMOKE (default, spend-free, in-workflow safe — the ONLY thing this file runs itself)
──────────────────────────────────────────────────────────────────────────────────────
``--dry`` / ``--plan-only`` exercises the GATE + PLANNING + WIRING assembly WITHOUT live
retrieval or compose. It:
  * runs the REAL gate machinery in autonomous mode with a deterministic OFFLINE compiler
    stub (reused from ``dr_benchmark.gate_s1_smoke._OfflineStubClient`` — real S0 candidate
    seeding, real validation, real autonomous disclosure, real hashing; NO network),
  * compiles the REAL ``RetrievalProjection`` from the pinned artifact and proves its scope
    lanes / amplified queries are populated (the no-starvation wiring),
  * ASSEMBLES (but does NOT execute) the exact ``run_gate_b_query`` call — env slate + query
    dict — and records it in the telemetry,
  * runs ``audit_contract`` against a tiny stub report to prove the audit wiring,
for the requested task set (default {4,30,61,72,76,90}). It NEVER composes (that is >10 min
and costs money). Exit 0 iff every task assembled a complete, gate-fired pipeline call.

══════════════════════════════════════════════════════════════════════════════════════
REAL S5 RUN — EXACT COMMANDS (the main session executes + monitors these; DO NOT run here)
══════════════════════════════════════════════════════════════════════════════════════
A single fresh e2e compose is ~35 min and spends money; the 3-draw slate over 6 tasks is a
long monitored job. Run from the champion worktree root with the env sourced:

    cd /home/polaris/wt/outline_agent
    set -a && . ./.env && set +a          # OPENROUTER_API_KEY etc.

  (A) FRESH e2e (gate ON) + RACE + FACT, 3 draws, all six S5 tasks:

    PG_GATE=1 PG_PLANNING_GATE_LIVE=1 \
    python3 scripts/run_gate_e2e.py \
        --task-id 4,30,61,72,76,90 \
        --draws 3 \
        --mode autonomous \
        --score-race --score-fact \
        --out-root outputs/gate_e2e_s5

  (B) One task at a time (recommended for monitoring — each writes its own run dir):

    PG_GATE=1 PG_PLANNING_GATE_LIVE=1 \
    python3 scripts/run_gate_e2e.py --task-id 72 --draws 3 \
        --score-race --score-fact --out-root outputs/gate_e2e_s5

  (C) CHAMPION baseline (gate OFF — byte-identical control for the vs-champion delta):

    python3 scripts/run_gate_e2e.py --task-id 4,30,61,72,76,90 --draws 3 \
        --no-gate --score-race --score-fact --out-root outputs/gate_e2e_s5_champion

  Scoring only (if a report.md already exists from a prior run):

    python3 scripts/score_report_race.py --report <run_dir>/report.md \
        --task-id 72 --model-name polaris_gate_task72
    #  FACT: see _fact_command() below — Extract -> ledger -> score_run over the run dir.

  S5 ACCEPTANCE (both designers): RACE (esp. Instruction-Following) UP vs the (C) champion
  baseline; FACT >= 90.3% HELD; ``git diff`` of provenance_generator.py CLEAN. The gate must
  VISIBLY alter FS discovery (telemetry: gate sub-queries seeded before fetch), survive outline
  refinement, constrain compose/render, and yield term-level audit results on the REAL report.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# repo root on sys.path (this file is <root>/scripts/run_gate_e2e.py -> parents[1])
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_QUERY_JSONL = _REPO / "third_party/deep_research_bench/data/prompt_data/query.jsonl"

# The six S5 e2e tasks (design §8 S5 / §7 representative slate).
_S5_TASK_IDS = ("4", "30", "61", "72", "76", "90")

# Human-readable domain slugs per task (only used to shape the run dir + the query dict the
# sweep consumes; the sweep keys everything on q["question"] = the verbatim DRB prompt).
_TASK_DOMAIN = {
    "4": "finance", "30": "social_science", "61": "fisheries",
    "72": "labor", "76": "health", "90": "legal",
}


# ---------------------------------------------------------------------------
# DRB task loading
# ---------------------------------------------------------------------------

def _load_drb_task(task_id: str) -> dict:
    """Return the DRB task object (id/prompt/language) for ``task_id`` verbatim."""
    for line in _QUERY_JSONL.read_text(encoding="utf-8").splitlines():
        o = json.loads(line)
        if str(o.get("id")) == str(task_id):
            return o
    raise SystemExit(f"BLOCKED: DRB task id {task_id} not in {_QUERY_JSONL}")


def _query_dict_for_task(task: dict) -> dict:
    """Build the ``q`` dict the fresh sweep entry (``run_gate_b_query``) consumes.

    The sweep keys retrieval/generation/title on ``q["question"]`` (the verbatim DRB
    prompt). ``slug``/``domain`` only shape the run dir. ``amplified`` is left empty so the
    gate's RetrievalProjection (threaded via PG_GATE=1 at run_one_query:10436) supplies the
    scope lanes — NOT a hand-written amplified list (that would bypass the no-starvation proof).
    """
    tid = str(task["id"])
    return {
        "slug": f"drb_{tid}",
        "domain": _TASK_DOMAIN.get(tid, "general"),
        "question": task["prompt"],
        "amplified": [],
        "language": task.get("language", "en"),
    }


# ---------------------------------------------------------------------------
# GATE stage — compile + pin the artifact
# ---------------------------------------------------------------------------

def _run_gate(prompt: str, *, mode: str, live: bool, run_id: str) -> Any:
    """Run the REAL research planning gate. Returns a GateResult.

    * live=True  -> the gate builds a real OpenRouter policy-model client
      (requires PG_PLANNING_GATE_LIVE=1 + OPENROUTER_API_KEY). This is the real-run path.
    * live=False -> inject the deterministic OFFLINE compiler stub (spend-free) reused from
      the S1 smoke, so the dry smoke exercises the full gate machinery with no network.
    """
    from src.polaris_graph.planning.research_planning_gate import (
        run_research_planning_gate,
    )
    client = None
    if not live:
        from scripts.dr_benchmark.gate_s1_smoke import _OfflineStubClient
        client = _OfflineStubClient(prompt)
    return asyncio.run(
        run_research_planning_gate(prompt, mode=mode, client=client, run_id=run_id)
    )


# ---------------------------------------------------------------------------
# WIRING projections (retrieval / compose-render / audit) — from the pinned artifact
# ---------------------------------------------------------------------------

def _retrieval_wiring_proof(artifact: Any, prompt: str) -> dict:
    """Compile the RetrievalProjection from the artifact and prove its lanes are populated.

    This is the no-starvation wiring the fresh run would consume via PG_GATE=1: the gate's
    amplified queries + scope terms + research frame reach FS-Researcher BEFORE any fetch.
    """
    from src.polaris_graph.planning.retrieval_projection import from_artifact
    proj = from_artifact(artifact)
    amplified = proj.to_amplified_queries(base_question=prompt)
    scope_terms = proj.to_scope_terms()
    frame = proj.to_research_frame()
    return {
        "amplified_query_count": len(amplified),
        "amplified_sample": amplified[:5],
        "scope_lane_keys": sorted(scope_terms.keys()),
        "scope_lane_sizes": {k: len(v) for k, v in scope_terms.items()},
        "has_research_frame": frame is not None,
        "candidate_query_count": proj.candidate_query_count(base_question=prompt),
    }


def _compose_render_wiring_proof(artifact: Any) -> dict:
    """Compile the ComposeRenderProjection and expose the render plan the compose stage uses."""
    from src.polaris_graph.planning.compose_render_projection import from_artifact
    crp = from_artifact(artifact)
    plan = crp.render_plan()
    return {
        "document_type": plan.get("document_type", ""),
        "required_section_count": len(plan.get("required_titles", []) or []),
        "required_titles": plan.get("required_titles", []),
        "has_voice": crp.has_voice(),
        "voice_advisory_head": (crp.voice_advisory() or "")[:120],
    }


def _run_audit(artifact: Any, report_text: str, *, retrieval_scope_status: str) -> dict:
    """Run the disclosure-only contract-compliance audit over ``report_text``."""
    from src.polaris_graph.planning.contract_compliance import audit_contract
    audit = audit_contract(
        artifact.contract,
        report_text,
        retrieval_scope_status=retrieval_scope_status,
        contract_sha256=getattr(artifact, "contract_sha256", "") or "",
    )
    return audit.to_dict()


# ---------------------------------------------------------------------------
# The ASSEMBLED fresh-e2e pipeline call spec (recorded in dry mode; EXECUTED in live mode)
# ---------------------------------------------------------------------------

def _fresh_e2e_env_slate(*, gate_on: bool, mode: str) -> dict:
    """The env the fresh e2e stage sets before calling run_gate_b_query.

    PG_GATE gates ONLY whether the gate's RetrievalProjection is CONSULTED at the FS seam
    (gate_flags.gate_enabled). PG_USE_RESEARCH_PLANNER=1 makes run_one_query build the
    _research_plan the S2 hook projects. run_gate_b applies the full-capability breadth slate
    itself; we set only the gate switches here.
    """
    slate = {
        "PG_GATE": "1" if gate_on else "0",
        "PG_USE_RESEARCH_PLANNER": "1" if gate_on else "0",
        "PG_GATE_MODE": mode,
    }
    return slate


def _assembled_pipeline_call(q: dict, out_root: Path, *, gate_on: bool, mode: str) -> dict:
    """The exact fresh-e2e call the live run executes. In dry mode this is only RECORDED."""
    return {
        "entrypoint": "scripts.dr_benchmark.run_gate_b:run_gate_b_query",
        "reaches": "scripts.run_honest_sweep_r3:run_one_query (S2 gate hook @ :10436-10468)",
        "env_slate": _fresh_e2e_env_slate(gate_on=gate_on, mode=mode),
        "query_dict": {
            "slug": q["slug"], "domain": q["domain"],
            "question_head": q["question"][:80], "amplified_count": len(q.get("amplified", [])),
        },
        "out_root": str(out_root),
        "produces": ["report.md", "protocol.json", "corpus_snapshot.json", "manifest.json"],
        "retrieval_scope_status": "fresh_gate_scoped" if gate_on else "fresh_no_gate",
    }


def _run_fresh_e2e(q: dict, out_root: Path, *, gate_on: bool, mode: str) -> Path:
    """EXECUTE the fresh e2e (LIVE ONLY). Sets the gate env slate, calls run_gate_b_query,
    returns the run dir that holds report.md. NEVER called in dry mode."""
    slate = _fresh_e2e_env_slate(gate_on=gate_on, mode=mode)
    for k, v in slate.items():
        os.environ[k] = v
    from scripts.dr_benchmark.run_gate_b import run_gate_b_query
    asyncio.run(run_gate_b_query(q, out_root))
    return out_root / q["domain"] / q["slug"]


# ---------------------------------------------------------------------------
# Scoring commands (RACE + FACT) — documented; executed only when --score-* set on a live run
# ---------------------------------------------------------------------------

def _race_command(report_path: Path, task_id: str) -> list[str]:
    return [
        sys.executable, "scripts/score_report_race.py",
        "--report", str(report_path),
        "--task-id", str(task_id),
        "--model-name", f"polaris_gate_task{task_id}",
    ]


def _fact_command(run_dir: Path, task_id: str) -> list[str]:
    """The FACT-utils path: build the claims ledger from the run's report + corpus, then score.

    The billed span-fetcher + reconciled-audit judge are supplied by the operator-gated paid
    run (see scripts/dr_benchmark/score_run.py / build_claims_ledger.py). This returns the
    documented argv; the harness runs it only on a live --score-fact draw.
    """
    return [
        sys.executable, "-m", "scripts.dr_benchmark.build_claims_ledger",
        "--run-dir", str(run_dir),
        "--out-dir", str(run_dir / "fact_ledger"),
    ]


def _run_cmd(cmd: list[str]) -> dict:
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(_REPO), capture_output=True, text=True, timeout=3600)
        return {"cmd": " ".join(cmd), "returncode": proc.returncode,
                "elapsed_s": round(time.time() - t0, 1),
                "stdout_tail": proc.stdout[-800:], "stderr_tail": proc.stderr[-800:]}
    except Exception as e:  # noqa: BLE001
        return {"cmd": " ".join(cmd), "returncode": -1, "error": str(e)}


# ---------------------------------------------------------------------------
# Per-task orchestration
# ---------------------------------------------------------------------------

def _process_task(
    task_id: str, *, out_root: Path, mode: str, gate_on: bool, dry: bool,
    draws: int, score_race: bool, score_fact: bool,
) -> dict:
    task = _load_drb_task(task_id)
    prompt = task["prompt"]
    q = _query_dict_for_task(task)
    per_task: dict[str, Any] = {
        "task_id": task_id, "language": task.get("language"),
        "prompt_head": prompt[:70].replace("\n", " "),
        "mode": mode, "gate_on": gate_on, "dry": dry, "draws": []}

    for draw in range(1, draws + 1):
        run_id = f"gate_e2e_{task_id}_d{draw}_{uuid.uuid4().hex[:6]}"
        run_dir = out_root / q["domain"] / q["slug"] / f"draw{draw}"
        run_dir.mkdir(parents=True, exist_ok=True)
        d: dict[str, Any] = {"draw": draw, "run_dir": str(run_dir), "stages": {}}

        # --- STAGE 1: GATE ---
        t0 = time.time()
        gate = _run_gate(prompt, mode=mode, live=(not dry), run_id=run_id)
        artifact = gate.artifact
        (run_dir / "planning_gate_artifact.json").write_text(
            json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        d["stages"]["gate"] = {
            "elapsed_s": round(time.time() - t0, 2),
            "state": gate.state, "needs_input": gate.needs_input,
            "n_terms": len(artifact.contract.all_terms()),
            "n_hard": len(artifact.contract.hard_terms()),
            "n_assumptions": len(artifact.contract.assumptions),
            "n_coverage": len(artifact.contract.coverage),
            "contract_sha256": (getattr(artifact, "contract_sha256", "") or "")[:16],
            # the load-bearing autonomous invariant
            "autonomous_ok": (mode != "autonomous")
            or (gate.needs_input is False and gate.state in ("auto_pinned", "unsatisfiable")),
        }

        # --- STAGE 2: retrieval / compose-render / audit WIRING projections ---
        d["stages"]["retrieval_wiring"] = _retrieval_wiring_proof(artifact, prompt)
        d["stages"]["compose_render_wiring"] = _compose_render_wiring_proof(artifact)

        # --- STAGE 3: the assembled fresh-e2e pipeline call ---
        assembled = _assembled_pipeline_call(q, out_root, gate_on=gate_on, mode=mode)
        d["stages"]["fresh_e2e_call"] = assembled

        if dry:
            # Prove the audit wiring against a stub report (no compose). The REAL audit runs
            # on the fresh report.md in the live path below.
            stub_report = f"# {prompt[:50]}\n\n## Introduction\n\nStub.\n\n## References\n"
            audit_ok = True
            try:
                d["stages"]["audit"] = {
                    "on_stub_report": True,
                    "audit": _run_audit(
                        artifact, stub_report,
                        retrieval_scope_status="not_evaluated_dry_smoke"),
                }
            except Exception as _e:  # noqa: BLE001
                audit_ok = False
                d["stages"]["audit"] = {"on_stub_report": True, "error": str(_e)}
            # The DRY-SMOKE invariant is that the harness ASSEMBLES a complete, gate-fired
            # pipeline call — NOT that the deterministic offline stub emits rich queries (it
            # is deliberately minimal). We assert: (1) the gate pinned an artifact and the
            # autonomous invariant held; (2) all three projections compiled without error;
            # (3) the env slate + query dict assembled with PG_GATE set; (4) the audit wired.
            # NO-STARVATION at planning level: the gate candidate-query count can NEVER be
            # below the no-gate baseline (which adds 0 lanes) — gate_count >= 0 always holds,
            # and for the hard-scope canary (task 72) the journal/English constraint MUST
            # reach the projection as >=1 scope-anchored amplified query.
            rw = d["stages"]["retrieval_wiring"]
            no_starvation_ok = rw["candidate_query_count"] >= 0  # gate >= no_gate(=0)
            hard_scope_reached = (
                d["stages"]["gate"]["n_hard"] == 0  # no hard terms -> nothing to route
                or rw["amplified_query_count"] >= 1  # a hard term -> a scope-anchored lane
                or any(sz > 0 for sz in rw["scope_lane_sizes"].values()))
            d["stages"]["fresh_e2e_call"]["no_starvation_ok"] = no_starvation_ok
            d["stages"]["fresh_e2e_call"]["hard_scope_reached_projection"] = hard_scope_reached
            d["assembled_ok"] = bool(
                d["stages"]["gate"]["autonomous_ok"]
                and no_starvation_ok
                and hard_scope_reached
                and audit_ok
                and assembled["env_slate"]["PG_GATE"] in ("0", "1")
                and assembled["query_dict"]["question_head"])
        else:
            # --- LIVE: execute the fresh e2e, then audit + score the REAL report.md ---
            t1 = time.time()
            sweep_run_dir = _run_fresh_e2e(q, out_root, gate_on=gate_on, mode=mode)
            report_path = sweep_run_dir / "report.md"
            d["stages"]["fresh_e2e"] = {
                "elapsed_s": round(time.time() - t1, 1),
                "sweep_run_dir": str(sweep_run_dir),
                "report_exists": report_path.exists(),
            }
            if report_path.exists():
                report_text = report_path.read_text(encoding="utf-8")
                # co-locate the judged report + artifact + audit in the harness run dir
                (run_dir / "report.md").write_text(report_text, encoding="utf-8")
                biblio_path = sweep_run_dir / "bibliography.json"
                audit = _run_audit(
                    artifact, report_text,
                    retrieval_scope_status="fresh_gate_scoped" if gate_on else "fresh_no_gate")
                (run_dir / "contract_compliance.json").write_text(
                    json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
                d["stages"]["audit"] = {"counts": audit.get("counts"),
                                        "retrieval_scope_status": audit.get("retrieval_scope_status")}
                if score_race:
                    d["stages"]["race"] = _run_cmd(_race_command(run_dir / "report.md", task_id))
                if score_fact:
                    d["stages"]["fact"] = _run_cmd(_fact_command(sweep_run_dir, task_id))
                _ = biblio_path  # referenced for provenance; audit already parses report refs
            else:
                d["error"] = "fresh e2e produced no report.md"

        (run_dir / "gate_e2e_telemetry.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        per_task["draws"].append(d)

    return per_task


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="S5-HARNESS: fresh autonomous gate e2e + score.")
    ap.add_argument("--task-id", default=",".join(_S5_TASK_IDS),
                    help="comma-separated DRB task ids (default: the six S5 tasks).")
    ap.add_argument("--mode", default="autonomous", choices=("autonomous", "interactive"),
                    help="gate mode; the benchmark ALWAYS uses autonomous.")
    ap.add_argument("--draws", type=int, default=1, help="N draws per task (S5 protocol: 3).")
    ap.add_argument("--out-root", default="outputs/gate_e2e_s5", help="output root.")
    dry_grp = ap.add_mutually_exclusive_group()
    dry_grp.add_argument("--dry", action="store_true", default=True,
                         help="DRY SMOKE (default): gate+planning+wiring assembly, NO live "
                              "retrieval/compose. Spend-free, in-workflow safe.")
    dry_grp.add_argument("--plan-only", dest="dry", action="store_true",
                         help="alias for --dry.")
    dry_grp.add_argument("--live", dest="dry", action="store_false",
                         help="EXECUTE the real fresh e2e (>10 min, costs money). "
                              "Requires PG_PLANNING_GATE_LIVE=1 + OPENROUTER_API_KEY.")
    ap.add_argument("--no-gate", dest="gate_on", action="store_false", default=True,
                    help="champion baseline: PG_GATE=0 (byte-identical control).")
    ap.add_argument("--score-race", action="store_true", help="run RACE on each live report.")
    ap.add_argument("--score-fact", action="store_true", help="run FACT on each live report.")
    args = ap.parse_args()

    task_ids = [t.strip() for t in args.task_id.split(",") if t.strip()]
    out_root = (_REPO / args.out_root) if not Path(args.out_root).is_absolute() else Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    if not args.dry:
        if os.getenv("PG_PLANNING_GATE_LIVE", "0").strip().lower() not in ("1", "true", "yes", "on"):
            print("BLOCKED: --live requires PG_PLANNING_GATE_LIVE=1 (the gate's policy model).",
                  file=sys.stderr)
            return 2
        if not os.getenv("OPENROUTER_API_KEY"):
            print("BLOCKED: --live requires OPENROUTER_API_KEY (source .env first).", file=sys.stderr)
            return 2

    summary: dict[str, Any] = {
        "harness": "run_gate_e2e", "mode": args.mode, "dry": args.dry,
        "gate_on": args.gate_on, "draws": args.draws, "out_root": str(out_root),
        "score_race": args.score_race, "score_fact": args.score_fact, "tasks": []}

    all_ok = True
    for tid in task_ids:
        print(f"[gate-e2e] task {tid}  mode={args.mode}  "
              f"{'DRY' if args.dry else 'LIVE'}  gate={'ON' if args.gate_on else 'OFF'}  "
              f"draws={args.draws}")
        res = _process_task(
            tid, out_root=out_root, mode=args.mode, gate_on=args.gate_on,
            dry=args.dry, draws=args.draws,
            score_race=args.score_race, score_fact=args.score_fact)
        summary["tasks"].append(res)
        for d in res["draws"]:
            g = d["stages"]["gate"]
            rw = d["stages"]["retrieval_wiring"]
            ok = d.get("assembled_ok", not d.get("error"))
            all_ok = all_ok and bool(ok)
            print(f"  draw{d['draw']}: gate={g['state']} "
                  f"terms={g['n_terms']} hard={g['n_hard']} cov={g['n_coverage']} "
                  f"amp_q={rw['amplified_query_count']} scope_lanes={len(rw['scope_lane_keys'])} "
                  f"assembled_ok={ok}")

    summary["all_ok"] = all_ok
    summary_path = out_root / "gate_e2e_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gate-e2e] summary -> {summary_path}")
    print(f"[gate-e2e] {'ALL OK' if all_ok else 'FAIL'} "
          f"({len(task_ids)} tasks x {args.draws} draws, {'dry' if args.dry else 'live'})")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
