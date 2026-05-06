# Codex Diff Review — I-f2-007 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-007 — F2 edge: French / PDF drop
**Branch:** bot/I-f2-007
**Brief:** APPROVED iter 2 (iter1 REQ_CH 1P1 → iter2 APPROVE 0/0/2P2 accept_remaining; both P2 addressed in implementation)
**Canonical-diff-sha256:** `f44fb19702f66de1ec6ca20fb372e2abd4a24acbd01d055cce9ead13cc6108b5`
**LOC:** 141 net insertions / 3 deletions
**Format:** `npx prettier --check` clean. **Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/app/intake/components/intake_form.tsx        EDIT  +17
web/app/intake/components/pdf_drop_banner.tsx    NEW   +67
web/app/intake/page.tsx                          EDIT  +9 / -3
web/tests/e2e/intake_edge.spec.ts                NEW   +51
```

## What changed

### `intake_form.tsx`
- Added module-private `looksNonEnglish(s)` returning true iff ANY of:
  - char in `[éèêëàâäçîïôöùûüÿñ]` (case-insensitive), OR
  - ≥3 matches of `\b(le|la|les|de|des|du|que|qui|et|est|un|une|sont|pour|avec|sans|dans)\b`.
- In `submit()`: AFTER `length < 3` check, BEFORE `setState({kind:"loading"})`, gate on `looksNonEnglish(trimmed)` → set error state with message "POLARIS currently supports English questions only.", return without API call.

### `pdf_drop_banner.tsx` (NEW)
- `"use client"`.
- `useEffect` mounts `dragover` (preventDefault) + `drop` (filter PDFs by type/extension; preventDefault + setShown(true)) listeners on `window`. Cleanup on unmount.
- `setReady(true)` after listeners attached. Exposes `data-testid="pdf-drop-ready"` with `data-ready="1"` for hydration-race guard (Codex iter-2 P2 #2).
- When `shown`, renders banner with `data-testid="pdf-drop-banner"` + dismiss button `data-testid="pdf-drop-dismiss"`.
- NO `useRouter` / NO redirect — Codex iter-1 P1 fix (`/upload` route does not exist yet).

### `page.tsx`
- Imports + mounts `<PdfDropBanner />` inside `<main>` above the IntakeForm.

### `tests/e2e/intake_edge.spec.ts` (NEW)
- **Test 1 (French):** mock /api/intake returning 500 (should-not-be-called). Fill input with French question. Click submit. Assert `intake-error` visible + contains "POLARIS currently supports English". Assert `intakeCalls === 0`.
- **Test 2 (PDF drop):** wait for `pdf-drop-ready` `data-ready === "1"` BEFORE dispatching the synthetic DragEvent (`new DataTransfer(); dt.items.add(File)`). Assert `pdf-drop-banner` visible. Click `pdf-drop-dismiss`; assert banner hidden.

## Iter-2 brief P2 advisories addressed

- **P2 #1 (stale redirect language):** Implementation has zero redirect logic.
- **P2 #2 (hydration-race):** `data-ready="1"` waited on before dispatch.

## Risks for Codex Red-Team

1. **`looksNonEnglish` false positives in clinical English.** "Le Bel" — proper noun "le" might match the stopword regex but only if it's a whitespace-bounded token. Unlikely in actual clinical questions. Brief-confirmed conservatively.

2. **Stopword threshold.** ≥3 matches required. A single English question with one accidental "de" / "le" passes. Three together is a strong French signal.

3. **`window` drag-drop listener scope.** Mounted only inside `/intake` route. Other pages unaffected.

4. **`dragover preventDefault`.** Required for `drop` to fire. Without it, the OS handles drop = open file in tab.

5. **PDF detection.** `file.type === "application/pdf"` for browser-recognized PDFs; `file.name.toLowerCase().endsWith(".pdf")` as fallback for cases where MIME type is empty.

6. **Hydration-race guard.** Test waits for `data-ready="1"` (set inside the `useEffect` after listeners attached) before dispatching the synthetic event. No race.

7. **Synthetic DragEvent in test.** Standard W3C pattern: `new DataTransfer()` + `dt.items.add(file)` + `new DragEvent("drop", {dataTransfer: dt})`. Works in Chromium, Firefox, WebKit.

8. **No `useRouter` / no redirect.** Reflects the missing `/upload` route. Future Issue replaces banner CTA with `<Link href="/upload">`.

9. **Dismiss button idempotency.** `setShown(false)` after first click hides; subsequent clicks no-op.

10. **No new package.json dep.**

11. **CHARTER §1 LOC cap.** 141 net insertions; well under 200.

12. **`<output>` vs `<div>` for ready signal.** Used `<span data-testid="pdf-drop-ready">` with `sr-only` class — invisible to users; readable to Playwright. Acceptable.

13. **`data-testid="pdf-drop-ready"` lifecycle.** Visible only when `!shown`. Once banner shows, the ready span unmounts. This is fine for the test pattern (read-once hydration-readiness signal).

## Out of scope (do NOT regress on these)

- /upload route → follow-up Issue.
- Sophisticated language detection → follow-up Issue.
- Backend `non_english` status code → follow-up if needed.
- Evaluator walkthrough → I-f2-008.

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


## Diff to review

```diff
diff --git a/web/app/intake/components/intake_form.tsx b/web/app/intake/components/intake_form.tsx
index 0682036..cfb7b4c 100644
--- a/web/app/intake/components/intake_form.tsx
+++ b/web/app/intake/components/intake_form.tsx
@@ -29,6 +29,16 @@ const SAMPLE_QUESTIONS = [
   "Is physical therapy effective for chronic back pain in adults?",
 ];
 
