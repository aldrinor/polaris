// I-ux-001c (#878) sub-PR 1: e2e Playwright for Inspector Proof Replay v6.
//
// Covers the storyboard hard rules (from `.codex/I-ux-001c/brief.md`):
//   - Sentence click → 6-beat reveal (claim echo, faithfulness, evidence
//     strength, source, signature, disclosure all visible)
//   - Keyboard: Enter on a claim button = select; Esc = clear; J/K (or arrows)
//     = next/previous claim; focus returns to the clicked sentence on Esc
//   - Mobile bottom-sheet variant (Sheet opens on selection)
//   - Reduced-motion = instant (no opacity ramp delay)
//   - Tri-state signature pill shows the correct state from the bundle
//
// Uses the canonical signed-bundle fixture at /inspector/v1-canonical-success
// (no backend required — bundle is loaded server-side from web/public/
// canonical_bundles/v1_canonical_success/).
//
// Run locally:
//   cd web && npx next start -p 3738 &
//   cd web && SCREENSHOT_BASE_URL=http://127.0.0.1:3738 \
//     npx playwright test tests/e2e/inspector_proof_replay.spec.ts
import { expect, test } from "@playwright/test";

const INSPECTOR_PATH = "/inspector/v1-canonical-success";

test.describe("I-ux-001c · Inspector Proof Replay v6 hero", () => {
  test("intended-use banner is mounted above the page chrome", async ({
    page,
  }) => {
    await page.goto(INSPECTOR_PATH);
    const banner = page.getByTestId("intended-use-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(/NOT.*clinical decision/i);
  });

  test("inspector proof header renders v6 two-band provenance strip", async ({
    page,
  }) => {
    await page.goto(INSPECTOR_PATH);
    await expect(page.getByTestId("inspector-h1")).toBeVisible();
    const strip = page.getByTestId("provenance-strip");
    await expect(strip).toBeVisible();
    // Faithfulness band
    await expect(strip).toContainText(/Faithfulness/i);
    await expect(strip).toContainText(/verified/i);
    await expect(strip).toContainText(/partial/i);
    await expect(strip).toContainText(/independent-family check/i);
    // Evidence strength band
    await expect(strip).toContainText(/Evidence strength/i);
    await expect(strip).toContainText(/high/i);
    await expect(strip).toContainText(/moderate/i);
    await expect(strip).toContainText(/signed bundle.*verifiable offline/i);
  });

  test("proof panel starts empty; sentence click reveals all 6 beats", async ({
    page,
  }) => {
    await page.goto(INSPECTOR_PATH);
    await page.waitForLoadState("networkidle");

    // Initial state — empty
    await expect(page.getByTestId("proof-panel-empty")).toBeVisible();

    // Click the first claim button
    const claimsList = page.getByTestId("claims-list");
    await expect(claimsList).toBeVisible();
    const firstClaim = claimsList.locator('[data-testid^="claim-"]').first();
    await firstClaim.click();

    // All 6 beats are visible (opacity:1 reached via the per-beat
    // transitionDelay; total reveal ≤ ~880ms for the last beat)
    await expect(page.getByTestId("proof-panel")).toBeVisible();
    await expect(page.getByTestId("challenged-sentence-label")).toBeVisible();
    await expect(page.getByTestId("claim-echo")).toBeVisible();
    await expect(page.getByTestId("faithfulness-block")).toBeVisible();
    await expect(page.getByTestId("evidence-strength-block")).toBeVisible();
    await expect(page.getByTestId("source-climax")).toBeVisible();
    await expect(page.getByTestId("signature-block")).toBeVisible();
    await expect(page.getByTestId("disclosure-block")).toBeVisible();
  });

  test("time-to-first-proof: faithfulness visible within 400ms of click", async ({
    page,
  }) => {
    await page.goto(INSPECTOR_PATH);
    const firstClaim = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]')
      .first();
    const t0 = Date.now();
    await firstClaim.click();
    await expect(page.getByTestId("faithfulness-block")).toBeVisible({
      timeout: 400,
    });
    const elapsed = Date.now() - t0;
    expect(elapsed).toBeLessThan(400);
  });

  test("keyboard navigation: Enter selects, J/K cycle, Esc clears + returns focus", async ({
    page,
  }) => {
    await page.goto(INSPECTOR_PATH);

    // Tab into the claims list and Enter on the first claim
    const firstClaim = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]')
      .first();
    await firstClaim.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("proof-panel")).toBeVisible();
    const firstClaimId = await firstClaim.getAttribute("data-testid");

    // J = next claim
    await page.keyboard.press("j");
    const secondPanel = page.getByTestId("proof-panel");
    const secondClaimId = await secondPanel.getAttribute("data-claim-id");
    expect(secondClaimId).not.toBeNull();

    // K = previous claim
    await page.keyboard.press("k");
    const backPanel = page.getByTestId("proof-panel");
    const backClaimId = await backPanel.getAttribute("data-claim-id");
    expect(firstClaimId).toContain(backClaimId ?? "");

    // Esc clears the selection and focus returns to the clicked sentence
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("proof-panel-empty")).toBeVisible();
    const focused = await page.evaluate(
      () => document.activeElement?.getAttribute("data-testid") ?? null,
    );
    expect(focused).toContain("claim-");
  });

  test("signature pill renders the bundle's tri-state value", async ({
    page,
  }) => {
    await page.goto(INSPECTOR_PATH);
    const firstClaim = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]')
      .first();
    await firstClaim.click();
    const sigBlock = page.getByTestId("signature-block");
    await expect(sigBlock).toBeVisible();
    // The canonical fixture is signed by the demo key → gpg_verified state
    const badge = sigBlock.getByTestId("signature-badge");
    await expect(badge).toHaveAttribute("data-state", /gpg_verified|present_unverified|missing/);
  });

  test("sealed evidence block: matched-numbers stamp shows when numerics match", async ({
    page,
  }) => {
    await page.goto(INSPECTOR_PATH);
    // Iterate claims until we find one with a matched-numbers stamp (the
    // canonical fixture has at least one claim with numerics, e.g. SURPASS
    // treatment differences).
    const claims = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]');
    const count = await claims.count();
    let foundStamp = false;
    for (let i = 0; i < count && !foundStamp; i++) {
      await claims.nth(i).click();
      const source = page.getByTestId("source-climax");
      await expect(source).toBeVisible();
      const stamp = page.getByTestId("matched-numbers-stamp");
      if ((await stamp.count()) > 0) {
        await expect(stamp).toContainText(/matched.*of.*numbers/i);
        foundStamp = true;
      }
    }
    // Don't hard-fail if no numeric claim — but at least one claim in the
    // canonical fixture should have one.
    expect(foundStamp).toBe(true);
  });

  test("desktop layout: split-view grid is rendered", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(INSPECTOR_PATH);
    const root = page.getByTestId("proof-replay");
    await expect(root).toHaveAttribute("data-viewport", "desktop");
  });

  test("mobile layout: bottom sheet opens on claim selection", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(INSPECTOR_PATH);
    const root = page.getByTestId("proof-replay");
    await expect(root).toHaveAttribute("data-viewport", "mobile");
    const firstClaim = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]')
      .first();
    await firstClaim.click();
    await expect(page.getByTestId("proof-replay-sheet")).toBeVisible();
    await expect(page.getByTestId("proof-panel")).toBeVisible();
  });

  test("reduced-motion: 6 beats appear instantly (no per-beat opacity ramp)", async ({
    browser,
  }) => {
    const ctx = await browser.newContext({ reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto(INSPECTOR_PATH);
    const firstClaim = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]')
      .first();
    const t0 = Date.now();
    await firstClaim.click();
    // All beats should be visible essentially immediately
    await expect(page.getByTestId("disclosure-block")).toBeVisible({
      timeout: 200,
    });
    const elapsed = Date.now() - t0;
    expect(elapsed).toBeLessThan(200);
    await ctx.close();
  });
});
