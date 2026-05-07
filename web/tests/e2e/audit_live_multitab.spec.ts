import { expect, test } from "@playwright/test";

import { EVENT_NAMES } from "../../lib/sse_events";

test("cancel in tab A propagates to tab B via BroadcastChannel", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const body = EVENT_NAMES.map(
    (n, i) => `event: ${n}\ndata: {"i":${i}}\n\n`,
  ).join("");
  for (const route_setup of [context]) {
    await route_setup.route("**/mock/sse", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "cache-control": "no-cache" },
        body,
      });
    });
  }

  const pageA = await context.newPage();
  const pageB = await context.newPage();
  const url = "/audit_live?url=/mock/sse&run_id=test-run-mt";
  await pageA.goto(url);
  await pageB.goto(url);

  await expect(pageA.getByTestId("run-cancel-btn")).toBeVisible({
    timeout: 5000,
  });
  await expect(pageB.getByTestId("run-cancel-btn")).toBeVisible({
    timeout: 5000,
  });

  await pageA.getByTestId("run-cancel-btn").click();

  await expect(pageA.getByTestId("run-cancelled")).toBeVisible({
    timeout: 1000,
  });
  await expect(pageB.getByTestId("run-cancelled")).toBeVisible({
    timeout: 2000,
  });

  await context.close();
});
