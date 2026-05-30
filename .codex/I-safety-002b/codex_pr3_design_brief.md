HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# PR-3 DESIGN BRIEF iter 2 — concise, please return the VERDICT YAML (do NOT exec)

iter 1 was investigative — you read scorer source, runner source, and tests, then ran out of
budget before producing the verdict YAML. For iter 2, all the source you need is **inlined
below** so you don't have to exec/read files. Please return the verdict YAML with answers to
the 6 design questions A–F.

## What I already verified you observed in iter 1
- Scorer is at `src/polaris_graph/benchmark/claim_audit_scorer.py` (NOT scripts/). My iter-1
  brief mis-described the path. Correction: PR-3 imports scorer from `src.polaris_graph...`.
- `ClaimRow` has stricter validation than the brief's minimal schema implied. Specifically:
  - `UNREACHABLE` requires `unreachable_subtype` (paywall|robots|fetch_failure|source_missing).
  - `FABRICATED` and `PARTIAL` require `span_quote` (the refuting/partial span).
  - `UNSUPPORTED` on a CITED claim requires `span_quote` OR `audit_note` (traceability).
  - The `Severity = Literal["S0","S1","S2","S3"]` type forbids any other tag.
- The dual-audit ledger JSON schema PR-3 defines MUST respect these constraints (the
  `score_run.py` loader will fail closed on any row that violates them — exactly what we want
  for clinical safety).

## PR-3 scope (TL;DR)
1. **Companion JSON snapshot of the frozen rubric** (`outputs/dr_benchmark/rubric_v3_frozen.json`)
   — generated once from `gold_rubrics_pathB.md`, then BOTH files SHA256-pinned in
   `freeze_pin.txt`. Rebuilds from markdown but only if the markdown sha matches the pin.
   Avoids brittle live-parsing of markdown during scoring.
2. **Ledger schema** (`scripts/dr_benchmark/ledger_schema.py`):
   - `Claim` (`claim_id`, `severity` S0-S3, `verdict`, `citation_id?`, `span_quote?`,
     `unreachable_subtype?`, `audit_note?`, `auditor: claude|codex`).
   - `Coverage` (`element_id`, `covered`, `citation_supported`, `auditor_note?`, `auditor`).
   - `Ledger` (system, question_id, list[Claim], list[Coverage], audit_method, audit_timestamp).
   - Pydantic/dataclass validation that mirrors `ClaimRow.__post_init__` constraints.
3. **Reconciler** (`scripts/dr_benchmark/reconcile.py`):
   `reconcile(claude_ledger, codex_ledger) -> reconciled_ledger`. Joins by `claim_id`. On
   verdict disagreement, applies conservative MAX (worse-of-two) for the gating verdict;
   records both verdicts in `reconciliation_notes` for traceability. Same for Coverage.
4. **Score CLI** (`scripts/dr_benchmark/score_run.py`):
   - Args: `--system {polaris|chatgpt|gemini} --question Q72|Q75|Q76|Q78|Q90 --rubric <path>
     --ledger <path> [--run-dir <path> if polaris]`.
   - For polaris: refuse to score if `pathB_gate_INVALID` sentinel exists in `--run-dir`
     (raise `InvalidRunError`). Confirm `pathB_gate_result.json` verdict==PASS.
   - Load ledger → build `ClaimRow[]` + `RubricElement[]` → call existing
     `system_passes_question` from `claim_audit_scorer.py`.
   - Output: `outputs/dr_benchmark/scored/<system>_<question>.json` (lane1 + lane2 + passed +
     reasons).
5. **Aggregator** (`scripts/dr_benchmark/aggregate_systems.py`): reads all scored/*.json →
   `outputs/dr_benchmark/final_report.md` with CLINICAL-3 (#75/#76/#78) and OVERALL-5 reported
   SEPARATELY per the locked honest-label discipline. Every cell traces to a (system, question,
   ledger row) — no "wins" headline.
6. **Smoke runbook** (`scripts/dr_benchmark/smoke.md`): how to run one operator-supervised
   single-question Path-B run to confirm POLARIS's clinical-tuned scope/corpus gates accept the
   non-clinical questions (#72 or #90) BEFORE 5 full runs.

## 6 design questions (please answer)
- **A. Rubric format**: companion JSON + dual SHA-pin (recommended) vs live markdown parse?
- **B. Coverage pass**: same-as-claims pass (auditor produces both rows once) vs separate sweep?
- **C. Disagreement rule**: conservative MAX (worse-of-two — clinical-lethal framing) vs flag-only?
- **D. Invalid aggregation**: report INVALID + omit from numerator (denominator stays 5) vs
  drop silently vs include?
- **E. Smoke scope**: ONE non-clinical question (cheaper, faster) vs BOTH #72 AND #90 (covers
  both non-clinical domains)?
- **F. Identity pins in final report**: REQUIRE the final report to cite freeze_pin.txt SHAs +
  pinned served-identity surrogates per role + per-question reachability proofs, vs optional?

## Output schema (return EXACTLY this — no exec, no source-reading)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
answers:
  A_rubric_format: companion-json | markdown-parse | both
  B_coverage_pass: same | separate
  C_disagreement_rule: conservative-max | average | flag-only
  D_invalid_aggregation: report-omit | report-include | omit-silent
  E_smoke_scope: one-question | both-72-and-90
  F_identity_pins_in_report: yes-required | optional
convergence_call: continue | accept_remaining
remaining_blockers_for_diff: []
```
