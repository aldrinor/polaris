HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Same bar every iter. Reserve P0/P1 for real execution risks.
- If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE: DIFF review of the cash-free benchmark scorer vs the APPROVED design
(design-gate APPROVE iter3, `.codex/I-meta-006/design_brief_iter3.md`). Open at most this
brief, the diff `.codex/I-meta-006/codex_diff.patch`, and the 4 changed src files +
`claim_audit_scorer.py` if needed. No repo-wide audit. Emit the verdict schema.

# I-meta-006 (#1006) — DIFF review: cash-free FACT benchmark scorer

## THE ONE QUESTION
Can the scorer (a) let a system get a FALSE faithfulness credit (a non-supported claim
scored VERIFIED / a wrong number passed / POLARIS auto-passing), or (b) silently EXCLUDE
a claim from the denominator so a bad report dodges scoring, or (c) emit a false PASS/fail
while rubrics are pending? Those are the only P0/P1 classes here. Everything else P2/P3.

## What the diff implements (verify against the APPROVED design)
1. `report_claim_extractor.py` — system-agnostic ATOMIC extraction. POLARIS reuses
   `parse_provenance_tokens` ([#ev:] span) + `[N]`; ChatGPT/Gemini map `(Author, Year)` +
   numbered superscripts against the references; injected `atomizer` (default = semicolon
   split). Uncited atoms KEPT (kind="uncited"). Markers stripped from atom text.
2. `fact_scorer.py` — `score_atoms(atoms, *, span_fetcher, judge) -> list[ClaimRow]`:
   - most-specific ref (ev_span > resolved cite > any cite; None = uncited).
   - uncited -> judge(text,None,None) -> UNSUPPORTED, citation_id=None, audit-assigned severity.
   - unresolved cite -> UNREACHABLE(source_missing), in denominator.
   - fetched-but-unreachable -> UNREACHABLE(fetcher subtype incl. metadata_only), in denominator.
   - fetched -> judge(text, span, ref); **substring validation**: VERIFIED/PARTIAL/FABRICATED
     require span_quote ⊂ fetched span ELSE fail-closed to UNSUPPORTED; judge UNREACHABLE
     when span WAS fetched -> coerced UNSUPPORTED. Builds the EXISTING `ClaimRow`.
3. `benchmark_scorecard.py` — `score_system_question` returns lane1 + lane2_pending + pass=null
   when NO rubric (never calls the PASS rule on an empty rubric); `build_scorecard` splits
   clinical-3 (#75/76/78) vs overall-5; reuses `lane1_faithfulness`.
4. `run_scorecard.py` — ingest stored competitor reports + a POLARIS run; **body-only**
   extraction (References section split off so reference lines are not scored as uncited
   atoms); injected fetcher+judge = only billed step.
5. `claim_audit_scorer.py` — `+metadata_only` UnreachableSubtype (additive Literal; existing
   4 values + all callers unaffected).

## Pressure-test (front-load any P0/P1)
- Substring validation: can a judge get VERIFIED/PARTIAL/FABRICATED accepted WITHOUT a real
  span_quote substring of the fetched text? (smoke: lying judge -> UNSUPPORTED.) Any verdict
  path that skips validation?
- Denominator integrity: is EVERY atom turned into exactly one ClaimRow (none excluded)?
  uncited + unresolved + unreachable all kept? (smoke asserts each.)
- POLARIS no-auto-pass: is POLARIS judged by the SAME judge-reads-fetched-span path (its
  [#ev:] span used only to DEFINE the cited span, never to auto-verify)?
- lane2_pending: with no rubric, is PASS withheld (pass=null), NOT a false fail from coverage
  0.00? (smoke asserts.)
- ClaimRow invariants: do all constructed rows satisfy `ClaimRow.__post_init__`
  (FABRICATED/PARTIAL need span_quote; UNSUPPORTED+cited needs span_quote or audit_note;
  UNREACHABLE needs subtype)? Any path that raises?
- run_scorecard body/References split: can a real report's prose be wrongly truncated, or a
  References line still leak in as a claim?

## Evidence
- 16 spend-free smoke (3 citation formats + uncited + compound; substring-validation
  fail-closed; uncited/unresolved/metadata-only UNREACHABLE; lane2_pending; clinical-3 vs
  overall-5; run_scorecard end-to-end with fakes) + 12 claim_audit + 200 dr_benchmark
  regression ALL PASS. No live client; injected fakes only.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
