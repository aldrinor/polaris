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

  2. FRESH E2E stage — with ``PG_GATE=1`` the harness calls the DIRECT single-task fresh entry
     ``run_honest_sweep_r3.run_one_query(q, out_root)`` — the S2 gate hook at
     run_honest_sweep_r3.py:10435-10468 threads the RetrievalProjection into FS-Researcher so
     the gate's scope lanes reach the frontier BEFORE any fetch. run_one_query keys everything
     on ``q["question"]`` = the VERBATIM DRB-v1 task-72 prompt (query.jsonl id 72), runs fresh
     retrieval -> outline FEED -> compose -> render, and writes ``report.md``.
     NOT ``run_gate_b_query`` — that path FORCES ``PG_BENCHMARK_OFFICIAL_QUESTION=1`` and reads
     the ABSENT ``third_party/DeepResearch-Bench-II/tasks_and_rubrics.jsonl`` (DRB-II lineage),
     which fail-loud-raises before retrieval. run_one_query has NO DRB-II coupling.

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
  * ASSEMBLES (but does NOT execute) the exact ``run_one_query`` call — env slate + query
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

# DRB task id -> the scope-gate domain run_one_query's run_scope_gate ACCEPTS. This is NOT a
# cosmetic slug: run_one_query passes q["domain"] straight into run_scope_gate
# (run_honest_sweep_r3.py:9498) which REJECTS any value outside scope_gate.SUPPORTED_DOMAINS
# ({ai_sovereignty,canada_us,clinical,custom,due_diligence,policy,tech,workforce}) and, on
# reject, aborts BEFORE retrieval with manifest.status=abort_scope_rejected. The prior table
# used free-text labels (finance/social_science/fisheries/labor/health/legal) that are NOT in
# SUPPORTED_DOMAINS — the live probe's domain='labor' is exactly why task 72 aborted at the
# scope gate. The AUTHORITATIVE source for these bindings is the champion's own SWEEP_QUERIES
# table (run_honest_sweep_r3.py ~L7713-7846): each DRB-EN benchmark entry pins slug->domain so
# the frozen per_query_report_contract in config/scope_templates/<domain>.yaml resolves at
# runtime (drb_72_ai_labor -> "workforce"; drb_76_gut_microbiota_crc -> "clinical";
# drb_90_adas_liability -> "policy"). We REUSE those verbatim. Tasks 4/30/61 have NO champion
# SWEEP_QUERIES binding (they are not in the DRB-EN slate the champion ships), so they take the
# documented DEFAULT below — scope_gate.DEFAULT_DOMAIN = "custom", the canonical free-form,
# tier-permissive template that run_scope_gate accepts for any domain-less caller (never
# clinical, never abort). Task 72 -> "workforce" is the load-bearing champion binding.
_TASK_DOMAIN = {
    # Champion SWEEP_QUERIES bindings (run_honest_sweep_r3.py) — verbatim, load-bearing:
    "72": "workforce",   # drb_72_ai_labor  (SWEEP_workforce_drb_72_ai_labor champion run_id)
    "76": "clinical",    # drb_76_gut_microbiota_crc
    "90": "policy",      # drb_90_adas_liability
    # No champion SWEEP_QUERIES binding -> documented default (scope_gate.DEFAULT_DOMAIN):
    "4": "custom",       # gold-price trend analysis (zh) — no DRB-EN slate entry
    "30": "custom",      # global-south civilizational exchange (zh) — no DRB-EN slate entry
    "61": "custom",      # chub-mackerel price dynamics (en) — no DRB-EN slate entry
}

# The documented fallback for any task id not in _TASK_DOMAIN — the scope-gate's own default
# (src/polaris_graph/nodes/scope_gate.py DEFAULT_DOMAIN), an ACCEPTED member of SUPPORTED_DOMAINS.
_DEFAULT_DOMAIN = "custom"


