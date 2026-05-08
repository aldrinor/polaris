# Codex Brief Review — I-f13-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Issue:** I-f13-001 — Pin replay UI. Scope: "same query rerun on different dates". Acceptance: "Playwright switch dates". LOC estimate 150.
- **What's needed:** a frontend route that lets the user pick two pinned snapshots of the SAME query and view them side-by-side (or stacked) so they can see how results changed over time. The "pin" concept is captured in the M-D11 / M-INT-0b substrate (pin capture on every sweep run); the UI is what's missing.
- **Existing substrate:** the polaris repo already pins runs (per M-INT-0b). What's missing is the UI to surface them. Per the "different dates" acceptance, the demo can use 2 hand-authored pinned snapshots (date-A vs date-B) demonstrating the side-by-side flow.
- **Honest framing per CLAUDE.md §9.4:** the live pin-fetch from a `/runs/{run_id}/pins/{date}` endpoint is post-Carney. THIS Issue ships the frontend pin-replay UI substrate with demo data; production wiring tracks separately.

## Plan

### Frontend

1. New `web/lib/pin_replay_demo.ts` (NEW):
   - Export `PinSnapshot` interface: `{ pin_date: string (ISO yyyy-mm-dd); query: string; verdict: "success"|"abort_no_verified_sections"; section_count_kept: number; section_count_dropped: number; verified_sentence_count: number; pass_rate: number }`.
   - Export `DEMO_PIN_REGISTRY: Record<string, PinSnapshot>` keyed by ISO date (e.g., `"2026-01-15"` and `"2026-04-30"` for the same query showing how results evolved).

2. New route `web/app/pin_replay/page.tsx` (NEW client component):
   - Renders a `<select>` (or two side-by-side selects) populated from `DEMO_PIN_REGISTRY` keys (the available pin dates).
   - State: `[date_a, set_date_a]`, `[date_b, set_date_b]` initialized to the two registry keys.
   - For each selection, render a card with `data-testid="pin-snapshot-a"` / `pin-snapshot-b` showing the snapshot's fields (date, verdict, kept/dropped counts, pass rate).
   - Below the two cards, render a small `<div data-testid="pin-replay-delta">` showing the deltas (e.g., "Pass rate: +12.5%", "Verified sentences: +5").
   - Honest-frame copy: "Sample pin-replay (demo data); production fetch from `/runs/{run_id}/pins/{date}` per M-INT-0b post-Carney."

### Playwright

3. `web/tests/e2e/pin_replay.spec.ts` (NEW):
   - Visit `/pin_replay`.
   - Assert `pin-snapshot-a` and `pin-snapshot-b` are visible with expected initial date strings.
   - Switch `date_a` via `<select>`: change to a different available date in `DEMO_PIN_REGISTRY`.
   - Assert `pin-snapshot-a` updates to show the new date's verdict / sentence counts.
   - Assert `pin-replay-delta` recomputes (text changes between selection events).

## Risks for Codex Red-Team

1. **Demo registry shape:** keep PinSnapshot lean (≤8 fields) so the demo data + delta computation is verifiable inline.
2. **`<select>` accessibility:** native `<select>` is the simplest; gives keyboard + screen-reader support out of the box. No custom dropdown needed.
3. **Honest framing:** route copy + JSDoc state demo-data-only, production wires post-Carney.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~50 LOC types/registry + ~80 LOC route + ~30 LOC spec = ~160. Under 200. Within issue_breakdown LOC estimate of 150.

## Acceptance criteria

1. New `web/lib/pin_replay_demo.ts` exports `PinSnapshot` type + `DEMO_PIN_REGISTRY` keyed by date.
2. `/pin_replay` route renders 2 snapshot cards with distinct testids + 1 delta panel.
3. Date `<select>` switching causes the selected snapshot card to update.
4. Playwright spec asserts initial render + at least one date-switch + delta-recompute.
5. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-5.

**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
