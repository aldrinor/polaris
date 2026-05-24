# Codex VISUAL audit — I-p2-054 (#855) Compare (run-vs-run), A++/S bar — iter 1 of 5

You have VISION. Audit /compare (cred-gated run-vs-run diff). It fetches GET /runs?status=completed
+ GET /runs/{l}/compare/{r}; rendered LOCALLY with a seeded session + Playwright route-mocked
FIXTURE (visual-audit only — never shipped; page keeps fetching real data). Front-load all; don't
pick bone from egg; APPROVE iff zero P0/P1.

## What changed (assess-first; page was decent but had real gaps)
- Added a LoadingState (was blank while loading) + a designed EmptyState (was a bare <p> link).
- FIXED a confusing color: the run-property flags rendered a brand-RED ✓ for pass (red checkmark
  reads as alarm). Now: --verified green Check for pass, muted X for a mismatch (a mismatch is
  informational, not an error — never the destructive token).
- Tokenized the run-picker selects (FIELD_CLASS, matches the rest of the product).
- Wrapped the picker, headline+flags, evidence, frame-coverage, and contradictions in Cards
  (brand-tinted elevation) for design-system consistency; headline "% shared evidence" as a stat;
  tabular-nums on counts.

## Attached
1. cmp_result_desktop  2. cmp_result_mobile  3. cmp_picker_desktop  4. cmp_empty_desktop

## Locked / do NOT flag
- Brand #c8102e (Compare button + nav active only). Fixture visual-audit-only. LIVE-populated
  verification DEFERRED (real JWT needed; 401-redirects). Evidence-id chips (ev-XXXX) + frame names
  are real ReportComparison fields. This is run-vs-run (NOT POLARIS-vs-external — that's Benchmark).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { result_desktop: "", result_mobile: "", picker: "", empty: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier run-diff (clear flags, readable evidence columns, clean states),
zero P0/P1.
