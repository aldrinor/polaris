/**
 * I-p2c-001: Cross-feature integration testing — F1→F2→F3→F4→F5 chain.
 *
 * Page-render navigation integration: walks each feature's primary fixture
 * page in sequence and asserts each page's primary testid renders. NOT a
 * backend pipeline integration — production end-to-end intake → run →
 * inspector smoke is M-LIVE-1 territory.
 */

import { expect, test } from "@playwright/test";

test("F1→F2→F3→F4→F5 page-render chain stays green", async ({ page }) => {
  const completed: string[] = [];

  // F1 — intake page (scope discovery / disambiguation entry).
  await page.goto("/intake");
  await expect(page.getByTestId("intake-form")).toBeVisible();
  await expect(page.getByTestId("intake-question-input")).toBeVisible();
  completed.push("F1");

  // F2 — disambiguation modal preview (cluster card harness).
  await page.goto("/disambiguation_modal_preview");
  await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
  completed.push("F2");

  // F3 — upload zone (sovereign-document handoff entry).
  await page.goto("/upload");
  await expect(page.getByTestId("upload-dropzone")).toBeVisible();
  completed.push("F3");

  // F4 — SSE harness (event-stream surface).
  await page.goto("/sse");
  await expect(page.getByTestId("sse-harness")).toBeVisible();
  completed.push("F4");

  // F5 — evidence tooltip harness (inspector hover surface).
  await page.goto("/sentence_hover_test/evidence_tooltip");
  await expect(page.getByTestId("evidence-tooltip-harness")).toBeVisible();
  await expect(page.getByTestId("evidence-tooltip-trigger")).toBeVisible();
  completed.push("F5");

  expect(completed).toEqual(["F1", "F2", "F3", "F4", "F5"]);
});
