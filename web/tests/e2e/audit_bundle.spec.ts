import { expect, test } from "@playwright/test";

/**
 * Slice 004 — Audit bundle download e2e.
 *
 * Drives /generation against the live polaris_v6 app. After the chain
 * produces a VerifiedReport, the "Download audit bundle" button is
 * present. Clicking it triggers a download (with GPG signer set) or
 * shows a structured error code (without).
 */

test.describe("Slice 004 — audit-bundle download from /generation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/generation", { waitUntil: "networkidle" });
  });

  test("download button appears after successful generation", async ({
    page,
  }) => {
    await page
      .getByTestId("generation-question-input")
      .fill("Is aspirin effective for headache in adults?");
    await page.getByTestId("generation-submit").click();

    // Wait for either verified report or generation error
    await Promise.race([
      page.getByTestId("verified-report-view").waitFor({
        state: "visible",
        timeout: 600_000,
      }),
      page.getByTestId("generation-error").waitFor({
        state: "visible",
        timeout: 600_000,
      }),
    ]);

    // Only assert the download button presence on success
    if (await page.getByTestId("verified-report-view").isVisible()) {
      await expect(page.getByTestId("download-audit-bundle")).toBeVisible();
    }
  });

  test("download click yields .tar.gz or structured error", async ({
    page,
  }) => {
    await page
      .getByTestId("generation-question-input")
      .fill("Is aspirin effective for headache in adults?");
    await page.getByTestId("generation-submit").click();
    await Promise.race([
      page.getByTestId("verified-report-view").waitFor({
        state: "visible",
        timeout: 600_000,
      }),
      page.getByTestId("generation-error").waitFor({
        state: "visible",
        timeout: 600_000,
      }),
    ]);

    if (!(await page.getByTestId("verified-report-view").isVisible())) {
      // No report -> no download button to test; skip
      return;
    }

    // Set up download listener BEFORE clicking
    const download_promise = page
      .waitForEvent("download", { timeout: 30_000 })
      .catch(() => null);

    await page.getByTestId("download-audit-bundle").click();

    const [download] = await Promise.all([
      Promise.race([
        download_promise,
        page
          .getByTestId("audit-bundle-error")
          .waitFor({ state: "visible", timeout: 30_000 })
          .then(() => null),
      ]),
    ]);

    if (download) {
      const filename = download.suggestedFilename();
      expect(filename).toMatch(/\.tar\.gz$/);
      expect(filename).toContain("audit_");
    } else {
      // Error path — must surface structured code (e.g. gpg_unavailable)
      await expect(page.getByTestId("audit-bundle-error")).toBeVisible();
      await expect(page.getByTestId("audit-bundle-error")).toContainText(
        /(gpg_unavailable|sign_failed|fk_chain|verdict)/i,
      );
    }
  });
});
