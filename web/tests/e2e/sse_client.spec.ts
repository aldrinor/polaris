import { expect, test } from "@playwright/test";

test("reconnects within 2s after force-disconnect", async ({ page }) => {
  let hits = 0;
  await page.route("**/mock/sse", async (route) => {
    hits += 1;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "cache-control": "no-cache" },
      body: hits === 1 ? "data: first\n\n" : "data: stable\n\n",
    });
  });

  await page.goto("/sse?url=/mock/sse");
  await expect(page.getByTestId("sse-harness")).toBeVisible();
  await page.waitForFunction(
    () => (window.__sse__?.total_connects ?? 0) >= 2,
    undefined,
    {
      timeout: 2000,
    },
  );
});

test("stops after maxRetries on persistent failure", async ({ page }) => {
  await page.route("**/mock/sse-fail", async (route) => {
    await route.fulfill({ status: 500, body: "down" });
  });

  await page.goto("/sse?url=/mock/sse-fail&max=3");
  await expect(page.getByTestId("sse-harness")).toBeVisible();
  await page.waitForFunction(
    () => (window.__sse__?.errors ?? []).some((e) => e.terminal),
    undefined,
    { timeout: 5000 },
  );
});
