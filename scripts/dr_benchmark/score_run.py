"""Path-B (system, question) scorer (I-safety-002b #925 PR-3).

Loads a RECONCILED dual-§-1.1 audit ledger + the frozen-rubric JSON snapshot, runs the
existing two-lane scorer, and writes a per-(system, question) scored JSON.

POLARIS-specific gate enforcement (Codex PR-3 design + Codex PR-2 P2 #2):
- If `<run_dir>/pathB_gate_INVALID` exists, refuse to score (the gate marked the run invalid).
- If `<run_dir>/pathB_gate_result.json` is missing OR verdict != "PASS", refuse to score.
- The gate is the SOURCE OF TRUTH for run validity; per-run artifacts (manifest, judge, etc.)
  may exist on disk even on FAIL, so the scorer MUST consult the sentinel + result first.

CLI:
    python -m scripts.dr_benchmark.score_run \
        --system polaris --question Q75 \
        --rubric outputs/dr_benchmark/rubric_v3_frozen.json \
        --ledger outputs/dr_benchmark/ledgers/polaris_Q75_reconciled.json \
        --run-dir outputs/honest_sweep_r3/health/Q75 \
        --out outputs/dr_benchmark/scored/polaris_Q75.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.dr_benchmark.ledger_schema import load_ledger
from src.polaris_graph.benchmark.benchmark_run_capture import corpus_truncated_from_manifest
from src.polaris_graph.benchmark.claim_audit_scorer import (
    ClaimRow,
    RubricElement,
    SystemQuestionLedger,
    aggregate,
    system_passes_question,
)


class InvalidRunError(RuntimeError):
    """POLARIS run was marked INVALID by the Path-B gate. Refuse to score."""


def _read_polaris_gate_identity(run_dir: Path) -> dict:
    """Codex PR-3 diff P2 #2: surface the gate's identity pins (served provider+model per
    role + reachability_checked) for the aggregator's REQUIRED identity-pins block."""
    pin = json.loads((run_dir / "pathB_gate_pin.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "pathB_gate_result.json").read_text(encoding="utf-8"))
    role_pins = pin.get("role_pins", [])
    return {
        "served_identity_by_role": result.get("served_identity_by_role", {}),
        "pinned_roles": [
            {"role": rp.get("role"), "model_slug": rp.get("model_slug"),
             "provider_name": rp.get("provider_name")}
            for rp in role_pins
        ],
        "reachability_checked": pin.get("reachability_checked"),
        "openrouter_allow_fallbacks": pin.get("openrouter_allow_fallbacks"),
        "openrouter_provider_order": pin.get("openrouter_provider_order"),
    }


def _check_polaris_gate(run_dir: Path) -> None:
    """For POLARIS scoring: the gate must have written a PASS result + no INVALID sentinel."""
    if not run_dir.exists():
        raise InvalidRunError(f"polaris run_dir does not exist: {run_dir}")
    # #958 (S2): scoring backstop — a truncated corpus is partial/invalid even if
    # the Path-B gate somehow recorded PASS. Read manifest.json directly.
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            _manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            _manifest = {}
        if corpus_truncated_from_manifest(_manifest):
            _rt = _manifest.get("retrieval", {})
            raise InvalidRunError(
                f"polaris run_dir corpus truncated (partial corpus): "
                f"{_rt.get('candidates_processed')}/{_rt.get('candidates_total')} "
                f"candidates processed ({run_dir})"
            )
    if (run_dir / "pathB_gate_INVALID").exists():
        marker = (run_dir / "pathB_gate_INVALID").read_text(encoding="utf-8").strip()
        raise InvalidRunError(
            f"polaris run_dir marked INVALID by Path-B gate: {marker} ({run_dir})"
        )
    result_path = run_dir / "pathB_gate_result.json"
    if not result_path.exists():
        raise InvalidRunError(
            f"polaris run_dir missing pathB_gate_result.json (gate not run): {run_dir}"
        )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("verdict") != "PASS":
        raise InvalidRunError(
            f"polaris run_dir gate verdict != PASS: {result.get('verdict')!r} "
            f"reason={result.get('reason')!r}"
        )


def score_one(
    *, system: str, question_id: str, rubric_path: Path, ledger_path: Path,
    run_dir: Path | None = None,
) -> dict:
    """Score one (system, question). Returns the scored dict; pure (no I/O beyond reads)."""
    polaris_gate_identity: dict | None = None
    if system == "polaris":
        if run_dir is None:
            raise InvalidRunError("polaris scoring requires --run-dir")
        _check_polaris_gate(run_dir)
        # Codex PR-3 diff P2 #2: surface the gate's served-identity + reachability for the
        # aggregator's REQUIRED identity-pins block (design answer F).
        polaris_gate_identity = _read_polaris_gate_identity(run_dir)

    ledger = load_ledger(ledger_path)
    # Codex PR-3 diff P1 #1: require a RECONCILED ledger; single-auditor ledgers must not
    # be scored directly (that would bypass the dual-§-1.1 conservative-MAX discipline).
    if ledger.auditor != "reconciled":
        raise ValueError(
            f"ledger.auditor must be 'reconciled' (Claude+Codex dual audit), got "
            f"{ledger.auditor!r}; pass the reconciled ledger from "
            f"scripts.dr_benchmark.reconcile, not a single-auditor ledger"
        )
    if ledger.system != system:
        raise ValueError(
            f"ledger.system {ledger.system!r} != requested system {system!r}"
        )
    if ledger.question_id != question_id:
        raise ValueError(
            f"ledger.question_id {ledger.question_id!r} != requested {question_id!r}"
        )

    rubric_doc = json.loads(rubric_path.read_text(encoding="utf-8"))
    question_block = next(
        (q for q in rubric_doc["questions"] if q["question_id"] == question_id), None,
    )
    if question_block is None:
        raise ValueError(f"rubric does not contain question_id={question_id!r}")
    if rubric_doc.get("rubric_sha256") != ledger.rubric_sha256:
        raise ValueError(
            "rubric_sha256 mismatch — ledger was audited against a DIFFERENT pinned rubric: "
            f"ledger={ledger.rubric_sha256}, rubric_doc={rubric_doc.get('rubric_sha256')}"
        )

    # Build ClaimRow[] from ledger.claims (mirrors validation; ledger already validated).
    rows = [
        ClaimRow(
            claim_id=c.claim_id,
            severity=c.severity,
            verdict=c.verdict,
            citation_id=c.citation_id,
            span_quote=c.span_quote,
            unreachable_subtype=c.unreachable_subtype,
            audit_note=c.audit_note,
        )
        for c in ledger.claims
    ]
    # Map coverage rows to RubricElement[] (the scorer expects covered+citation_supported).
    coverage_by_eid = {cv.element_id: cv for cv in ledger.coverage}
    rubric_elements = []
    for el in question_block["elements"]:
        cv = coverage_by_eid.get(el["element_id"])
        if cv is None:
            # No coverage row for a required element = NOT covered (conservative).
            rubric_elements.append(RubricElement(
                element_id=el["element_id"], covered=False, citation_supported=False,
            ))
        else:
            rubric_elements.append(RubricElement(
                element_id=el["element_id"],
                covered=cv.covered,
                citation_supported=cv.citation_supported,
            ))

    result = system_passes_question(rows, rubric_elements)
    out = {
        "system": system,
        "question_id": question_id,
        "rubric_sha256": rubric_doc["rubric_sha256"],
        "ledger_audit_method": ledger.audit_method,
        "n_claims_material": result["lane1"]["material_atoms"],
        "n_rubric_elements": len(rubric_elements),
        "passed": result["passed"],
        "reasons": result["reasons"],
        "lane1": result["lane1"],
        "lane2": result["lane2"],
    }
    # I-perm-024 (#1216): wire the extended claim-by-claim metrics into the LIVE scorer
    # (the wiring audit found run_scorecard.py is never invoked in the live path — this is).
    # Default-OFF PG_BENCH_EXTENDED_METRICS -> byte-identical when off. Every metric is derived
    # ONLY from the audited ledger rows + the frozen rubric, NEVER raw report text (§-1.1). The
    # Claimify dedup is intentionally SKIPPED: the reconciled ledger's claims are already atomic
    # and unique by claim_id (the dual-§-1.1 audit deduplicates), so there is no inflation vector
    # to collapse and the ledger carries no per-claim text to dedup on.
    if os.environ.get("PG_BENCH_EXTENDED_METRICS", "").strip().lower() in (
        "1", "true", "yes", "on",
    ):
        from src.polaris_graph.benchmark.extended_metrics import (
            citation_support_rate,
            diversity_score,
            faithfulness_precision,
            load_safety_floor_element_ids,
            required_entity_recall,
            safety_floor_recall,
        )
        _safety_ids = load_safety_floor_element_ids(question_id)
        out["extended"] = {
            "faithfulness_precision": faithfulness_precision(rows),
            "citation_support_rate": citation_support_rate(rows),
            "diversity_score": diversity_score(rows),
            "required_entity_recall": required_entity_recall(rubric_elements),
            "safety_floor_recall": safety_floor_recall(rubric_elements, _safety_ids),
            "dedup_applied": False,
            "methodology_note": (
                "derived from the reconciled dual-§-1.1 audit ledger rows (already atomic/"
                "unique by claim_id) + the frozen rubric; NEVER from raw report text; "
                "diversity_score is a diagnostic, NOT a superiority signal."
            ),
        }
    if polaris_gate_identity is not None:
        out["pathB_gate_identity"] = polaris_gate_identity
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Path-B (system, question) scorer.")
    p.add_argument("--system", required=True, choices=("polaris", "chatgpt", "gemini"))
    p.add_argument("--question", required=True, dest="question_id",
                   choices=("Q72", "Q75", "Q76", "Q78", "Q90"))
    p.add_argument("--rubric", required=True, type=Path,
                   help="frozen-rubric JSON snapshot (rubric_v3_frozen.json)")
    p.add_argument("--ledger", required=True, type=Path,
                   help="reconciled dual-audit ledger JSON (claude+codex)")
    p.add_argument("--run-dir", type=Path, default=None,
                   help="polaris run dir (required for system=polaris; gate-check)")
    p.add_argument("--out", required=True, type=Path,
                   help="path to write scored JSON")
    args = p.parse_args(argv)

    try:
        scored = score_one(
            system=args.system, question_id=args.question_id,
            rubric_path=args.rubric, ledger_path=args.ledger,
            run_dir=args.run_dir,
        )
    except InvalidRunError as exc:
        print(f"[score_run] INVALID: {exc}", file=sys.stderr)
        # Write a stub INVALID record so the aggregator can still account for it.
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "system": args.system, "question_id": args.question_id,
            "passed": False, "invalid": True, "reason": str(exc),
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 2  # distinct from generic error
    except Exception as exc:
        print(f"[score_run] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(scored, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
