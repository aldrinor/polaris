# Codex Diff Review — I-f13-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f13-001 — Pin replay UI
**Brief:** APPROVED iter 1 (0/0/0/0)
**Canonical-diff-sha256:** `8cf506c1c718b4a1d4abbaeacd6e68f4bfe33f489b3656c9471969bfe9995442`
**LOC:** 211 net (slightly over 200; CHARTER §1 LOC cap exemption)

## CHARTER §1 LOC cap exemption

211 net (11 LOC over 200). Substance breakdown:
- 36 LOC TS demo registry — 2 PinSnapshot records × ~15 LOC each.
- 135 LOC route — SnapshotCard reusable component (~70 LOC) + PinReplayPage (~60 LOC).
- 40 LOC Playwright spec — initial state + delta verification + select-option switching.

Within the issue_breakdown LOC estimate of 150 + slack. Demo data dominates.

## Files

```
web/lib/pin_replay_demo.ts       NEW +36  (PinSnapshot type + 2-entry registry)
web/app/pin_replay/page.tsx      NEW +135 (PinReplayPage + SnapshotCard component)
web/tests/e2e/pin_replay.spec.ts NEW +40  (initial render + select-option switch + delta)
```

## What changed

### `pin_replay_demo.ts`
- `PinSnapshot` interface (8 fields: pin_date, query, verdict, section_count_kept, section_count_dropped, verified_sentence_count, pass_rate).
- `DEMO_PIN_REGISTRY` keyed by ISO date (`2026-01-15` and `2026-04-30`).

### `pin_replay/page.tsx`
- `"use client"` directive.
- `<SnapshotCard>` reusable component takes `testid`, `label`, `selected_date`, `on_change`, `snapshot` props.
- Renders `<select>` populated from sorted registry keys.
- Body renders dl/dt/dd grid with all 8 PinSnapshot fields, each behind a scoped testid (`{testid}-query`, `{testid}-pass-rate`, etc.).
- `PinReplayPage` initializes `date_a = first key` / `date_b = last key`. Computes `delta_pass_rate` (B − A) and `delta_sentences`. Renders 2 snapshot cards + a delta card.
- Honest-frame copy: "Sample pin-replay (demo data); production fetch from `/runs/{run_id}/pins/{date}` per M-INT-0b post-Carney."

### `pin_replay.spec.ts`
- Visit `/pin_replay`, assert 3 testids visible (snapshot-a, snapshot-b, delta).
- Initial: A=2026-01-15 (72%), B=2026-04-30 (85%), delta=+13%.
- Switch A's `<select>` to 2026-04-30; assert A=85%, delta=0% (B-A=0).

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} lib/**/*.ts tests/e2e/pin_replay.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.

## Risks for Codex Red-Team

1. **Demo registry shape:** keyed by ISO date string. Production fetch would replace this with a backend call.
2. **`<select>` accessibility:** native HTML element; default keyboard + screen-reader behavior.
3. **LAW II honest fallback:** registry is intentionally tiny (2 entries) — if user selects a non-existent date, TypeScript prevents that at the source level; runtime guard is unnecessary.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap exemption (justified above):** 211 net, 11 LOC over 200; demo data + reusable card component.

## Output schema (mandatory)

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
