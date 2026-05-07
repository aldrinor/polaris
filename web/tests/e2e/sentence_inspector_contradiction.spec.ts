import { expect, test } from "@playwright/test";

test("Sentence row with contradiction signal shows ⚠ badge", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  const row = page.locator('[data-sentence-id="sec_x:26"]');
  const badge = row.getByTestId("inspector-contradiction-sec_x:26");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("3 sources disagree");
  await expect(badge).toHaveAttribute(
    "title",
    /Three Cochrane reviews disagree on dose-response curve/,
  );
});

test("Sentence row without contradiction shows NO contradiction badge", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  const row = page.locator('[data-sentence-id="sec_x:5"]');
  await expect(row.getByTestId("inspector-contradiction-sec_x:5")).toHaveCount(
    0,
  );
});

test("Click contradiction badge → ContradictionPane shows N sides", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.getByTestId("inspector-contradiction-sec_x:26").click();
  await expect(page.getByTestId("contradiction-pane")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("contradiction-pane-title")).toContainText(
    "3 sources disagree",
  );
  // 3 sides rendered.
  await expect(page.getByTestId("contradiction-side-0")).toBeVisible();
  await expect(page.getByTestId("contradiction-side-1")).toBeVisible();
  await expect(page.getByTestId("contradiction-side-2")).toBeVisible();
  // Side 0 detail check (T1 + sample + hedge + PT08 + claim).
  await expect(page.getByTestId("contradiction-source-0")).toContainText(
    "src-0",
  );
  await expect(page.getByTestId("contradiction-tier-0")).toContainText("T1");
  await expect(page.getByTestId("contradiction-sample-0")).toContainText(
    "1247",
  );
  await expect(page.getByTestId("contradiction-hedge-0")).toContainText(
    "high confidence",
  );
  await expect(page.getByTestId("contradiction-pt08-0")).toContainText("PT04");
  await expect(page.getByTestId("contradiction-claim-0")).toContainText(
    "81mg",
  );
  // SentenceInspector did NOT also open (Codex iter-1 P2 click propagation guard).
  await expect(page.getByTestId("sentence-inspector-sheet")).toHaveCount(0);
});

test("Regulatory category badge in pane (I-f8-004)", async ({ page }) => {
  await page.goto("/sentence_hover_test");
  await page.getByTestId("inspector-contradiction-sec_x:28").click();
  await expect(page.getByTestId("contradiction-pane")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("contradiction-category")).toContainText(
    "Regulatory",
  );
  await expect(page.getByTestId("contradiction-claim-0")).toContainText(
    "FDA-approved",
  );
  await expect(page.getByTestId("contradiction-claim-1")).toContainText(
    "NOT FDA-approved",
  );
});

test("Guideline-vs-trial evidence-type tags (I-f8-005)", async ({ page }) => {
  await page.goto("/sentence_hover_test");
  await page.getByTestId("inspector-contradiction-sec_x:29").click();
  await expect(page.getByTestId("contradiction-pane")).toBeVisible({
    timeout: 500,
  });
  await expect(
    page.getByTestId("contradiction-evidence-type-0"),
  ).toContainText("Trial");
  await expect(
    page.getByTestId("contradiction-evidence-type-1"),
  ).toContainText("Guideline");
});

test("Self-contradiction badge + pane (I-f8-003)", async ({ page }) => {
  await page.goto("/sentence_hover_test");
  const badge = page.getByTestId("inspector-contradiction-sec_x:27");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("Source self-contradicts");
  await expect(badge).toContainText("2 spans");
  await badge.click();
  await expect(page.getByTestId("contradiction-pane-title")).toContainText(
    "Self-contradiction",
  );
  await expect(page.getByTestId("contradiction-pane-title")).toContainText(
    "2 spans",
  );
  // Both sides reference src-0.
  await expect(page.getByTestId("contradiction-source-0")).toContainText(
    "src-0",
  );
  await expect(page.getByTestId("contradiction-source-1")).toContainText(
    "src-0",
  );
  await expect(page.getByTestId("contradiction-claim-0")).toContainText("safe");
  await expect(page.getByTestId("contradiction-claim-1")).toContainText(
    "dangerous",
  );
});
