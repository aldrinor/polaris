# Claude architect audit — I-p2-054 (#855): Compare page S-audit

## Goal
Fourth cred-gated page (build-order step 5): /compare (run-vs-run diff). Live it 401-redirects
without a real reviewer JWT. Audited by rendering locally (seeded session + route-mocked runs-list
and /runs/{l}/compare/{r} fixture) to SEE the picker, result, empty, and loading states. Fixture is
visual-audit-only — never shipped.

## What looking-at-it found
The page was in better shape than the other cred-gated pages (it already used ErrorState + Button),
but had real S-bar gaps:
- No LoadingState (blank while the runs list loaded) and a bare <p> link for the empty state.
- A genuinely confusing colour: the run-property flags ("Same template", "Pipeline status match",
  …) rendered a brand-RED ✓ for a pass. A red checkmark reads as an alarm in this product's
  language. Worse, two runs differing on template/question is informational — not an error — so a
  ✗ should be neutral, not red either.
- Raw <select> styling (not the tokenized field style used elsewhere).
- And the P1 Codex caught on the render: when two runs share a template + question (a very common
  compare case — e.g. re-running the same question), the option labels were visually identical
  (template · question · id, with the id truncated off the end of the select), and the result
  never showed WHICH two runs were compared.

## What changed (1 page file + the S-tier tracker doc)
- LoadingState + a designed EmptyState (GitCompareArrows icon + "Start a run" action).
- Flag: --verified green Check for a pass, muted X for a mismatch (never the destructive token).
- Tokenized RunPicker select (FIELD_CLASS); Card-elevated picker / headline+flags / evidence /
  frame-coverage / contradictions; "% shared evidence" headline stat (tabular-nums).
- optionLabel leads with the unique run id + completion date (shortDate, "en-CA") so runs sharing
  a template/question stay distinguishable; ComparisonView header shows "left_run_id ↔
  right_run_id"; the mobile stat stacks.

## Honest framing (§-1.1 mindfulness)
This is a structural run-vs-run diff (shared evidence IDs, frame overlap, contradiction counts,
boolean run properties) — NOT a clinical-claim quality comparison and it does not declare one run
"better". The % and flags are real ReportComparison fields. No fabricated SHIPPED data.

## Preserved
The state machine + the distinct-runs gate + onCompare + compareErrorMessage; testids
(compare-page, compare-left, compare-right, comparison-result); the real listCompletedRuns(50) +
compareRuns(left,right) fetches.

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-2 (result desktop A / mobile A / picker A / empty A).
  Code diff APPROVE.

## Honest verification state
LIVE-populated verification on polarisresearch.ca is DEFERRED — the page 401-redirects without the
real reviewer credential. States verified against a route-mocked fixture (visual audit only) + the
natural empty/loading states.

## Constraints honored
Brand `#c8102e` (Compare button + nav active only); tokens only; logic/testids preserved; no
fabricated SHIPPED data; no test relaxation.

canonical-diff-sha256: a21660b2544b18710e621289b6ed66451b5b3ff298982a1b3e0275260eefa4a5