+const FRENCH_STOPWORD_RE =
+  /\b(le|la|les|de|des|du|que|qui|et|est|un|une|sont|pour|avec|sans|dans)\b/gi;
+const FRENCH_ACCENTED_RE = /[éèêëàâäçîïôöùûüÿñ]/i;
+
+function looksNonEnglish(s: string): boolean {
+  if (FRENCH_ACCENTED_RE.test(s)) return true;
+  const matches = s.match(FRENCH_STOPWORD_RE);
+  return (matches?.length ?? 0) >= 3;
+}
+
 export function IntakeForm() {
   const [question, setQuestion] = useState("");
   const [state, setState] = useState<IntakeState>({ kind: "idle" });
@@ -51,6 +61,13 @@ export function IntakeForm() {
       });
       return;
     }
+    if (looksNonEnglish(trimmed)) {
+      setState({
+        kind: "error",
+        message: "POLARIS currently supports English questions only.",
+      });
+      return;
+    }
 
     setState({ kind: "loading" });
     try {
diff --git a/web/app/intake/components/pdf_drop_banner.tsx b/web/app/intake/components/pdf_drop_banner.tsx
new file mode 100644
index 0000000..ce192fc
--- /dev/null
+++ b/web/app/intake/components/pdf_drop_banner.tsx
@@ -0,0 +1,67 @@
+"use client";
+
+import { useEffect, useState } from "react";
+
+function isPdf(file: File): boolean {
+  return (
+    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
+  );
+}
+
+export function PdfDropBanner() {
+  const [shown, setShown] = useState(false);
+  const [ready, setReady] = useState(false);
+
+  useEffect(() => {
+    const handleDragOver = (e: DragEvent) => e.preventDefault();
+    const handleDrop = (e: DragEvent) => {
+      const files = e.dataTransfer?.files;
+      if (!files || files.length === 0) return;
+      let pdfFound = false;
+      for (let i = 0; i < files.length; i++) {
+        const f = files.item(i);
+        if (f && isPdf(f)) {
+          pdfFound = true;
+          break;
+        }
+      }
+      if (pdfFound) {
+        e.preventDefault();
+        setShown(true);
+      }
+    };
+    window.addEventListener("dragover", handleDragOver);
+    window.addEventListener("drop", handleDrop);
+    setReady(true);
+    return () => {
+      window.removeEventListener("dragover", handleDragOver);
+      window.removeEventListener("drop", handleDrop);
+    };
+  }, []);
+
+  if (!shown)
+    return (
+      <span
+        data-testid="pdf-drop-ready"
+        data-ready={ready ? "1" : "0"}
+        className="sr-only"
+      />
+    );
+
+  return (
+    <div
+      data-testid="pdf-drop-banner"
+      className="flex items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-200"
+    >
+      <span>PDFs go through the upload flow (coming soon).</span>
+      <button
+        type="button"
+        data-testid="pdf-drop-dismiss"
+        onClick={() => setShown(false)}
+        className="text-xs font-medium underline-offset-2 hover:underline"
+      >
+        Dismiss
+      </button>
+    </div>
+  );
+}
diff --git a/web/app/intake/page.tsx b/web/app/intake/page.tsx
index 1c714fb..f475adb 100644
--- a/web/app/intake/page.tsx
+++ b/web/app/intake/page.tsx
@@ -3,6 +3,7 @@ import Link from "next/link";
 import { Button } from "@/components/ui/button";
 
 import { IntakeForm } from "./components/intake_form";
+import { PdfDropBanner } from "./components/pdf_drop_banner";
 
 export const metadata = {
   title: "Intake — POLARIS Canada",
@@ -44,12 +45,14 @@ export default function IntakePage() {
           <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
             Type a clinical research question and POLARIS will run it through
             the BPEI front half: refusal-bait detection, scope classification
-            (efficacy / safety / diagnosis / prognosis), and PICO axis
-            ambiguity detection. No retrieval is run yet — this is the gate
-            that decides if a question is researchable as written.
+            (efficacy / safety / diagnosis / prognosis), and PICO axis ambiguity
+            detection. No retrieval is run yet — this is the gate that decides
+            if a question is researchable as written.
           </p>
         </section>
 
+        <PdfDropBanner />
+
         <IntakeForm />
       </main>
 
diff --git a/web/tests/e2e/intake_edge.spec.ts b/web/tests/e2e/intake_edge.spec.ts
new file mode 100644
index 0000000..0240bc4
--- /dev/null
+++ b/web/tests/e2e/intake_edge.spec.ts
@@ -0,0 +1,51 @@
+import { expect, test } from "@playwright/test";
+
+test("French question → English-only message; intake API not called", async ({
+  page,
+}) => {
+  let intakeCalls = 0;
+  await page.route("**/api/intake", async (route) => {
+    intakeCalls++;
+    await route.fulfill({ status: 500, body: "should-not-be-called" });
+  });
+
+  await page.goto("/intake");
+  await page
+    .getByTestId("intake-question-input")
+    .fill(
+      "Quels sont les effets secondaires de la metformine chez les adultes?",
+    );
+  await page.getByTestId("intake-submit").click();
+
+  await expect(page.getByTestId("intake-error")).toBeVisible();
+  await expect(page.getByTestId("intake-error")).toContainText(
+    "POLARIS currently supports English",
+  );
+  expect(intakeCalls).toBe(0);
+});
+
+test("PDF drop on /intake → banner appears, then dismisses", async ({
+  page,
+}) => {
+  await page.goto("/intake");
+  await expect(page.getByTestId("pdf-drop-ready")).toHaveAttribute(
+    "data-ready",
+    "1",
+  );
+
+  await page.evaluate(() => {
+    const dt = new DataTransfer();
+    dt.items.add(new File([], "test.pdf", { type: "application/pdf" }));
+    window.dispatchEvent(
+      new DragEvent("drop", {
+        dataTransfer: dt,
+        bubbles: true,
+        cancelable: true,
+      }),
+    );
+  });
+
+  await expect(page.getByTestId("pdf-drop-banner")).toBeVisible();
+  await page.getByTestId("pdf-drop-dismiss").click();
+  await expect(page.getByTestId("pdf-drop-banner")).toBeHidden();
+});

```
