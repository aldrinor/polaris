# Codex Diff Review — I-f2-005 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-005 — F2 functional test BPEI end-to-end
**Branch:** bot/I-f2-005
**Brief:** APPROVED iter 2 (iter1 REQ_CH 1P1 → iter2 APPROVE 0/0/1P2 accept_remaining; P2 addressed in implementation)
**Canonical-diff-sha256:** `694fabdda24b738ba88532532bff95a98e187c9b354d4db422b4e667f6387003`
**LOC:** 155 net insertions / 23 deletions (well under CHARTER §1 200-cap)
**Type-check:** `npx tsc --noEmit` clean.
**Format:** `npx prettier --check` clean.

## Files

```
web/lib/api.ts                                                       EDIT  +35 / -0
web/app/intake/components/disambiguation_modal.tsx                   EDIT  +1 / -5
web/app/(test_harness)/disambiguation_modal_preview/_client.tsx      EDIT  +2 / -4
web/app/intake/components/intake_form.tsx                            EDIT  +37 / -0
web/tests/e2e/intake_disambiguation.spec.ts                          NEW   +84
```

## What changed

### `web/lib/api.ts`
- `IntakeScopeDecision` gains optional `needs_disambiguation?: boolean` + `candidate_snippets?: {text, embedding}[]`.
- New exports: `DisambiguationCluster`, `DisambiguationResponse`, `runDisambiguation(candidates) -> DisambiguationResponse`.
- `runDisambiguation` POSTs `JSON.stringify({ candidates })` (object wrapper, NOT bare array — Codex iter-1 P1 fix).

### `web/app/intake/components/disambiguation_modal.tsx`
- 2-line refactor: drop local `DisambiguationCluster` type export; `import type { DisambiguationCluster } from "@/lib/api"`.

### `web/app/(test_harness)/disambiguation_modal_preview/_client.tsx`
- Import path swap: `DisambiguationCluster` from `@/lib/api` instead of the modal file.

### `web/app/intake/components/intake_form.tsx`
- New state: `disambigClusters`, `disambigOpen`, `pickedClusterLabel`.
- After `runIntake()` success: if `decision.needs_disambiguation && decision.candidate_snippets?.length > 0`, fire `runDisambiguation(...)`. Open modal only when `is_ambiguous=true && clusters.length > 1` (Codex iter-2 P2 fix).
- Mounts `<DisambiguationModal>` + `<output data-testid="disambig-picked-label">` for Playwright assertion.

### `web/tests/e2e/intake_disambiguation.spec.ts`
- Mocks /api/intake (returns `needs_disambiguation=true`, 3 candidate snippets).
- Mocks /api/disambiguation: asserts `body.candidates.length === 3` (request shape regression guard); 100ms realistic delay; returns 3 BPEI clusters.
- Test flow: type "BPEI" → click submit → wait for `disambiguation-cluster-0` → measure latency `< 500ms` → assert `toHaveCount(3)` → click cluster_id=1 → assert `disambig-picked-label === "institute"` → assert modal hidden.

## Iter-2 brief P2 advisory addressed

- **Modal opens only when `is_ambiguous && clusters.length > 1`** (intake_form.tsx:68 `if (dis.is_ambiguous && dis.clusters.length > 1)`). Empty/unambiguous responses do not surface a modal.

## Risks for Codex Red-Team

1. **Trigger-condition design (Option A locked).** Backend writer for `needs_disambiguation` + `candidate_snippets` is `I-f2-005a` follow-up Issue — explicitly named; not a P0/P1 blocker for THIS PR.

2. **Request body shape.** `JSON.stringify({ candidates })` matches `DisambiguationRequest.candidates`. Test asserts `body.candidates.length === 3`. Bare-array regression cannot pass.

3. **Origin-safe globs.** `**/api/intake` and `**/api/disambiguation` cover both `BACKEND_URL=http://127.0.0.1:8000` and Next baseURL `:3738`.

4. **Realistic mock latency.** 100ms `setTimeout` before fulfill makes `<500ms` assertion non-vacuous.

