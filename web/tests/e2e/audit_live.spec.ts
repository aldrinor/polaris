import { expect, test } from "@playwright/test";

import { EVENT_NAMES } from "../../lib/sse_events";

test("each of 6 event-type panels renders within 1s of mock SSE emit", async ({
  page,
}) => {
  const body = EVENT_NAMES.map(
    (name, i) => `event: ${name}\ndata: {"i":${i}}\n\n`,
  ).join("");
  await page.route("**/mock/sse", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "cache-control": "no-cache" },
      body,
    });
  });

  await page.goto("/audit_live?url=/mock/sse");
  for (const name of EVENT_NAMES) {
    await expect(page.getByTestId(`panel-${name}-count`)).toContainText(
      /[1-9]\d* events/,
      {
        timeout: 1000,
      },
    );
  }
});
