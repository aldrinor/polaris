# FX-10 (#1115) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Your iter-1 findings → fixed (the delta in iter-2)

- **P1 (CI blocker)**: the source-sentinel `test_research_planner_phase1.py:708`
  string-matched the old ON-mode construction `CompletenessReport(domain=q["domain"])`,
  which FX-10 rewrote to `CompletenessReport(domain=q["domain"], notes=["no_checklist_loaded"])`.
  **FIXED**: the sentinel now asserts `CompletenessReport(` AND `no_checklist_loaded` are
  present (legitimate contract update — the neutral report now tags itself not_applicable).
  `pytest ...::test_p1_18_on_mode_bypasses_domain_template` passes.
- **P2 (consumer-facing honesty residual)**: `audit_ir/loader.py` mapped any
  `covered_fraction: 1.0` → `completeness_percent: 100.0`, ignoring `completeness_state`, so
  an AuditIR/API consumer could still present a not_applicable manifest as 100%. **FIXED**:
  added a `completeness_state` field to the `RunManifest` AuditIR dataclass (defaulted LAST
  so existing constructors are unaffected — verified all 5 test constructors still pass) +
  `_parse_completeness_state()` (prefers the explicit manifest field; infers not_applicable
  from `total_applicable==0` for pre-FX-10 manifests). covered_fraction stays numeric.

## Evidence (offline; no spend) — diff `.codex/I-ready-017/fx10_codex_diff.patch` (vs FX-09 tip `61856dfd`)
- **Offline smoke:** 58 tests (6 FX-10 incl. 2 new loader tests: explicit-field +
  pre-FX-10 inference; + audit_ir loader regression). The P1 sentinel + all 5
  RunManifest-constructor test files pass (129 in the broader run). loader.py parses.
- **§-1.1 (iter-1, still valid):** real held manifest `{covered_fraction:1.0,
  total_applicable:0}` → new property tags not_applicable; consumer-safety behavioral test
  through the real `compute_evaluator_gate` (not_applicable advisory-skip, measured-0.3
  flagged).

## Faithfulness check
Honesty fix across BOTH the manifest producer and the AuditIR consumer. No
grounding/strict_verify/4-role change; covered_fraction stays numeric; only additive fields.

## Question
Are P1 (brittle sentinel) and P2 (AuditIR loader honesty) now correctly resolved, with no
broken RunManifest constructor and the not_applicable state surfaced end-to-end (producer +
loader)? Anything blocking?
