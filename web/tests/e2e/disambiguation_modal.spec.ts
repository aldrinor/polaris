import { expect, test } from "@playwright/test";

const VARIANTS: Array<{ n: 2 | 3 | 5 }> = [{ n: 2 }, { n: 3 }, { n: 5 }];

for (const { n } of VARIANTS) {
  test(`disambiguation modal renders ${n} cluster cards and handles selection + cancel`, async ({
    page,
  }) => {
    await page.goto(`/disambiguation_modal_preview?n=${n}`);

    await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
    const cards = page.locator('[data-testid^="disambiguation-cluster-"]');
    await expect(cards).toHaveCount(n);

    for (let i = 0; i < n; i++) {
      await expect(
        page.getByTestId(`disambiguation-cluster-${i}`),
      ).toBeVisible();
    }

    await page.getByTestId("disambiguation-cluster-1").click();
    await expect(page.getByTestId("last-picked")).toHaveText("1");

    await page.getByTestId("reopen").click();
    await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("last-picked")).toHaveText("");

    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > 1280,
    );
    expect(overflows).toBe(false);
  });
}
