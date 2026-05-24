# Claude architect audit — I-p2-055 (#857): Source Review page S-audit

## Goal
Fifth (final pre-journey) cred-gated page: /source_review (source-set health, between Intake and
Plan). Live it 401-redirects without a real reviewer JWT. Audited by rendering locally (seeded
session + route-mocked /api/v6/templates fixture). Fixture is visual-audit-only — never shipped.

## What looking-at-it found
This was already the strongest cred-gated page and needed the least: it uses the state-kit
(Loading/Error), the tier-1/2/3 token dots, and — notably — EXEMPLARY honest framing. It explicitly
shows the curated source-set DEFINITION (the T1/T2/T3 domains + per-tier minimums from the
authoritative config) and the adequacy bar, and says plainly that the ACTUAL corpus is retrieved +
adequacy-gated during the run; it does NOT fabricate a retrieved corpus or a "readiness %". That is
the LAW II discipline the whole product should model.

The only real gap was visual consistency: the question card, the three tier cards, and the "how
sources are gathered" explainer were flat `rounded-lg border` with no elevation, out of step with
the brand-tinted `shadow-card` the rest of the cred-gated set now uses. And the error state had no
retry affordance (Codex visual iter-1 P2).

## What changed (1 page file + the S-tier tracker)
- `shadow-card` + `rounded-xl` on the question / tier / "how sources" cards.
- A "Try again" retry on the ErrorState: a reloadKey re-runs the templates fetch; the reset
  (setError/setTemplate null + bump reloadKey) lives in the onRetry handler, not the effect, so it
  stays clean under react-hooks/set-state-in-effect.

## Preserved
The real listTemplates() fetch, the asTemplateId allow-list, the frame manifest, the testid
(source-review-page), and the honest no-fabricated-corpus framing.

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-2 (populated desktop S- / mobile A++ / error A+). Code
  diff APPROVE.

## Honest verification state
LIVE-populated verification on polarisresearch.ca is DEFERRED — the page 401-redirects without the
real reviewer credential. States verified against a route-mocked templates fixture (visual audit
only) + the natural error state.

## Constraints honored
Brand `#c8102e` (Continue + Try-again + nav active); tier dots = tier tokens; tokens only;
logic/testid/honest-framing preserved; no fabricated SHIPPED data; no test relaxation.

canonical-diff-sha256: 8116403775b465126934f8035fd8c7c058fd2a915362d8d0c2e61e037478928a
