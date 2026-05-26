"""Operator-launched smoke for PG_ATOM_REFUSAL_MODE=log_only calibration.

Closes Codex PR #906 iter-5 follow-up #1: "Real-run smoke with
PG_ATOM_REFUSAL_MODE=log_only to calibrate refusal rates."

Why operator-launched (not autonomous):
    Real V4 Pro API calls cost actual $$. Per CLAUDE.md §8.4 + the
    operator's stated preference ("control the resources carefully"),
    autonomous heavy ML/API runs are forbidden. This script is the
    canonical entry point the operator invokes when ready.

What this captures:
    1. PG_ATOM_REFUSAL_MODE=log_only — validator populates SectionResult
       atom_validation_result + writes gaps.json sidecar; report.md is
       UNCHANGED from pre-Step-3b behavior. Safe to compare reports
       side-by-side with off-mode baseline.
    2. Single-vector smoke (Tirzepatide T2DM by default — known to have
       atomizable claims from SURPASS-2 evidence).
    3. Aggregates per-section refusal_count + soft_mismatch_count +
       allowed_count into a calibration summary printed at end.

Usage (manual operator invocation):
    PG_ATOM_REFUSAL_MODE=log_only python scripts/smoke_atom_refusal_log_only.py
    # OR with explicit vector:
    PG_ATOM_REFUSAL_MODE=log_only python scripts/smoke_atom_refusal_log_only.py \\
        --vector clinical_tirzepatide_t2dm

Output:
    - outputs/honest_sweep_r3/clinical/<vector>/gaps.json
        (per Codex APPROVE_DESIGN schema)
    - stdout: refusal-rate calibration summary

Decision criteria for flipping to PG_ATOM_REFUSAL_MODE=strict (per
Codex Step 3b iter-1 advice):
    - Average refusal_rate < 30% across sections (else V4 Pro's atom
      compliance needs prompt tightening before strict)
    - Zero "missing_atom_citation" reasons where a valid atom_NNN
      should have existed (would indicate validator false-positive)
    - SOFT mismatch count low (else the SOFT layer's value-token
      matching is too strict)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Operator smoke for atom-refusal log_only calibration. "
            "Real V4 Pro API calls — operator-launched only."
        ),
    )
    p.add_argument(
        "--vector",
        default="clinical_tirzepatide_t2dm",
        help="Vector slug to run (default: clinical_tirzepatide_t2dm)",
    )
    p.add_argument(
        "--out-root",
        default="outputs/honest_sweep_r3",
        help="Output root (default: outputs/honest_sweep_r3) — matches "
             "run_honest_sweep_r3.py's flag exactly.",
    )
    args = p.parse_args()

    # Operator must set the mode explicitly — script does not flip the
    # flag for them. Defensive check.
    mode = os.environ.get("PG_ATOM_REFUSAL_MODE", "off").strip().lower()
    if mode != "log_only":
        print(
            "ERROR: PG_ATOM_REFUSAL_MODE must be 'log_only' for this smoke. "
            f"Got {mode!r}. Set via:\n"
            "  PG_ATOM_REFUSAL_MODE=log_only python scripts/smoke_atom_refusal_log_only.py",
            file=sys.stderr,
        )
        return 2

    # Sanity check the canonical sweep entry exists
    sweep_script = Path("scripts/run_honest_sweep_r3.py")
    if not sweep_script.exists():
        print(f"ERROR: {sweep_script} not found — wrong CWD?", file=sys.stderr)
        return 2

    # Launch the single-vector sweep
    cmd = [
        sys.executable,
        str(sweep_script),
        "--only",
        args.vector,
        "--out-root",
        args.out_root,
    ]
    print(f"[smoke] launching: {' '.join(cmd)}", flush=True)
    print(f"[smoke] PG_ATOM_REFUSAL_MODE={mode}", flush=True)
    rc = subprocess.run(cmd, env=os.environ.copy()).returncode
    if rc != 0:
        print(f"[smoke] sweep returned non-zero exit: {rc}", file=sys.stderr)
        return rc

    # Locate the produced gaps.json
    candidate_dirs = list(Path(args.out_root).rglob(args.vector))
    if not candidate_dirs:
        print(
            f"[smoke] WARN: no run directory matching {args.vector!r} found "
            f"under {args.out_root}",
            file=sys.stderr,
        )
        return 0
    run_dir = candidate_dirs[0]
    gaps_path = run_dir / "gaps.json"
    if not gaps_path.exists():
        print(
            f"[smoke] WARN: gaps.json not produced at {gaps_path}. "
            f"Atom validator may have skipped (empty catalog?) or hooked "
            f"path didn't trigger. Check run_log.txt for "
            f"'[gaps]' or '[multi_section] I-gen-005 Step 3b atom validation' lines.",
            file=sys.stderr,
        )
        return 0

    # Print calibration summary
    with gaps_path.open(encoding="utf-8") as f:
        gaps = json.load(f)

    print("")
    print("=" * 70)
    print("ATOM-REFUSAL LOG_ONLY CALIBRATION SUMMARY")
    print("=" * 70)
    print(f"document_id:    {gaps.get('document_id')}")
    print(f"generated_at:   {gaps.get('generated_at')}")
    totals = gaps.get("totals", {})
    print(f"total_sentences: {totals.get('total_sentences', 0)}")
    print(f"  refused:       {totals.get('refused', 0)}")
    print(f"  soft_mismatch: {totals.get('soft_mismatch', 0)}")
    print(f"  allowed:       {totals.get('allowed', 0)}")

    total_s = totals.get("total_sentences", 0)
    if total_s > 0:
        refusal_rate = totals.get("refused", 0) / total_s
        print(f"  refusal_rate:  {refusal_rate:.1%}")
        # Codex iter-1 advice threshold
        if refusal_rate < 0.30:
            print("  → strict-rollout candidate (refusal_rate < 30%)")
        else:
            print(
                "  → V4 Pro atom compliance needs work BEFORE flipping to "
                "strict (refusal_rate >= 30%)"
            )

    print("")
    print("Per-section breakdown:")
    for sec in gaps.get("sections", []):
        s = sec.get("summary", {})
        title = sec.get("section_title", "?")
        print(
            f"  {title!r}: "
            f"refused={s.get('refused', 0)} "
            f"soft={s.get('soft_mismatch', 0)} "
            f"allowed={s.get('allowed', 0)}"
        )

    # Top refusal reasons (a sample)
    reason_counts: dict[str, int] = {}
    for sec in gaps.get("sections", []):
        for claim in sec.get("claims", []):
            r = claim.get("reason")
            if r and r != "no_violation":
                reason_counts[r] = reason_counts.get(r, 0) + 1

    if reason_counts:
        print("")
        print("Top non-violation reasons:")
        for reason, n in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {n}")

    print("=" * 70)
    print(f"Full gaps.json: {gaps_path}")
    print("")
    print(
        "Next: if refusal_rate looks reasonable, flip to "
        "PG_ATOM_REFUSAL_MODE=strict and rerun the same sweep. Refused "
        "sentences will be replaced with refusal disclosure blocks in "
        "report.md."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
