import { expect, test } from "@playwright/test";

/**
 * Slice 005 demo polish — home walkthrough.
 *
 * The home page must surface the four-step demo flow (intake → retrieval
 * → generation → benchmark) so a non-developer can click through in order
 * during the Sep 6 tracer demo.
 */

test.describe("Home — tracer demo walkthrough", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
  });

  test("renders walkthrough section with all 4 slice cards", async ({
    page,
  }) => {
    await expect(page.getByTestId("demo-walkthrough")).toBeVisible();
    await expect(page.getByTestId("demo-slice-intake")).toBeVisible();
    await expect(page.getByTestId("demo-slice-retrieval")).toBeVisible();
    await expect(page.getByTestId("demo-slice-generation")).toBeVisible();
    await expect(page.getByTestId("demo-slice-benchmark")).toBeVisible();
  });

  test("each card links to its slice page", async ({ page }) => {
    const cards = [
      { id: "intake", href: "/intake" },
      { id: "retrieval", href: "/retrieval" },
      { id: "generation", href: "/generation" },
      { id: "benchmark", href: "/benchmark" },
    ];
    for (const { id, href } of cards) {
      const link = page
        .getByTestId(`demo-slice-${id}`)
        .getByRole("link");
      await expect(link).toHaveAttribute("href", href);
    }
  });
});
