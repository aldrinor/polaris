import { expect, test } from "@playwright/test";

test("Frame coverage panel renders above the report with gap details", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await expect(page.getByTestId("frame-coverage-gaps")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-progress")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gap-count")).toContainText(
    "1 gap",
  );
  // Gap entry with entity_name + reason.
  const gap = page.getByTestId("frame-coverage-gap-0");
  await expect(gap).toBeVisible();
  await expect(gap).toContainText("Pediatric population");
  await expect(gap).toContainText("No OA");
  await expect(gap).toContainText("no open-access version of Cochrane review");
});

test("Click gap → detail Sheet shows entity + suggested action with substituted name", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.getByTestId("frame-coverage-gap-0").click();
  await expect(page.getByTestId("frame-gap-detail-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("frame-gap-detail-title")).toContainText(
    "Pediatric population",
  );
  await expect(page.getByTestId("frame-gap-action")).toContainText(
    "Pediatric population",
  );
});

test("Click copy button → 'Copied!' confirmation flashes", async ({ page }) => {
  // Codex iter-1 P1: stub navigator.clipboard.writeText so the test passes
  // across chromium/firefox/webkit without browser-specific permissions.
  await page.addInitScript(() => {
    // Always provide a writable stub on every page in this test.
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (_text: string) => {
          /* noop stub */
        },
      },
    });
  });
  await page.goto("/sentence_hover_test");
  await page.getByTestId("frame-coverage-gap-0").click();
  await expect(page.getByTestId("frame-gap-detail-sheet")).toBeVisible({
    timeout: 500,
  });
  await page.getByTestId("frame-gap-copy-button").click();
  await expect(page.getByTestId("frame-gap-copy-confirm")).toBeVisible();
});

test("Frame coverage panel is the first child of verified-report-view (above-the-fold)", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  // Codex iter-1 P1: Node.DOCUMENT_POSITION_* constants only exist inside
  // the browser context; do the check inside page.evaluate.
  // Codex iter-1 P2: assert first-child of verified-report-view — the
  // explicit above-the-fold semantics, not just "not after."
  const is_first_child = await page.evaluate(() => {
    const rv = document.querySelector('[data-testid="verified-report-view"]');
    if (!rv) return false;
    const first = rv.firstElementChild;
    return first?.getAttribute("data-testid") === "frame-coverage-gaps";
  });
  expect(is_first_child).toBe(true);
});
