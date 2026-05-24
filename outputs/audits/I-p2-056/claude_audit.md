# Claude architect audit — I-p2-056 (#859): Plan review page S-audit

## Goal
First leg of the Plan→Run→Compare journey finale: /plan (cred-gated run-start surface). On mount it
re-runs the FULL intake gate (clinical + PICO classifier) over the immutable question, so direct
navigation is gated identically; "Start research run" is enabled ONLY for an in_scope,
disambiguation-resolved question. Audited by rendering locally (seeded session + route-mocked intake
fixture). Fixture is visual-audit-only — never shipped.

## What looking-at-it found
The page was recent (#754) and already strong: honest framing ("Confirm what POLARIS will research
before the run starts"), token-based states + ErrorState, the in_scope guard (refusal token), the
concurrent-run guard (contradiction token), and the disambiguation modal. Two focused gaps:
- The "Your question" card + the four "What POLARIS will do" step cards were flat (`rounded-lg
  border`, the question card rounded-xl but no shadow) — out of step with the brand-tinted
  `shadow-card` elevation the rest of the cred-gated set now uses.
- All four step icons were brand-red (`text-primary`). The design system reserves the brand accent
  for one meaning-only use per screen (the primary action) — four decorative red process icons +
  the red Start button over-uses it.

## What changed (1 page file + the S-tier tracker)
- `shadow-card` + `rounded-xl` on the question card + the four step cards.
- Step-icon container `text-primary` → `text-muted-foreground`; the brand accent now lives only on
  "Start research run" (and the global nav active state). No logic touched.

## Preserved
The runIntake gate + runDisambiguation + createRun flow, the canStart = inScope &&
disambigResolved gate (enforced both on the disabled button AND re-asserted at call time), the
testids (plan-page, plan-start-run, plan-blocked, plan-concurrent), and the honest framing.

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-1 (ready desktop A / ready mobile A / blocked A /
  no-question A-). Code diff APPROVE. Residual P2 (accept_remaining): no-question empty-state
  vertical rhythm — no execution impact, edge-case state off the demo path.

## Honest verification state
LIVE start-run verification on polarisresearch.ca is DEFERRED — it requires auth + a real backend
run. The intake-gate states (ready / blocked / no-question) verified against a route-mocked fixture
(visual audit only) + the natural no-question state.

## Constraints honored
Brand `#c8102e` (Start run + nav active only); tokens only; gate logic/testids/honest-framing
preserved; no fabricated SHIPPED data; no test relaxation.

canonical-diff-sha256: 7518b871a40c077f02584e3c1c5ce60fe732aa15780f9c524213b2cba6b5af27
