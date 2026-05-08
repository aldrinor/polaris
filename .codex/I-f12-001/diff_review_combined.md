# Codex Diff Review — I-f12-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f12-001 — Two-run picker UI. Brief APPROVE iter 3.
- **Net LOC:** 185.
- **Branch:** `bot/I-f12-001`.

## What changed

1. `web/app/generation/components/two_run_picker.tsx` (NEW, 78 LOC, `"use client"`):
   - `RunListItem` exported type.
   - `TwoRunPicker({ runs, onCompare })` with native `<input type="checkbox">` controls.
   - Local `useState<string[]>` selection. Toggle handler refuses a 3rd check by short-circuiting `prev.length >= 2`.
   - `data-testid="selection-count"` reads "{N} of 2 selected".
   - `data-testid="compare-button"` disabled until `selected.length === 2`.
   - Each row checkbox has `data-testid="run-checkbox-{run_id}"` plus a `<label htmlFor>` linking to it.

2. `web/app/sentence_hover_test/two_run_picker/page.tsx` (NEW, 53 LOC, `"use client"`):
   - 4 STUB_RUNS, supplies `onCompare` callback that updates a `last` state.
   - `data-testid="last-compared-pair"` displays the joined-id string.

3. `web/tests/e2e/two_run_picker.spec.ts` (NEW, 50 LOC, 4 specs):
   - `picks exactly 2 runs and emits compare event` — `.check()` r1 + r2, assert count "2 of 2", click compare, assert pair "r1,r2".
   - `compare button disabled until exactly 2 selected`.
   - `cannot select more than 2` — `.check()` first 2; `.click()` (NOT `.check()`) the 3rd; assert third `not.toBeChecked()` and count still "2 of 2".
   - `unchecking a row removes it from selection`.

## Test results (local chromium)

```
$ npx playwright test --project=chromium tests/e2e/two_run_picker.spec.ts --reporter=line
4 passed (2.4s)
```

## Risks for Codex Red-Team

1. **Client-boundary correctness.** Both component + fixture page are `"use client"`; no server→client function-prop crossing.
2. **Native checkbox semantics.** `<input type="checkbox">` ensures `getByRole("checkbox")` and `.check()`/`.uncheck()` work. The 3rd-selection refusal preserves the unchecked state, which is why spec 3 uses `.click()` then asserts `not.toBeChecked()`.
3. **§9.4 hygiene.** The literal `2` is the explicit business rule; type signature `[string, string]` and `.length === 2` checks pin it. No magic-number tunable.
4. **CHARTER §3 LOC cap.** 185 net (under 200).

## Acceptance criteria — forced enumeration

1. ✅ `web/app/generation/components/two_run_picker.tsx` (`"use client"`) with `TwoRunPicker` rendering native checkbox controls + compare button.
2. ✅ `/sentence_hover_test/two_run_picker` fixture page hosts STUB_RUNS + onCompare callback.
3. ✅ Playwright spec at `web/tests/e2e/two_run_picker.spec.ts` with 4 specs exercising checkbox semantics + exactly-2 rule.
4. ✅ CHARTER §3 LOC cap (185 ≤ 200).

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

