import { expect, test } from "@playwright/test";

const SCENARIOS: { name: string; trigger: string }[] = [
  { name: "near-top", trigger: "evidence-tooltip-trigger-top" },
  { name: "near-bottom", trigger: "evidence-tooltip-trigger-bottom" },
  { name: "near-right", trigger: "evidence-tooltip-trigger-right" },
];

for (const { name, trigger } of SCENARIOS) {
  test(`${name} — popup stays inside viewport`, async ({ page }) => {
    await page.goto("/sentence_hover_test/evidence_tooltip_edges");
    await page.getByTestId(trigger).hover();
    const popup = page.getByTestId("evidence-tooltip-popup");
    await expect(popup).toBeVisible({ timeout: 1000 });

    const result = await page.evaluate(() => {
      const popups = document.querySelectorAll(
        '[data-testid="evidence-tooltip-popup"]',
      );
      // There should be exactly one popup visible at a time.
      const target = popups[popups.length - 1] as HTMLElement | undefined;
      if (!target) return null;
      const r = target.getBoundingClientRect();
      return {
        left: r.left,
        top: r.top,
        right: r.right,
        bottom: r.bottom,
        vw: window.innerWidth,
        vh: window.innerHeight,
      };
    });
    expect(result).not.toBeNull();
    if (!result) return;
    expect(result.left).toBeGreaterThanOrEqual(0);
    expect(result.top).toBeGreaterThanOrEqual(0);
    expect(result.right).toBeLessThanOrEqual(result.vw);
    expect(result.bottom).toBeLessThanOrEqual(result.vh);
  });
}
