# POLARIS pass 9 — 8-query sweep content audit

You are auditing the actual RESULTS of an 8-query POLARIS pipeline A
sweep. Passes 1-8 audited the CODE; this pass audits the OUTPUT.

## Sweep summary

Total cost: **$0.0109** (vs per-query $0.10 cap, sweep ≈ 0.14% of budget).

| slug | status | release | fetched | words | kept/dropped | rule | judge (g/a/r) |
|---|---|---|---|---|---|---|---|
| clinical_tirzepatide_t2dm | partial_qwen_advisory | False | 16/300 | 580 | 19/6 | 13/13 | 2/1/2 |
| clinical_afib_anticoagulation | partial_qwen_advisory | False | 16/657 | 751 | 25/6 | 13/13 | 3/0/2 |
| policy_fda_ai_devices | success | True | 13/32 | 609 | 21/0 | 13/13 | 5/0/0 |
| policy_medicare_drug_price | partial_qwen_advisory | False | 13/95 | 530 | 17/4 | 13/13 | 4/0/1 |
| tech_rag_architectures_2024 | success | True | 19/46 | 654 | 26/0 | 13/13 | 3/2/0 |
| tech_long_context_transformer | abort_corpus_inadequate | None | 20/30 | 0 | 0/0 | — | — |
| dd_novo_nordisk_obesity_position | success | True | 17/24 | 840 | 30/4 | 12/13 | 4/0/1 |
| dd_lilly_tirzepatide_manufacturing | success | True | 12/16 | 568 | 19/4 | 12/13 | 3/1/1 |

4/8 released (50%). 3/8 partial_qwen_advisory (release blocked by qwen
citation_tightness). 1/8 abort_corpus_inadequate (retrieval shortfall).

## Per-query artifact locations

All artifacts are under `outputs/sweep_r3_final/<domain>/<slug>/`:

- `manifest.json` — structured run result (status, gate, costs)
- `report.md` — the generated research report
- `verification_details.json` — per-sentence drop reasons (NEW in
  commit b2b6f5a)
- `evaluator_rule_checks.json` — PT01..PT13 rule outcomes
- `qwen_judge_output.json` — qwen-judge verdicts across 5 axes
  (citation_tightness, hedging, tone, flow, completeness)
- `run_log.txt` — per-stage log of the pipeline
- `bibliography.json` — numbered bibliography with source URLs
- `contradictions.json` — Phase 3 contradiction detector output
- `corpus_adequacy.json` — Phase 2 adequacy gate decisions
- `live_corpus_dump.json` — classified sources with tier info
- `cost_ledger.jsonl` — per-LLM-call cost records

Full index: `outputs/codex_findings/full_audit_pass_9/sweep_index.md`.

Sweep-level summary: `outputs/sweep_r3_final/sweep_summary.{json,md}`.

## Your mandate — CONTENT AUDIT (not code)

### 1. Are the released reports actually useful research reports?

Open `report.md` for each of the 4 released queries:
- `policy_fda_ai_devices`
- `tech_rag_architectures_2024`
- `dd_novo_nordisk_obesity_position`
- `dd_lilly_tirzepatide_manufacturing`

For each answer:
- Does the report substantively answer the question?
- Are the claims grounded — i.e., does each citation [N] actually
  point to a source that supports the adjacent sentence? Spot
  check 3-5 citations per report by opening
  `verification_details.json` (kept-sentence spans) and
  `live_corpus_dump.json` (evidence_id → source URL + tier).
- Is the tier mix reported honestly and the material_deviation
  flag consistent with the actual distribution?
- Are the contradictions disclosed and the limitations section
  accurate?
- Is the report's length/depth appropriate for the question, or
  is it thin?

If a released report has any hallucinated citation, wrong numeric
claim, or misleading framing, flag it as a **blocker**. The
pipeline's whole value proposition is "honest by construction" —
a released-but-wrong report is a worse failure than a blocked
correct report.

