"""Offline distill-replay proof harness (I-perm-019 / proves #1209 keystone).

Controlled A/B over a SAVED drb_76 evidence pool: run the SAME section through
the production ``_run_section`` twice — once with ``PG_SECTION_DISTILL`` OFF
(legacy single-pass) and once ON (the #1209 map-reduce keystone) — and compare
strict_verify-verified sentence counts. Proves the keystone RAISES verified
coverage + LOWERS drop rate without new fabrication, BEFORE any paid Q1 re-run.

Faithfulness: this harness ORCHESTRATES the real production ``_run_section`` /
``strict_verify`` (zero logic drift — the ``tests/polaris_graph/replay``
pattern). It changes NO gate. The live A/B makes real LLM calls and is gated
behind ``--live`` (default OFF) so this module imports + unit-tests offline.

Usage (offline, no spend):
    python scripts/dr_benchmark/offline_distill_replay.py            # prints how to run live
Usage (live A/B, authorized spend, on the OVH VM):
    python scripts/dr_benchmark/offline_distill_replay.py --live \
        --pool outputs/audits/I-perm-010/run_drb76_iter2/drb_76_gut_microbiota_crc/evidence_pool.json \
        --section-title "Safety and contraindications" \
        --section-focus "Safety, adverse events, and contraindications of the intervention" \
        --ts 20260611T120000Z

LAW II: the verified-count LIFT is a real measured result of the ``--live`` run;
this module never fabricates it. Offline it only exercises the counting/compare
logic against deterministic inputs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# I-perm-019 (#1211) Codex diff-gate iter-1 P1: bootstrap the repo root onto
# sys.path so the deferred ``import src.polaris_graph...`` in the --live path
# resolves when this file is run DIRECTLY (``python
# scripts/dr_benchmark/offline_distill_replay.py``) — direct execution seeds
# sys.path[0] with scripts/dr_benchmark, NOT the repo root, so without this the
# --live arm dies with ``ModuleNotFoundError: No module named 'src'`` before the
# A/B proof runs. Mirrors run_honest_sweep_r3.py's ROOT bootstrap.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Module-level imports of the PRODUCTION generator are deferred into the live
# path so the offline unit test can import this module + its pure helpers
# without importing the heavy generator stack.


def load_pool(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load a saved evidence_pool.json (a LIST of rows) into the
    ``{evidence_id: row}`` dict shape ``_run_section`` consumes. Fail loud on a
    row missing ``evidence_id`` (LAW II — no silent drop)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else list(raw.values())
    pool: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows):
        eid = row.get("evidence_id")
        if not eid:
            raise ValueError(f"evidence row {i} has no evidence_id — refusing to drop it silently")
        pool[eid] = row
    if not pool:
        raise ValueError(f"empty evidence pool: {path}")
    return pool


def result_metrics(res: Any) -> dict[str, Any]:
    """Extract the comparable metrics from a production ``SectionResult``.

    Pure — takes any object exposing the SectionResult fields, so the offline
    test can pass a lightweight stand-in.
    """
    verified = int(getattr(res, "sentences_verified", 0) or 0)
    dropped = int(getattr(res, "sentences_dropped", 0) or 0)
    total = verified + dropped
    verified_text = getattr(res, "verified_text", "") or ""
    return {
        "sentences_verified": verified,
        "sentences_dropped": dropped,
        "total_sentences": total,
        "drop_rate": (dropped / total) if total else 0.0,
        "body_words": len(verified_text.split()),
        "regen_attempted": bool(getattr(res, "regen_attempted", False)),
        "dropped_due_to_failure": bool(getattr(res, "dropped_due_to_failure", False)),
        "input_tokens": int(getattr(res, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(res, "output_tokens", 0) or 0),
        "error": getattr(res, "error", "") or "",
    }


def compare(legacy: dict[str, Any], distill: dict[str, Any]) -> dict[str, Any]:
    """Compare two arms' metrics. ``distill_raises_verified`` is the keystone's
    acceptance signal: distilled verified count >= legacy verified count."""
    return {
        "delta_verified": distill["sentences_verified"] - legacy["sentences_verified"],
        "delta_drop_rate": round(distill["drop_rate"] - legacy["drop_rate"], 4),
        "delta_body_words": distill["body_words"] - legacy["body_words"],
        "distill_raises_verified": distill["sentences_verified"] >= legacy["sentences_verified"],
        "distill_lowers_drop_rate": distill["drop_rate"] <= legacy["drop_rate"],
    }


def build_report(
    *,
    pool_path: str,
    section_title: str,
    section_focus: str,
    n_ev: int,
    model: str,
    legacy: dict[str, Any],
    distill: dict[str, Any],
    ts: str,
) -> dict[str, Any]:
    """Assemble the full JSON report (pure)."""
    return {
        "harness": "offline_distill_replay",
        "issue": "I-perm-019 / #1209",
        "ts": ts,
        "pool": pool_path,
        "section": {"title": section_title, "focus": section_focus, "n_ev": n_ev},
        "model": model,
        "legacy_off": legacy,
        "distill_on": distill,
        "comparison": compare(legacy, distill),
    }


async def _run_arm(
    section: Any,
    pool: dict[str, dict[str, Any]],
    *,
    distill_on: bool,
    model: str,
    temperature: float,
    max_tokens_per_section: int,
    min_kept_fraction: float,
) -> Any:
    """Run ONE arm through the production ``_run_section`` with the flag toggled.

    Sets ``PG_SECTION_DISTILL`` for exactly this call and restores it after, so
    the two arms are otherwise identical inputs.
    """
    from src.polaris_graph.generator.multi_section_generator import _run_section

    prev = os.environ.get("PG_SECTION_DISTILL")
    os.environ["PG_SECTION_DISTILL"] = "1" if distill_on else "0"
    try:
        return await _run_section(
            section,
            pool,
            model=model,
            temperature=temperature,
            max_tokens_per_section=max_tokens_per_section,
            min_kept_fraction=min_kept_fraction,
        )
    finally:
        if prev is None:
            os.environ.pop("PG_SECTION_DISTILL", None)
        else:
            os.environ["PG_SECTION_DISTILL"] = prev


async def run_live_ab(args: argparse.Namespace) -> int:
    """Run both arms live, write the report + per-arm verified text, and return
    a process exit code (nonzero if the keystone did NOT raise verified count —
    fail loud, never pass a regression silently)."""
    from src.polaris_graph.generator.multi_section_generator import SectionPlan

    pool = load_pool(args.pool)
    ev_ids = list(pool.keys())
    if args.max_ev and args.max_ev > 0:
        ev_ids = ev_ids[: args.max_ev]
    section = SectionPlan(title=args.section_title, focus=args.section_focus, ev_ids=ev_ids)

    legacy_res = await _run_arm(
        section, pool, distill_on=False, model=args.model,
        temperature=args.temperature, max_tokens_per_section=args.max_tokens,
        min_kept_fraction=args.min_kept_fraction,
    )
    distill_res = await _run_arm(
        section, pool, distill_on=True, model=args.model,
        temperature=args.temperature, max_tokens_per_section=args.max_tokens,
        min_kept_fraction=args.min_kept_fraction,
    )

    legacy = result_metrics(legacy_res)
    distill = result_metrics(distill_res)
    report = build_report(
        pool_path=args.pool, section_title=args.section_title,
        section_focus=args.section_focus, n_ev=len(ev_ids), model=args.model,
        legacy=legacy, distill=distill, ts=args.ts,
    )

    out_dir = Path(args.out or "outputs/audits/I-perm-019")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"replay_{args.ts}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    # Dump both arms' verified prose for the §-1.1 line-by-line fabrication audit.
    (out_dir / f"legacy_{args.ts}.txt").write_text(
        getattr(legacy_res, "verified_text", "") or "", encoding="utf-8"
    )
    (out_dir / f"distill_{args.ts}.txt").write_text(
        getattr(distill_res, "verified_text", "") or "", encoding="utf-8"
    )

    cmp = report["comparison"]
    print(json.dumps(report, indent=2))
    print(
        f"\n[offline_distill_replay] verified: legacy={legacy['sentences_verified']} "
        f"-> distill={distill['sentences_verified']} (delta {cmp['delta_verified']:+d}); "
        f"drop_rate {legacy['drop_rate']:.2f} -> {distill['drop_rate']:.2f}; "
        f"body_words {legacy['body_words']} -> {distill['body_words']}"
    )
    if not cmp["distill_raises_verified"]:
        print(
            "[offline_distill_replay] FAIL: distill LOWERED verified count — "
            "the keystone regressed on this section. Investigate before any paid run."
        )
        return 1
    print("[offline_distill_replay] PASS: distill did not lower verified count.")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline distill-replay A/B proof harness (#1209).")
    p.add_argument("--live", action="store_true",
                   help="Make REAL LLM calls (authorized spend). Default OFF refuses to run the arms.")
    p.add_argument("--pool", type=str,
                   default="outputs/audits/I-perm-010/run_drb76_iter2/drb_76_gut_microbiota_crc/evidence_pool.json")
    p.add_argument("--section-title", type=str, default="Safety and contraindications")
    p.add_argument("--section-focus", type=str,
                   default="Safety, adverse events, and contraindications of the intervention")
    p.add_argument("--max-ev", type=int, default=40,
                   help="Cap evidence rows fed to the section (mirrors PG_MAX_EV_PER_SECTION).")
    p.add_argument("--model", type=str, default=os.getenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro"))
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--max-tokens", type=int, default=int(os.getenv("PG_MAX_TOKENS_PER_SECTION", "16384")))
    p.add_argument("--min-kept-fraction", type=float, default=0.4)
    p.add_argument("--ts", type=str, default="manual",
                   help="Timestamp tag for output filenames (pass explicitly; no wall-clock in-script).")
    p.add_argument("--out", type=str, default="")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live:
        print(
            "offline_distill_replay: refusing to run the LIVE A/B without --live "
            "(it makes real, billable LLM calls).\n"
            "To run the authorized micro-proof on the OVH VM:\n"
            "  python scripts/dr_benchmark/offline_distill_replay.py --live \\\n"
            f"    --pool {build_arg_parser().get_default('pool')} \\\n"
            "    --section-title \"Safety and contraindications\" \\\n"
            "    --section-focus \"Safety, adverse events, and contraindications of the intervention\" \\\n"
            "    --ts <UTC_STAMP>\n"
            "It runs the SAME section through _run_section with PG_SECTION_DISTILL OFF then ON and "
            "compares strict_verify-verified sentence counts."
        )
        return 0
    return asyncio.run(run_live_ab(args))


if __name__ == "__main__":
    raise SystemExit(main())
