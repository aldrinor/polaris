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
import subprocess
import sys
import time
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
# live path — DOUBLE-GATED, PAID. Runs compose→bridge→RACE→FACT per arm and diffs.
#
# SAFETY MODEL: the paid seam is the LiveRunner class. It ONLY ever spends money via
# subprocess (it never imports the benchmark's live clients in-process), and it is
# instantiated ONLY on the real path AFTER the double gate + cost warning. The
# orchestrator (run_live_ab) takes the runner by injection, so every test drives a
# fully mocked runner that returns canned scores — no test touches the real class.
# ─────────────────────────────────────────────────────────────────────────────

# Paths to the vendored benchmark.
_DRB = _ROOT / "third_party" / "deep_research_bench"
_DRB_QUERY = _DRB / "data" / "prompt_data" / "query.jsonl"

# Default live task set: a single task = DRB task 72 (configurable via --live-tasks).
_DEFAULT_LIVE_TASKS = ("72",)

# Default corpus + judge models (all env-overridable / CLI-overridable).
_DEFAULT_CORPUS = "data/cp4_corpus_s3gear_329.json"
_DEFAULT_RACE_MODEL = "openai/gpt-5.5"
_DEFAULT_FACT_MODEL = "openai/gpt-5.4-mini"

# The four RACE dimensions (exact keys) + how they appear in race_result.txt.
_RACE_DIMS = {
    "comprehensiveness": "Comprehensiveness",
    "insight": "Insight",
    "instruction_following": "Instruction Following",
    "readability": "Readability",
    "overall": "Overall Score",
}
_FACT_KEYS = ("valid_rate", "total_valid_citations", "total_citations")


def _load_drb_task(task_id: str) -> dict[str, Any]:
    """Load a DRB task row (id/topic/language/prompt) verbatim from query.jsonl. Offline
    file read — no network. Raises if the task id is unknown."""
    for line in _DRB_QUERY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if str(o.get("id")) == str(task_id):
            return o
    raise SystemExit(f"BLOCKED: DRB task id {task_id} not in {_DRB_QUERY}")


def _arm_flag_env(*, treatment: bool, web_search: bool) -> dict[str, str]:
    """PURE: the env OVERRIDES for ONE arm. Both arms are held byte-identical EXCEPT the
    three treatment flags, so the only variable in the A/B is the intake contract.

      * PG_OUTLINE_AGENT=1            (champion model-lock, both arms)
      * PG_SYNTHESIS_QUANT_DIRECTIVE=0  (pinned identical on both arms — removed as a confound)
      * PG_OUTLINE_WEB_SEARCH=0      (nondeterminism control; both arms; --live-web -> 1)
      * the 3 contract flags         = "1" (treatment) / "0" (baseline)
    """
    env = {
        "PG_OUTLINE_AGENT": "1",
        "PG_SYNTHESIS_QUANT_DIRECTIVE": "0",
        "PG_OUTLINE_WEB_SEARCH": "1" if web_search else "0",
    }
    for f in _TREATMENT_FLAGS:
        env[f] = "1" if treatment else "0"
    return env


def _parse_race_result(path: Path) -> dict[str, float | None]:
    """Parse third_party/.../results/race/<target>/race_result.txt (5 'Name: score'
    lines) into {overall, comprehensiveness, insight, instruction_following, readability}."""
    raw: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            try:
                raw[k.strip()] = float(v.strip())
            except ValueError:
                continue
    return {key: raw.get(label) for key, label in _RACE_DIMS.items()}


def _parse_fact_result(path: Path) -> dict[str, float | None]:
    """Parse .../results/fact/<target>/fact_result.txt (total_citations /
    total_valid_citations / valid_rate) → {valid_rate, total_valid_citations, total_citations}.
    valid_rate == supported / validated (unknown excluded from the denominator)."""
    raw: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            try:
                raw[k.strip()] = float(v.strip())
            except ValueError:
                continue
    return {k: raw.get(k) for k in _FACT_KEYS}


