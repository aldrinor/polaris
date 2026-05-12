/**
 * I-snowball-006 — Playwright smoke for /runs/[runId]/graph.
 *
 * Mocks the backend `/api/runs/<id>/graph` endpoint with a deterministic
 * fixture so the test is hermetic and does not depend on a live FastAPI
 * server.
 */

import { test, expect } from "@playwright/test";
import fixture from "../fixtures/graph_payload.json";

test.describe("Claim graph page (I-snowball-006)", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/runs/*/graph", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
    });
  });

  test("loads page and renders graph canvas", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    await expect(page.getByTestId("graph-page")).toBeVisible();
    await expect(page.getByTestId("claim-graph")).toBeVisible();
  });

  test("search filters AccessibleGraphList", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    await page.getByPlaceholder(/Search nodes/).fill("safety");
    await expect(
      page.getByTestId("graph-list-row-section:safety"),
    ).toBeVisible();
    await expect(
      page.getByTestId("graph-list-row-frame:efficacy_endpoint"),
    ).toHaveCount(0);
  });

  test("PNG download triggers", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    // Wait for cytoscape mount (Download PNG enables once cy is ready).
    const pngButton = page.getByTestId("graph-export-png");
    await expect(pngButton).toBeEnabled({ timeout: 10_000 });
    const downloadPromise = page.waitForEvent("download");
    await pngButton.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.png$/);
  });

  test("JSON download triggers", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("graph-export-json").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.json$/);
  });

  test("404 backend → error UI", async ({ page }) => {
    await page.route("**/api/runs/no_such_run/graph", (route) =>
      route.fulfill({ status: 404, body: "run not found" }),
    );
    await page.goto("/runs/no_such_run/graph");
    await expect(page.getByRole("alert")).toContainText("Failed to load graph");
  });
});
