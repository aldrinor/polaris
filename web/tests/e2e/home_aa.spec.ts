// I-ux-001c (#878) sub-PR 2: axe WCAG 2.2 AA scan for the v6 home hero.
//
// Asserts zero serious/critical axe violations on the marketing-auth hero
// at desktop + mobile viewports. The eyebrow (brand-red small caps) is the
// most contrast-risky element; the proof-as-CTA card's tri-state signature
// pill is the next most-likely failure point.
//
// This is a focused scan in addition to f1_a11y.spec.ts (which checks the
// home + command-palette-open + intake combo); this file isolates the v6
// hero so axe failures surface to this PR's scope cleanly.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

function critical_or_serious(v: { impact?: string | null }) {
  return v.impact === "serious" || v.impact === "critical";
}

test.describe("I-ux-001c · Home v6 axe WCAG 2.2 AA", () => {
  test("desktop 1440x900 — zero serious/critical axe violations", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("home-h1")).toBeVisible();
    await expect(page.getByTestId("proof-as-cta")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(WCAG_TAGS)
      .analyze();
    // Codex diff iter-1 P2-003: the brief calls for "axe WCAG 2.2 AA"
    // strictness; previously this only filtered serious+critical. We now
    // assert ZERO violations across all impacts (minor/moderate/serious/
    // critical). The serious/critical breakdown is retained in the
    // diagnostic message so a regression localizes immediately.
    const blockers = results.violations.filter(critical_or_serious);
    expect(
      results.violations,
      `serious/critical: ${JSON.stringify(blockers, null, 2)}\n\nall: ${JSON.stringify(results.violations, null, 2)}`,
    ).toEqual([]);
  });

  test("mobile 390x844 — zero serious/critical axe violations", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("home-h1")).toBeVisible();
    await expect(page.getByTestId("proof-as-cta")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(WCAG_TAGS)
      .analyze();
    // Codex diff iter-1 P2-003: the brief calls for "axe WCAG 2.2 AA"
    // strictness; previously this only filtered serious+critical. We now
    // assert ZERO violations across all impacts (minor/moderate/serious/
    // critical). The serious/critical breakdown is retained in the
    // diagnostic message so a regression localizes immediately.
    const blockers = results.violations.filter(critical_or_serious);
    expect(
      results.violations,
      `serious/critical: ${JSON.stringify(blockers, null, 2)}\n\nall: ${JSON.stringify(results.violations, null, 2)}`,
    ).toEqual([]);
  });
});