class LiveRunner:  # pragma: no cover — PAID/network seam, never exercised by tests
    """The real, PAID + network execution seam. EVERY method here spends money or hits
    the network (compose LLM, RACE judge, FACT validator, Jina scrape). It shells out to
    the champion compose driver and the vendored benchmark stages as SUBPROCESSES — it
    never imports a live client into this process. Fully injectable: tests replace it
    with a recorder, so this class is never constructed under test."""

    def __init__(self, *, corpus: str, race_model: str, fact_model: str,
                 max_parallel: int, max_workers: int, n_total_process: int,
                 web_search: bool) -> None:
        self.corpus = corpus
        self.race_model = race_model
        self.fact_model = fact_model
        self.max_parallel = max_parallel
        self.max_workers = max_workers
        self.n_total_process = n_total_process
        self.web_search = web_search

    # ── arm 1: compose ────────────────────────────────────────────────────────
    def compose(self, task: dict[str, Any], *, treatment: bool, arm_out_dir: Path) -> Path:
        """Run the champion compose driver once with this arm's flag-set. Returns the
        composed report.md path (deterministic via --out-dir)."""
        env = dict(os.environ)
        env.update(_arm_flag_env(treatment=treatment, web_search=self.web_search))
        cmd = [
            sys.executable, "scripts/compose_agentic_report_s3gear329.py",
            "--corpus", self.corpus,
            "--rq-drb-task", str(task["id"]),
            "--max-parallel", str(self.max_parallel),
            "--out-dir", str(arm_out_dir),
        ]
        subprocess.run(cmd, cwd=str(_ROOT), env=env, check=True)
        return arm_out_dir / "report.md"

    # ── arm 2: report → DRB raw_data bridge ───────────────────────────────────
    def bridge(self, *, report_md: Path, task: dict[str, Any], target_name: str) -> Path:
        """Serialize the freshly composed report.md into the DRB raw_data JSONL row that
        RACE + FACT expect — keyed by the verbatim task prompt so target/reference/criteria
        align. Also (re)writes the single-task query file. Returns the raw_data path."""
        report_text = report_md.read_text(encoding="utf-8")
        row = {"id": task["id"], "prompt": task["prompt"], "article": report_text}
        raw_path = _DRB / "data" / "test_data" / "raw_data" / f"{target_name}.jsonl"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

        q_path = _DRB / "data" / "prompt_data" / f"query_task{task['id']}.jsonl"
        q_path.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")
        return raw_path

    # ── arm 3: RACE ───────────────────────────────────────────────────────────
    def race(self, *, target_name: str, task: dict[str, Any]) -> dict[str, float | None]:
        """Score the bridged article with the official RACE harness (openai/gpt-5.5 judge,
        reference-based). NOTE: never pass --skip_cleaning — cleaning and scoring are coupled
        in the harness, so --skip_cleaning would produce NO scores."""
        out_dir = _DRB / "results" / "race" / target_name
        out_dir.mkdir(parents=True, exist_ok=True)
        q_path = _DRB / "data" / "prompt_data" / f"query_task{task['id']}.jsonl"
        env = dict(os.environ)
        env["LLM_BACKEND"] = "openrouter"
        env["RACE_MODEL"] = self.race_model
        lang_flag = "--only_en" if task.get("language", "en") == "en" else "--only_zh"
        cmd = [
            sys.executable, "-u", "deepresearch_bench_race.py", target_name,
            "--raw_data_dir", "data/test_data/raw_data",
            "--query_file", str(q_path.relative_to(_DRB)),
            "--output_dir", str(out_dir.relative_to(_DRB)),
            "--max_workers", str(self.max_workers),
            lang_flag, "--force",
        ]
        subprocess.run(cmd, cwd=str(_DRB), env=env, check=True)
        return _parse_race_result(out_dir / "race_result.txt")

    # ── arm 4: FACT (extract → dedup → scrape → validate → stat) ───────────────
    def fact(self, *, target_name: str, task: dict[str, Any]) -> dict[str, float | None]:
        """Run the full FACT chain on the bridged article and parse valid_rate. Stages are
        resumable/append-only, so stale outputs are deleted first for a clean recompute."""
        cdir = _DRB / "results" / "fact" / target_name
        cdir.mkdir(parents=True, exist_ok=True)
        raw = f"data/test_data/raw_data/{target_name}.jsonl"
        q_path = _DRB / "data" / "prompt_data" / f"query_task{task['id']}.jsonl"
        query = str(q_path.relative_to(_DRB))
        n = str(self.n_total_process)
        env = dict(os.environ)
        env["LLM_BACKEND"] = "openrouter"
        env["FACT_MODEL"] = self.fact_model

        extracted = f"results/fact/{target_name}/extracted.jsonl"
        deduped = f"results/fact/{target_name}/deduplicated.jsonl"
        scraped = f"results/fact/{target_name}/scraped.jsonl"
        validated = f"results/fact/{target_name}/validated.jsonl"
        fact_txt = cdir / "fact_result.txt"
        for stale in ("extracted.jsonl", "deduplicated.jsonl", "scraped.jsonl",
                      "validated.jsonl", "fact_result.txt"):
            (cdir / stale).unlink(missing_ok=True)

        stages = [
            ["-m", "utils.extract", "--raw_data_path", raw, "--output_path", extracted,
             "--query_data_path", query, "--n_total_process", n],
            ["-m", "utils.deduplicate", "--raw_data_path", extracted, "--output_path", deduped,
             "--query_data_path", query, "--n_total_process", n],
            ["-m", "utils.scrape", "--raw_data_path", deduped, "--output_path", scraped,
             "--n_total_process", n],
            ["-m", "utils.validate", "--raw_data_path", scraped, "--output_path", validated,
             "--query_data_path", query, "--n_total_process", n],
            ["-m", "utils.stat", "--input_path", validated,
             "--output_path", str(fact_txt.relative_to(_DRB))],
        ]
        for stage in stages:
            subprocess.run([sys.executable, "-u", *stage], cwd=str(_DRB), env=env, check=True)
        return _parse_fact_result(fact_txt)


