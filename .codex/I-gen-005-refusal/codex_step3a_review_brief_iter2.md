# Codex Step 3a iter 2 — atom_NNN additive to [ev_XXX]

## §8.3.1 cap (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL findings. No drip-feeding. Same quality bar.
- "Don't pick bone from egg" — reserve P0/P1 for execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0/P1 AND zero continuing P0/P1.
```

## Iter 1 verdict → iter 2 fix

REQUEST_CHANGES with 1 P1 + 2 P2 + 1 P3.

P1 (caught critical bug): atom_NNN told to REPLACE [ev_XXX] in the
prompt — but strict_verify requires [ev_XXX] tokens. Compliant model
output would lose factual sentences before validation.

iter-2 fix: atom_NNN is ADDITIVE. Instruction now reads:
> "ATOM-CITATION CONTRACT (additive to [ev_XXX]):
> For factual quantitative claims... cite BOTH the atom_NNN ID
> (in parentheses) AND the existing [ev_XXX] provenance marker.
> atom_NNN is ADDITIVE — it does NOT replace [ev_XXX]."

Worked example updated:
> "Tirzepatide 15 mg reduced HbA1c by -2.30 percentage points
> versus -1.86 with semaglutide (atom_003, atom_004) [ev_001]."

Both citations present. strict_verify sees [ev_001] and accepts.
Future post-hoc validator (Step 3b) sees (atom_003, atom_004) and
validates against catalog.

## Step 3b plan (per your iter-1 advice)

Per your iter-1 P2/P3 + recommendations:
- Separate PR (SAME_PR -> SEPARATE_PR)
- Logging-only initial mode behind a flag
- Persist atom catalog from _call_section so validator sees the SAME
  section-local numbering used in the prompt (no rebuild with global
  numbering)
- Strip atom_\d+ before strict_verify numeric matching to avoid the
  suffix being parsed as an integer

These are all deferred to the Step 3b PR.

## P3 cleanup

The comment header now correctly says "Step 3b not yet wired" to avoid
misleading operators.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

p1_atom_now_additive_to_ev: YES | NO
  if_no: |
    (failure case)

instruction_wording_no_conflict_with_section_system_prompt: YES | NO

example_shows_both_citations: YES | NO

novel_p0: [...]
novel_p1: [...]
continuing_p0: [...]
continuing_p1: [...]
p2: [...]
p3: [...]

approval_to_proceed_to_step_3b_pr: YES | NO
convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Diff at `.codex/I-gen-005-refusal/codex_step3a_diff_iter2.patch`.