## Diff (appended below)
diff --git a/web/app/generation/components/two_run_picker.tsx b/web/app/generation/components/two_run_picker.tsx
new file mode 100644
index 0000000..53ba99c
--- /dev/null
+++ b/web/app/generation/components/two_run_picker.tsx
@@ -0,0 +1,80 @@
+"use client";
+
+import { useState } from "react";
+
+export type RunListItem = {
+  run_id: string;
+  template: string;
+  question: string;
+  finished_at: string;
+};
+
+export function TwoRunPicker({
+  runs,
+  onCompare,
+}: {
+  runs: RunListItem[];
+  onCompare: (ids: [string, string]) => void;
+}) {
+  const [selected, setSelected] = useState<string[]>([]);
+
+  function toggle(run_id: string, want_checked: boolean): void {
+    setSelected((prev) => {
+      if (want_checked) {
+        if (prev.includes(run_id)) return prev;
+        if (prev.length >= 2) return prev;
+        return [...prev, run_id];
+      }
+      return prev.filter((id) => id !== run_id);
+    });
+  }
+
+  const ready = selected.length === 2;
+
+  return (
+    <div className="space-y-4">
+      <p
+        data-testid="selection-count"
+        className="text-muted-foreground text-sm"
+      >
+        {selected.length} of 2 selected
+      </p>
+      <ul className="border-border divide-y divide-border rounded-md border">
+        {runs.map((r) => {
+          const checked = selected.includes(r.run_id);
+          return (
+            <li key={r.run_id} className="flex items-center gap-3 p-3">
+              <input
+                type="checkbox"
+                id={`chk-${r.run_id}`}
+                data-testid={`run-checkbox-${r.run_id}`}
+                checked={checked}
+                onChange={(e) => toggle(r.run_id, e.target.checked)}
+                className="h-4 w-4"
+              />
+              <label htmlFor={`chk-${r.run_id}`} className="flex-1 cursor-pointer">
+                <span className="block font-medium">{r.run_id}</span>
+                <span className="text-muted-foreground block text-xs">
+                  {r.template} — {r.question}
+                </span>
+              </label>
+            </li>
+          );
+        })}
+      </ul>
+      <button
+        type="button"
+        data-testid="compare-button"
+        disabled={!ready}
+        onClick={() => {
+          if (ready) {
+            onCompare([selected[0], selected[1]]);
+          }
+        }}
+        className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground inline-flex items-center rounded-md px-4 py-2 text-sm font-medium disabled:cursor-not-allowed"
+      >
+        Compare
+      </button>
+    </div>
+  );
+}
diff --git a/web/app/sentence_hover_test/two_run_picker/page.tsx b/web/app/sentence_hover_test/two_run_picker/page.tsx
new file mode 100644
index 0000000..16e16c8
--- /dev/null
+++ b/web/app/sentence_hover_test/two_run_picker/page.tsx
@@ -0,0 +1,55 @@
+"use client";
+
+import { useState } from "react";
+
+import {
+  RunListItem,
+  TwoRunPicker,
+} from "@/app/generation/components/two_run_picker";
+
+const STUB_RUNS: RunListItem[] = [
+  {
+    run_id: "r1",
+    template: "clinical_summary",
+    question: "Drug X efficacy?",
+    finished_at: "2026-05-08T00:00:00Z",
+  },
+  {
+    run_id: "r2",
+    template: "regulatory_review",
+    question: "FDA Q1 update?",
+    finished_at: "2026-05-08T01:00:00Z",
+  },
+  {
+    run_id: "r3",
+    template: "clinical_summary",
+    question: "Drug Y safety?",
+    finished_at: "2026-05-08T02:00:00Z",
+  },
+  {
+    run_id: "r4",
+    template: "trade_brief",
+    question: "Tariff B impact?",
+    finished_at: "2026-05-08T03:00:00Z",
+  },
+];
+
+export default function TwoRunPickerFixturePage() {
+  const [last, setLast] = useState<string>("");
+  return (
+    <main className="bg-background text-foreground mx-auto max-w-2xl px-6 py-8">
+      <h1 className="text-2xl font-semibold tracking-tight">
+        Two-run picker fixture (I-f12-001)
+      </h1>
+      <div className="mt-6">
+        <TwoRunPicker runs={STUB_RUNS} onCompare={([a, b]) => setLast(`${a},${b}`)} />
+      </div>
+      <p
+        data-testid="last-compared-pair"
+        className="text-muted-foreground mt-6 text-sm"
+      >
+        {last}
+      </p>
+    </main>
+  );
+}
diff --git a/web/tests/e2e/two_run_picker.spec.ts b/web/tests/e2e/two_run_picker.spec.ts
new file mode 100644
index 0000000..2cf2a1a
--- /dev/null
+++ b/web/tests/e2e/two_run_picker.spec.ts
@@ -0,0 +1,50 @@
+import { expect, test } from "@playwright/test";
+
+const URL = "/sentence_hover_test/two_run_picker";
+
+test("picks exactly 2 runs and emits compare event", async ({ page }) => {
+  await page.goto(URL);
+  await page.getByTestId("run-checkbox-r1").check();
+  await page.getByTestId("run-checkbox-r2").check();
+  await expect(page.getByTestId("selection-count")).toHaveText(
+    "2 of 2 selected",
+  );
+  const compare = page.getByTestId("compare-button");
+  await expect(compare).toBeEnabled();
+  await compare.click();
+  await expect(page.getByTestId("last-compared-pair")).toHaveText("r1,r2");
+});
+
+test("compare button disabled until exactly 2 selected", async ({ page }) => {
+  await page.goto(URL);
+  const compare = page.getByTestId("compare-button");
+  await expect(compare).toBeDisabled();
+  await page.getByTestId("run-checkbox-r1").check();
+  await expect(compare).toBeDisabled();
+  await page.getByTestId("run-checkbox-r2").check();
+  await expect(compare).toBeEnabled();
+});
+
+test("cannot select more than 2", async ({ page }) => {
+  await page.goto(URL);
+  await page.getByTestId("run-checkbox-r1").check();
+  await page.getByTestId("run-checkbox-r2").check();
+  // Use click() not check() — UI refuses the state change so check() would error.
+  await page.getByTestId("run-checkbox-r3").click();
+  await expect(page.getByTestId("run-checkbox-r3")).not.toBeChecked();
+  await expect(page.getByTestId("selection-count")).toHaveText(
+    "2 of 2 selected",
+  );
+});
+
+test("unchecking a row removes it from selection", async ({ page }) => {
+  await page.goto(URL);
+  await page.getByTestId("run-checkbox-r1").check();
+  await expect(page.getByTestId("selection-count")).toHaveText(
+    "1 of 2 selected",
+  );
+  await page.getByTestId("run-checkbox-r1").uncheck();
+  await expect(page.getByTestId("selection-count")).toHaveText(
+    "0 of 2 selected",
+  );
+});
