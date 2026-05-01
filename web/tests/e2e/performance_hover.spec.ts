import { expect, test } from "@playwright/test";

/**
 * Phase 2C.4 F-2 (root_cause) — measure REAL hover-to-tooltip latency.
 *
 * Closes outputs/audits/continuous/4fe03f7_audit.md P1.2: the original
 * 2C.4 spec docstring promised hover-latency measurement but no test
 * file actually exercised it.
 *
 * Approach
 * --------
 * `EvidenceTooltip` wraps base-ui `Tooltip.Root`. On mouseenter the lib
 * waits its open-delay (~600ms in base-ui v1.4 default) before showing
 * the popup. So end-to-end user-perceived latency is:
 *
 *   total_ms = base_ui_open_delay_ms + react_render_ms
 *
 * The render contribution is what we care about for perf regressions.
 * We bound the WHOLE thing (1000ms = 600ms typical open-delay + 400ms
 * render budget) so a regression in either component fails the gate.
 *
 * Hover target: the `[#ev:ev_clin_001:1200-1450]` provenance token
 * inside the Verified-sentences tab on golden_clinical_001.
 */

test.describe("Performance — hover-to-tooltip end-to-end latency", () => {
  // The popup unique signature is the `<p>` containing `<evidenceId> · tier <T>`
  // text rendered first inside Tooltip.Popup (see EvidenceTooltip component).
  // base-ui doesn't put role="tooltip" on Popup so we content-select instead.
  const POPUP_TEXT = /ev_clin_001 · tier T1/;

  test("token hover → tooltip visible < 1000ms (golden_clinical_001)", async ({
    page,
  }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();

    const trigger = page
      .locator("text=/\\[#ev:ev_clin_001:1200-1450\\]/")
      .first();
    await trigger.waitFor({ state: "visible", timeout: 5_000 });

    const start = Date.now();
    await trigger.hover();
    await page.getByText(POPUP_TEXT).first().waitFor({
      state: "visible",
      timeout: 5_000,
    });
    const totalMs = Date.now() - start;

    expect(totalMs).toBeLessThan(1000);
  });

  test("hover-out hides tooltip < 500ms", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();

    const trigger = page
      .locator("text=/\\[#ev:ev_clin_001:1200-1450\\]/")
      .first();
    await trigger.waitFor({ state: "visible", timeout: 5_000 });
    await trigger.hover();
    await page.getByText(POPUP_TEXT).first().waitFor({
      state: "visible",
      timeout: 5_000,
    });

    // Move the cursor far away to trigger close.
    const start = Date.now();
    await page.mouse.move(0, 0);
    await page.getByText(POPUP_TEXT).first().waitFor({
      state: "hidden",
      timeout: 1_500,
    });
    const closeMs = Date.now() - start;

    expect(closeMs).toBeLessThan(500);
  });
});