5. **Toothless-pattern guard.** Test asserts `disambig-picked-label === "institute"` (post-pick state in parent), not just `last-picked` text.

6. **Modal trigger triple-guard.** `needs_disambiguation` + `is_ambiguous` + `clusters.length > 1`. Three guards prevent empty-modal regression.

7. **`DisambiguationCluster` type ownership move.** Now in `web/lib/api.ts`. Modal + harness import. Type contract identical.

8. **`<output>` element with `sr-only` class.** Hidden visually; readable to screen readers AND Playwright. Acceptable accessibility pattern.

9. **No new package.json dep.**

10. **CHARTER §1 LOC cap.** 155 net additions, well under 200. Prettier already applied.

11. **Hermeticity.** All 8 tests in `web/tests/e2e/` use `page.route()` mocks. No real backend hit. Test runs against `next start`.

12. **Async ordering.** `t_submit = Date.now()` BEFORE click; `t_modal = Date.now()` AFTER `expect(...).toBeVisible()` resolves. Latency window slightly pessimistic (includes Playwright's wait-for-visible polling) but bounded by `<500ms`.

13. **Mock embeddings format.** `[1,0]/[0,1]/[-1,0]` — 2-D placeholder. Real backend never sees them in this test.

## Out of scope (do NOT regress on these)

- Backend writer for `needs_disambiguation` flag → I-f2-005a.
- BPEI 3-cluster real-LLM smoke → I-f2-006/007/008.
- Latency budget under real load → I-f2-008.

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
diff --git a/web/app/(test_harness)/disambiguation_modal_preview/_client.tsx b/web/app/(test_harness)/disambiguation_modal_preview/_client.tsx
index 28ba523..af42b8d 100644
--- a/web/app/(test_harness)/disambiguation_modal_preview/_client.tsx
+++ b/web/app/(test_harness)/disambiguation_modal_preview/_client.tsx
@@ -2,10 +2,8 @@
 
 import { useState } from "react";
 
-import {
-  DisambiguationModal,
-  type DisambiguationCluster,
-} from "@/app/intake/components/disambiguation_modal";
+import { DisambiguationModal } from "@/app/intake/components/disambiguation_modal";
+import type { DisambiguationCluster } from "@/lib/api";
 
 const FIXTURE_CLUSTERS: DisambiguationCluster[] =
   "syndrome,institute,chemical,company,course".split(",").map((label, i) => ({
diff --git a/web/app/intake/components/disambiguation_modal.tsx b/web/app/intake/components/disambiguation_modal.tsx
index d0f0955..c29c5c5 100644
--- a/web/app/intake/components/disambiguation_modal.tsx
+++ b/web/app/intake/components/disambiguation_modal.tsx
@@ -4,15 +4,10 @@ import { useEffect, useRef } from "react";
 import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
 
 import { Button } from "@/components/ui/button";
+import type { DisambiguationCluster } from "@/lib/api";
 
 const MAX_SAMPLE_LEN = 80;
 
-export type DisambiguationCluster = {
-  cluster_id: number;
-  label: string;
-  sample_snippets: string[];
-};
-
 export type DisambiguationModalProps = {
   open: boolean;
   clusters: DisambiguationCluster[];
diff --git a/web/app/intake/components/intake_form.tsx b/web/app/intake/components/intake_form.tsx
index 12de2f9..0682036 100644
--- a/web/app/intake/components/intake_form.tsx
+++ b/web/app/intake/components/intake_form.tsx
@@ -7,11 +7,14 @@ import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
 import { Input } from "@/components/ui/input";
 import {
   IntakeBadRequestError,
+  runDisambiguation,
   runIntake,
+  type DisambiguationCluster,
   type IntakeScopeDecision,
 } from "@/lib/api";
 
 import { AmbiguityModal } from "./ambiguity_modal";
+import { DisambiguationModal } from "./disambiguation_modal";
 import { ScopeDecisionView } from "./scope_decision_view";
 
 type IntakeState =
@@ -30,6 +33,13 @@ export function IntakeForm() {
   const [question, setQuestion] = useState("");
   const [state, setState] = useState<IntakeState>({ kind: "idle" });
   const [modalOpen, setModalOpen] = useState(false);
+  const [disambigClusters, setDisambigClusters] = useState<
+    DisambiguationCluster[]
+  >([]);
+  const [disambigOpen, setDisambigOpen] = useState(false);
+  const [pickedClusterLabel, setPickedClusterLabel] = useState<string | null>(
+    null,
+  );
 
   async function submit(e: React.FormEvent<HTMLFormElement>) {
     e.preventDefault();
@@ -49,6 +59,17 @@ export function IntakeForm() {
       if (result.decision.status === "ambiguous_needs_clarification") {
         setModalOpen(true);
       }
+      if (
+        result.decision.needs_disambiguation &&
+        result.decision.candidate_snippets &&
+        result.decision.candidate_snippets.length > 0
+      ) {
+        const dis = await runDisambiguation(result.decision.candidate_snippets);
+        if (dis.is_ambiguous && dis.clusters.length > 1) {
+          setDisambigClusters(dis.clusters);
+          setDisambigOpen(true);
+        }
+      }
     } catch (err) {
       if (err instanceof IntakeBadRequestError) {
         setState({ kind: "error", message: err.message });
@@ -90,9 +111,9 @@ export function IntakeForm() {
               autoComplete="off"
             />
             <p className="text-muted-foreground text-xs">
-              POLARIS only researches clinical evidence questions
-              (efficacy, safety, diagnosis, prognosis). Other domains will be
-              marked out of scope.
+              POLARIS only researches clinical evidence questions (efficacy,
+              safety, diagnosis, prognosis). Other domains will be marked out of
+              scope.
             </p>
 
             <div className="flex flex-wrap items-center gap-2">
@@ -104,9 +125,7 @@ export function IntakeForm() {
               >
                 {state.kind === "loading" ? "Checking…" : "Check scope"}
               </Button>
-              <span className="text-muted-foreground text-xs">
-                or try:
-              </span>
+              <span className="text-muted-foreground text-xs">or try:</span>
               {SAMPLE_QUESTIONS.map((sample) => (
                 <button
                   key={sample}
@@ -143,6 +162,21 @@ export function IntakeForm() {
         onContinue={() => setModalOpen(false)}
         onCancel={() => setModalOpen(false)}
       />
+
+      <DisambiguationModal
+        open={disambigOpen}
+        clusters={disambigClusters}
+        onSelectCluster={(cid) => {
+          const found = disambigClusters.find((c) => c.cluster_id === cid);
+          setPickedClusterLabel(found?.label ?? null);
+          setDisambigOpen(false);
+        }}
+        onCancel={() => setDisambigOpen(false)}
+      />
+
+      <output data-testid="disambig-picked-label" className="sr-only">
+        {pickedClusterLabel ?? ""}
+      </output>
     </div>
   );
 }
diff --git a/web/lib/api.ts b/web/lib/api.ts
index 3da5771..9de7a7a 100644
--- a/web/lib/api.ts
+++ b/web/lib/api.ts
@@ -363,6 +363,32 @@ export interface IntakeScopeDecision {
   decision_id: string;
   decided_at_utc: string;
   latency_ms: number;
+  needs_disambiguation?: boolean;
+  candidate_snippets?: { text: string; embedding: number[] }[];
+}
+
+export type DisambiguationCluster = {
+  cluster_id: number;
+  label: string;
+  sample_snippets: string[];
+};
+
+export interface DisambiguationResponse {
+  is_ambiguous: boolean;
+  num_clusters: number;
+  clusters: DisambiguationCluster[];
+  server_time_utc: string;
+}
+
+export async function runDisambiguation(
+  candidates: { text: string; embedding: number[] }[],
+): Promise<DisambiguationResponse> {
+  const response = await fetch(`${BACKEND_URL}/api/disambiguation`, {
+    method: "POST",
+    headers: { "content-type": "application/json" },
+    body: JSON.stringify({ candidates }),
+  });
+  return asJsonOrThrow<DisambiguationResponse>(response);
 }
 
 export interface IntakeSuccessResponse {
@@ -470,10 +496,7 @@ export interface RetrievalSuccessResponse {
 
 export interface RetrievalErrorBody {
   error: true;
-  code:
-    | "wrong_status"
-    | "wrong_scope_class"
-    | "fetch_backend_unavailable";
+  code: "wrong_status" | "wrong_scope_class" | "fetch_backend_unavailable";
   message: string;
   decision_id: string | null;
 }
@@ -657,9 +680,7 @@ export async function getGenerationHealth(): Promise<GenerationHealthResponse> {
 }
 
 /** Filter to non-dropped sections (verified + regenerated). */
-export function keptSections(
-  report: VerifiedReport,
-): VerifiedReportSection[] {
+export function keptSections(report: VerifiedReport): VerifiedReportSection[] {
   return report.sections.filter((s) => s.section_status !== "dropped");
 }
 
diff --git a/web/tests/e2e/intake_disambiguation.spec.ts b/web/tests/e2e/intake_disambiguation.spec.ts
new file mode 100644
index 0000000..e00cf43
--- /dev/null
+++ b/web/tests/e2e/intake_disambiguation.spec.ts
@@ -0,0 +1,84 @@
+import { expect, test } from "@playwright/test";
+
+test("BPEI: type → submit → modal → 3 candidates → pick → label flows to parent", async ({
+  page,
+}) => {
+  await page.route("**/api/intake", async (route) => {
+    await route.fulfill({
+      status: 200,
+      contentType: "application/json",
+      body: JSON.stringify({
+        error: false,
+        decision: {
+          status: "in_scope",
+          scope_class: "clinical_efficacy",
+          ambiguity_axes: [],
+          clarifications_needed: [],
+          provenance: {},
+          decision_id: "test-decision-id",
+          decided_at_utc: new Date().toISOString(),
+          latency_ms: 12,
+          needs_disambiguation: true,
+          candidate_snippets: [
+            { text: "BPEI syndrome notes", embedding: [1, 0] },
+            { text: "BPEI institute notes", embedding: [0, 1] },
+            { text: "BPEI chemical notes", embedding: [-1, 0] },
+          ],
+        },
+        server_time_utc: new Date().toISOString(),
+      }),
+    });
+  });
+
+  await page.route("**/api/disambiguation", async (route) => {
+    const body = JSON.parse(route.request().postData() ?? "{}");
+    expect(Array.isArray(body.candidates)).toBe(true);
+    expect(body.candidates).toHaveLength(3);
+    await new Promise((resolve) => setTimeout(resolve, 100));
+    await route.fulfill({
+      status: 200,
+      contentType: "application/json",
+      body: JSON.stringify({
+        is_ambiguous: true,
+        num_clusters: 3,
+        clusters: [
+          {
+            cluster_id: 0,
+            label: "syndrome",
+            sample_snippets: ["BPEI syndrome..."],
+          },
+          {
+            cluster_id: 1,
+            label: "institute",
+            sample_snippets: ["BPEI institute..."],
+          },
+          {
+            cluster_id: 2,
+            label: "chemical",
+            sample_snippets: ["BPEI chemical..."],
+          },
+        ],
+        server_time_utc: new Date().toISOString(),
+      }),
+    });
+  });
+
+  await page.goto("/intake");
+  await page.getByTestId("intake-question-input").fill("BPEI");
+
+  const t_submit = Date.now();
+  await page.getByTestId("intake-submit").click();
+  await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
+  const t_modal = Date.now();
+
+  expect(t_modal - t_submit).toBeLessThan(500);
+
+  const cards = page.locator('[data-testid^="disambiguation-cluster-"]');
+  await expect(cards).toHaveCount(3);
+
+  await page.getByTestId("disambiguation-cluster-1").click();
+  await expect(page.getByTestId("disambig-picked-label")).toHaveText(
+    "institute",
+  );
+  await expect(page.getByTestId("disambiguation-cluster-0")).toBeHidden();
+});

```
