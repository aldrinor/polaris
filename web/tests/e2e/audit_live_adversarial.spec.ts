import { expect, test } from "@playwright/test";

async function fulfill_sse(
  page: import("@playwright/test").Page,
  body: string,
) {
  await page.route("**/mock/sse", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "cache-control": "no-cache" },
      body,
    });
  });
}

test("partial-evidence warning when 80% of candidates dropped", async ({
  page,
}) => {
  const candidates = Array.from(
    { length: 10 },
    (_, i) => `event: retrieval_candidate\ndata: {"i":${i}}\n\n`,
  ).join("");
  const drops = Array.from(
    { length: 8 },
    (_, i) => `event: source_dropped\ndata: {"i":${i}}\n\n`,
  ).join("");
  await fulfill_sse(page, candidates + drops);
  await page.goto("/audit_live?url=/mock/sse");
  await expect(page.getByTestId("partial-evidence-warning")).toBeVisible({
    timeout: 1500,
  });
});

test("zero-verified-abort banner when all verify decisions drop", async ({
  page,
}) => {
  const verifies = Array.from(
    { length: 5 },
    (_, i) => `event: verify_decision\ndata: {"kept":false,"i":${i}}\n\n`,
  ).join("");
  await fulfill_sse(page, verifies);
  await page.goto("/audit_live?url=/mock/sse");
  await expect(page.getByTestId("zero-verified-abort")).toBeVisible({
    timeout: 1500,
  });
});

test("no banners on normal path", async ({ page }) => {
  const candidates = Array.from(
    { length: 10 },
    (_, i) => `event: retrieval_candidate\ndata: {"i":${i}}\n\n`,
  ).join("");
  const drops = `event: source_dropped\ndata: {"i":0}\n\n`;
  const verifies = Array.from(
    { length: 5 },
    (_, i) => `event: verify_decision\ndata: {"kept":true,"i":${i}}\n\n`,
  ).join("");
  await fulfill_sse(page, candidates + drops + verifies);
  await page.goto("/audit_live?url=/mock/sse");
  await expect(page.getByTestId("panel-verify_decision-count")).toContainText(
    "5 events",
    { timeout: 5000 },
  );
  await expect(page.getByTestId("partial-evidence-warning")).toBeHidden();
  await expect(page.getByTestId("zero-verified-abort")).toBeHidden();
});

test("cap-boundary regression: 100 candidates + 50 drops (50%) does NOT trip warning", async ({
  page,
}) => {
  const candidates = Array.from(
    { length: 100 },
    (_, i) => `event: retrieval_candidate\ndata: {"i":${i}}\n\n`,
  ).join("");
  const drops = Array.from(
    { length: 50 },
    (_, i) => `event: source_dropped\ndata: {"i":${i}}\n\n`,
  ).join("");
  await fulfill_sse(page, candidates + drops);
  await page.goto("/audit_live?url=/mock/sse");
  await expect(page.getByTestId("panel-source_dropped-count")).toContainText(
    "50 events",
    { timeout: 5000 },
  );
  await expect(page.getByTestId("partial-evidence-warning")).toBeHidden();
});
