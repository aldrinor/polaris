import { expect, test, type Page } from "@playwright/test";

interface FakeEntry {
  entry_id: string;
  workspace_id: string;
  kind: string;
  content: string;
  created_at: string;
  use_count: number;
  derived_from_run_ids: string[];
}

const seed: FakeEntry = {
  entry_id: "seed-1",
  workspace_id: "ws_demo",
  kind: "user_preference",
  content: "Prefers CMHC primary source.",
  created_at: "2026-01-01T00:00:00Z",
  use_count: 0,
  derived_from_run_ids: [],
};

async function mock(page: Page) {
  const state = { entries: [{ ...seed }], counter: 1 };
  await page.route("**/workspaces/ws_demo/memory/*", async (route) => {
    if (route.request().method() === "DELETE") {
      const id = route.request().url().split("/").pop()!;
      state.entries = state.entries.filter((e) => e.entry_id !== id);
      await route.fulfill({ status: 204 });
      return;
    }
    await route.continue();
  });
  await page.route("**/workspaces/ws_demo/memory", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.entries),
      });
      return;
    }
    if (route.request().method() === "POST") {
      state.counter += 1;
      const body = JSON.parse(route.request().postData() ?? "{}");
      const created: FakeEntry = {
        ...seed,
        entry_id: `seed-${state.counter}`,
        kind: body.kind,
        content: body.content,
        created_at: new Date(2026, 0, state.counter).toISOString(),
      };
      state.entries.push(created);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(created),
      });
      return;
    }
    await route.continue();
  });
}

test("memory page: save adds entry, then forget removes it", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/memory");
  await expect(page.getByTestId("memory-row-seed-1")).toBeVisible();
  await page
    .getByTestId("memory-save-content")
    .fill("Reject blogspot sources.");
  await page.getByTestId("memory-save-kind").selectOption("rejected_source");
  await page.getByTestId("memory-save").click();
  await expect(page.getByTestId("memory-row-seed-2")).toBeVisible();
  await expect(page.getByTestId("memory-row-seed-2")).toContainText(
    "Reject blogspot sources.",
  );
  await page.getByTestId("memory-forget-seed-2").click();
  await expect(page.getByTestId("memory-row-seed-2")).toHaveCount(0);
  await expect(page.getByTestId("memory-row-seed-1")).toBeVisible();
});