# ── orchestration (pure + injectable — this is what the tests drive) ──────────

def _diff_scores(baseline: dict[str, float | None],
                 treatment: dict[str, float | None]) -> dict[str, float | None]:
    """treatment − baseline per metric (None if either side is missing)."""
    out: dict[str, float | None] = {}
    for k in baseline:
        b, t = baseline[k], treatment.get(k)
        out[k] = None if (b is None or t is None) else round(t - b, 6)
    return out


def _aggregate(per_task: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean baseline / treatment / delta per metric across all tasks."""
    def mean(vals: list[float | None]) -> float | None:
        xs = [v for v in vals if v is not None]
        return round(sum(xs) / len(xs), 6) if xs else None

    agg: dict[str, Any] = {"n_tasks": len(per_task), "race": {}, "fact": {}}
    if not per_task:
        return agg
    for grp, keys in (("race", _RACE_DIMS.keys()), ("fact", _FACT_KEYS)):
        for k in keys:
            b = mean([t["baseline"][grp][k] for t in per_task])
            tr = mean([t["treatment"][grp][k] for t in per_task])
            agg[grp][k] = {
                "baseline": b, "treatment": tr,
                "delta": None if (b is None or tr is None) else round(tr - b, 6),
            }
    return agg


def run_live_ab(tasks: list[dict[str, Any]], runner: Any, *, workdir: Path) -> dict[str, Any]:
    """PURE ORCHESTRATOR (paid work lives entirely in `runner`). Per task, per arm:
    compose → bridge → RACE → FACT, IN THAT ORDER; then diff treatment − baseline. The
    ONLY difference between arms is which flag-set `runner.compose` receives
    (treatment=False vs True); every other input is identical.

    Tests inject a mock `runner` that records the call sequence + flags and returns canned
    scores, so this function's ordering and delta math are verified with ZERO paid calls."""
    per_task: list[dict[str, Any]] = []
    for task in tasks:
        arms: dict[str, Any] = {}
        for arm, treatment in (("baseline", False), ("treatment", True)):
            arm_out_dir = workdir / f"task{task['id']}" / arm
            target_name = f"abctr_task{task['id']}_{arm}"
            report_md = runner.compose(task, treatment=treatment, arm_out_dir=arm_out_dir)
            runner.bridge(report_md=report_md, task=task, target_name=target_name)
            race = runner.race(target_name=target_name, task=task)
            fact = runner.fact(target_name=target_name, task=task)
            arms[arm] = {"target": target_name, "race": race, "fact": fact}
        per_task.append({
            "id": task["id"],
            "baseline": arms["baseline"],
            "treatment": arms["treatment"],
            "delta": {
                "race": _diff_scores(arms["baseline"]["race"], arms["treatment"]["race"]),
                "fact": _diff_scores(arms["baseline"]["fact"], arms["treatment"]["fact"]),
            },
        })
    return {"mode": "live", "tasks": per_task, "aggregate": _aggregate(per_task)}


def _fmt(v: float | None) -> str:
    return "  n/a " if v is None else f"{v:+.4f}" if isinstance(v, float) else str(v)


def render_live_report(result: dict[str, Any]) -> str:
    """Human-readable baseline-vs-treatment diff table (per task + aggregate)."""
    lines: list[str] = ["", "== A/B CONTRACT EVAL — LIVE RESULT (baseline OFF vs treatment ON) =="]
    for t in result["tasks"]:
        lines.append(f"\n--- task {t['id']} ---")
        lines.append(f"{'metric':<26}{'baseline':>12}{'treatment':>12}{'delta':>12}")
        for grp, keys in (("race", _RACE_DIMS.keys()), ("fact", _FACT_KEYS)):
            for k in keys:
                b = t["baseline"][grp][k]
                tr = t["treatment"][grp][k]
                d = t["delta"][grp][k]
                bs = "  n/a " if b is None else f"{b:.4f}"
                ts = "  n/a " if tr is None else f"{tr:.4f}"
                lines.append(f"{grp+'.'+k:<26}{bs:>12}{ts:>12}{_fmt(d):>12}")
    agg = result["aggregate"]
    lines.append(f"\n--- AGGREGATE over {agg['n_tasks']} task(s) ---")
    lines.append(f"{'metric':<26}{'baseline':>12}{'treatment':>12}{'delta':>12}")
    for grp in ("race", "fact"):
        for k, cell in agg[grp].items():
            bs = "  n/a " if cell["baseline"] is None else f"{cell['baseline']:.4f}"
            ts = "  n/a " if cell["treatment"] is None else f"{cell['treatment']:.4f}"
            lines.append(f"{grp+'.'+k:<26}{bs:>12}{ts:>12}{_fmt(cell['delta']):>12}")
    return "\n".join(lines) + "\n"


def _cost_warning(tasks: list[dict[str, Any]], args: argparse.Namespace) -> str:
    """The MANDATORY cost warning + exact plan printed BEFORE any paid execution."""
    n = len(tasks)
    ids = ", ".join(str(t["id"]) for t in tasks)
    web = "ON (--live-web)" if args.live_web else "OFF (default; PG_OUTLINE_WEB_SEARCH=0 both arms)"
    return "\n".join([
        "",
        "############################################################################",
        "#  PAID LIVE A/B — THIS SPENDS REAL MONEY (compose LLM + RACE + FACT).      #",
        "############################################################################",
        f"  tasks           : {n}  (DRB task ids: {ids})",
        f"  arms per task   : 2  (baseline = 3 contract flags OFF; treatment = ON)",
        f"  => compose runs : {2 * n}  full champion literature-review composes",
        f"  web search      : {web}  (nondeterminism control; only variable is the contract)",
        f"  RACE judge      : {args.race_model}   (LLM_BACKEND=openrouter, --only_en/zh, --force)",
        f"  FACT validator  : {args.fact_model}   (extract→dedup→scrape[Jina]→validate→stat)",
        f"  corpus          : {args.corpus}",
        "",
        "  PER-ARM COST (order-of-magnitude — actuals depend on report length / #citations):",
        "    - compose : ~2-4M LLM tokens (dominant cost; hundreds of calls: outline,",
        "                per-section writers, side-judges, credibility pass)",
        "    - RACE    : a handful of gpt-5.5 judge calls (target + reference, dynamic dims)",
        "    - FACT    : 1 extract + a few dedup + ~40-120 Jina scrapes + ~40-120 gpt-5.4-mini",
        "                validator calls (one per unique cited URL)",
        f"    => multiply by {2 * n} arms for this run.",
        "",
        "  HONEST CAVEAT: on the champion compose path only PG_POSTWRITE_STRUCTURE_CHECK is",
        "  reachable; PG_INTAKE_CONTRACT_COMPILE / PG_EXTRACT_INSTRUCTION_SLOTS take effect",
        "  only via graph_v2.run_scope_gate, which this path does NOT route through — so their",
        "  live RACE/FACT delta is expected to be ZERO on the champion path today.",
        "############################################################################",
    ])


def run_live(args: argparse.Namespace, runner: Any | None = None) -> int:
    """Real compose→bridge→RACE→FACT A/B. DOUBLE-GATED: requires BOTH --live AND
    --i-understand-this-spends=<token>. Prints a cost warning + the exact plan BEFORE any
    execution. The paid seam (LiveRunner) is constructed ONLY here on the real path, AFTER
    the gate; tests inject a mocked `runner` and never build it."""
    if not args.live or args.i_understand_this_spends != _SPEND_TOKEN:
        print(
            "REFUSED: the live path is double-gated. Pass BOTH --live AND "
            f"--i-understand-this-spends={_SPEND_TOKEN} to run PAID compose+RACE+FACT scoring.",
            file=sys.stderr,
        )
        return 2

    task_ids = [s.strip() for s in str(args.live_tasks).split(",") if s.strip()]
    tasks = [_load_drb_task(tid) for tid in task_ids]

    # MANDATORY: warn + print the exact plan BEFORE any paid work runs.
    print(_cost_warning(tasks, args), file=sys.stderr)

    workdir = Path(args.live_workdir) if args.live_workdir else (
        _ROOT / "outputs" / time.strftime("ab_contract_live_%Y%m%d_%H%M%S"))
    workdir.mkdir(parents=True, exist_ok=True)

    if runner is None:  # real path — build the paid seam only now
        if not os.getenv("OPENROUTER_API_KEY"):
            print("BLOCKED: OPENROUTER_API_KEY not set — source .env first "
                  "(compose + RACE + FACT all require it).", file=sys.stderr)
            return 2
        runner = LiveRunner(
            corpus=args.corpus, race_model=args.race_model, fact_model=args.fact_model,
            max_parallel=args.max_parallel, max_workers=args.max_workers,
            n_total_process=args.n_total_process, web_search=args.live_web,
        )

    result = run_live_ab(tasks, runner, workdir=workdir)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    print(render_live_report(result))
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", default=False,
                   help="Run the PAID compose+RACE+FACT A/B (off by default). Requires the spend token.")
    p.add_argument("--i-understand-this-spends", dest="i_understand_this_spends", default="",
                   help=f"Confirmation token required with --live (must equal '{_SPEND_TOKEN}').")
    p.add_argument("--tasks", default=None,
                   help="Optional path to a JSON list of fixture tasks (dry-run mode; defaults to built-in set).")
    p.add_argument("--out", default=None,
                   help="Optional path to write the JSON report to (both modes).")
    # ── live-path options (all ignored in the default dry-run mode) ──
    p.add_argument("--live-tasks", dest="live_tasks", default=",".join(_DEFAULT_LIVE_TASKS),
                   help="Comma-separated DRB task ids to A/B in --live mode (default '72' = a single task).")
    p.add_argument("--live-web", dest="live_web", action="store_true", default=False,
                   help="LIVE nondeterminism control: by DEFAULT PG_OUTLINE_WEB_SEARCH=0 on BOTH arms "
                        "(the only variable is the contract). Pass --live-web to set it =1 on both arms "
                        "(reintroduces web-search nondeterminism into the A/B).")
    p.add_argument("--corpus", default=_DEFAULT_CORPUS,
                   help=f"Corpus JSON for compose in --live mode (default {_DEFAULT_CORPUS}).")
    p.add_argument("--race-model", dest="race_model", default=os.getenv("RACE_MODEL", _DEFAULT_RACE_MODEL),
                   help=f"RACE judge model (default {_DEFAULT_RACE_MODEL}).")
    p.add_argument("--fact-model", dest="fact_model", default=os.getenv("FACT_MODEL", _DEFAULT_FACT_MODEL),
                   help=f"FACT validator model (default {_DEFAULT_FACT_MODEL}).")
    p.add_argument("--max-parallel", dest="max_parallel", type=int, default=3,
                   help="compose --max-parallel in --live mode (default 3).")
    p.add_argument("--max-workers", dest="max_workers", type=int, default=4,
                   help="RACE --max_workers in --live mode (default 4).")
    p.add_argument("--n-total-process", dest="n_total_process", type=int, default=10,
                   help="FACT stage --n_total_process in --live mode (default 10).")
    p.add_argument("--live-workdir", dest="live_workdir", default=None,
                   help="Where compose writes per-arm reports in --live mode (default a timestamped outputs/ dir).")
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
