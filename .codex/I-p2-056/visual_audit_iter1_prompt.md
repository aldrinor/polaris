# Codex VISUAL audit — I-p2-056 (#859) Plan review (run-start), A++/S — iter 1 of 5

You have VISION. Audit /plan — the run-start surface (intake → plan → run). On mount it re-runs the
FULL intake gate (clinical + PICO classifier) over the immutable question; "Start research run" is
enabled ONLY for an in_scope, disambiguation-resolved question. Rendered LOCALLY with a seeded
session + Playwright route-mocked intake fixture (visual-audit only — never shipped; page keeps
fetching real data). Front-load all; don't pick bone from egg; APPROVE iff zero P0/P1.

## What changed (assess-first; page was recent + strong)
The page already had honest framing + token states + the scope/concurrent guards. Focused changes:
- Gave the "Your question" card + the four "What POLARIS will do" step cards brand-tinted
  `shadow-card` + `rounded-xl` (the steps were flat rounded-lg) for parity with the cred-gated set.
- Toned the four step icons from brand-red (`text-primary`) to muted — the design system reserves
  brand for the single primary action (Start research run), not 4 decorative process icons.

## Attached
1. plan_ready_desktop  2. plan_ready_mobile  3. plan_blocked_desktop  4. plan_noquestion_desktop

## Locked / do NOT flag
- Brand #c8102e (Start research run button only). Fixture visual-audit-only. The blocked state
  (out_of_scope) correctly DISABLES Start + shows the refusal-token guard — that's the gate working,
  not a defect. LIVE start-run verification DEFERRED (needs auth + a backend run).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { ready_desktop: "", ready_mobile: "", blocked: "", no_question: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier run-start surface (clear plan, working scope guard, one accent),
zero P0/P1.
