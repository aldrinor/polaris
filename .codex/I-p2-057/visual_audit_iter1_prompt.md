# Codex VISUAL audit — I-p2-057 (#861) Run progress (live run), A++/S — iter 1 of 5

You have VISION. Audit /runs/[runId] — the live-run progress page (depth visible; Perplexity-style
4-stage progress consuming SSE sub-task events). Rendered LOCALLY with a seeded session + a mocked
EventSource emitting canned SSE events + a route-mocked getRun (visual-audit only — never shipped;
page keeps its real SSE + fetch). Front-load all; don't pick bone from egg; APPROVE iff zero P0/P1.

## What changed (assess-first; component was recent + exemplary)
The run_progress component was already strong — honest stream-loss handling, the "never green-check
an unobserved stage" rule, a Thinking-Toggle (collapse depth), honest "—" elapsed when the run
wasn't watched live. Focused changes:
- The "done" stage chip + the retrieval source ✓ were brand-RED (a red done-checkmark reads as an
  alarm). Moved to `--verified` green — the product's verdict language (done/verified = green).
- Gave the stage cards + the counters + the page's actions card brand-tinted `shadow-card` +
  `rounded-xl` (were flat).
- Reworded the page's "Affordances during this run" (UX jargon) → "While this run works".

## Attached
1. run_live_desktop (scope+retrieval done, generation active, verification pending)
2. run_live_mobile  3. run_done_desktop (all stages done + the follow-up panel)

## Locked / do NOT flag
- Brand #c8102e (New-run + Ask buttons + the active-stage spinner + nav active). Mocked
  EventSource/getRun fixture is visual-audit-only. The "—" elapsed on the DONE state is HONEST (the
  page didn't watch the run live, so it won't show a bogus page-open duration). LIVE end-to-end run
  verification DEFERRED (needs auth + a real backend run). The active spinner is brand (the single
  "what's happening now" focus); done = green is intentional.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { live_desktop: "", live_mobile: "", done_desktop: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier live-run surface (clear staged depth, green done-checks, honest
counters), zero P0/P1.
