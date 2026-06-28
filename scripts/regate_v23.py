"""M-34 re-gate: re-run PRISMA rule checks + evaluator_gate on an
existing sweep artifact directory WITHOUT re-generation or re-sweep.

Use case: V23 full-scale aborted on PT11 (3/36 uncited decimals from
long-sentence window bug). M-34 fixes the bug in
`run_rule_checks`. This script replays the evaluator on the existing
report.md, recomputes the gate, and rewrites `manifest.json`,
`evaluator_rule_checks.json`, and the matching entry in
`sweep_summary.json`/`sweep_summary.md`.

This is evaluator-only. It does NOT re-run the judge (already ran
during the original sweep; the judge verdicts stored in
`judge_output.json` (or legacy `qwen_judge_output.json`) are reused
verbatim).

Usage:
    python scripts/regate_v23.py \\
        --sweep-root outputs/full_scale_v23 \\
        --slug clinical_tirzepatide_t2dm
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.polaris_graph.evaluator.evaluator_gate import compute_evaluator_gate
from src.polaris_graph.evaluator.external_evaluator import (
    RuleCheckResult,
    run_rule_checks,
)


@dataclass
class _EvOutShim:
    """Minimal shim of EvaluatorOutput for compute_evaluator_gate."""
    rule_checks: list[RuleCheckResult]
    contradictions_missing: list[str]


@dataclass
class _JudgeShim:
    """Minimal shim of JudgeResult for compute_evaluator_gate."""
    parse_ok: bool
    verdicts: dict[str, Any]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _status_from_gate(gate) -> str:
    """Mirror the orchestrator's status-selection logic for the
    evaluator-gated path. See run_honest_sweep_r3.py:1326-1344."""
    if gate.gate_class == "abort":
        return "abort_evaluator_critical"
    if gate.gate_class == "partial" and gate.judge_critical_axes:
        return "partial_evaluator_advisory"
    # I-run11-009 (#1055): a release-withholding gate (e.g. judge_parse_failed ->
    # advisory_unavailable + release_allowed=False) must NOT map to "success" — mirror the
    # fail-closed orchestrator ladder so the regate manifest cannot contradict the gate.
    if not getattr(gate, "release_allowed", True):
        return "abort_evaluator_critical"
    return "success"


def regate_run(run_dir: Path) -> dict[str, Any]:
    report_path = run_dir / "report.md"
    manifest_path = run_dir / "manifest.json"
    rule_checks_path = run_dir / "evaluator_rule_checks.json"
    judge_path = run_dir / "judge_output.json"
    if not judge_path.exists():
        # I-modref-004 (#530): legacy V23 artifacts use the old filename.
        judge_path = run_dir / "qwen_judge_output.json"
    protocol_path = run_dir / "protocol.json"
    contradictions_path = run_dir / "contradictions.json"
    bibliography_path = run_dir / "bibliography.json"

    report_text = report_path.read_text(encoding="utf-8")
    manifest_prev = _load_json(manifest_path)
    rule_checks_prev = _load_json(rule_checks_path)
    judge_prev = _load_json(judge_path) if judge_path.exists() else {}
    protocol = _load_json(protocol_path)
    contradictions = (
        _load_json(contradictions_path)
        if contradictions_path.exists()
        else []
    )
    # evaluator_rule_checks.json has shape {... "rule_checks": [...], ...}
    contradictions_for_checks = (
        contradictions.get("contradictions", contradictions)
        if isinstance(contradictions, dict)
        else contradictions
    )
    biblio = _load_json(bibliography_path) if bibliography_path.exists() else []
    evidence_pool = {
        entry.get("evidence_id", f"ev_{i:03d}"): entry
        for i, entry in enumerate(biblio if isinstance(biblio, list) else [])
    }

    generator_model = manifest_prev.get("generator", {}).get(
        "model",
        rule_checks_prev.get("generator_model", "deepseek/deepseek-v4-pro"),
    )
    evaluator_model = rule_checks_prev.get(
        "evaluator_model", "google/gemma-4-31b-it"
    )

    # I-deepfix-001 B4 P2-B (#1344): thread the generator/evaluator training families (derived from
    # the resolved model names) so PT03 verifies the two-family invariant HONESTLY on replay. Without
    # them, run_rule_checks now treats segregation as NOT-proven (conservative) for an LLM evaluator.
    from src.polaris_graph.llm.openrouter_client import family_from_model  # noqa: PLC0415
    generator_family = family_from_model(generator_model)
    evaluator_family = family_from_model(evaluator_model)

    # Reconstruct tier_distribution_report from manifest.corpus.tier_fractions.
    # The original sweep passes asdict(compute_tier_distribution(...)); we
    # only need the tier_fractions key for PT07's static check.
    corpus_block = manifest_prev.get("corpus", {}) or {}
    tier_distribution_report = None
    if "tier_fractions" in corpus_block:
        tier_distribution_report = {"tier_fractions": corpus_block["tier_fractions"]}

    new_results, n_contra_disclosed, missing_contra = run_rule_checks(
        report_text=report_text,
        protocol=protocol,
        tier_distribution_report=tier_distribution_report,
        contradictions=contradictions_for_checks,
        evidence_pool=evidence_pool,
        generator_model=generator_model,
        evaluator_model=evaluator_model,
        generator_family=generator_family,
        evaluator_family=evaluator_family,
    )

    new_rule_checks_payload = dict(rule_checks_prev)
    new_rule_checks_payload["rule_checks"] = [
        {
            "item_id": r.item_id,
            "name": r.name,
            "passed": r.passed,
            "details": r.details,
        }
        for r in new_results
    ]
    new_rule_checks_payload["contradictions_disclosed"] = n_contra_disclosed
    new_rule_checks_payload["contradictions_missing"] = missing_contra
    new_rule_checks_payload["_regate_note"] = (
        "Re-gated under M-34 (PT11 lookahead widen). Prior gate was "
        f"status={manifest_prev.get('status')!r}, "
        f"release_allowed={manifest_prev.get('release_allowed')}."
    )

    ev_shim = _EvOutShim(
        rule_checks=new_results,
        contradictions_missing=missing_contra,
    )
    judge_verdicts = judge_prev.get("verdicts", {}) if isinstance(judge_prev, dict) else {}
    judge_shim = _JudgeShim(
        parse_ok=bool(judge_verdicts),
        verdicts=judge_verdicts,
    )
    adequacy = manifest_prev.get("adequacy")
    completeness = manifest_prev.get("completeness")
    new_gate = compute_evaluator_gate(
        ev_shim,
        judge_result=judge_shim,
        adequacy=adequacy,
        completeness=completeness,
    )
    new_status = _status_from_gate(new_gate)

    new_manifest = dict(manifest_prev)
    new_manifest["evaluator_gate"] = new_gate.to_dict()
    new_manifest["release_allowed"] = new_gate.release_allowed
    new_manifest["evaluator_rule_pass"] = sum(
        1 for r in new_results if r.passed
    )
    new_manifest["evaluator_rule_fail"] = sum(
        1 for r in new_results if not r.passed
    )
    new_manifest["status"] = new_status
    new_manifest["_regate_prev_status"] = manifest_prev.get("status")
    new_manifest["_regate_prev_release_allowed"] = manifest_prev.get(
        "release_allowed"
    )
    new_manifest["_regate_note"] = (
        "Re-gated under M-34 (commit bf78396) — PT11 lookahead-window "
        "widened 200→1000 chars. No re-generation or re-retrieval."
    )

    _dump_json(manifest_path, new_manifest)
    _dump_json(rule_checks_path, new_rule_checks_payload)

    return {
        "run_dir": str(run_dir),
        "prev_status": manifest_prev.get("status"),
        "prev_release_allowed": manifest_prev.get("release_allowed"),
        "new_status": new_status,
        "new_release_allowed": new_gate.release_allowed,
        "pt11_details": next(
            (r.details for r in new_results if r.item_id == "PT11"),
            "",
        ),
        "evaluator_rule_pass": new_manifest["evaluator_rule_pass"],
        "evaluator_rule_fail": new_manifest["evaluator_rule_fail"],
        "gate_reasons": new_gate.reasons,
    }


def update_sweep_summary(
    sweep_root: Path,
    slug: str,
    regate_result: dict[str, Any],
) -> None:
    summary_path = sweep_root / "sweep_summary.json"
    if not summary_path.exists():
        return
    summary = _load_json(summary_path)
    if not isinstance(summary, list):
        return
    for entry in summary:
        if entry.get("slug") == slug:
            entry["status"] = regate_result["new_status"]
            manifest = entry.get("manifest")
            if isinstance(manifest, dict):
                manifest["status"] = regate_result["new_status"]
                manifest["release_allowed"] = regate_result["new_release_allowed"]
                manifest["evaluator_rule_pass"] = regate_result["evaluator_rule_pass"]
                manifest["evaluator_rule_fail"] = regate_result["evaluator_rule_fail"]
            entry["_regate_note"] = (
                f"Re-gated under M-34; prior status "
                f"{regate_result['prev_status']!r} "
                f"(release_allowed={regate_result['prev_release_allowed']})."
            )
            break
    _dump_json(summary_path, summary)

    # Also patch the matrix markdown for operator visibility.
    md_path = sweep_root / "sweep_summary.md"
    if md_path.exists():
        md = md_path.read_text(encoding="utf-8")
        md += (
            f"\n\n> Note: {slug} re-gated under M-34 on re-evaluation. "
            f"Prior status `{regate_result['prev_status']}` → "
            f"new status `{regate_result['new_status']}` "
            f"(release_allowed={regate_result['new_release_allowed']}).\n"
        )
        md_path.write_text(md, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sweep-root",
        default="outputs/full_scale_v23",
        help="Sweep output root directory (default: outputs/full_scale_v23)",
    )
    parser.add_argument(
        "--slug",
        default="clinical_tirzepatide_t2dm",
        help="Slug to re-gate (default: clinical_tirzepatide_t2dm)",
    )
    args = parser.parse_args()

    sweep_root = Path(args.sweep_root)
    # Find the run directory matching the slug.
    candidates = list(sweep_root.rglob("manifest.json"))
    target = None
    for c in candidates:
        if c.parent.name == args.slug:
            target = c.parent
            break
    if target is None:
        print(f"ERROR: slug {args.slug!r} not found under {sweep_root}")
        return 2
    print(f"Re-gating {target}")
    result = regate_run(target)
    update_sweep_summary(sweep_root, args.slug, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
