Diff review for GH#422 I-gen-001 (PBO scope conflation). Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify P3/P2/cosmetic.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Brief lineage

Brief iter 1 returned REQUEST_CHANGES asking for actual implementation (which was the intent — the brief proposed the plan, Codex demanded the code). Diff iter 1 now implements rule 13 + tests.

# Test results

```
PYTHONPATH=src python -m pytest tests/polaris_graph/test_multi_section_gap4.py \
  tests/polaris_graph/test_multi_section_limitations_r1.py \
  tests/polaris_graph/test_section_prompt_gh422.py
19 passed in 2.80s
```

# Diff (saved at .codex/I-gen-001/codex_diff.patch)

## Production code: src/polaris_graph/generator/multi_section_generator.py

Append rule 13 to SECTION_SYSTEM_PROMPT_TEMPLATE immediately after rule 12c (line 658):

```diff
@@ rule 12c block @@
 BAD: "This trial also reported maintained [ENDPOINT] [ev_X]." — anaphoric sentence with no antecedent frame. BAD: "The [PROGRAM] trials found greater [ENDPOINT] reduction with [INTERVENTION] [ev_X]." — group reference without enumeration or pooled N.
+13. **Policy-scope disambiguation (M-NEW-1, GH#422)**: When a paragraph names a specific program (Bill C-64, ACA, MACRA, EU AI Act, Article 34.7 CUSMA review, a particular budget line, etc.) and the evidence pool also contains projections / cost estimates / impact analyses for a RELATED-BUT-BROADER scope (universal single-payer projection vs phase-1 narrow program; comprehensive coverage estimate vs narrow amendment; multi-jurisdiction equivalent of a single-state rule), do NOT silently fold the broader projection into the narrow-program paragraph. When citing numbers from the broader scope, EXPLICITLY label the scope-attribution INLINE in the SAME sentence as the citation. Required pattern: write "PBO 2023 universal single-payer projection estimates the additional cost at $11.2B in 2024-25 [ev_X]" — NOT "the incremental cost is $11.2B in 2024-25 [ev_X]" inside a paragraph that opens with Bill C-64 phase-1. The decimal and the citation are correct; the missing scope label is what makes the conflation. Same evidence-ID, additional 4-8 word scope phrase before the citation. This rule fires regardless of which section the named-program paragraph appears in (Regulatory, Comparative, Economic, etc.). Failure mode this rule prevents: a reader concludes a narrow program will cost the broader program's projected figure. [Concrete GOOD/BAD examples follow]
```

Stats: `+1 line of code (rule appended to template), 0 lines of code refactor, 0 production-path behavior changes besides prompt content`.

## Tests: tests/polaris_graph/test_section_prompt_gh422.py (new file, +60 lines)

5 new tests:
- test_section_prompt_contains_policy_scope_disambiguation_rule (rule 13 header present)
- test_section_prompt_names_bill_c64_example (Bill C-64 + PBO references)
- test_section_prompt_requires_inline_scope_label (EXPLICITLY label demand present)
- test_section_prompt_rule_13_fires_across_sections (rule applies to all 7 standard section titles)
- test_section_prompt_rule_13_documents_bad_example (BAD example present)

All 5 pass.

# Verification

1. ✅ Rule 13 appended to SECTION_SYSTEM_PROMPT_TEMPLATE
2. ✅ Rule references GH#422 for traceability
3. ✅ Bill C-64 + PBO universal single-payer named explicitly
4. ✅ Inline-scope-label requirement stated
5. ✅ GOOD + BAD examples provided
6. ✅ Rule fires across all section titles (not Regulatory-only)
7. ✅ 5 regression tests for the rule
8. ✅ Existing multi_section tests unchanged (14 pass)
9. ✅ Zero refactor; prompt-only change

# Out of scope

- GH#423 duplicate-fact redundancy fix (separate PR; needs sequential-section refactor)
- Re-running Q5 sweep (manual smoke test recommended but not strictly required for prompt-level fix; will run post-merge)

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
