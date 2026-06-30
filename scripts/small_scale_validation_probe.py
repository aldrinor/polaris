#!/usr/bin/env python3
"""TURNKEY small-scale validation probe (I-deepfix-001 #1344).

Proves the A5 BREADTH fix (the §-1.3 demote-not-drop + raised fetch budget) and the
A6 KIMI-JUDGE swap (qwen 429-tear -> moonshotai/kimi-k2.6) CHEAPLY on the VM, WITHOUT
the full $40 8-query sweep. Two probes:

  * PROBE 1 (breadth): a single NON-simple ``--only`` query run on the VM. The §-1.3
    demote + fetch-budget proof lives in the FRONT-HALF manifest fields, so a single
    cheap query is enough -- the proof is the MECHANISM firing, not scale.
  * PROBE 2 (kimi): a ``--resume`` from a SMALL banked corpus_snapshot, which re-runs
    the 4-role D8 seam with the default kimi judge (no re-fetch -> cheap). This is the
    LIVE companion to the diced preflight's ``D4_four_role_judge_seam_LIVE`` dice.

THIS RUNNER NEVER SPENDS. It has exactly two modes:

  * PRINT mode (no ``--assert-dir``): PRINTS the exact VM command(s) the OPERATOR runs.
    It launches nothing, loads no model, calls no OpenRouter endpoint.
  * ASSERT mode (``--assert-dir DIR``): runs OFFLINE, read-only assertions on an
    ALREADY-PRODUCED run_dir. It only reads JSON/JSONL the run already wrote and shells
    out to the (offline, read-only) diced preflight. No paid call, no model load.

Per CLAUDE.md memory (ALL heavy GPU+LLM runs on the VM, never local; §8.4): the actual
VM runs are the OPERATOR's to launch. This harness is the BUILD + the offline-assert glue.

WHY NO ``--stop-after corpus_snapshot``: ``scripts/run_honest_sweep_r3.py`` has NO
stop-after / front-half-only flag (traced 2026-06-30: argparse exposes only --only,
--out-root, --resume, --pathB-gate, --replay-from-pin). The ``corpus_snapshot.json``
checkpoint persists DATA + count subsets but NOT ``retrieval.relevance_gate`` (the §-1.3
demote proof lives ONLY in the finalized ``manifest.json``). So the cheapest HONEST
front-half breadth proof is a single NON-simple ``--only`` query run end-to-end -- far
cheaper than the $40 8-query sweep, and its front-half breadth fields are present in the
manifest regardless of the back half. (Do NOT pick a trivially-simple query: the sweep's
simple-router drops the fetch budget to ``PG_SIMPLE_FETCH_CAP``=40, which would defeat the
"fetched materially > legacy 40" proof. A drb_* benchmark slug is non-simple by routing.)

LAW VI: every host/path/threshold is an env var (``PG_DICED_*`` / ``PG_PROBE_*``).
LAW II / §8.4: no network, no model load, no heavy src import. Pure stdlib; this module
NEVER imports ``src.polaris_graph`` so the heavy package __init__ never runs.

Usage
-----
    python scripts/small_scale_validation_probe.py --probe breadth     # print the VM cmd
    python scripts/small_scale_validation_probe.py --probe kimi         # print the VM cmd
    python scripts/small_scale_validation_probe.py --probe both         # print both cmds
    python scripts/small_scale_validation_probe.py --probe breadth --assert-dir DIR
    python scripts/small_scale_validation_probe.py --probe kimi    --assert-dir DIR

Exit code: 0 == all selected checks GREEN (or PRINT mode), 1 == >=1 check RED (fail-loud),
2 == harness error (e.g. --assert-dir not found).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DICED_PREFLIGHT = _REPO_ROOT / "scripts" / "pipeline_diced_preflight.py"

# Manifest hard-fail status the kimi seam must NOT reach.
_TRANSPORT_EXHAUSTED = "abort_role_transport_exhausted"
# The disclosed-gap label the kimi seam must NOT emit on a clean completion.
_SEAM_UNADJUDICATED = "four_role_seam_unadjudicated"

GREEN = "GREEN"
RED = "RED"


# --------------------------------------------------------------------------------------------
# Env helpers (LAW VI)
# --------------------------------------------------------------------------------------------

def _env(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None or raw.strip() == "" else raw


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


# --------------------------------------------------------------------------------------------
# Check primitive
# --------------------------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    passed: bool
    detail: str

    @property
    def status(self) -> str:
        return GREEN if self.passed else RED


# --------------------------------------------------------------------------------------------
# VM command builders (placeholders consistent with pipeline_diced_preflight.py: PG_DICED_VM_*)
# --------------------------------------------------------------------------------------------

def _ssh_prefix() -> str:
    """The ssh destination, key, and port -- all env-overridable, defaults from the campaign VM
    (memory: VM == ssh2.vast.ai:37450). ``PG_DICED_VM_HOST`` is the SAME env name the diced
    preflight reads, so the two harnesses target the same box by default."""
    key = _env("PG_DICED_VM_KEY", "~/.ssh/id_ed25519")
    port = _env("PG_DICED_VM_PORT", "37450")
    host = _env("PG_DICED_VM_HOST", "root@ssh2.vast.ai")
    return f"ssh -i {key} -p {port} {host}"


def _remote_repo() -> str:
    return _env("PG_DICED_VM_REPO", "/workspace/POLARIS")


def breadth_vm_command() -> str:
    """PROBE 1 -- the exact VM command for the front-half breadth proof.

    No --stop-after flag exists, so this runs ONE non-simple query end-to-end (cheap vs the
    $40 8-query sweep). PG_RETRIEVAL_RELEVANCE_GATE=1 (default ON) so retrieval.relevance_gate
    populates; PG_SWEEP_FETCH_CAP / PG_LIVE_FETCH_CAP are LEFT UNSET so the fetch budget
    defaults to the new 200 (the breadth lever); PG_RELEVANCE_FLOOR left unset (default 0.30).
    """
    slug = _env("PG_PROBE_BREADTH_SLUG", "drb_72_ai_labor")
    out_root = _env("PG_PROBE_BREADTH_OUT", "outputs/probe_breadth")
    return (
        f"{_ssh_prefix()} 'cd {_remote_repo()} && "
        f"env -u OPENAI_API_KEY "
        f"PG_RETRIEVAL_RELEVANCE_GATE=1 "
        f"python scripts/run_honest_sweep_r3.py "
        f"--only {slug} --out-root {out_root} "
        f"2>&1 | tee /tmp/probe_breadth.log'"
    )


def kimi_vm_command() -> str:
    """PROBE 2 -- the exact VM command for the kimi 4-role D8 seam smoke.

    LAUNCH VIA run_gate_b.py, NOT run_honest_sweep_r3.py --pathB-gate. run_gate_b.py is the ONLY
    slate-applying entrypoint: its main() + run_gate_b_query CONSTRUCT the kimi judge transport (via
    benchmark_verifier_lineup), call enable_four_role_mode() (PG_FOUR_ROLE_MODE=1 -> the seam
    activates), AND apply_full_capability_benchmark_slate() (so PG_BREADTH_ENRICHMENT_ENABLED is ON
    -> the kimi judge adjudicates the FULL breadth basket, not a narrow report). run_honest_sweep_r3.py
    --pathB-gate wraps run_one_query in pathB_runner.gate_around_question, which does NOT apply the
    slate -> enrichment OFF -> the cite-breadth + kimi-judge path is not really exercised. run_gate_b.py
    has its OWN --resume (-> run_gate_b_query(resume=...) -> run_one_query(resume=...)), so it re-enters
    from the SMALL banked corpus_snapshot under {out_root}/<domain>/{slug}/ with NO re-fetch (cheap).
    PG_BENCHMARK_JUDGE_MODEL is LEFT UNSET so the default moonshotai/kimi-k2.6 judge is used. The seam
    wall is raised generously for the big/slow judge (PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS, LAW VI override).
    """
    slug = _env("PG_PROBE_KIMI_SLUG", "drb_72_ai_labor")
    out_root = _env("PG_PROBE_KIMI_OUT", "outputs/probe_kimi_resume")
    seam_wall = _env_int("PG_PROBE_SEAM_DEADLINE_S", 3600)
    return (
        f"{_ssh_prefix()} 'cd {_remote_repo()} && "
        f"env -u OPENAI_API_KEY "
        f"PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS={seam_wall} "
        f"python scripts/dr_benchmark/run_gate_b.py "
        f"--only {slug} --resume --out-root {out_root} "
        f"2>&1 | tee /tmp/probe_kimi.log'"
    )


# --------------------------------------------------------------------------------------------
# PURE assertion functions (testable: take loaded dicts/lists, return list[Check]).
# These read the NEW manifest fields (retrieval.relevance_gate from A5c; the seam telemetry
# sidecars from A6). No I/O, no spend.
# --------------------------------------------------------------------------------------------

def _active_fetch_cap(caps: dict) -> int:
    """The active PG_LIVE_FETCH_CAP value disclosed in retrieval_caps.search_truncations (the
    fetch BUDGET). 0 if absent -> the budget check then requires dropped_pre_fetch == 0."""
    for t in caps.get("search_truncations", []) or []:
        if isinstance(t, dict) and t.get("cap") == "PG_LIVE_FETCH_CAP":
            try:
                return int(t.get("value") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def breadth_manifest_checks(manifest: dict, *, legacy_fetch_floor: int = 40) -> list[Check]:
    """The §-1.3 BREADTH proof, read from a FRESH finalized manifest.json.

    1. retrieval.relevance_gate is PRESENT (A5c persisted it to the DURABLE manifest -- a
       pre-A5c manifest or a B4-OFF run has it None).
    2. relevance_gate.demoted_fetched_to_fill > 0  == below-floor sources reached the fetch
       BUDGET and were FETCHED -> the §-1.3 demote-not-drop FIRED.
    3. retrieval_caps.dropped_pre_fetch is fully attributable to the DISCLOSED fetch budget,
       NOT a hard floor-drop: dropped_pre_fetch <= max(0, discovered - fetch_cap - failed).
       (When discovered <= budget this requires dropped_pre_fetch == 0.)
    4. candidates_fetched is materially > the legacy 40 (the raised budget actually fetched
       more than the old cap).
    """
    retrieval = manifest.get("retrieval") or {}
    caps = retrieval.get("retrieval_caps") or {}
    rg = retrieval.get("relevance_gate")
    present = isinstance(rg, dict)
    checks: list[Check] = []

    checks.append(Check(
        "breadth.relevance_gate_present",
        present,
        ("retrieval.relevance_gate is PRESENT (A5c durable-manifest persistence)"
         if present else
         "retrieval.relevance_gate is MISSING/None -- B4 gate OFF, only-seeds, or a "
         "pre-A5c manifest; the §-1.3 demote proof cannot be read"),
    ))

    demoted = int((rg or {}).get("demoted_fetched_to_fill", 0) or 0) if present else 0
    checks.append(Check(
        "breadth.demote_fired",
        present and demoted > 0,
        (f"relevance_gate.demoted_fetched_to_fill={demoted} "
         f"(>0 == below-floor candidates reached the fetch BUDGET and were FETCHED -> the "
         f"§-1.3 demote-not-drop fired; ==0 means the floor was still a pre-fetch cut OR the "
         f"corpus had no below-floor sources)"),
    ))

    discovered = int(caps.get("candidates_discovered", 0) or 0)
    fetched = int(caps.get("fetched", retrieval.get("fetched", 0)) or 0)
    failed = int(caps.get("failed", retrieval.get("failed", 0)) or 0)
    dropped = int(caps.get("dropped_pre_fetch", 0) or 0)
    fetch_cap = _active_fetch_cap(caps)
    budget_overflow = max(0, discovered - fetch_cap - failed) if fetch_cap > 0 else 0
    ok_budget = dropped <= budget_overflow
    checks.append(Check(
        "breadth.dropped_is_budget_not_floor",
        ok_budget,
        (f"dropped_pre_fetch={dropped} <= budget_overflow={budget_overflow} "
         f"(candidates_discovered={discovered} fetch_cap={fetch_cap} failed={failed}); "
         f"a drop BEYOND the disclosed budget would be a §-1.3-banned hard floor-FILTER"),
    ))

    checks.append(Check(
        "breadth.fetched_above_legacy_40",
        fetched > legacy_fetch_floor,
        (f"candidates_fetched={fetched} > legacy_floor={legacy_fetch_floor} "
         f"(the raised budget fetched more than the old 40-cap)"),
    ))

    return checks


def kimi_seam_checks(
    manifest: dict,
    rate_limit_telemetry: Optional[dict],
    role_calls: list[dict],
    *,
    max_429: int = 0,
) -> list[Check]:
    """The KIMI 4-role D8 seam proof, read from a FRESH --resume run_dir.

    1. status != abort_role_transport_exhausted  (the seam did not die).
    2. four_role_seam_inert is not True           (a transport WAS injected -- run_gate_b.py).
    3. no held_reason starts with "seam_"         (proxy for the runtime _seam_held_reason is None).
    4. no four_role_seam_unadjudicated disclosed gap (the judge bound for the claims).
    5. rate_limit_hits_total <= max_429            (no 429-storm; the kimi 21-provider point).
    6. four_role_evaluation.final_verdicts non-empty.
    7. every judge-role call returned a parseable verdict body (non-empty raw_text -- no 400 on
       the bare reasoning block). The distinct served_model count is reported as the (best-effort)
       multi-provider proxy; the BINDING check is parseability ("OR at minimum ...").
    """
    fr = manifest.get("four_role_evaluation") or {}
    status = manifest.get("status", "")
    checks: list[Check] = []

    checks.append(Check(
        "kimi.not_transport_exhausted",
        status != _TRANSPORT_EXHAUSTED,
        f"manifest.status={status!r} (must NOT be {_TRANSPORT_EXHAUSTED})",
    ))

    inert = bool(manifest.get("four_role_seam_inert", False))
    checks.append(Check(
        "kimi.seam_not_inert",
        not inert,
        (f"four_role_seam_inert={inert} (False == a real RoleTransport was injected by "
         f"Gate-B; True == PG_FOUR_ROLE_MODE on but no transport -> seam never ran)"),
    ))

    held = fr.get("held_reasons") or []
    seam_held = [h for h in held if isinstance(h, str) and h.startswith("seam_")]
    checks.append(Check(
        "kimi.no_seam_held_reason",
        not seam_held,
        (f"four_role_evaluation.held_reasons seam_*={seam_held or '[]'} "
         f"(a seam_timeout / seam_error:* held_reason == the seam tore)"),
    ))

    gaps = list(manifest.get("disclosed_gaps") or [])
    gaps += [g for g in (fr.get("gaps") or []) if isinstance(g, str)]
    seam_gap = [g for g in gaps if isinstance(g, str) and _SEAM_UNADJUDICATED in g]
    checks.append(Check(
        "kimi.no_seam_unadjudicated_gap",
        not seam_gap,
        (f"{_SEAM_UNADJUDICATED} disclosed gaps={len(seam_gap)} "
         f"(0 == the judge adjudicated; >0 == the seam could not bind the judge)"),
    ))

    total_429 = int((rate_limit_telemetry or {}).get("rate_limit_hits_total", -1))
    have_telemetry = rate_limit_telemetry is not None
    checks.append(Check(
        "kimi.no_429_storm",
        have_telemetry and 0 <= total_429 <= max_429,
        (f"four_role_rate_limit_telemetry.rate_limit_hits_total={total_429} <= max={max_429} "
         f"(telemetry_present={have_telemetry}; a missing sidecar == the seam never completed)"),
    ))

    fv = fr.get("final_verdicts") or {}
    checks.append(Check(
        "kimi.final_verdicts_nonempty",
        len(fv) > 0,
        f"four_role_evaluation.final_verdicts count={len(fv)} (>0 == the judge settled claims)",
    ))

    judge_calls = [c for c in role_calls if isinstance(c, dict) and c.get("role") == "judge"]
    used_fallback = False
    if not judge_calls:
        # robustness: if the role label differs, fall back to ALL role calls
        judge_calls = [c for c in role_calls if isinstance(c, dict)]
        used_fallback = True
    parseable = [c for c in judge_calls if (c.get("raw_text") or "").strip()]
    served = sorted({c.get("served_model") for c in judge_calls if c.get("served_model")})
    all_parseable = len(judge_calls) > 0 and len(parseable) == len(judge_calls)
    checks.append(Check(
        "kimi.judge_calls_parseable",
        all_parseable,
        (f"judge_calls={len(judge_calls)}{' (role==judge absent; used ALL role calls)' if used_fallback else ''} "
         f"parseable(non-empty raw_text)={len(parseable)}; distinct served_model="
         f"{served} (>1 == provider load-balancing; multi-provider is a proxy, parseability "
         f"is the binding check)"),
    ))

    return checks


# --------------------------------------------------------------------------------------------
# I/O wrappers + diced-preflight shell-out (offline, read-only, no spend)
# --------------------------------------------------------------------------------------------

def _resolve_run_dir(d: Path) -> Path:
    """The run_dir holds manifest.json directly. If the operator passes the --out-root instead,
    descend to the single child holding manifest.json. Fail loud on ambiguity/absence."""
    if (d / "manifest.json").is_file():
        return d
    children = [c for c in sorted(d.iterdir()) if c.is_dir() and (c / "manifest.json").is_file()] if d.is_dir() else []
    if len(children) == 1:
        return children[0]
    if not children:
        raise FileNotFoundError(
            f"no manifest.json in {d} nor in any immediate child -- pass the per-query run_dir"
        )
    raise FileNotFoundError(
        f"ambiguous: {len(children)} child run_dirs hold a manifest.json under {d}; "
        f"pass the specific per-query run_dir ({', '.join(c.name for c in children)})"
    )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def diced_preflight_checks(run_dir: Path, diced_path: Path, dice_names: list[str]) -> list[Check]:
    """Shell out to the (offline, read-only) diced preflight on the FRESH run_dir and assert the
    NAMED dice are GREEN. The diced preflight NEVER makes a paid call (its own docstring); we gate
    ONLY on the ``dice_names`` the caller passes (other dice may be RED for unrelated reasons on a
    single-query dir; each probe asserts only the dice its LAUNCH PATH can actually flip GREEN).

    WHICH DICE PER PROBE (the diced-leg/launch-path coupling -- Codex P1 #1344 wave-3):
      * BREADTH probe -> ``["D3_relevance_gate_fetch_budget"]`` ONLY. The breadth probe launches the
        NO-slate ``run_honest_sweep_r3.py`` (PG_BREADTH_ENRICHMENT_ENABLED stays OFF), so its proof
        is the FRONT-HALF demote-not-drop + fetch-budget dice (D3). The BACK-HALF cite-breadth dice
        ``D2_composition_breadth`` reads report.md cited/pool ratio and is GREEN only once the slate's
        post-gen weighted-enrichment fires -> it would stay RED here even on a correctly-fixed
        pipeline (a false-FAIL), so it is NOT asserted on the breadth probe.
      * KIMI probe -> ``["D2_composition_breadth"]``. The kimi probe launches via ``run_gate_b.py``
        WITH the slate -> enrichment ON -> the composer surfaces the weighted tail, so the cite-breadth
        dice can legitimately go GREEN there.

    A concurrent workflow owns pipeline_diced_preflight.py -- we only CONSUME its verdict."""
    if not diced_path.is_file():
        return [Check("diced.preflight_present", False, f"diced preflight not found at {diced_path}")]
    with tempfile.TemporaryDirectory(prefix="probe_diced_") as td:
        out = Path(td) / "diced.json"
        cmd = [sys.executable, str(diced_path), "--fixture", str(run_dir), "--json", str(out)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            return [Check("diced.ran", False, "diced preflight timed out (>900s)")]
        if not out.is_file():
            tail = (proc.stderr or proc.stdout or "")[-400:]
            return [Check("diced.ran", False,
                          f"diced preflight produced no --json (exit={proc.returncode}): {tail}")]
        payload = _load_json(out)
    offline = {r.get("name"): r.get("status") for r in payload.get("offline", []) or []}
    checks: list[Check] = []
    for dice in dice_names:
        st = offline.get(dice, "ABSENT")
        checks.append(Check(
            f"diced.{dice}", st == GREEN,
            f"{dice}={st} (was RED on the old banked fixture; GREEN proves the fix landed)",
        ))
    return checks


# --------------------------------------------------------------------------------------------
# PRINT mode
# --------------------------------------------------------------------------------------------

def _print_banner() -> None:
    print("=" * 92)
    print("  SMALL-SCALE VALIDATION PROBE (I-deepfix-001 #1344) -- NO SPEND, BUILD + OFFLINE-ASSERT")
    print("  This runner launches NO run, loads NO model, calls NO OpenRouter endpoint.")
    print("  The VM runs below are the OPERATOR's to launch (heavy runs are VM-only, §8.4).")
    print("=" * 92)


def print_breadth(_argv_note: str = "") -> None:
    print("\n--- PROBE 1: BREADTH front-half (the §-1.3 demote + raised-budget proof, cheap) ---")
    print("WHY one query end-to-end: run_honest_sweep_r3.py has NO --stop-after flag and the")
    print("corpus_snapshot checkpoint does NOT carry retrieval.relevance_gate; the §-1.3 demote")
    print("proof lives ONLY in the finalized manifest.json. A single NON-simple query is the cheap")
    print("unit (far below the $40 8-query sweep). Do NOT pick a trivially-simple slug: the sweep")
    print("simple-router would drop the fetch budget to PG_SIMPLE_FETCH_CAP=40.")
    print("NOTE on the launcher: this FRONT-HALF breadth proof is FINE via run_honest_sweep_r3.py.")
    print("The §-1.3 demote + fetch-budget mechanism lives in RETRIEVAL (manifest.retrieval.*), not")
    print("in the post-gen breadth ENRICHMENT, so it fires with PG_RETRIEVAL_RELEVANCE_GATE=1 set")
    print("explicitly + PG_SWEEP_FETCH_CAP defaulting to 200 -- the slate (which run_honest_sweep_r3.py")
    print("does NOT apply -> PG_BREADTH_ENRICHMENT_ENABLED stays OFF) is not needed for THIS proof.")
    print("(The kimi seam probe below DOES need the slate, so it launches via run_gate_b.py.)")
    print("\nVM COMMAND:")
    print("  " + breadth_vm_command())
    print("\nTHEN assert offline on the fresh run_dir (this runner, no spend):")
    print("  python scripts/small_scale_validation_probe.py --probe breadth --assert-dir "
          "<fresh_run_dir>")
    print("\nASSERTIONS (fail-loud):")
    print("  - manifest.retrieval.relevance_gate is PRESENT")
    print("  - relevance_gate.demoted_fetched_to_fill > 0          (the §-1.3 demote fired)")
    print("  - retrieval_caps.dropped_pre_fetch <= the disclosed fetch budget (no hard floor-drop)")
    print("  - candidates_fetched materially > the legacy 40")
    print("  - diced preflight on the fresh dir: D3_relevance_gate_fetch_budget == GREEN")
    print("    (the FRONT-HALF demote+budget dice; the BACK-HALF cite-breadth dice "
          "D2_composition_breadth belongs to the KIMI probe, which runs WITH the slate)")


def print_kimi(_argv_note: str = "") -> None:
    print("\n--- PROBE 2: KIMI 4-role D8 seam smoke (cheap live proof the seam completes) ---")
    print("WHY run_gate_b.py --resume (NOT run_honest_sweep_r3.py --pathB-gate): run_gate_b.py is the")
    print("ONLY slate-applying entrypoint. Its main()/run_gate_b_query construct the kimi judge")
    print("transport (benchmark_verifier_lineup), call enable_four_role_mode() (PG_FOUR_ROLE_MODE=1),")
    print("AND apply_full_capability_benchmark_slate() (PG_BREADTH_ENRICHMENT_ENABLED ON -> the judge")
    print("adjudicates the FULL breadth basket). run_honest_sweep_r3.py --pathB-gate does NOT apply the")
    print("slate -> enrichment OFF -> the kimi-judge path is not really exercised. run_gate_b.py has its")
    print("OWN --resume, so it re-enters from a SMALL banked corpus_snapshot (NO re-fetch, cheap).")
    print("PG_BENCHMARK_JUDGE_MODEL is left UNSET so the default moonshotai/kimi-k2.6 judge is used.")
    print("This is the LIVE companion to the diced preflight's D4_four_role_judge_seam_LIVE dice.")
    print("\nVM COMMAND (point --out-root at a dir already holding <domain>/<slug>/corpus_snapshot.json):")
    print("  " + kimi_vm_command())
    print("\nTHEN assert offline on the produced run_dir (this runner, no spend):")
    print("  python scripts/small_scale_validation_probe.py --probe kimi --assert-dir "
          "<resume_run_dir>")
    print("\nASSERTIONS (fail-loud):")
    print("  - manifest.status != abort_role_transport_exhausted")
    print("  - four_role_seam_inert is not True; no seam_* held_reason; no "
          "four_role_seam_unadjudicated gap")
    print("  - four_role_rate_limit_telemetry.rate_limit_hits_total == 0   (no 429-storm)")
    print("  - four_role_evaluation.final_verdicts non-empty")
    print("  - every judge call returned a parseable verdict body (no 400 on the bare reasoning "
          "block); distinct served_model reported as the multi-provider proxy")
    print("  - diced preflight on the produced dir: D2_composition_breadth == GREEN")
    print("    (the slate is ON here -> post-gen weighted-enrichment fires -> the composer surfaces "
          "the cite-breadth tail; this dice cannot go GREEN on the no-slate breadth probe)")


# --------------------------------------------------------------------------------------------
# ASSERT mode
# --------------------------------------------------------------------------------------------

def assert_breadth(run_dir: Path, diced_path: Path) -> list[Check]:
    manifest = _load_json(run_dir / "manifest.json")
    legacy_floor = _env_int("PG_PROBE_LEGACY_FETCH_FLOOR", 40)
    checks = breadth_manifest_checks(manifest, legacy_fetch_floor=legacy_floor)
    # FRONT-HALF diced leg ONLY: the breadth probe launches the NO-slate run_honest_sweep_r3.py, so
    # the BACK-HALF cite-breadth dice (D2_composition_breadth) cannot go GREEN here (enrichment OFF)
    # -> asserting it would be a false-FAIL. Assert the FRONT-HALF demote+budget dice only; the
    # cite-breadth dice is asserted by the KIMI probe (slate ON -> enrichment surfaces the tail).
    checks += diced_preflight_checks(run_dir, diced_path, ["D3_relevance_gate_fetch_budget"])
    return checks


def assert_kimi(run_dir: Path, diced_path: Path) -> list[Check]:
    manifest = _load_json(run_dir / "manifest.json")
    rl_path = run_dir / "four_role_rate_limit_telemetry.json"
    rate_limit = _load_json(rl_path) if rl_path.is_file() else None
    role_calls = _load_jsonl(run_dir / "four_role_role_calls.jsonl")
    max_429 = _env_int("PG_PROBE_MAX_429", 0)
    checks = kimi_seam_checks(manifest, rate_limit, role_calls, max_429=max_429)
    # BACK-HALF cite-breadth diced leg: the kimi probe launches via run_gate_b.py WITH the slate ->
    # PG_BREADTH_ENRICHMENT_ENABLED ON -> the composer surfaces the weighted tail, so the post-gen
    # D2_composition_breadth dice can legitimately go GREEN here (it cannot on the no-slate breadth probe).
    checks += diced_preflight_checks(run_dir, diced_path, ["D2_composition_breadth"])
    return checks


def _print_checks(title: str, checks: list[Check]) -> bool:
    name_w = max([len(c.name) for c in checks] + [24])
    print(f"\n  {title}")
    print("  " + "-" * (name_w + 8))
    for c in checks:
        mark = "GREEN" if c.passed else "RED  "
        print(f"  {mark}  {c.name:<{name_w}}  {c.detail}")
    return all(c.passed for c in checks)


# --------------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Small-scale validation probe for the breadth (A5) + kimi-judge (A6) fixes. "
                    "PRINTS the VM command(s); with --assert-dir runs OFFLINE assertions. NEVER spends.",
    )
    ap.add_argument("--probe", choices=["breadth", "kimi", "both"], required=True,
                    help="which fix to probe.")
    ap.add_argument("--assert-dir", default=None,
                    help="run OFFLINE assertions on this ALREADY-PRODUCED run_dir (or its out-root). "
                         "Omit to PRINT the VM command(s) instead.")
    ap.add_argument("--diced-preflight", default=str(_DEFAULT_DICED_PREFLIGHT),
                    help="path to pipeline_diced_preflight.py (breadth assert shells out to it).")
    ap.add_argument("--json", default=None, help="write a machine-readable result sidecar here.")
    args = ap.parse_args(argv)

    probes = ["breadth", "kimi"] if args.probe == "both" else [args.probe]

    # ---- PRINT mode -----------------------------------------------------------------------
    if not args.assert_dir:
        _print_banner()
        if "breadth" in probes:
            print_breadth()
        if "kimi" in probes:
            print_kimi()
        print("\n" + "=" * 92)
        print("  PRINT mode only -- nothing was executed, no spend. Launch the VM command(s) above,")
        print("  then re-run with --assert-dir <fresh_run_dir> to validate offline.")
        print("=" * 92)
        return 0

    # ---- ASSERT mode (offline, read-only) -------------------------------------------------
    raw_dir = Path(args.assert_dir)
    if not raw_dir.exists():
        print(f"[probe] HARNESS ERROR: --assert-dir not found: {raw_dir}", file=sys.stderr)
        return 2
    try:
        run_dir = _resolve_run_dir(raw_dir)
    except FileNotFoundError as exc:
        print(f"[probe] HARNESS ERROR: {exc}", file=sys.stderr)
        return 2

    diced_path = Path(args.diced_preflight)
    print(f"[probe] assert mode on run_dir: {run_dir}")
    all_results: dict[str, list[Check]] = {}
    overall_ok = True

    if "breadth" in probes:
        try:
            checks = assert_breadth(run_dir, diced_path)
        except Exception as exc:  # fail-loud: an un-runnable assertion is RED, never skipped
            checks = [Check("breadth.harness", False, f"EXCEPTION {type(exc).__name__}: {exc}")]
        all_results["breadth"] = checks
        overall_ok &= _print_checks("PROBE 1 -- BREADTH (front-half §-1.3 demote + budget)", checks)

    if "kimi" in probes:
        try:
            checks = assert_kimi(run_dir, diced_path)
        except Exception as exc:
            checks = [Check("kimi.harness", False, f"EXCEPTION {type(exc).__name__}: {exc}")]
        all_results["kimi"] = checks
        overall_ok &= _print_checks("PROBE 2 -- KIMI (4-role D8 seam completion)", checks)

    verdict = "PASS" if overall_ok else "FAIL"
    n_red = sum(1 for cs in all_results.values() for c in cs if not c.passed)
    print(f"\n  PROBE RESULT: {verdict}  ({n_red} RED check(s))")
    print("=" * 92)

    if args.json:
        payload = {
            "verdict": verdict,
            "run_dir": str(run_dir),
            "probes": {
                name: [c.__dict__ for c in cs] for name, cs in all_results.items()
            },
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[probe] wrote sidecar -> {args.json}")

    # Fail-loud: exit non-zero on any RED check.
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
