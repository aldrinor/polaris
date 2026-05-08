# Codex Diff Review — I-f13-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f13-002 — Diff visualization
**Brief:** APPROVED iter 1 (all 3 P2 fixes applied: full registry passed to PinTimeseries, deterministic evidence_id per date/metric, string vs numeric delta handling)
**Canonical-diff-sha256:** `691b17e1b6bdcbe24e2198bec67a1c92e899e08fda0a4bfa9ee16cd282121dec`
**LOC:** 226 net (over 200; CHARTER §1 LOC cap exemption)

## CHARTER §1 LOC cap exemption

226 net total. Substance breakdown:
- 16 LOC pin_replay_demo.ts extension (new 2026-03-01 entry).
- 51 LOC PinTimeseries component (sort + map + 2 charts).
- 116 LOC DiffSidePanel component (FIELDS table + format/delta helpers + Sheet shell).
- 22 LOC page integration (button, state, components).
- 41 LOC Playwright spec.

Within issue_breakdown LOC estimate of 180 + slack. The DiffSidePanel substrate (FIELDS table + numeric vs string delta handling) is the bulk; substrate-only, no abstractions.

## Files

```
web/lib/pin_replay_demo.ts                          +12 (3rd snapshot 2026-03-01)
web/app/pin_replay/components/pin_timeseries.tsx    NEW +51 (2 timeseries charts)
web/app/pin_replay/components/diff_side_panel.tsx   NEW +116 (FIELDS table + numeric/string delta)
web/app/pin_replay/page.tsx                         +22  (PinTimeseries + diff button + DiffSidePanel)
web/tests/e2e/pin_replay_diff.spec.ts               NEW +41  (timeseries + diff pane assertions)
```

## What changed

### `pin_replay_demo.ts`
- New `2026-03-01` snapshot between the existing two. Pass rate 79%, 21 verified sentences. Gives the timeseries chart 3 data points per series (Codex iter-1 P2 #1 — full registry, not just 2 endpoints).

### `pin_timeseries.tsx` (NEW)
- Sorts snapshots by date, builds two `TimelinePoint[]` arrays (pass_rate_pct, verified_sentences). Each datum has a deterministic `evidence_id` = `demo-pin-{date}-{metric}` (Codex iter-1 P2 #2 — TimelinePoint requires evidence_id).
- Two `<VegaChart>` instances scoped via `pin-timeseries-pass-rate` and `pin-timeseries-sentence-count` testids.

### `diff_side_panel.tsx` (NEW)
- `FIELDS` array drives the table rows; each row has `kind: "numeric" | "string"`.
- `formatValue` / `computeDelta` handle the two kinds separately:
  - Numeric: B − A (or B*100 − A*100 for pass_rate); rendered with sign prefix.
  - String/categorical (query, verdict): `(unchanged)` or `(changed)` per Codex iter-1 P2 #3.
- Per-field testids: `pin-diff-row-{key}` and `pin-diff-delta-{key}`.

### `page.tsx`
- Imports `PinTimeseries` and `DiffSidePanel`.
- New `[diff_open, set_diff_open]` state.
- New "Show snapshot diff" button with `pin-show-diff` testid.
- Renders timeseries below the snapshot grid + DiffSidePanel.

### `pin_replay_diff.spec.ts`
- Asserts both timeseries charts visible + svg attaches.
- Click `pin-show-diff` → DiffSidePanel opens.
- 3 row testids visible (pass_rate, verified_sentence_count, query).
- pass_rate delta `+13%` (between A=72% and B=85%).
- query delta `unchanged` (string).
- No vega-chart-error.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} lib/**/*.ts tests/e2e/pin_replay_diff.spec.ts`: exit 0.
- `npx prettier --check .` (web/): exit 0.
- Existing `pin_replay.spec.ts` continues to pass (initial state assertions unchanged for snap A/B).

## Risks for Codex Red-Team

1. **TimelinePoint evidence_id contract:** every TimelinePoint requires evidence_id. Deterministic per-date/metric IDs satisfy the contract.
2. **String vs numeric delta:** FIELDS array kinds drive the dispatch; query/verdict report `unchanged`/`changed`, numerics report `+N%` or `+N`.
3. **Existing spec compatibility:** `pin_replay.spec.ts` (I-f13-001) selects `2026-04-30` for date_b — still the last key in sorted PIN_DATES with the new 3-entry registry, so initial assertions remain valid.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap exemption (justified above):** 226 net, 26 LOC over 200; substrate-only.

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
