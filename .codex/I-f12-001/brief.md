# Codex Brief Review — I-f12-001 (ITER 3 of 5)

## Iter 3 changes per Codex iter 2

- **P1 (Playwright semantics for rejected third selection):** spec 3 (`cannot select more than 2`) uses `.check()` for the first two boxes, then `.click()` for the third (since `.check()` would error when the UI refuses the change). After the third `.click()`, assert the third checkbox `not.toBeChecked()` and `selection-count` still reads "2 of 2 selected".

## Iter 2 changes per Codex iter 1

- **P1 (client boundary):** `two_run_picker.tsx` uses `"use client"` directive (parallels `generation_runner.tsx`). The fixture page is also a `"use client"` page (parallels `web/app/sentence_hover_test/follow_up_append/page.tsx`). The `onCompare` callback is supplied inside the client page, not a server-page boundary.
- **P1 (checkbox semantics):** each row uses `<input type="checkbox">` (real checkbox element) wrapped in a `<label>`. Tests assert `getByRole("checkbox", { name: ... }).check()`. The exactly-2 rule is enforced by intercepting the change handler to refuse a 3rd check. Compare button is `<button data-testid="compare-button">`.
- **P2 (compare backend exists):** acknowledged. `src/polaris_v6/api/compare.py` already exposes `GET /runs/{left}/compare/{right}`. This issue ships UI for run-pair selection only; the compare result rendering is I-f12-002.
- **P2 (`getCompletedRuns`):** dropped from this brief. Run-list data is supplied via the page-level `STUB_RUNS` constant in the fixture page. The real run-list endpoint is post-MVP (I-f12-003+).

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f12-001 — Two-run picker UI. Pick any 2 completed runs. Acceptance: Playwright pick. LOC estimate 110.
- **Substrate today:** `src/polaris_v6/api/compare.py` already exposes a `GET /runs/{left}/compare/{right}` endpoint; I-f12-001 covers ONLY the run-pair selection UI. Result rendering + run-list endpoint are downstream.
- **Honest framing per CLAUDE.md §9.4:** ship a deterministic UI substrate that renders a list of completed-run rows with native `<input type="checkbox">` controls enforcing exactly-2 selection, and a Compare button enabled only when exactly 2 are selected. Run-list data wired via a `runs` prop. Real backend endpoint is post-MVP.

## Plan

### `web/app/generation/components/two_run_picker.tsx` (NEW, ~75 LOC)

```tsx
"use client";
import { useState } from "react";

export type RunListItem = {
  run_id: string;
  template: string;
  question: string;
  finished_at: string;
};

export function TwoRunPicker({
  runs,
  onCompare,
}: {
  runs: RunListItem[];
  onCompare: (ids: [string, string]) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  // ... onChange handler refuses a 3rd check if 2 already selected.
  // Selection-count text: <p data-testid="selection-count">{N} of 2 selected</p>.
  // Compare button disabled until selected.length === 2; onClick passes [a, b].
}
```

### `web/app/sentence_hover_test/two_run_picker/page.tsx` (NEW, ~30 LOC)

```tsx
"use client";
import { useState } from "react";
import { TwoRunPicker, RunListItem } from "@/app/generation/components/two_run_picker";

const STUB_RUNS: RunListItem[] = [
  { run_id: "r1", template: "clinical_summary", question: "Drug X efficacy?", finished_at: "..." },
  { run_id: "r2", template: "regulatory_review", question: "FDA Q1?", finished_at: "..." },
  { run_id: "r3", template: "clinical_summary", question: "Drug Y safety?", finished_at: "..." },
  { run_id: "r4", template: "trade_brief", question: "Tariff B?", finished_at: "..." },
];

export default function Page() {
  const [last, setLast] = useState<string>("");
  return (
    <main className="...">
      <TwoRunPicker runs={STUB_RUNS} onCompare={([a, b]) => setLast(`${a},${b}`)} />
      <p data-testid="last-compared-pair">{last}</p>
    </main>
  );
}
```

### Tests `web/tests/e2e/two_run_picker.spec.ts` (NEW, ~35 LOC, 4 specs)

1. `picks exactly 2 runs and emits compare event` — `getByRole("checkbox", { name: /r1/i }).check()`, `getByRole("checkbox", { name: /r2/i }).check()`, assert `selection-count` reads "2 of 2 selected", click `compare-button`, assert `last-compared-pair` reads `r1,r2`.
2. `compare button disabled until exactly 2 selected` — initially disabled; after 1 check still disabled; after 2 enabled.
3. `cannot select more than 2` — `.check()` first 2; for the third use `.click()` (NOT `.check()` since the UI refuses the state change), then assert third checkbox is `not.toBeChecked()` and `selection-count` still reads "2 of 2 selected".
4. `unchecking a row removes it from selection` — check then uncheck same row; assert count drops back to 0.

## Risks for Codex Red-Team

1. **Client boundary correctness.** Component + fixture page both `"use client"`. No server→client function-prop crossing.
2. **Native `<input type="checkbox">` matches `getByRole("checkbox")`** — Playwright accessibility-tree query.
3. **§9.4 hygiene.** No magic numbers — the 2-cap is a literal in the type signature `[string, string]` and selection.length === 2 check (explicit business rule).
4. **CHARTER §3 LOC cap.** ~140 LOC net (75+30+35). Under 200.

## Acceptance criteria

1. New `web/app/generation/components/two_run_picker.tsx` (`"use client"`) with `TwoRunPicker` rendering native checkbox controls + compare button.
2. Standalone fixture page at `/sentence_hover_test/two_run_picker` (`"use client"`) hosting STUB_RUNS + onCompare callback.
3. Playwright spec at `web/tests/e2e/two_run_picker.spec.ts` with 4 specs exercising checkbox semantics + exactly-2 rule.
4. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-4.
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
