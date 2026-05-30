RULE NOW — emit the YAML verdict block FIRST, before any prose. Do NOT explore the repo more than the
grounded facts below require. (A prior design run explored 7000+ lines and exited without a verdict.)

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
authoring_procedure: <your ruling: the exact contamination-safe steps>
contract_shape: <per-slug per_query_report_contract fields incl. severity/s0/coverage_content_requirements>
attestation: <what the attestation artifact must contain + when frozen>
required_changes: [...]   # only if REQUEST_CHANGES
convergence_call: accept_remaining
```

# Codex DESIGN review — I-meta-002 PR-10: the 5 benchmark native contracts (gold-blind, attested, frozen). APPROVE this concrete plan.

The no-spend serving path is COMPLETE (M1-M5 + offline e2e committed + Codex-approved). The LAST
no-spend prerequisite before the paid canary is authoring a NATIVE `per_query_report_contract` for each
of the 5 LOCKED golden DRB-EN benchmark slugs, so POLARIS's own 4-role gate has a coverage denominator
for the benchmark questions (today only clinical_tirzepatide_t2dm + policy_medicare_drug_price have
contracts; the 5 benchmark slugs have NONE, so the builder fail-closes on them). This is
CONTAMINATION-CRITICAL: the contracts must be authored BLIND to the frozen gold rubric and the stored
competitor answers — else POLARIS is taught-to-the-test, which is §-1.1 lethal in clinical context.

## The 5 LOCKED benchmark slugs (from .codex/I-safety-002b/golden_questions_locked.md)
DRB-EN #75 (metal ions/CVD), #76 (gut microbiota), #78 (Parkinson's/DBS) — clinical;
#72 (AI labor), #90 (ADAS liability) — source-critical. (Domains: #75/#76/#78 clinical;
#72/#90 likely tech/policy/workforce — may need new domain scope templates or custom.)

## CONCRETE PLAN to APPROVE
**Per-slug contract** added under each domain's `config/scope_templates/<domain>.yaml`
`per_query_report_contract[<slug>]`, same shape M3a validates: `required_entities[*]` each with
`id`, `type`, `anchor`, `doi`/`pmid`/`url_pattern`, `required_fields`, plus the native annotations
`severity: S0|S1|S2|S3` and (when S0) `s0_category` (one of d8 s0_must_cover_categories) +
non-blank `coverage_content_requirements`.

**Contamination-safe authoring procedure (the core ruling I need):**
1. Author EACH required_entity SOLELY from: (a) the QUESTION TEXT itself, (b) POLARIS's native domain
   scope protocol (config/scope_templates + completeness_checklists), (c) POLARIS's D8 policy
   s0_must_cover categories, and (d) general domain knowledge of what a rigorous answer to THAT question
   must cover. NEVER open outputs/dr_benchmark/rubric_v3_frozen.json, the freeze pin, or ANY stored
   competitor (gpt_5_5_pro / gemini_3_1_pro) answer.
2. The build agent that authors them runs with NO access to outputs/dr_benchmark (enforce by: the
   authoring task is instructed not to read it; a test/grep asserts the new contract entries contain no
   verbatim spans copied from the gold rubric).
3. Emit `.codex/I-meta-002-pr10-contracts/contract_attestation.txt`: author, date, the exact inputs
   used (question text + which native scope/checklist files), an explicit signed statement "authored
   without reading outputs/dr_benchmark gold rubric or competitor answers," and the SHA256 of each
   new contract block.
4. FREEZE: once authored + Codex-approved, SHA-pin the 5 contract blocks (a freeze_pin file) BEFORE any
   benchmark run, so they cannot drift after the answer key is consulted by the external scorer.

**Sequencing:** author all 5 in ONE PR (they're data + attestation, reviewed together), Codex diff-gate,
commit, freeze. Then the only remaining step is operator-gated lock promotion + the paid canary.

## Questions for you
1. `authoring_procedure`: is the gold-blind procedure above sufficient, or do you require a stronger
   isolation (e.g. author in a worktree with outputs/dr_benchmark removed; a diff-time check that no
   new contract string appears verbatim in the gold rubric)?
2. `contract_shape`: for the 2 source-critical slugs (#72 AI labor, #90 ADAS liability) the native
   "entities" are statutes/standards/reports, not trials — confirm `type` values + that url_pattern
   (not doi) is the canonical id, and how severity maps when there's no clinical S0 (likely S1/S2 only,
   no S0 s0_category required for non-clinical slugs — confirm S0 is clinical-only here).
3. `attestation`: is the attestation artifact + SHA-freeze sufficient proof of gold-blindness, or do
   you want the attestation itself Codex-reviewed against the diff?
4. Any contamination / teaching-to-the-test / fail-open risk in this plan?

APPROVE the plan (with your authoring_procedure + contract_shape + attestation rulings) so I can build
the 5 contracts, or REQUEST_CHANGES with required_changes. NO SPEND.
