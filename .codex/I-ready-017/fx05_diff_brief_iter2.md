# FX-05 (#1109) diff-gate — ITER 2 of 5

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

## Your iter-1 findings → fixed (this is the ONLY delta in iter-2)

- **P1 (real, valid)**: the structured-authorization gate closed the free-text
  loophole, but default-deny was not *enforced* by 3 of the 4 callers —
  `run_live_honest_cycle.py`, `run_honest_on_prerebuild_corpus.py`, and
  `honest_pipeline.py` computed `approved=False` then still proceeded into
  generation/report/evaluator (only `run_honest_sweep_r3.py` had the
  `if not approved` abort). **FIXED**: added the `abort_corpus_approval_denied`
  short-circuit BEFORE the generation call in all three:
  - `run_live_honest_cycle.py` — aborts before `generate_live_draft` (writes an
    abort `report.md`, `return 4`).
  - `run_honest_on_prerebuild_corpus.py` — aborts before
    `generate_multi_section_report` (abort `report.md`, `return 4`).
  - `honest_pipeline.py` — aborts before `strict_verify`/report/evaluator;
    returns `PipelineResult(status="abort_corpus_approval_denied", evaluator=None)`
    + abort `report.md` + manifest. `PipelineResult.evaluator` is now
    `Optional` and a new `status` field carries the verdict. Its sole consumer
    `run_honest_full_cycle.py` now guards on `result.status` before using
    `result.evaluator`.

- **P2 (stale operator text)**: **FIXED** in all 3 places — `render_approval_html`
  material banner, the module docstring, and the sweep abort artifact in
  `run_honest_sweep_r3.py` now reference the structured
  `PG_AUTHORIZED_SWEEP_APPROVAL` credential instead of "provide a substantive
  note".

## Evidence (offline; no spend) — diff `.codex/I-ready-017/fx05_codex_diff.patch` (vs base `b5ea6db4`)

- **Behavioral proof (REAL offline `run_honest_pipeline` run):** a clinical
  question over a 10×T5 industry corpus (material deviation) with the flag unset
  → `status=abort_corpus_approval_denied`, `evaluator is None`,
  `final_report_text==""`, `report.md` carries the abort verdict and contains NO
  `## Methods` synthesis. The pipeline does NOT proceed past the gate.
- **Offline smoke:** 36 tests pass (+3 abort-before-generation enforcement tests,
  one per caller — `if not approved:` precedes the generation call and returns
  early). All 4 modified modules import cleanly.
- **§-1.1 audit on REAL output** (iter-1, still valid): the held drb_72
  `corpus_approval.json` replayed through the gate → canned note DENIES, no-flag
  DENIES, flag APPROVES (`outputs/audits/I-ready-017/fx05_s11_audit.md`).

## Faithfulness-invariant check
No change to provenance / strict_verify / 4-role. FX-05 gates corpus approval
(pre-generation spend), upstream of those invariants.

## Question
Is `abort_corpus_approval_denied` now enforced (abort BEFORE generation) in ALL
callers, with no faithfulness-invariant regression and no stale operator text
remaining? Anything else blocking?
