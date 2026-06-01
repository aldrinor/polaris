HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding. Same bar every iter.
- "Don't pick bone from egg" — reserve P0/P1 for real design risks; rest P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- This is a DESIGN gate (methodology correctness), not a diff review. Verdict APPROVE iff
  the design is §-1.1-sound and buildable as specified; else REQUEST_CHANGES with the
  specific methodology corrections.

REVIEW DISCIPLINE: design review. Open at most this brief +
`src/polaris_graph/benchmark/claim_audit_scorer.py` +
`.codex/I-safety-002b/golden_questions_locked.md`. No repo-wide audit. Emit the schema.

# I-meta-006 — Cash-free system-agnostic benchmark scorer (FACT claim-by-claim) — DESIGN

## Context + the methodology decision I need you to rule
The operator chose "build the benchmark scorer first, no spend." Goal: score the 5
LOCKED golden questions (DRB-EN #75/#76/#78/#72/#90; "citation-faithfulness stress slice,
3 clinical + 2 source-critical") claim-by-claim, IDENTICALLY across POLARIS, ChatGPT 5.5
Pro DR, Gemini 3.1 Pro DR. Competitor reports are already stored as markdown under
`outputs/dr_benchmark/external_outputs/{gpt_5_5_pro,gemini_3_1_pro}/Q##_*.md` (academic
"(Author, Year)" citations + a references list, NOT POLARIS `[#ev:]` tokens).

**§-1.1 is the binding standard (clinical-safety-critical):** the per-claim verdict
(VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE) MUST come from reading the claim
against the FETCHED cited span (cited text, not title/abstract). Metadata / count /
string-presence / sample-based scoring is BANNED ("lethal in clinical"). The EXISTING
`claim_audit_scorer.py` already encodes this: it is a PURE AGGREGATOR over a reconciled
per-claim ledger; it assigns NO verdicts; it gives POLARIS no free pass. It REPLACED the
§-1.1-banned `beat_both_scorer.py` (count/pattern/auto-win) — so I will REUSE
`claim_audit_scorer` and will NOT reuse `beat_both_scorer`.

## Proposed design (rule on each piece)
A cash-free harness in `src/polaris_graph/benchmark/`; the verdict-assignment + source
fetch are INJECTED callables (faked in tests, real in the operator-gated paid run), so
EXTRACTION + AGGREGATION are deterministic + spend-free-tested.

1. **NEW `report_claim_extractor.py`** — system-agnostic. `extract_claims(report_text,
   system, references) -> list[ExtractedClaim{claim_id, text, citation_refs:[ref]}]`.
   - POLARIS: reuse `split_into_sentences` + `parse_provenance_tokens` ([#ev:]/[N] + bibliography).
   - ChatGPT / Gemini: split into atomic sentences; map each to the citation(s) it carries
     — academic "(Author, Year)" inline keys resolved against the report's references list
     (and numbered superscripts where present). A sentence with NO citation is still an
     extracted claim (it scores as uncited).
   Deterministic; cash-free.
2. **NEW `fact_scorer.py`** — `score_claims(claims, *, span_fetcher, judge) -> list[ClaimRow]`.
   For each claim: `span_fetcher(citation_ref)` returns the FETCHED cited source text
   (injected — real fetcher in the paid run; UNREACHABLE subtype on fetch failure), then
   `judge(claim_text, fetched_span)` returns a Verdict by READING the span (injected — the
   §-1.1 reader: an LLM judge or the Claude+Codex dual audit). Emits the EXISTING `ClaimRow`
   for `claim_audit_scorer`. The judge reads the fetched span (§-1.1-compliant), NOT metadata.
3. **NEW `benchmark_scorecard.py`** — for the 5 Qs × 3 systems: extract -> fact_score ->
   `claim_audit_scorer.aggregate`, with lane2 coverage from the pre-registered gold rubric.
   Emit per-system: clinical-3 (#75/#76/#78) AND overall-5 separately (per the locked label).
   Honest framing: per-claim-traceable, NOT a one-number "wins" headline.
4. **Run wiring `scripts/dr_benchmark/run_scorecard.py`** — ingest the stored competitor
   reports + a POLARIS run's report+bibliography, run the scorecard with the REAL
   fetcher+judge (the only billed step, operator-gated). Cash-free with injected fakes.
5. **REUSE:** `claim_audit_scorer` (ClaimRow + lane1/lane2 + aggregate), `ledger_schema`,
   `split_into_sentences`/`parse_provenance_tokens`, the stored reports, the locked Qs.
   **DO NOT reuse** `beat_both_scorer` (§-1.1-banned).

## Specific methodology questions (rule on each)
- **Q1 (the core §-1.1 reconciliation):** is an INJECTED `judge(claim, fetched_span)` that
  reads the fetched span an acceptable §-1.1 audit engine for the AUTOMATED scorecard, OR
  must the verdict come ONLY from the Claude+Codex dual line-by-line audit (i.e. the harness
  should produce the EXTRACTION worklist for the dual audit, and aggregate the reconciled
  ledger, never auto-judge)? If both are acceptable, what guardrail keeps an automated judge
  from degrading into a metadata/pattern check (e.g. must return the supporting/refuting span
  quote it relied on, mirroring ClaimRow.span_quote)?
- **Q2 (citation resolution honesty):** academic "(Author, Year)" → fetchable source is
  lossy. If a claim's citation cannot be resolved to a fetchable span, is the correct verdict
  UNREACHABLE(source_missing), or is the claim excluded? (Excluding would let an
  unresolvable-citation report dodge faithfulness scoring — a rigging risk.)
- **Q3 (cross-system fairness):** POLARIS emits machine-checkable spans; ChatGPT/Gemini do
  not. Does scoring POLARIS by the SAME judge-reads-fetched-span path (ignoring its
  [#ev:] spans for the verdict, using them only for extraction) keep the protocol identical,
  or does any asymmetry remain that gives POLARIS a free pass?
- **Q4 (RACE scope):** DeepResearch-Bench RACE (adaptive-criteria quality/depth) is a
  separate, more subjective lane. Scope it OUT of this issue (FACT faithfulness + lane2
  coverage only) and file RACE as a follow-up, or is it required for the head-to-head?
- **Q5 (lane2 rubric):** the pre-registered gold rubrics for these 5 Qs — do they already
  exist (referenced in `.codex/I-safety-002b/`), so lane2 reuses them, or is rubric
  construction part of this issue?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
rulings:   # your answer to Q1..Q5
  q1: ...
  q2: ...
  q3: ...
  q4: ...
  q5: ...
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
