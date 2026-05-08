/**
 * I-p2c-005: Mobile end-to-end — F1→F5 chain on mobile viewport.
 *
 * Same scope as p2c_001_chain but on a mobile viewport (375×667, hasTouch,
 * iPhone-13 user agent). F5 step explicitly tests the mobile tap-to-show
 * fallback (per I-f6-003 evidence-tooltip).
 *
 * Page-render integration only; backend pipeline mobile is M-LIVE-1.
 */

import { devices, expect, test } from "@playwright/test";

test.use({
  viewport: { width: 375, height: 667 },
  hasTouch: true,
  isMobile: true,
  userAgent: devices["iPhone 13"].userAgent,
});

test("Mobile F1→F5 page-render chain + tap-to-show on F5", async ({ page }) => {
  const completed: string[] = [];

  await page.goto("/intake");
  await expect(page.getByTestId("intake-form")).toBeVisible();
  await expect(page.getByTestId("intake-question-input")).toBeVisible();
  completed.push("F1");

  await page.goto("/disambiguation_modal_preview");
  await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
  completed.push("F2");

  await page.goto("/upload");
  await expect(page.getByTestId("upload-dropzone")).toBeVisible();
  completed.push("F3");

  await page.goto("/sse");
  await expect(page.getByTestId("sse-harness")).toBeVisible();
  completed.push("F4");

  // F5 — evidence tooltip: trigger renders; tap surfaces the popup
  // (mobile tap-to-show fallback per I-f6-003).
  await page.goto("/sentence_hover_test/evidence_tooltip");
  const trigger = page.getByTestId("evidence-tooltip-trigger");
  await expect(trigger).toBeVisible();
  await trigger.tap();
  await expect(page.getByTestId("evidence-tooltip-popup")).toBeVisible({
    timeout: 5_000,
  });
  completed.push("F5");

  expect(completed).toEqual(["F1", "F2", "F3", "F4", "F5"]);
});
