HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# PR-3 DESIGN BRIEF: scoring integration + operator-supervised smoke (I-safety-002b / #925)

PR-1 (capture primitives + completion-boundary hooks) and PR-2 (role tags + retrieval hooks +
runner --pathB-gate lifecycle) are both Codex-APPROVED (PR-1 APPROVE iter2; PR-2 iter2 in audit
as of this writing). PR-3 is the final wiring: how to take a gate-PASS POLARIS run + 2 competitor
reports + the dual §-1.1 line-by-line audit ledgers and produce the head-to-head verdict against
the FROZEN gold rubric (freeze_pin.txt).

## Inputs (already on disk, NOT in scope to re-build)
- **Frozen gold rubric**: `.codex/I-safety-002b/gold_rubrics_pathB.md` (FROZEN 2026-05-28, dual
  audit complete, hash-pinned in freeze_pin.txt). 5 questions × 7-8 required ELEMENTS each, each
  tagged with an authoritative source class + verbatim gold span.
- **Competitor outputs**: `outputs/dr_benchmark/external_outputs/{gpt_5_5_pro,gemini_3_1_pro}/Q##_*.md`
  (10/10 stored 2026-05-28, sha256-pinned).
- **POLARIS gate artifacts (per question, from PR-2)**: `outputs/honest_sweep_r3/<domain>/<slug>/`
  - `pathB_gate_pin.json`, `pathB_gate_result.json` (verdict PASS|FAIL)
  - `pathB_gate_INVALID` sentinel iff gate FAILED (preflight or post-run)
  - Plus the run's normal artifacts (report.md, manifest.json, evaluator_rule_checks.json, etc.).
- **POLARIS report**: `report.md` in the run_dir (the deliverable being audited).

## What PR-3 produces
1. **Frozen-rubric JSON snapshot** (`outputs/dr_benchmark/rubric_v3_frozen.json`): parse
   `gold_rubrics_pathB.md` once into a machine-readable structure
   `{question_id, elements: [{element_id, requirement_text, source_class, gold_span_url}]}`. Pin
   the sha256 in `freeze_pin.txt` (rubric markdown already pinned; this is a derived snapshot
   pinned against the markdown sha so a rubric edit invalidates the snapshot).
2. **Ledger schema** (`scripts/dr_benchmark/ledger_schema.py`): the per-(system×question) JSON
   the dual §-1.1 line-by-line audit produces — one ClaimRow per atomic claim:
   `{claim_id, severity (S0|S1|S2|S3), verdict (VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE),
   citation_id, span_quote, unreachable_subtype?, audit_note?, auditor (claude|codex)}`. The dual
   audit is HUMAN/AGENT WORK, not code — PR-3 just defines the schema both audits write to,
   plus a `reconcile(claude_rows, codex_rows)` helper for the cross-review.
3. **Coverage schema** (per-(system×question) gold-rubric coverage): one row per rubric element
   `{element_id, covered: bool, citation_supported: bool, auditor_note?}`.
4. **CLI `scripts/dr_benchmark/score_run.py`**:
   - input: `--system {polaris|chatgpt|gemini} --question Q72|Q75|Q76|Q78|Q90 --run-dir <path>
     --rubric <pin> --ledger <path> --coverage <path>`.
   - For POLARIS: check `pathB_gate_INVALID` sentinel; if present, refuse to score
     (`InvalidRunError`).
   - Load ledger + coverage; build `ClaimRow[]` + `RubricElement[]`; call existing
     `system_passes_question` + `aggregate` from `claim_audit_scorer.py`.
   - Output: `outputs/dr_benchmark/scored/<system>_<question>.json` with the lane-1 + lane-2
     numbers + the `passed` verdict + reasons.
5. **Final aggregation tool** (`scripts/dr_benchmark/aggregate_systems.py`): reads all
   scored/*.json → produces `outputs/dr_benchmark/final_report.md` with clinical-3
   (#75/#76/#78) and overall-5 sections SEPARATELY (per the locked honest-label discipline);
   no "wins" headline; per-claim traceability.
6. **Operator-supervised smoke run** (Codex iter-1 PR-2 brief answer E confirmed yes): a single
   non-clinical question (#72 or #90) is run with `--pathB-gate` to confirm POLARIS's
   clinical-tuned scope/corpus gates accept the non-clinical questions BEFORE 5 full runs.
   PR-3 includes a `scripts/dr_benchmark/smoke.md` runbook for this.

## Open design questions
A. **Rubric markdown -> JSON parsing**: should I parse `gold_rubrics_pathB.md` directly (cost: a
   regex/markdown parser; brittle to formatting changes) OR author a `gold_rubrics.json`
   companion file once + pin both files? My lean: **companion JSON + dual pin** — markdown stays
   human-readable; JSON stays machine-readable; freeze_pin.txt pins both. Edit invalidates both.
B. **Coverage judgments**: the rubric defines required ELEMENTS; coverage is a per-system
   per-element bool (covered? citation_supported?). This is a JUDGMENT the dual audit must
   produce. Should the dual audit produce coverage rows directly, or should a separate "coverage
   sweep" follow the claim audit? My lean: **same pass** — auditor reads the report once,
   producing both claim rows AND coverage rows per element.
C. **Inter-auditor disagreement**: when Claude's ledger says VERIFIED on a claim and Codex says
   UNSUPPORTED, what's the verdict? My lean: **conservative MAX (worse-of-two)** for the gating
   verdict, with the disagreement recorded; report both verdicts in the final tracing JSON. This
   matches the §-1.1 "clinical lethal" framing — if either auditor finds a problem, the claim is
   flagged.
D. **Sentinel-as-skip granularity**: if `pathB_gate_INVALID` exists in a question's run_dir,
   PR-3 refuses to score THAT question (it is documented INVALID). But should the aggregate
   still report the question as "INVALID" (graded fail-by-procedure) or simply omit it from the
   denominator? My lean: **report INVALID + omit from numerator** (clinical-3 / overall-5 may
   become 2/3 or 4/5 of valid runs, with the invalid run documented). Never silently drop.
E. **Smoke run cost**: PR-2's gate enforces full power (PG_SWEEP_MAX_SERPER=50, etc.) so a
   single-question smoke run is the same shape as a real run. Operator-supervised, run on #72
   or #90 (the non-clinical questions, which are the scope-rejection risk). Should the smoke
   be ONE question or BOTH (#72 AND #90)?
F. **Final report identity guarantees**: the final report MUST cite (a) the freeze_pin.txt
   sha256s, (b) the gate's pinned served-identity surrogates per role, (c) the per-question
   reachability proofs. This is what makes the head-to-head defensible.

## Output schema (return EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
answers:
  A_rubric_format: <markdown-parse | companion-json | both>
  B_coverage_pass: <same | separate>
  C_disagreement_rule: <conservative-max | average | flag-only>
  D_invalid_aggregation: <report-omit | report-include | omit-silent>
  E_smoke_scope: <one-question | both-72-and-90>
  F_identity_pins_in_report: <yes-required | optional>
convergence_call: continue | accept_remaining
remaining_blockers_for_diff: []
```
Loose verdict prose without this schema will be rejected and resubmitted.
