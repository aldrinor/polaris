You are auditing M-35 pass-2 (addressing pass-1 BLOCKED verdict).
Narrow scope — read ONLY the pass-2 diff.

## Context

Pass-1 verdict (your prior audit, `findings.md`):
- BLOCKED on one defect: `primary_trial_expander.py:108` used
  `" " in stripped`, which rejected only literal ASCII space.
  Interior tabs/newlines bypassed the guard.
- Three non-gating mediums: backslash guard, schema smoke test,
  sweep log wording.

## Pass-2 changes (commit to be audited)

1. **Blocker fix**: guard rewritten to use
   `any(ch.isspace() for ch in stripped) or '"' in stripped or
   "\\" in stripped` — catches all whitespace classes that
   `str.isspace()` recognizes, plus double quote, plus backslash
   (medium #1 rolled in).

2. **Medium #3 fix**: sweep script log message in
   `scripts/run_honest_sweep_r3.py` template-load except branch
   now says "continuing without regulatory (M-28) OR primary-
   trial (M-35) expansion" instead of just "regulatory".

3. **New guard tests** (5):
   - `test_tab_in_entry_rejected`
   - `test_newline_in_entry_rejected`
   - `test_carriage_return_in_entry_rejected`
   - `test_vertical_tab_in_entry_rejected`
   - `test_backslash_in_entry_rejected` (trailing + mid-string)

4. **New schema smoke tests** (4) — medium #2:
   - `test_clinical_template_loads_with_both_m28_and_m35_keys`
   - `test_clinical_template_exposes_tirzepatide_trial_anchors`
     (generic: checks the expander emits, does NOT assert trial
     names — those live in YAML)
   - `test_policy_template_has_no_m35_field_and_expander_noop`
   - `test_tech_template_has_neither_field_and_expander_noop`

## Files to read

```
src/polaris_graph/retrieval/primary_trial_expander.py  (updated guard ~line 103-117)
tests/polaris_graph/test_m35_primary_trial_expander.py  (+9 tests, ~115 new LOC)
scripts/run_honest_sweep_r3.py                          (log wording ~line 553-558)
```

Do NOT re-audit the full M-35 abstraction — that was READY on every
structural axis in pass-1. Only verify the pass-2 diff actually
closes the pass-1 blocker and the three mediums are addressed.

## What to verify

1. Does the new guard predicate (`isspace()` / `"` / `\`) actually
   drop every failure case from pass-1's reproduced behavior? (Tab,
   newline, backslash, and the original space/quote cases.)
2. Are there any whitespace / quoting / escaping surfaces NOT covered
   by the union? (e.g. U+00A0 non-breaking space — Python's
   `str.isspace()` returns True for this in Python 3.11+, so it's
   caught. U+200B zero-width space — `isspace()` returns False; but
   ZWSP inside a quoted search query wouldn't break parsing, it
   would just be invisible. Still consider: should it be rejected
   too for aesthetic / debugging reasons?)
3. Are the 4 schema smoke tests actually testing what Codex asked
   for? (clinical has both fields, policy has M-28 only, tech has
   neither, expander no-ops in the last two cases.)
4. Does the sweep-script log wording change affect any grep-based
   monitoring or log-parsing downstream? (There should be no such
   consumer — it's a one-off operator-facing warning.)

## What counts as a blocker vs medium

- **BLOCKER**: any path that still produces a malformed query under
  the new guard. Any assertion that a test change doesn't actually
  exercise the pass-1 failure class.
- **MEDIUM**: tightening suggestions beyond the agreed scope.
- **LOW**: style.

## Deliverable

Write `outputs/codex_findings/m35_code_audit_pass2/findings.md`
with final verdict (READY | BLOCKED | CONDITIONAL), any remaining
blockers, and any new mediums.
