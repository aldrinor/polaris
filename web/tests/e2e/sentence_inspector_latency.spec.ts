import { expect, test } from "@playwright/test";

const TIERS = [50, 100, 200, 500];

for (const n of TIERS) {
  test(`Inspector opens in <1000ms at n=${n} sentences`, async ({ page }) => {
    await page.goto(`/sentence_hover_test/stress?n=${n}`);
    await expect(page.getByTestId(`inspector-latency-${n}`)).toBeVisible();
    await expect(page.getByTestId("verified-report-view")).toBeVisible();
    // Codex iter-1 P2: assert row count to prevent false-pass with fewer rows.
    await expect(page.getByTestId("kept-sentence")).toHaveCount(n);

    // Codex iter-1 P2: use performance.now() for tighter precision.
    const elapsed_ms = await page.evaluate(async () => {
      const target = document.querySelector(
        '[data-sentence-id="sec_stress:0"]',
      ) as HTMLElement | null;
      if (!target) throw new Error("sentence row not found");
      const t0 = performance.now();
      target.click();
      // Wait for the Sheet to attach to the DOM.
      await new Promise<void>((resolve) => {
        const observer = new MutationObserver(() => {
          if (
            document.querySelector('[data-testid="sentence-inspector-sheet"]')
          ) {
            observer.disconnect();
            resolve();
          }
        });
        observer.observe(document.body, { childList: true, subtree: true });
        if (
          document.querySelector('[data-testid="sentence-inspector-sheet"]')
        ) {
          observer.disconnect();
          resolve();
        }
      });
      const t1 = performance.now();
      return t1 - t0;
    });

    expect(elapsed_ms).toBeLessThan(1000);
    await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible();
  });
}
