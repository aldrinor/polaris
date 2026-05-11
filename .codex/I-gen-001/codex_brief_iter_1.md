Review brief for GH#422 I-gen-001 — PBO universal-plan numbers in Bill C-64 phase-1 section.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Bug

Q5 Pharmacare Regulatory section places PBO 2023 universal-single-payer projection numbers ($11.2B 2024-25 → $13.4B 2027-28 incremental public cost; $33.2B → $38.9B total drug expenditure) inside the Bill C-64 phase-1 paragraph. Bill C-64 phase-1 covers only contraception + diabetes medications; the PBO numbers project universal single-payer with expanded Quebec formulary. Decimals correct, scope-attribution wrong.

Surfaced by Tier-1 pilot Q5-T1-014 (PR #421, GH#420 reconciliation) and prior FAB-led Q5-C4 audit. Same issue both times.

# Files I have ALSO checked and they're clean

- `src/polaris_graph/generator/multi_section_generator.py:639-761` — SECTION_SYSTEM_PROMPT_TEMPLATE (the section-level prompt rules). Currently has 12 numbered rules + several lettered sub-rules (12a/12b/12c) + M-47/M-42c blocks for Mechanism + EVIDENCE TIER DISCIPLINE + TRIAL-SPECIFIC CITATION RULE + jurisdictional precision rule 11 + jurisdictional coverage rule 11b. Fix slot: new rule 13 for policy-scope disambiguation. Per-section template; doesn't need code refactor.
- `src/polaris_graph/generator/multi_section_generator.py:764-870` — `_call_section` per-section LLM call. SECTION_SYSTEM_PROMPT_TEMPLATE.format(title=..., focus=...) at line 800. Adding rule 13 to template = automatic propagation to every section call.
- `config/scope_templates/policy.yaml` — domain template for policy queries. Contains tier expectations + COI/exclusion rules. Does NOT currently encode scope-attribution rules. Not the right place for a per-claim-citation discipline rule; that belongs in SECTION_SYSTEM_PROMPT_TEMPLATE.
- `src/polaris_graph/generator2/section_blueprint.py` — slice-002 separate generator path (not used by production sweep). Out of scope.
- `tests/polaris_graph/test_multi_section_generator*.py` — existing tests for prompt construction. Will need a new test confirming rule-13 appears in policy-domain Regulatory sections.

# Proposed fix scope

Add a new numbered rule to SECTION_SYSTEM_PROMPT_TEMPLATE addressing policy-scope disambiguation:

```
13. **Policy-scope disambiguation (M-NEW-1)**: When this section opens with a specific named program (Bill C-64, ACA, MACRA, EU AI Act, etc.) and the evidence pool also contains projections / cost estimates / impact analyses for a RELATED-BUT-BROADER scope (e.g., PBO universal single-payer projection when the section discusses Bill C-64 phase-1; CBO comprehensive coverage estimate when discussing a narrow ACA amendment; multi-jurisdiction equivalent of a single-state rule), do NOT silently fold the broader projection into the narrow-program paragraph. When citing numbers from the broader scope, EXPLICITLY label the scope-attribution INLINE: write "PBO 2023 universal single-payer projection estimates ... [ev_X]" not "incremental cost is $11.2B [ev_X]" if the cited source is a universal-plan analysis. The decimal and the citation are correct; the missing scope label is what makes the conflation. Same evidence-ID, additional 4-8 word scope phrase in the sentence. This rule fires regardless of which section the named-program paragraph appears in (Regulatory, Comparative, Economic, etc.).
```

## Why prompt-level (not code-level)

- The fix surface is purely a model-instruction issue. The model already cites the right ev_id; it just needs to wrap the citation with a 4-8 word scope-attribution phrase.
- No code refactor needed; SECTION_SYSTEM_PROMPT_TEMPLATE.format auto-propagates.
- Operational cost: 0 LLM-call increase, ~30 additional tokens per section system prompt.
- Test: new pytest in `tests/polaris_graph/` confirming rule-13 string appears in formatted prompt for a policy-domain section title.

## Acceptance criteria

1. SECTION_SYSTEM_PROMPT_TEMPLATE contains rule 13 with the exact verbiage above.
2. New test `test_section_prompt_contains_policy_scope_disambiguation_rule` confirming rule 13 string is in formatted prompt for any section title.
3. Existing tests unchanged (prompt template additions are backwards-compatible).
4. Re-run Q5 sweep → manual inspection of Regulatory section → PBO numbers cited WITH "universal single-payer projection" label.
5. Q5-T1-014 audit verdict (if re-run under Tier-1 schema) → VERIFIED (no longer PARTIAL on framing).

## Out of scope (deferred to GH#423 separate PR)

- Duplicate-fact redundancy fix (the 40% same-fact-across-sections issue) — requires parallel→sequential refactor of section calls + cross-section fact-ledger threading. Bigger architectural change. Separate PR.

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