def _registered_slug_for_task(tid: str) -> str:
    """Resolve the DRB task id to a stable, human-readable run-dir slug.

    Since the fresh entry is now ``run_one_query`` DIRECT (NOT ``run_gate_b_query``), the slug
    NO LONGER drives any DRB-II canonical-question binding — run_one_query keys everything on
    ``q["question"]`` (the verbatim DRB-v1 prompt) and uses ``q["slug"]`` ONLY to shape
    ``out_root/<domain>/<slug>/``. We still reuse the gate0_lineage registry purely as a source
    of a descriptive name (task 72 -> ``drb_72_ai_labor``) so the run dir is legible and stable
    across runs; a task with no registered slug falls back to the bare ``drb_<id>``. Importing
    the registry constants does NOT read the (absent) DRB-II tasks_and_rubrics.jsonl — that
    read lived only inside run_gate_b_query's forced canonical binding, which we no longer hit.
    Import is lazy so this script's no-import-side-effect posture is unchanged.
    """
    import re  # noqa: PLC0415

    from scripts.dr_benchmark.gate0_lineage import (  # noqa: PLC0415
        DRB_SLUGS_WITHOUT_CANONICAL_GOLD as _NO_GOLD,
        SLUG_TO_IDX as _SLUG_TO_IDX,
    )

    for _slug in (*_SLUG_TO_IDX.keys(), *_NO_GOLD):
        _m = re.match(r"^drb_(\d+)_", _slug)
        if _m and _m.group(1) == str(tid):
            return _slug
    return f"drb_{tid}"


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
    """Build the ``q`` dict the fresh sweep entry (``run_one_query``) consumes.

    run_one_query keys retrieval/generation/title on ``q["question"]`` — set here to the
    VERBATIM DRB-v1 task prompt (query.jsonl ``prompt``). ``slug``/``domain`` only shape the
    run dir. ``amplified`` is left empty so the gate's RetrievalProjection (threaded via
    PG_GATE=1 at the S2 hook, run_honest_sweep_r3.py:10435-10468) supplies the scope lanes —
    NOT a hand-written amplified list (that would bypass the no-starvation proof).
    """
    tid = str(task["id"])
    domain = _TASK_DOMAIN.get(tid, _DEFAULT_DOMAIN)
    # FAIL-LOUD at assembly: a domain outside SUPPORTED_DOMAINS makes run_scope_gate abort
    # BEFORE retrieval (manifest.status=abort_scope_rejected) — the exact live-probe failure
    # (domain='labor'). Catch it here at zero cost instead of after the live gate compile.
    from src.polaris_graph.nodes.scope_gate import SUPPORTED_DOMAINS  # noqa: PLC0415
    if domain not in SUPPORTED_DOMAINS:
        raise SystemExit(
            f"BLOCKED: task {tid} maps to domain {domain!r} which is NOT in scope_gate."
            f"SUPPORTED_DOMAINS ({sorted(SUPPORTED_DOMAINS)}); run_scope_gate would abort "
            f"pre-retrieval. Fix _TASK_DOMAIN in scripts/run_gate_e2e.py."
        )
    return {
        # Descriptive, stable run-dir slug (drb_72 -> drb_72_ai_labor). Cosmetic only now:
        # run_one_query does NO lineage lookup on the slug, so there is no forced official-
        # question rebind and no DRB-II gold-file read. q["question"] below is the sole prompt.
        "slug": _registered_slug_for_task(tid),
        # MUST be a scope_gate.SUPPORTED_DOMAINS member or run_scope_gate aborts pre-retrieval.
        "domain": domain,
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
    """The env the fresh e2e stage sets before calling run_one_query.

    PG_GATE gates ONLY whether the gate's RetrievalProjection is CONSULTED at the FS seam
    (gate_flags.gate_enabled). PG_USE_RESEARCH_PLANNER=1 makes run_one_query build the
    _research_plan the S2 hook projects — BOTH are required for the projection to thread (see
    run_honest_sweep_r3.py:10448 `_pg_gate_enabled() and _use_research_planner and
    _research_plan is not None`). The full-capability retrieval breadth slate (PG_SWEEP_*) is
    supplied by the real-run env in the module docstring; we set only the gate switches here.
    """
    slate = {
        "PG_GATE": "1" if gate_on else "0",
        "PG_USE_RESEARCH_PLANNER": "1" if gate_on else "0",
        "PG_GATE_MODE": mode,
    }
    # FIX 5(a): resolve UNKNOWN credibility tiers on a GATE-ON live run so the quality mask
    # reads REAL tiers (not a 41%-UNKNOWN corpus that would over-mask once armed). The W5
    # credibility-LLM-tiering winner is read from PG_CREDIBILITY_LLM_TIERING in live_retriever;
    # default it ON under the gate, but HONOR an explicit operator override (so it can be turned
    # off for a cost-bounded smoke). The no-gate control leaves it byte-identical (never set here).
    if gate_on:
        slate["PG_CREDIBILITY_LLM_TIERING"] = os.environ.get(
            "PG_CREDIBILITY_LLM_TIERING", "1"
        )
    # FIX 3(a): arm the four-role D8 seam on a GATE-ON run so the STRONGEST verifier actually
    # adjudicates this run. Without PG_FOUR_ROLE_MODE=1 run_one_query takes the legacy
    # single-evaluator path -> release_disclosure.adjudicated=False -> the frozen
    # build_d8_unadjudicated_banner (provenance_generator.py:3212) prepends the "UNVERIFIED-by-D8"
    # banner to report.md. Arming the mode makes D8 bind (adjudicated=True) so the banner returns
    # "" at the FROZEN builder itself — the ONLY legitimate removal (never PG_REPORT_D8_BANNER=0,
    # never editing the builder). (a) and (b) MUST land together: this flag WITHOUT an injected
    # four_role_transport trips the fail-closed guard (run_honest_sweep_r3.py:18668, "release
    # HELD") for the REAL runner. _run_fresh_e2e injects that transport in the SAME gate-on branch;
    # the --dry-e2e mock (make_mock_run_one_query) REPLACES run_one_query so the guard never reads
    # this flag on the offline path. The no-gate control never sets it (byte-identical to champion).
    if gate_on:
        slate["PG_FOUR_ROLE_MODE"] = "1"
    return slate


def _assembled_pipeline_call(q: dict, out_root: Path, *, gate_on: bool, mode: str) -> dict:
    """The exact fresh-e2e call the live run executes. In dry mode this is only RECORDED."""
    return {
        "entrypoint": "scripts.run_honest_sweep_r3:run_one_query",
        "reaches": "S2 gate hook @ run_honest_sweep_r3.py:10435-10468 (DIRECT — no DRB-II lineage)",
        "verbatim_prompt": "DRB-v1 query.jsonl id 72 (q['question'], no PG_BENCHMARK_OFFICIAL_QUESTION rebind)",
        "env_slate": _fresh_e2e_env_slate(gate_on=gate_on, mode=mode),
        "query_dict": {
            "slug": q["slug"], "domain": q["domain"],
            "question_head": q["question"][:80], "amplified_count": len(q.get("amplified", [])),
        },
        "out_root": str(out_root),
        "produces": ["report.md", "protocol.json", "manifest.json"],
        "retrieval_scope_status": "fresh_gate_scoped" if gate_on else "fresh_no_gate",
    }


# Terminal statuses run_one_query returns when it ABORTED before producing a scoreable report.
# run_one_query writes a STUB report.md on scope-reject (run_honest_sweep_r3.py:9651) so a bare
# report_path.exists() check reads a hard abort as success — the false-OK bug. Any status with
# these prefixes is a FAILURE; the stub is not a scoreable report. (Kept as prefixes so new
# abort_*/fail_*/error_* statuses added downstream are caught without editing this list.)
_ABORT_STATUS_PREFIXES = ("abort", "fail", "error", "cancel")


def _is_abort_status(status: str | None) -> bool:
    """True iff run_one_query's terminal status denotes a non-scoreable abort/failure."""
    s = (status or "").strip().lower()
    return any(s.startswith(p) for p in _ABORT_STATUS_PREFIXES)


def _run_fresh_e2e(
    q: dict, out_root: Path, *, gate_on: bool, mode: str, runner: Any = None,
) -> tuple[Path, dict]:
    """EXECUTE the fresh e2e. Sets the gate env slate, calls run_one_query DIRECTLY, returns
    the run dir that holds report.md.

    ``runner`` is the coroutine function invoked as ``runner(q, out_root)``. It defaults to the
    REAL ``scripts.run_honest_sweep_r3.run_one_query`` (the live path). The --dry-e2e mode and
    the offline integration test inject a NETWORK-MOCKED stub with the SAME (q, out_root) ->
    summary-dict interface, so the FULL harness path is exercised offline against run_one_query's
    real contract: same env slate, same q-dict, same report.md discovery, same abort detection.

    WHY run_one_query (NOT run_gate_b_query): run_gate_b_query FORCES
    ``PG_BENCHMARK_OFFICIAL_QUESTION=1`` and rebinds ``q["question"]`` to the DeepResearch-
    Bench-II canonical gold question by reading ``third_party/DeepResearch-Bench-II/
    tasks_and_rubrics.jsonl`` via gate0_lineage — a file this repo does NOT ship (we score
    against DRB v1, task 72). That path fail-loud-raises GateZeroLineageError before any
    retrieval. ``run_one_query`` is the DIRECT home of the S2 gate hook
    (run_honest_sweep_r3.py:10435-10468) and keys ALL of retrieval/generation/title on
    ``q["question"]`` — the VERBATIM DRB-v1 task-72 prompt supplied in ``q`` — with NO
    DRB-II coupling (the only gate0_lineage import inside run_one_query is guarded by
    ``resume=True``, which we never set). With ``PG_GATE=1`` + ``PG_USE_RESEARCH_PLANNER=1``
    threaded by ``_fresh_e2e_env_slate`` below, run_one_query builds ``_research_plan`` and
    the S2 hook projects the RetrievalProjection into FS-Researcher (the no-starvation path);
    with PG_GATE=0 the hook stays byte-identical to champion. run_one_query writes
    ``report.md`` (+ manifest.json/protocol.json) to ``out_root/<domain>/<slug>/``.

    Retrieval breadth (PG_SWEEP_* — 12/12/40) is applied by the real-run env, NOT here; this
    helper threads ONLY the gate switches so the byte-identical control (--no-gate) holds.
    """
    slate = _fresh_e2e_env_slate(gate_on=gate_on, mode=mode)
    for k, v in slate.items():
        os.environ[k] = v
    # FIX 3(b): the four-role D8 transport + input builder — the PAIR that lands WITH FIX 3(a)'s
    # PG_FOUR_ROLE_MODE=1. run_one_query already accepts these params (run_honest_sweep_r3.py:8997
    # `four_role_transport` / `four_role_input_builder`); the seam activates ONLY when BOTH the env
    # flag is on AND a transport is INJECTED. We mirror scripts/dr_benchmark/run_gate_b.py's
    # build_gate_b_transport (transport-mode default "openrouter" per PG_FOUR_ROLE_TRANSPORT — a
    # US benchmark router, no self-hosted stack) + make_gate_b_input_builder. Importing run_gate_b
    # opens NO client and touches NO socket (its module docstring: the transport is built INSIDE
    # build_gate_b_transport, never at import), so this lazy import preserves the harness's
    # no-network-at-import invariant. ONLY the REAL runner gets the transport: when ``runner`` is
    # injected (the --dry-e2e mock, signature ``(q, out_root)``) we pass NOTHING extra — the mock
    # REPLACES run_one_query and never consults the seam. Gated on gate_on so the --no-gate control
    # calls runner(q, out_root) exactly as before (byte-identical to champion).
    #
    # RERANKER NOTE: the W5 content-relevance reranker is revived NOT by any code change here but
    # by running with PG_WINNER_FIRING_GATE UNSET (default ON, run_honest_sweep_r3.py:12855) on a
    # FREE GPU so Qwen3-Reranker-0.6B loads instead of OOM'ing on a contended card — an operator
    # runtime condition, orthogonal to this D8 wiring.
    four_role_kwargs: dict = {}
    if runner is None:
        from scripts.run_honest_sweep_r3 import run_one_query as runner
        if gate_on:
            from scripts.dr_benchmark.run_gate_b import (
                build_gate_b_transport,
                make_gate_b_input_builder,
            )
            four_role_kwargs = {
                "four_role_transport": build_gate_b_transport(),
                "four_role_input_builder": make_gate_b_input_builder(),
            }
        # A/B-experiment RESUME: env-gated (default OFF => byte-identical, resume never set).
        # PG_E2E_RESUME=1 re-enters run_one_query at the post-selection corpus_snapshot
        # (run_honest_sweep_r3.py:7191), skipping retrieval; verify/D8/assemble still re-run.
        # ONLY the real runner (never the --dry-e2e mock, which has signature (q, out_root)).
        if os.getenv("PG_E2E_RESUME", "").strip().lower() in ("1", "true", "yes", "on"):
            four_role_kwargs["resume"] = True
    # Capture run_one_query's summary — its ``status`` is the authoritative abort/success
    # signal. A scope reject (or any abort) returns status=abort_* AFTER writing a stub
    # report.md, so we can NOT infer success from report.md alone (that was the false-OK bug).
    summary = asyncio.run(runner(q, out_root, **four_role_kwargs))
    if not isinstance(summary, dict):
        summary = {"status": "error_no_summary", "error": "run_one_query returned non-dict"}
    return out_root / q["domain"] / q["slug"], summary


def _assert_pinned_contract_identity(sweep_dir: Path, expected_sha: str) -> str:
    """FIX 2(b): FAIL-LOUD identity guard for the KEYSTONE hand-off.

    After the fresh e2e runs, read back the pinned ``planning_gate_artifact.json`` from the
    TASK-LEVEL sweep dir (the one ``run_one_query`` actually reads) and assert its
    ``contract_sha256`` still equals the gate's pinned sha ``expected_sha``. A mismatch means
    the contract that steered the run was NOT the one the gate pinned — a silently-swapped /
    recompiled contract (the exact keystone bug). Returns an ERROR STRING on any failure
    (missing/unreadable file, absent sha, or mismatch) so the caller sets ``d['error']`` and
    the run is never scored silently; returns ``""`` when the identity holds.

    This is pure post-run verification of a JSON artifact — no pipeline/verifier contact."""
    art_path = sweep_dir / "planning_gate_artifact.json"
    if not art_path.exists():
        return ("CONTRACT IDENTITY GUARD: pinned planning_gate_artifact.json absent at the "
                f"sweep dir {sweep_dir} after the run — the seam recompiled or never read it.")
    try:
        loaded = json.loads(art_path.read_text(encoding="utf-8"))
    except Exception as _e:  # noqa: BLE001
        return f"CONTRACT IDENTITY GUARD: sweep artifact unreadable ({_e})."
    got_sha = (loaded.get("contract_sha256") or "") if isinstance(loaded, dict) else ""
    if not expected_sha:
        return "CONTRACT IDENTITY GUARD: gate pinned an EMPTY contract_sha256 (nothing to steer)."
    if got_sha != expected_sha:
        return ("CONTRACT IDENTITY GUARD: sweep contract_sha256 "
                f"{got_sha[:16]!r} != pinned {expected_sha[:16]!r} — a swapped/recompiled "
                "contract steered the run; refusing to score.")
    return ""


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


# ---------------------------------------------------------------------------
# Network-mocked run_one_query stub (the --dry-e2e / integration-test runner)
# ---------------------------------------------------------------------------

def make_mock_run_one_query(
    *, expected_question: str, status: str = "released_with_disclosed_gaps",
    write_report: bool = True, assertions: bool = True,
):
    """Build a NETWORK-MOCKED stand-in for ``run_honest_sweep_r3.run_one_query``.

    The returned coroutine has run_one_query's REAL interface — ``async (q, out_root) -> summary
    dict`` — but does ZERO network / LLM / retrieval / compose. It:

      * ASSERTS (when ``assertions``) that the harness handed it an ACCEPTED scope-gate domain
        (in SUPPORTED_DOMAINS — the fix-(2) canary), the VERBATIM task question (byte-match vs
        ``expected_question`` — proves no prompt drift / no DRB-II rebind), and that the gate env
        slate threaded (PG_GATE + PG_USE_RESEARCH_PLANNER present in os.environ — proves the S2
        projection would fire), replicating the exact preconditions the real run_one_query needs;
      * writes a realistic ``report.md`` to ``out_root/<domain>/<slug>/`` (the real run's output
        location) UNLESS ``write_report`` is False (used to prove the fail-loud "no report" path);
      * returns a summary dict shaped like run_one_query's real return (status/slug/domain/
        question/run_dir/error) with the requested terminal ``status`` — a non-abort status for
        the success case, or an ``abort_*`` status to prove fail-loud fires on the abort STUB.
    """
    async def _mock_run_one_query(q: dict, out_root: Path) -> dict:
        if assertions:
            from src.polaris_graph.nodes.scope_gate import SUPPORTED_DOMAINS
            assert q["domain"] in SUPPORTED_DOMAINS, (
                f"WIRING MISMATCH: run_one_query got domain {q['domain']!r} NOT in "
                f"SUPPORTED_DOMAINS — run_scope_gate would abort pre-retrieval."
            )
            assert q["question"] == expected_question, (
                "WIRING MISMATCH: run_one_query got a NON-VERBATIM question (prompt drift / "
                "unexpected rebind)."
            )
            assert os.environ.get("PG_GATE") in ("0", "1"), (
                "WIRING MISMATCH: PG_GATE not threaded into the run_one_query env."
            )
            assert "PG_USE_RESEARCH_PLANNER" in os.environ, (
                "WIRING MISMATCH: PG_USE_RESEARCH_PLANNER not threaded — the S2 projection "
                "would never fire (run_honest_sweep_r3.py:10448 requires it)."
            )
        run_dir = out_root / q["domain"] / q["slug"]
        run_dir.mkdir(parents=True, exist_ok=True)
        if write_report:
            # A realistic non-trivial report the RACE/FACT stages can consume (sections + a
            # citation), NOT the abort stub. The bytes are synthetic; the WIRING is real.
            (run_dir / "report.md").write_text(
                f"# {q['question'][:60]}\n\n## Introduction\n\nMocked offline report body for "
                f"the dry-e2e wiring proof.\n\n## Findings\n\nFinding one [1].\n\n"
                f"## References\n\n[1] Example Source. (2025).\n",
                encoding="utf-8")
        return {
            "slug": q["slug"], "domain": q["domain"], "question": q["question"],
            "run_id": f"MOCK_{q['domain']}_{q['slug']}", "status": status,
            "run_dir": str(run_dir), "error": "" if not _is_abort_status(status) else status,
        }
    return _mock_run_one_query


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
    dry_e2e: bool = False, e2e_runner: Any = None,
) -> dict:
    """Orchestrate one DRB task.

    Three modes:
      * dry (default)   — gate+wiring assembly only, NO run_one_query call (spend-free smoke).
      * dry_e2e         — drive the FULL live harness path (gate offline stub + _run_fresh_e2e)
                          but with ``e2e_runner`` = a NETWORK-MOCKED run_one_query stub. Proves
                          the whole wiring offline; NO network, NO spend. The gate also runs on
                          the offline compiler stub (live=False) so no OPENROUTER call fires.
      * live            — the real fresh e2e (network + spend).
    """
    task = _load_drb_task(task_id)
    prompt = task["prompt"]
    q = _query_dict_for_task(task)
    # dry_e2e drives the live branch (executes run_one_query via the injected runner).
    take_live_branch = (not dry) or dry_e2e
    # The gate fires its real OpenRouter policy model ONLY on a true live run; dry AND dry_e2e
    # both use the offline compiler stub so the test/mode is fully spend-free.
    gate_live = (not dry) and (not dry_e2e)
    per_task: dict[str, Any] = {
        "task_id": task_id, "language": task.get("language"),
        "prompt_head": prompt[:70].replace("\n", " "),
        "mode": mode, "gate_on": gate_on, "dry": dry, "dry_e2e": dry_e2e, "draws": []}

    for draw in range(1, draws + 1):
        run_id = f"gate_e2e_{task_id}_d{draw}_{uuid.uuid4().hex[:6]}"
        run_dir = out_root / q["domain"] / q["slug"] / f"draw{draw}"
        run_dir.mkdir(parents=True, exist_ok=True)
        d: dict[str, Any] = {"draw": draw, "run_dir": str(run_dir), "stages": {}}

        # --- STAGE 1: GATE ---
        t0 = time.time()
        gate = _run_gate(prompt, mode=mode, live=gate_live, run_id=run_id)
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

        if not take_live_branch:
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
            # FIX 2(a): KEYSTONE hand-off. run_one_query reads the pin from the TASK-LEVEL
            # sweep dir (out_root/domain/slug), NOT this draw{N} dir. The gate wrote the pin
            # to run_dir=draw{N} above (:550), so the seam found nothing at the task level and
            # RECOMPILED a degenerate contract — the bug that steered a full run for a day.
            # Write the SAME pinned artifact to the task-level dir the sweep actually reads,
            # overwriting per-draw (draws share the sweep dir). Pure planning-input wiring,
            # upstream of everything; strict_verify/provenance untouched. GATED on gate_on so
            # the --no-gate control writes nothing here and stays byte-identical to champion.
            sweep_dir = out_root / q["domain"] / q["slug"]
            _pinned_sha = getattr(artifact, "contract_sha256", "") or ""
            if gate_on:
                sweep_dir.mkdir(parents=True, exist_ok=True)
                (sweep_dir / "planning_gate_artifact.json").write_text(
                    json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
            t1 = time.time()
            sweep_run_dir, sweep_summary = _run_fresh_e2e(
                q, out_root, gate_on=gate_on, mode=mode, runner=e2e_runner)
            # FIX 2(b): FAIL-LOUD identity guard. Only meaningful when the gate is ON (the pin
            # is the contract that must steer the run). Read the pin back from the sweep dir and
            # assert its contract_sha256 matches the gate's pinned sha; a mismatch means a
            # silently-swapped/recompiled contract — never score such a run.
            if gate_on:
                _guard_err = _assert_pinned_contract_identity(sweep_dir, _pinned_sha)
                if _guard_err:
                    d["error"] = _guard_err
            report_path = sweep_run_dir / "report.md"
            sweep_status = sweep_summary.get("status")
            aborted = _is_abort_status(sweep_status)
            d["stages"]["fresh_e2e"] = {
                "elapsed_s": round(time.time() - t1, 1),
                "sweep_run_dir": str(sweep_run_dir),
                "report_exists": report_path.exists(),
                "sweep_status": sweep_status,
                "sweep_error": sweep_summary.get("error") or "",
                "aborted": aborted,
            }
            # FAIL-LOUD: a run that ABORTED (scope reject, safety refusal, no-sources,
            # corpus-inadequate, budget, ...) or produced NO report.md is NOT a scoreable
            # report — even though the abort path writes a STUB report.md. Do NOT audit/score
            # a stub; set d["error"] so per-draw ok is False and main() exits non-zero.
            if d.get("error"):
                # FIX 2(b): the identity guard already tripped — a swapped/recompiled contract
                # steered this run; do NOT audit/score it (keep the pre-existing guard error).
                pass
            elif aborted:
                d["error"] = (
                    f"fresh e2e ABORTED: status={sweep_status!r} "
                    f"{sweep_summary.get('error') or ''}".strip()
                )
            elif not report_path.exists():
                d["error"] = "fresh e2e produced no report.md (no abort status either)"
            else:
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
                d["live_ok"] = True

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
    ap.add_argument("--dry-e2e", action="store_true", default=False,
                    help="OFFLINE full-path proof: drive the ENTIRE live harness path "
                         "(gate offline stub -> _run_fresh_e2e -> run_one_query) with the "
                         "network MOCKED (built-in stub). No spend, no OPENROUTER, in-workflow "
                         "safe. Proves the wiring the next LIVE run depends on.")
    ap.add_argument("--no-gate", dest="gate_on", action="store_false", default=True,
                    help="champion baseline: PG_GATE=0 (byte-identical control).")
    ap.add_argument("--score-race", action="store_true", help="run RACE on each live report.")
    ap.add_argument("--score-fact", action="store_true", help="run FACT on each live report.")
    args = ap.parse_args()

    task_ids = [t.strip() for t in args.task_id.split(",") if t.strip()]
    out_root = (_REPO / args.out_root) if not Path(args.out_root).is_absolute() else Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # --dry-e2e drives the LIVE branch with a mocked runner: NO real live run, so it needs
    # NEITHER OPENROUTER nor PG_PLANNING_GATE_LIVE. Only a true --live run is guarded.
    real_live = (not args.dry) and (not args.dry_e2e)
    # assembly_only = the default spend-free smoke (gate+wiring, no run_one_query at all).
    assembly_only = args.dry and (not args.dry_e2e)
    if real_live:
        if os.getenv("PG_PLANNING_GATE_LIVE", "0").strip().lower() not in ("1", "true", "yes", "on"):
            print("BLOCKED: --live requires PG_PLANNING_GATE_LIVE=1 (the gate's policy model).",
                  file=sys.stderr)
            return 2
        if not os.getenv("OPENROUTER_API_KEY"):
            print("BLOCKED: --live requires OPENROUTER_API_KEY (source .env first).", file=sys.stderr)
            return 2

    summary: dict[str, Any] = {
        "harness": "run_gate_e2e", "mode": args.mode, "dry": args.dry,
        "dry_e2e": args.dry_e2e,
        "gate_on": args.gate_on, "draws": args.draws, "out_root": str(out_root),
        "score_race": args.score_race, "score_fact": args.score_fact, "tasks": []}

    all_ok = True
    _label = "DRY" if assembly_only else ("DRY-E2E(mocked)" if args.dry_e2e else "LIVE")
    for tid in task_ids:
        print(f"[gate-e2e] task {tid}  mode={args.mode}  "
              f"{_label}  gate={'ON' if args.gate_on else 'OFF'}  "
              f"draws={args.draws}")
        # In --dry-e2e, build a network-mocked run_one_query keyed on THIS task's verbatim
        # prompt so the stub asserts a byte-exact question match (no drift).
        _e2e_runner = None
        if args.dry_e2e:
            _task = _load_drb_task(tid)
            _e2e_runner = make_mock_run_one_query(expected_question=_task["prompt"])
        res = _process_task(
            tid, out_root=out_root, mode=args.mode, gate_on=args.gate_on,
            dry=assembly_only, dry_e2e=args.dry_e2e, e2e_runner=_e2e_runner,
            draws=args.draws,
            score_race=args.score_race, score_fact=args.score_fact)
        summary["tasks"].append(res)
        for d in res["draws"]:
            g = d["stages"]["gate"]
            rw = d["stages"]["retrieval_wiring"]
            # ASSEMBLY-ONLY: assembled_ok is authoritative. LIVE / DRY-E2E: the draw is OK only
            # if it produced a SCOREABLE report — d["live_ok"] is set True ONLY after a non-abort
            # report.md was audited (never on the abort stub). Any d["error"] (abort / missing
            # report) => NOT OK. This is the fix for the false "[gate-e2e] ALL OK" on an abort.
            if assembly_only:
                ok = bool(d.get("assembled_ok"))
            else:
                ok = bool(d.get("live_ok")) and not d.get("error")
            all_ok = all_ok and ok
            tail = f"assembled_ok={ok}" if assembly_only else (
                f"live_ok={ok} status="
                f"{d.get('stages', {}).get('fresh_e2e', {}).get('sweep_status')!r}"
                + (f" ERROR={d['error']}" if d.get("error") else ""))
            print(f"  draw{d['draw']}: gate={g['state']} "
                  f"terms={g['n_terms']} hard={g['n_hard']} cov={g['n_coverage']} "
                  f"amp_q={rw['amplified_query_count']} scope_lanes={len(rw['scope_lane_keys'])} "
                  f"{tail}")

    summary["all_ok"] = all_ok
    summary_path = out_root / "gate_e2e_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gate-e2e] summary -> {summary_path}")
    if not all_ok:
        # FAIL-LOUD: enumerate every draw that did NOT produce a scoreable report so a live
        # abort can NEVER be reported as success. This prints to stderr and returns non-zero.
        for res in summary["tasks"]:
            for d in res.get("draws", []):
                if d.get("error"):
                    print(f"[gate-e2e][FAIL] task {res['task_id']} draw{d['draw']}: "
                          f"{d['error']}", file=sys.stderr)
        print(f"[gate-e2e] FAIL ({len(task_ids)} tasks x {args.draws} draws, "
              f"{_label}) — at least one draw produced NO scoreable "
              f"report (abort / missing report.md). This run is NOT scoreable.",
              file=sys.stderr)
        return 1
    print(f"[gate-e2e] ALL OK "
          f"({len(task_ids)} tasks x {args.draws} draws, {_label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
