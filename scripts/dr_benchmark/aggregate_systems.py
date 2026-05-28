"""Path-B final aggregator (I-safety-002b #925 PR-3).

Reads all `outputs/dr_benchmark/scored/<system>_<question>.json` and produces the FINAL
report `outputs/dr_benchmark/final_report.md` with:
- **CLINICAL-3** (#75/#76/#78) and **OVERALL-5** sections reported SEPARATELY (Codex PR-3
  design answer D + the locked honest-label discipline). No "wins" headline.
- **INVALID rows reported as INVALID, omitted from numerator** (Codex answer D `report-omit`).
  Denominator reports the valid subset; invalid runs are listed with reasons.
- **Identity pins REQUIRED** (Codex answer F `yes-required`): cite freeze_pin.txt SHAs, the
  pinned served-identity surrogates per role (from `pathB_gate_pin.json`), and per-question
  retrieval reachability proofs.

Pure aggregator: no scoring decisions made here. Every cell traces to a scored JSON file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_CLINICAL_QUESTIONS = ("Q75", "Q76", "Q78")
_ALL_QUESTIONS = ("Q72", "Q75", "Q76", "Q78", "Q90")
_SYSTEMS = ("polaris", "chatgpt", "gemini")


def _read_scored(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect(scored_dir: Path) -> dict[str, dict[str, dict]]:
    """Return {system: {question_id: scored_dict}} from scored_dir."""
    out: dict[str, dict[str, dict]] = {s: {} for s in _SYSTEMS}
    for f in sorted(scored_dir.glob("*.json")):
        d = _read_scored(f)
        sys_id = d.get("system")
        qid = d.get("question_id")
        if sys_id in out and qid:
            out[sys_id][qid] = d
    return out


def _section(scored: dict[str, dict[str, dict]], question_ids: tuple[str, ...], label: str) -> list[str]:
    """Render a section table for the given question subset."""
    lines = [f"### {label}\n"]
    lines.append("| System | Valid runs | Passed | Pass rate | Invalid (reasons) |")
    lines.append("|---|---|---|---|---|")
    for sys_id in _SYSTEMS:
        valid: list[dict] = []
        invalid: list[dict] = []
        for qid in question_ids:
            d = scored.get(sys_id, {}).get(qid)
            if d is None:
                invalid.append({"question_id": qid, "reason": "no scored JSON"})
                continue
            if d.get("invalid"):
                invalid.append({"question_id": qid, "reason": d.get("reason", "INVALID")})
            else:
                valid.append(d)
        passed = sum(1 for d in valid if d.get("passed"))
        n_valid = len(valid)
        rate = f"{passed}/{n_valid}" if n_valid else "0/0"
        rate_pct = f"({100.0 * passed / n_valid:.0f}%)" if n_valid else "(n/a)"
        invalid_str = "; ".join(
            f"{x['question_id']}: {x['reason'][:80]}" for x in invalid
        ) or "—"
        lines.append(
            f"| {_cell(sys_id)} | {n_valid} | {passed} | {_cell(rate)} {_cell(rate_pct)} | "
            f"{_cell(invalid_str)} |"
        )
    lines.append("")
    return lines


def _cell(text: str) -> str:
    """Escape characters that break markdown table cells (Codex PR-3 diff P3 #2)."""
    return (
        (text or "")
        .replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _per_question_detail(scored: dict[str, dict[str, dict]]) -> list[str]:
    lines = ["### Per-question detail (clinical-3 + overall-5)\n"]
    for qid in _ALL_QUESTIONS:
        lines.append(f"#### {qid}\n")
        lines.append("| System | Passed | Lane-1 hard_fail | Lane-2 coverage | Reasons |")
        lines.append("|---|---|---|---|---|")
        for sys_id in _SYSTEMS:
            d = scored.get(sys_id, {}).get(qid)
            if d is None:
                lines.append(f"| {sys_id} | — | — | — | no scored JSON |")
                continue
            if d.get("invalid"):
                lines.append(
                    f"| {sys_id} | INVALID | — | — | {_cell(str(d.get('reason', ''))[:120])} |"
                )
                continue
            lane1 = d.get("lane1", {})
            lane2 = d.get("lane2", {})
            reasons = "; ".join(d.get("reasons", [])) or "passed"
            lines.append(
                f"| {sys_id} | {d.get('passed')} | "
                f"{lane1.get('hard_fail_count', '?')} | "
                f"{lane2.get('coverage_fraction', 0):.2f} | "
                f"{_cell(reasons[:120])} |"
            )
        lines.append("")
    return lines


def _identity_pins_block(freeze_pin: Path, scored: dict[str, dict[str, dict]]) -> list[str]:
    """Identity pins block (Codex answer F yes-required) — cite freeze_pin SHAs AND, per
    Codex PR-3 diff P2 #2, the pathB_gate served-identity + reachability proofs from each
    POLARIS scored JSON (which scored_run.py surfaces under `pathB_gate_identity`)."""
    lines = ["## Pre-registration identity pins (REQUIRED)\n"]
    if freeze_pin.exists():
        lines.append("**freeze_pin.txt contents** (hash-anchored answer key):\n")
        lines.append("```")
        lines.extend(freeze_pin.read_text(encoding="utf-8").splitlines())
        lines.append("```\n")
    else:
        lines.append(f"freeze_pin.txt NOT FOUND at {freeze_pin} — IDENTITY UNVERIFIED\n")

    # Per-(polaris, question) served-identity + reachability proofs from the gate.
    polaris = scored.get("polaris", {})
    if polaris:
        lines.append(
            "**POLARIS pathB_gate identity per question** "
            "(served provider/model proven; retrieval backends reachability-checked):\n"
        )
        lines.append("| Question | Generator (served) | Evaluator (served) | Reachability | Fallbacks | Provider order |")
        lines.append("|---|---|---|---|---|---|")
        for qid in sorted(polaris.keys()):
            d = polaris.get(qid, {})
            ident = d.get("pathB_gate_identity") or {}
            if not ident:
                lines.append(f"| {qid} | — | — | — | — | — |")
                continue
            pins_by_role = {p.get("role"): p for p in ident.get("pinned_roles", [])}
            served = ident.get("served_identity_by_role", {}) or {}
            gen = pins_by_role.get("generator", {}) or {}
            ev = pins_by_role.get("evaluator", {}) or {}
            gen_str = (
                f"{gen.get('provider_name', '?')}/{gen.get('model_slug', '?')} "
                f"surrogate={(served.get('generator') or '?')[:12]}…"
            )
            ev_str = (
                f"{ev.get('provider_name', '?')}/{ev.get('model_slug', '?')} "
                f"surrogate={(served.get('evaluator') or '?')[:12]}…"
            )
            lines.append(
                f"| {qid} | {_cell(gen_str)} | {_cell(ev_str)} | "
                f"{ident.get('reachability_checked')} | "
                f"{ident.get('openrouter_allow_fallbacks')} | "
                f"{_cell(str(ident.get('openrouter_provider_order') or '—'))} |"
            )
        lines.append("")
    return lines


def render_final_report(
    *, scored_dir: Path, freeze_pin: Path, out_path: Path,
) -> int:
    scored = _collect(scored_dir)
    lines: list[str] = []
    lines.append("# Path-B DR head-to-head — final report (I-safety-002b / #925)\n")
    lines.append(
        "Honest label: **DRB-EN high-stakes citation-faithfulness stress slice "
        "(3 clinical + 2 source-critical)**. NOT 'the 5 objectively hardest' (DRB has no "
        "hardness rank). Clinical-3 + Overall-5 reported SEPARATELY per the locked honest-"
        "label discipline. No 'wins' headline; every cell traces to a scored JSON.\n",
    )
    lines.extend(_identity_pins_block(freeze_pin, scored))
    lines.append("## Pass-rate summary\n")
    lines.extend(_section(scored, _CLINICAL_QUESTIONS, "Clinical-3 (#75/#76/#78)"))
    lines.extend(_section(scored, _ALL_QUESTIONS, "Overall-5 (#72/#75/#76/#78/#90)"))
    lines.extend(_per_question_detail(scored))
    lines.append(
        "## Notes\n\n"
        "- INVALID runs are reported and OMITTED from the numerator/denominator of the "
        "valid subset (Codex PR-3 design answer D `report-omit`).\n"
        "- Pass = zero S0–S2 FABRICATED/UNSUPPORTED material claims AND coverage ≥0.70 "
        "(claim_audit_scorer thresholds, frozen).\n"
        "- For POLARIS: scoring requires the Path-B gate's PASS verdict + absence of the "
        "`pathB_gate_INVALID` sentinel. Gate FAILURES are reported as INVALID with the "
        "gate's reason.\n"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[aggregate_systems] wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Path-B final aggregator.")
    p.add_argument("--scored-dir", type=Path,
                   default=Path("outputs/dr_benchmark/scored"))
    p.add_argument("--freeze-pin", type=Path,
                   default=Path(".codex/I-safety-002b/freeze_pin.txt"))
    p.add_argument("--out", type=Path,
                   default=Path("outputs/dr_benchmark/final_report.md"))
    args = p.parse_args(argv)
    return render_final_report(
        scored_dir=args.scored_dir, freeze_pin=args.freeze_pin, out_path=args.out,
    )


if __name__ == "__main__":
    sys.exit(main())
