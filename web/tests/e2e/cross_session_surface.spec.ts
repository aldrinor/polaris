import { expect, test } from "@playwright/test";

const fixed_now = Date.parse("2026-05-08T12:00:00Z");

function ago(days: number): string {
  return new Date(fixed_now - days * 24 * 60 * 60 * 1000).toISOString();
}

test("memory page surfaces prior runs with relative-time labels", async ({
  page,
}) => {
  await page.addInitScript((nowMs: number) => {
    const _Date = Date;
    class FixedDate extends _Date {
      constructor(...args: unknown[]) {
        super(...(args as []));
      }
      static now() {
        return nowMs;
      }
    }
    (globalThis as unknown as { Date: typeof Date }).Date =
      FixedDate as unknown as typeof Date;
  }, fixed_now);

  await page.route("**/workspaces/ws_demo/memory", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          entry_id: "run-1",
          workspace_id: "ws_demo",
          kind: "prior_run_summary",
          content: "tirzepatide vs semaglutide review",
          created_at: ago(1),
          use_count: 0,
          derived_from_run_ids: [],
        },
        {
          entry_id: "run-5",
          workspace_id: "ws_demo",
          kind: "prior_run_summary",
          content: "CMHC housing-starts 2025 Q4",
          created_at: ago(5),
          use_count: 0,
          derived_from_run_ids: [],
        },
        {
          entry_id: "run-14",
          workspace_id: "ws_demo",
          kind: "prior_run_summary",
          content: "Bank of Canada rate path",
          created_at: ago(14),
          use_count: 0,
          derived_from_run_ids: [],
        },
      ]),
    });
  });

  await page.goto("/memory");
  await expect(page.getByTestId("recent-runs")).toBeVisible();
  await expect(page.getByTestId("recent-run-run-1")).toContainText("yesterday");
  await expect(page.getByTestId("recent-run-run-5")).toContainText(
    "5 days ago",
  );
  await expect(page.getByTestId("recent-run-run-14")).toContainText(
    "2 weeks ago",
  );
});