### 2. Why did the partial_qwen_advisory queries fail qwen?

Open the 3 reports and their qwen outputs:
- `clinical_tirzepatide_t2dm` (qwen: 2 good / 1 acceptable / 2 revise)
- `clinical_afib_anticoagulation` (qwen: 3 good / 0 acceptable / 2 revise)
- `policy_medicare_drug_price` (qwen: 4 good / 0 acceptable / 1 revise)

For each: does qwen's citation_tightness complaint have substance,
or is qwen being overly strict on an otherwise-accurate report?
This is a judgment call — not every qwen revise-flag reflects
a real defect.

### 3. Why did tech_long_context_transformer abort?

Status: `abort_corpus_inadequate`. The retrieval step got 20
sources classified but couldn't pass the corpus adequacy gate.
Open `corpus_adequacy.json` + `run_log.txt` for this query.

- Is this a legitimate refusal (not enough high-tier sources
  existed for this question) or a bug (adequacy thresholds
  mis-tuned for this topic)?
- If legitimate: does the manifest expose the refusal cleanly
  enough for a downstream consumer to understand why?
- If a bug: what should we fix before re-running?

### 4. Cross-query cost + performance sanity

- Total cost $0.0109 for 8 queries = $0.00136 avg. Well under
  the $0.10/query cap. Is this low because (a) generation was
  actually cheap on these queries, or (b) the generator cut
  short on some queries?
- Wall time 156s to 462s per query (average ~280s = 4.7 min).
  Anything anomalous?
- The tech_long_context_transformer abort happened after $0. Is
  that expected for abort_corpus_inadequate (the generator never
  ran)?

### 5. Honest-by-construction invariants survived the sweep?

- Two-family evaluator segregation: generator is DeepSeek V3.2;
  evaluator is Qwen3-8B. Any sign of same-family contamination?
- Provenance tokens present and verified on every kept sentence?
- Strict_verify actually dropped unsupported sentences (not
  rubber-stamping)?
- Budget cap respected on every query?
- Prompt-injection sanitization applied (no `<<<evidence:...>>>`
  leaks)?

### 6. Final verdict

One of:
- **APPROVED-FOR-FULL-SCALE-RUN**: the 4 released reports meet
  the quality bar, the 3 partial releases are legitimate qwen
  advisories, the 1 abort is expected pipeline refusal, no
  hallucinations / wrong claims / invariant breaks.
- **BLOCKED-ON-ISSUE**: one or more of the above found a
  release-blocking defect. List it specifically with a reproducer
  and a recommended fix.
- **CONDITIONAL**: approve with specific targeted improvements.

## Output

Write to `outputs/codex_findings/full_audit_pass_9/findings.md`
with frontmatter:

```yaml
---
verdict: APPROVED-FOR-FULL-SCALE-RUN | BLOCKED-ON-ISSUE | CONDITIONAL
pass: 9
sweep_commit: 3e4dd03
released_reports_quality: <brief>
partial_qwen_advisory_legitimate: true | false | mixed
tech_long_context_abort_legitimate: true | false
hallucinations_found: <int>
invariant_breaks: <list or empty>
rationale: |
  <3-5 sentences>
---
```

Followed by per-section findings.

## Ground rules

- Quote specific file paths and line numbers in your findings. I
  will cross-check.
- Do NOT declare APPROVED without opening at least 2 reports and
  cross-checking 3+ citations per report.
- If you find ONE hallucinated citation, that's a BLOCKER even if
  the rest of the sweep is clean. Honest-by-construction means
  the pipeline must never release a wrong claim.

## Auth + duration

OAuth chatgpt. 30-45 minutes expected (this is a deeper audit than
passes 3-8 because it involves reading actual reports).

---

Start:

```
cat outputs/codex_findings/full_audit_pass_9/sweep_index.md | head -50
cat outputs/sweep_r3_final/sweep_summary.md
ls outputs/sweep_r3_final/policy/policy_fda_ai_devices/
```

Then walk sections 1-6.
