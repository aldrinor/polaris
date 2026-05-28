HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT exec pytest. The 84/84 test results are inlined below; rely on the diff.

# DIFF AUDIT: PR-3 scoring pipeline + frozen-rubric JSON + smoke runbook (I-safety-002b / #925)

Per your APPROVE on PR-3 design iter 2 (A=companion-json, B=same-pass, C=conservative-max,
D=report-omit, E=one-question, F=yes-required identity pins). Diff at
`.codex/I-safety-002b/codex_diff_pr3.patch` (commit 2894f617 on bot/I-ux-002).

## Pre-verified test results (do NOT re-run)
```
$ python -m pytest tests/dr_benchmark/ -q
tests\dr_benchmark\test_claim_audit_scorer.py ............              [ 14%]
tests\dr_benchmark\test_medhallu_adapter.py ............                [ 28%]
tests\dr_benchmark\test_pathB_capture.py .............                  [ 44%]
tests\dr_benchmark\test_pathB_run_gate.py .....................         [ 69%]
tests\dr_benchmark\test_pathB_runner.py .........                       [ 79%]
tests\dr_benchmark\test_pr3_pipeline.py .................               [100%]
============================= 84 passed in 2.63s ==============================
```

## What landed (5 modules + 1 runbook + 1 test file + 1 generated artifact)
1. **`scripts/dr_benchmark/ledger_schema.py`** (158 LOC): `Claim`, `Coverage`, `Ledger`
   dataclasses with **validation MIRRORING `ClaimRow.__post_init__`** (UNREACHABLE requires
   subtype; FABRICATED/PARTIAL require span_quote; UNSUPPORTED+cited requires span OR
   audit_note). Duplicate `claim_id` / `element_id` rejected at construction. `Auditor`
   includes "reconciled" for the reconcile.py output.
2. **`scripts/dr_benchmark/reconcile.py`** (182 LOC): `reconcile(claude, codex) -> Ledger`.
   Conservative-MAX rule (Codex answer C). On claim disagreement: take the WORSE verdict +
   WORSE severity; preserve disagreement in `audit_note`. On coverage disagreement:
   `covered AND citation_supported` each fall to worse-of-two. **Silent-auditor**: if only
   ONE auditor produced a row for a claim_id, the row is ESCALATED to UNSUPPORTED (or kept
   worse if already worse) and noted in `audit_note`. **Identity guards**: raises
   ValueError if system / question_id / rubric_sha256 differ between auditors.
3. **`scripts/dr_benchmark/score_run.py`** (184 LOC): per-(system, question) CLI.
   **POLARIS gate enforcement** (Codex PR-2 P2 #2 + PR-3 design): refuses to score if
   `pathB_gate_INVALID` exists in run_dir; refuses if `pathB_gate_result.json` missing or
   `verdict != "PASS"`. **Rubric/ledger sha256 cross-check**: refuses if the ledger was
   audited against a DIFFERENT pinned rubric. Builds ClaimRow + RubricElement; missing
   coverage row for a required element → covered=False (conservative). Writes scored JSON
   (or stub INVALID record).
4. **`scripts/dr_benchmark/build_rubric_json.py`** (138 LOC): parses
   `.codex/I-safety-002b/gold_rubrics_pathB.md` into
   `outputs/dr_benchmark/rubric_v3_frozen.json`. **Dual-pin discipline**: reads the pinned
   markdown SHA from `freeze_pin.txt`; refuses to overwrite if current markdown SHA ≠ pin
   (unless `--allow-unpinned` for the initial build). Output records the markdown SHA as
   `rubric_sha256`. **First build output**: 5 questions, 39 elements
   (Q75: 7, Q76: 8, Q78: 8, Q72: 8, Q90: 8); JSON SHA `9aa494937dd61938…` appended to
   `freeze_pin.txt` (dual-pin).
5. **`scripts/dr_benchmark/aggregate_systems.py`** (165 LOC): final-report renderer.
   **Clinical-3 (#75/#76/#78) + Overall-5 reported SEPARATELY** (locked honest-label
   discipline). INVALID rows reported with reason + OMITTED from numerator+denominator
   of the valid subset. **Identity pins block REQUIRED** (Codex answer F): cites
   `freeze_pin.txt` contents verbatim.
6. **`scripts/dr_benchmark/smoke.md`** (84 LOC): operator-supervised single-question
   runbook. Recommends smoke on **#72 (AI labor)** — non-clinical, cleanest scope-gate
   test. Preflight checklist (env vars, gate invariants), pass criteria
   (`pathB_gate_result.json verdict=PASS` + absence of `pathB_gate_INVALID` + manifest
   `success`), fail-mode table with URGENT-issue triggers for `abort_scope_rejected` /
   `abort_corpus_inadequate` (the clinical-tuned-gate risk you flagged in PR-2 design E).
7. **`tests/dr_benchmark/test_pr3_pipeline.py`** (301 LOC, 17 tests): ledger validation +
   duplicate detection + dump/load roundtrip; reconcile conservative-MAX + silent-auditor
   + rubric-sha mismatch error; score POLARIS refuses on INVALID sentinel + missing
   result + FAIL verdict; score passes on PASS + competitor no-gate; rubric/ledger sha
   mismatch error; aggregate renders clinical-3 + overall-5 + INVALID + identity pins.

## Audit focus
- **Schema validation parity** with `ClaimRow.__post_init__`: are there constraints in
  `ClaimRow` that `Claim.__post_init__` misses (so a bad ledger could pass schema
  validation but fail the scorer)?
- **Reconcile conservative-MAX correctness**: is the verdict order `VERIFIED < PARTIAL <
  UNREACHABLE < UNSUPPORTED < FABRICATED` the right gating order? (rationale: UNREACHABLE
  is a fetcher-side problem and not a hard fail; UNSUPPORTED + FABRICATED ARE hard fails.)
- **Silent-auditor escalation**: I escalate "only one auditor covered the claim" to
  UNSUPPORTED (or worse). Is that the right discipline, or should it be FABRICATED
  (treating silence as the worst case)?
- **Rubric-sha mismatch in score_run**: I cross-check the ledger's `rubric_sha256` against
  the loaded rubric JSON. If they differ, the ledger was audited against a DIFFERENT
  pinned rubric — pre-registration violation. Is the right action to REFUSE (current
  behavior) or just WARN?
- **build_rubric_json regex**: parses `^N. **text**` numbered-list lines from each `## #N`
  block. Code only retains numbering that runs `1, 2, 3, …` (stops on reset). If the
  markdown rubric ever uses sub-numbering (`1.1` style), the parser quietly drops them.
  Acceptable, or do you want explicit element-id annotation in the markdown?
- **smoke.md scope (#72 recommended)**: do you agree #72 is the cleaner first smoke (vs
  #90 case-law fabrication firewall) for testing whether non-clinical questions clear the
  scope/corpus gates? My reasoning: #90's case-law verification is a harder TEST of
  POLARIS's strict_verify but the same SCOPE-GATE shape; #72 isolates the scope question.

## Output schema (return EXACTLY this — no exec)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
schema_parity_with_ClaimRow: true | false
reconcile_conservative_max_correct: true | false
silent_auditor_escalation_correct: true | false
rubric_sha_mismatch_action: refuse | warn | other
build_rubric_json_parser_acceptable: true | false
smoke_scope_choice: agree-72 | prefer-90 | both
convergence_call: continue | accept_remaining
remaining_blockers: []
```
