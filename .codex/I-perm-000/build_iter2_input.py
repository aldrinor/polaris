"""Assemble the Codex architecture-review iter-2 input from the real on-disk files.

Deterministic, VERIFY-not-hunt: embeds (1) the canonical cap directive, (2) the
ask, (3) Codex's own iter-1 verdict verbatim, (4) the Revision-1 resolution
section verbatim, (5) a P1/change -> R-item resolution map, (6) the full
blueprint + 9-issue charter for line-level verification, (7) the output schema.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODEX_DIR = ROOT / ".codex" / "I-perm-000"
BLUEPRINT = ROOT / "docs" / "permanent_fix_migration_blueprint.md"
CHARTER = ROOT / "docs" / "permanent_fix_9_issues.md"
ITER1_VERDICT = CODEX_DIR / "architecture_review_verdict.txt"

CAP_DIRECTIVE = """HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" - if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" - DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
"""

ASK = """# Codex architecture review - I-perm-000 permanent-fix blueprint - ITER 2 of 5

You are the ONLY gate on this architecture design (a DESIGN blueprint, not a code diff).

## What changed since your iter-1 REQUEST_CHANGES

Your iter-1 verdict was REQUEST_CHANGES with ZERO P0, 7 P1 (all clinical-safety
hardening), 5 P2, and 10 required_design_changes. You confirmed the
no-fabrication CORE is structurally sound (FABRICATED latch byte-unchanged,
zero-grounding abort retained, per-claim gates untouched).

I appended **REVISION 1** to the blueprint (section at the very end, header
"## REVISION 1") resolving every P1 + every required_design_change + the two
P2 status/threshold items, PLUS the operator's locked clinical safety-floor
decision (honest insufficient-safety report). Revision 1 is BINDING and
supersedes any conflicting earlier text in the blueprint.

## Your job this iteration

VERIFY, claim-by-claim, that each of your iter-1 findings is genuinely resolved
by the corresponding R-item in Revision 1 - do NOT re-discover from scratch, and
do NOT bank new findings for a future round (there is no iter 6 past the cap).
For each iter-1 P1 and each required_design_change, decide: RESOLVED (cite the
R-item + blueprint line) or STILL-OPEN (say exactly what is missing).

Then issue ONE verdict for the whole architecture:
- APPROVE iff every iter-1 P1 + every required change is resolved AND you find
  zero NEW P0/P1 design risk.
- REQUEST_CHANGES with a precise residual list otherwise.

Specifically pressure-test, because these are the load-bearing clinical-safety claims:
1. R1 canonical predicate: is `hard_block = fabricated_latched OR (zero_verified AND zero_usable_evidence)` plus `normal_release_blocked = hard_block OR safety_floor==insufficient` actually ONE coherent predicate that bundle.py / status map / UI / regression can all key on? Any remaining split-brain?
2. R2/R3 safety floor: does "Safety section zero VERIFIED claims OR all S0 categories disclosed-gaps -> block normal render, ship honest `released_insufficient_safety_evidence` report; SUBSET -> caveated normal release" fully close your tension_1 + tension_2? Is the prominence STRUCTURAL (top block + section-local + key-findings + machine-readable), not placement-only?
3. R4 confidence: does requiring `verdict==VERIFIED` for BOTH `high` AND `moderate` (non-VERIFIED -> only `low`/`no-source-found`) close the "moderate - 3 sources on unsupported content" echo risk (tension_3)?
4. R5 origin display: credible_independent_origins gated by credibility floor, raw echo_count separate/advisory - does this close tension_3 display?
5. R6 cross-document SAFETY guard: same substance/intervention AND compatible risk-population/contraindication target before crediting a pooled S0 safety category; I-perm-004 re-anchor stays row-scoped - does this close tension_4?
6. R7 sequencing: I-perm-008 Key-Findings ordering fix promoted to Wave 0 AND a precondition for enabling PG_ALWAYS_RELEASE - does this close the "ordering leak must be early" P1?
7. R8 annotator fail-closed: FABRICATED rows hard-block before annotation; unlabelable material non-VERIFIED fails closed (ReportRedactionError-equivalent) - does this close the label-not-delete P1?
8. R9/R10 regression thresholds + locked status vocabulary - do these close the two P2s?

Be honest about any residual real risk. The cap means do not hold anything back.
If RESOLVED across the board, APPROVE and set convergence_call: accept_remaining.

## Output schema (REQUIRED - emit exactly this YAML, last `verdict:` line is parsed by CI)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
per_iter1_finding_resolution:
  - finding: <short id of the iter-1 P1 or required change>
    status: RESOLVED | STILL_OPEN
    evidence: <R-item + blueprint line, or what is missing>
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
"""

OUTPUT_SCHEMA_NOTE = ""


def section(title: str, body: str) -> str:
    return f"\n\n========== {title} ==========\n\n{body}\n"


def main() -> None:
    parts = [CAP_DIRECTIVE, ASK]
    parts.append(section("CODEX ITER-1 VERDICT (verbatim - the findings you must verify-resolve)",
                         ITER1_VERDICT.read_text(encoding="utf-8")))

    bp = BLUEPRINT.read_text(encoding="utf-8")
    # Revision 1 starts at the "## REVISION 1" header.
    rev_idx = bp.find("## REVISION 1")
    rev_section = bp[rev_idx:] if rev_idx != -1 else "(REVISION 1 SECTION NOT FOUND)"
    parts.append(section("REVISION 1 - THE RESOLUTIONS (verbatim, BINDING, supersedes conflicting earlier text)",
                         rev_section))

    parts.append(section("FULL MIGRATION BLUEPRINT (for line-level verification)", bp))
    parts.append(section("THE 9-ISSUE CHARTER (governing reframe + per-issue scope)",
                         CHARTER.read_text(encoding="utf-8")))

    out = "".join(parts)
    out_path = CODEX_DIR / "architecture_review_iter2_input.md"
    out_path.write_text(out, encoding="utf-8")
    print(f"wrote {out_path} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
