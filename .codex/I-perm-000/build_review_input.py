"""Assemble the Codex ARCHITECTURE review input for I-perm-000.

Pure file concatenation: header + ask + full blueprint + full 9-issues charter
+ grounding code excerpts. No network, no LLM. Deterministic.
"""
from __future__ import annotations

import io
from pathlib import Path

ROOT = Path(r"C:\POLARIS")
OUT = ROOT / ".codex" / "I-perm-000" / "architecture_review_input.md"


def slurp(rel: str) -> str:
    with io.open(ROOT / rel, encoding="utf-8") as f:
        return f.read()


def slurp_lines(rel: str, start: int, end: int) -> str:
    """1-indexed inclusive line slice, prefixed with line numbers for grounding."""
    with io.open(ROOT / rel, encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    for i in range(start, min(end, len(lines)) + 1):
        out.append(f"{i:>5}\t{lines[i - 1].rstrip(chr(10))}")
    return "\n".join(out)


HEADER = """# CODEX ARCHITECTURE REVIEW — POLARIS Permanent-Fix Migration Blueprint (I-perm-000)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What this review IS (read carefully — this is NOT a code-diff review)

This is an **ARCHITECTURE review** of an **operator-directed strategic reframe**, not a review of a code diff. No code has been written yet. You are pressure-testing a *design blueprint* (`docs/permanent_fix_migration_blueprint.md`) that proposes migrating the POLARIS deep-research pipeline from one governing posture to another:

- **FROM:** WITHHOLD-when-imperfect — ~7 stacked aggregate gates (scope-reject, corpus-inadequate, corpus-approval-denied, per-section <40%-verified drop, four-role <70%-coverage hold, S0-must-cover hold, zero-verified abort) can each withhold, abort, or thin a research report even after deep research succeeded.
- **TO:** ALWAYS-RELEASE with honest **per-claim confidence + provenance**, and let the human reader judge.

**The ONLY hard line** (operator-locked, NOT negotiable, NOT relaxable by you): **never assert an *ungrounded* claim as fact.** An unsupported claim ships as a transparent "no grounded source found" label — never silently, never as confident prose. Safety caveats are shown PROMINENTLY. This radical-transparency posture is also the deliberate differentiator vs ChatGPT/Gemini deep-research (which ship confident-looking unsupported citations).

The blueprint's core safety claim is a **RELOCATION, not a relaxation**: *aggregate/report-level* gates move from trap-doors to DISPLAYED labels and always release; *per-CLAIM* faithfulness gates (strict_verify numeric-in-span + ≥2 content-word overlap + entailment; the FABRICATED occurrence latch; the zero-grounding abort) stay BINDING and byte-unchanged. No per-claim threshold is lowered.

## The empirical keystone this program is built on (verify the logic, not just trust it)

`outputs/audits/beatboth8/drb_76/` is a fully-rendered clinical report that was **BLOCKED** (`status=abort_four_role_release_held`, `release_allowed=False`, `coverage_fraction=0.40`, `held_reasons=['d8_unsupported_residual_below_coverage','d8_s0_must_cover_missing:contraindications','d8_pending_rewrite']`) — yet the report **shipped the exact contraindication safety fact** ("*S. boulardii* probiotics are not recommended for patients who are immunocompromised, critically ill, or have indwelling catheters") as a VERIFIED claim on the page. The must-cover gate fired `missing:contraindications` *while the safety fact was present and verified*. Zero fabrication defects; the user never saw the report. That false-withhold is the bug class this 9-issue program kills.

---

## THE ASK (what you must rule on, with evidence)

Emit your verdict in the §8.3.9 YAML schema (below) PLUS two extra blocks. Be concrete and cite file:line / blueprint-section where you can.

### 1. RULE ON EACH OF THE 6 OPEN TENSIONS (blueprint Section 6) — `tension_rulings:` block, one ruling each.
The two HIGHEST-STAKES are #1 and #2; spend most of your judgement there.
- **Tension 1 — caveat PROMINENCE vs the clinical hard line.** Is top-of-report caveat placement an *empirically sufficient* structural guarantee, or merely assumed? Is there a class of report (e.g. ALL S0 safety categories are disclosed-gaps) where ABORT is still the correct behavior rather than always-release? Do we need a stronger structural guarantee (interstitial acknowledgement, or refuse-to-release-clinical-when-all-safety-categories-are-gaps)?
- **Tension 2 — is `has_any_verified_claim` (1-of-N, per-REPORT) the right release floor?** A report with 1 verified claim of 37 where the other 36 are all safety-critical would release. Should the floor be **per-SECTION** (a Safety section with zero verified claims is a hard-block even if other sections are rich), not per-report? This is the single highest-stakes parameter in the reframe and interacts with I-perm-001's `hard_block` definition. RULE on per-section-vs-per-report explicitly.
- **Tension 3 — credibility-as-weight + `independent_origin_count` echo risk.** Can 3 low-credibility sources echoing one unsupported claim render "moderate · 3 sources" and read as corroborated? Must "independent origin" be gated on credibility, and must the chip never exceed "low" for a non-VERIFIED claim regardless of origin count?
- **Tension 4 — pooled cross-document re-anchor (I-perm-002 reusing I-perm-004's argmax over the whole pool).** Is the title-anchor guard sufficient to prevent re-pointing a claim to a coincidental match in an UNRELATED paper, or is a same-population/same-intervention check required before crediting cross-document satisfaction of a *safety* category?
- **Tension 5 — `released_with_disclosed_gaps` as a success-adjacent status weakening the regression signal.** Once a True→False `release_allowed` flip is no longer auto-CRITICAL, what `release_quality_score`-drop magnitude should trip the alert, and is detection of a *new systematic withholding* bug lost?
- **Tension 6 — I-perm-003's honest no-op.** Acceptable to merge I-perm-003 with only synthetic-pool proof (the selector drops 0 on beatboth8), or must it be sequenced strictly AFTER I-perm-007 grows a real pool?

### 2. CONFIRM THE NO-FABRICATION HARD LINE IS PRESERVED.
Specifically verify the design keeps: (a) per-claim gates untouched (strict_verify, provenance entailment, report_redactor refuse-in-place); (b) the FABRICATED occurrence latch byte-unchanged (`release_policy.py:200-205`); (c) the zero-grounding abort retained (narrowed to true zero-verified-AND-zero-evidence, rendering an honest report). Flag ANY place in the 9-issue design where the reframe could let an UNSUPPORTED or FABRICATED claim ship as confident fact.

### 3. CHECK THE BUILD-ORDER / DEPENDENCY PLAN IS SOUND (blueprint Section 4).
Especially: is **Decision B (the shared per-claim confidence + `ReleaseDisclosure` schema) landing BEFORE I-perm-004/005** correctly sequenced so 004 (populates) and 005 (renders) don't deadlock? Is the keystone-first ordering (001 → {002,004,005,006}) right? Are the CORE-lane serialization (release_policy.py / native_gate_b_inputs.py hot files) and the I-perm-008 Key-Findings-ordering-fix-can-land-early calls correct?

### 4. `required_design_changes:` block — anything that MUST change before any code is written.

### 5. Output schema (§8.3.9) — emit EXACTLY this, plus the two extra blocks above:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
tension_rulings:
  tension_1_caveat_prominence_vs_clinical_floor: "<ruling>"
  tension_2_per_section_vs_per_report_floor: "<ruling>"
  tension_3_credibility_echo: "<ruling>"
  tension_4_cross_document_reanchor: "<ruling>"
  tension_5_regression_signal: "<ruling>"
  tension_6_iperm003_no_op_sequencing: "<ruling>"
required_design_changes: [...]
```

---
"""


def main() -> None:
    blueprint = slurp("docs/permanent_fix_migration_blueprint.md")
    nine = slurp("docs/permanent_fix_9_issues.md")

    rp = slurp_lines("src/polaris_graph/roles/release_policy.py", 180, 300)
    ngb_a = slurp_lines("src/polaris_graph/roles/native_gate_b_inputs.py", 300, 360)
    ngb_b = slurp_lines("src/polaris_graph/roles/native_gate_b_inputs.py", 470, 540)
    rr = slurp_lines("src/polaris_graph/roles/report_redactor.py", 60, 120)

    doc = []
    doc.append(HEADER)
    doc.append("\n## DOCUMENT 1 (FULL TEXT) — `docs/permanent_fix_migration_blueprint.md`\n")
    doc.append("```markdown\n" + blueprint + "\n```\n")
    doc.append("\n## DOCUMENT 2 (FULL TEXT) — `docs/permanent_fix_9_issues.md` (the operator charter)\n")
    doc.append("```markdown\n" + nine + "\n```\n")
    doc.append("\n## GROUNDING CODE (current tree, for verifying the design against reality)\n")
    doc.append(
        "\n> NOTE for Codex: the blueprint cites `generator/report_redactor.py`, but the file actually lives "
        "at `src/polaris_graph/roles/report_redactor.py` (path discrepancy — flag if you think it matters; "
        "the line content matches the blueprint's `_GAP_REPLACEMENT` claim at :85-88).\n"
    )
    doc.append("\n### `src/polaris_graph/roles/release_policy.py` lines 180-300 (the D8 release decision — FABRICATED latch :200-205, coverage floor :241-253, S0 must-cover :255-273, pending-rewrite :296-297)\n")
    doc.append("```python\n" + rp + "\n```\n")
    doc.append("\n### `src/polaris_graph/roles/native_gate_b_inputs.py` lines 300-360 (the tunnel-vision seam: `_content_requirements_satisfied` exact-string match :312-328, `_claim_covers_entity` :331-352)\n")
    doc.append("```python\n" + ngb_a + "\n```\n")
    doc.append("\n### `src/polaris_graph/roles/native_gate_b_inputs.py` lines 470-540 (claim build + coverage attribution + `rewrite_already_attempted=False` hardcode :529)\n")
    doc.append("```python\n" + ngb_b + "\n```\n")
    doc.append("\n### `src/polaris_graph/roles/report_redactor.py` lines 60-120 (the redact-to-gap-stub mechanism the reframe turns into a labeler: `_NON_VERIFIED_VERDICTS` :77-79, `_GAP_REPLACEMENT` :85-88)\n")
    doc.append("```python\n" + rr + "\n```\n")
    doc.append("\n---\n\n**END OF REVIEW INPUT. Emit the YAML verdict + tension_rulings + required_design_changes now. Front-load all findings (iter 1 of 5).**\n")

    text = "\n".join(doc)
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"WROTE {OUT}  ({len(text)} chars)")


if __name__ == "__main__":
    main()
