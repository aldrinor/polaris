# PR-10 build spec — 5 benchmark native per_query_report_contract entries (gold-blind, attested, frozen) — NO SPEND

Codex APPROVED this (design verdict .codex/I-meta-002-pr10-contracts/codex_design_verdict.txt) with the
tightening: author in a CLEAN WORKTREE where outputs/dr_benchmark is ABSENT (instruction-only isolation
is insufficient for this contamination class), then a diff-time verbatim-overlap contamination check.

## CONTAMINATION IS THE WHOLE POINT (§-1.1 LETHAL if violated)
You are authoring POLARIS's OWN required-element contracts for the 5 benchmark questions. These give
POLARIS's 4-role gate a native coverage denominator. They MUST be derived BLIND to the answer key.
- The gold rubric (outputs/dr_benchmark/rubric_v3_frozen.json), freeze pins, and the stored competitor
  answers (outputs/dr_benchmark/external_outputs/gpt_5_5_pro/*, gemini_3_1_pro/*) are GITIGNORED, so in
  your fresh worktree they DO NOT EXIST. Do NOT attempt to read, reconstruct, or `git show` them. Do NOT
  read .codex/I-safety-002b/gold_rubrics_pathB.md or freeze_pin.txt either (those describe the gold).
- Derive EACH required_entity SOLELY from: (a) the QUESTION TEXT (in .codex/I-safety-002b/golden_questions_locked.md),
  (b) POLARIS native config/scope_templates/<domain>.yaml + config/completeness_checklists/<domain>.yaml,
  (c) config/architecture/d8_release_policy.yaml s0_must_cover categories, (d) general domain knowledge
  of what a rigorous answer to THAT question must cover.
- **DO NOT target any element COUNT.** The gold rubric's per-question element counts are part of the
  answer key — matching them would be teaching-to-the-test. Derive however many entities POLARIS's own
  scope says are required; a count that happens to differ from the gold is CORRECT, not a bug.

## The 5 questions (question_id -> domain template)
- Q75 (metal ions / CVD) — clinical -> config/scope_templates/clinical.yaml
- Q76 (gut microbiota / CRC) — clinical -> clinical.yaml
- Q78 (Parkinson's / DBS) — clinical -> clinical.yaml
- Q72 (AI / labor & jobs) — source-critical -> config/scope_templates/workforce.yaml
- Q90 (ADAS / liability, crime & law) — source-critical -> config/scope_templates/policy.yaml
Read the FULL question text for each from .codex/I-safety-002b/golden_questions_locked.md.

## Step 1 — resolve the canonical slug + domain
From the TRACKED benchmark wiring (scripts/dr_benchmark/*, src/polaris_graph/benchmark/*, how
run_one_query derives q["slug"]/q["domain"] for a benchmark question), determine the EXACT slug key
each of Q72/Q75/Q76/Q78/Q90 will use as `per_query_report_contract[<slug>]` and which domain template it
loads. (The external scorer keys by question_id Q##; the 4-role builder keys the contract by the run's
slug — find the slug the benchmark run assigns.) Report the slug<->question_id<->domain mapping.

## Step 2 — author the contracts (BLIND)
Add `per_query_report_contract[<slug>]` to the right domain template (clinical.yaml already has the
section; policy.yaml has it; workforce.yaml will add it). Match the EXISTING contract shape M3a
validates (see src/polaris_graph/roles/native_gate_b_inputs.py): each `required_entities[*]` has
`id`, `type`, `anchor`, a canonical identifier (`doi`/`pmid` for biomedical literature; `url_pattern`
for statutes/standards/agency reports/datasets/web sources), `required_fields`, `severity` (S0|S1|S2|S3),
and a NON-BLANK `coverage_content_requirements` (list of deterministic tokens/phrases the claim text
must contain). When `severity: S0`, also a valid `s0_category` from d8 s0_must_cover_categories.
- Clinical (Q75/76/78): S0 only where the native clinical policy has a true must-cover catastrophic
  omission (contraindications/dosing/black-box/pregnancy-renal-hepatic/regulatory-status); else S1/S2/S3.
- Source-critical (Q72/Q90): types may be statute/regulation/standard/agency_report/policy_report/
  economic_report/legal_case/technical_standard/dataset/authoritative_source; url_pattern is the
  canonical id. Do NOT force S0 — use S1/S2/S3 unless the native domain policy defines a must-cover
  catastrophic/invalidating omission category for that domain.

## Step 3 — attestation
Emit `.codex/I-meta-002-pr10-contracts/contract_attestation.txt` containing: author (Claude build agent),
date (pass it in — do NOT call datetime in library code; the agent may write the date string it is told),
the exact allowed inputs used PER SLUG (question text + which native scope/checklist files), an EXPLICIT
statement "authored in an isolated worktree with outputs/dr_benchmark absent; gold rubric, freeze pins,
and competitor answers were NOT read", the isolation method (fresh git worktree), and a placeholder for
the SHA256 of each new contract block (Claude main-thread computes + fills the hashes after bring-back).

## Step 4 — report for bring-back
Because you are in a worktree, REPORT the FULL verbatim YAML of each new per_query_report_contract block
+ the attestation text in your final message, so Claude main-thread can apply them, run the diff-time
contamination check (verbatim-overlap vs outputs/dr_benchmark, which exists in main tree), run the M3a
validator over each new contract (must parse + validate fail-closed), Codex-review the diff + attestation,
commit, and SHA-freeze.

## Constraints
- NO SPEND / NO NETWORK. Frozen: claim_audit_scorer.py, runtime lock (NOT promoted). snake_case YAML
  keys; non-blank coverage_content_requirements (M3a raises on blank). Do NOT edit anything except the
  3 domain templates' per_query_report_contract sections + the attestation.
