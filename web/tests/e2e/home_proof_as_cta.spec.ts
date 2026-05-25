// I-ux-001c (#878) sub-PR 2: e2e Playwright for the Home page proof-as-CTA
// hero card.
//
// Asserts the spec from `.codex/I-ux-001c-2/brief.md` iter-4 APPROVE:
//   - Eyebrow + H1 + subtitle render with the v6 copy
//   - Proof-as-CTA card renders with `data-state="loaded"` when the
//     canonical bundle is available, and shows a real verified claim
//     plus the matched-numbers stamp
//   - Numerics in the claim are wrapped in `proof-numeric` spans (visible
//     verification of the bolded-green visual treatment)
//   - The proof-sig pill renders the tri-state value from the bundle
//   - One primary CTA, links to /intake
//
// The Home page reads from the canonical fixture at
// web/public/canonical_bundles/v1_canonical_success/ via the server-side
// home_brief_loader, so no backend is required.
import { expect, test } from "@playwright/test";

const HOME_PATH = "/";

test.describe("I-ux-001c · Home proof-as-CTA hero", () => {
  test("hero eyebrow + H1 + subtitle render with v6 copy", async ({ page }) => {
    await page.goto(HOME_PATH);
    await expect(page.getByTestId("home-eyebrow")).toContainText(
      /POLARIS.*Canadian-hosted.*clinical research/i,
    );
    await expect(page.getByTestId("home-h1")).toContainText(
      "Every sentence proves itself",
    );
    await expect(page.getByTestId("home-subtitle")).toContainText(
      /Canadian-hosted.*verified against its cited source/i,
    );
  });

  test("proof-as-CTA card loads with REAL verified claim from canonical bundle", async ({
    page,
  }) => {
    await page.goto(HOME_PATH);
    const card = page.getByTestId("proof-as-cta");
    await expect(card).toBeVisible();
    // Canonical fixture is present in CI + dev → loaded state
    await expect(card).toHaveAttribute("data-state", "loaded");
    // The claim is a real sentence (>20 chars; bundle's first verified
    // sentence is the SURPASS HbA1c claim).
    const claim = page.getByTestId("proof-claim");
    await expect(claim).toBeVisible();
    const text = (await claim.textContent()) ?? "";
    expect(text.length).toBeGreaterThan(20);
    // Codex diff iter-2 P1: the loader's verified-gate is
    // matched === total. The visible stamp MUST reflect that — if
    // numerics are present, the matched count must equal the total.
    const stampText =
      (await page.getByTestId("proof-matched-stamp").textContent()) ?? "";
    const m = stampText.match(/matched\s+(\d+)\s+of\s+(\d+)/i);
    if (m) {
      // Numeric claim: matched === total per the verified-gate.
      expect(m[1]).toEqual(m[2]);
    }
    // (If m is null the claim is pure-prose — verifier_pass with zero
    // numerics — and the stamp reads "verifier passed against …".)
  });

  test("numerics in the claim are bolded green via proof-numeric spans", async ({
    page,
  }) => {
    await page.goto(HOME_PATH);
    const card = page.getByTestId("proof-as-cta");
    await expect(card).toBeVisible();
    // The canonical SURPASS claim has decimal numerics. If a numeric exists,
    // it MUST be wrapped in a proof-numeric span (not raw text).
    const numerics = card.locator('[data-testid="proof-numeric"]');
    // At least one numeric in the canonical fixture's first verified claim.
    const count = await numerics.count();
    expect(count).toBeGreaterThan(0);
  });

  test("matched-numbers stamp renders the exact 'matched <N> of <M> numbers' shape", async ({
    page,
  }) => {
    await page.goto(HOME_PATH);
    const stamp = page.getByTestId("proof-matched-stamp");
    await expect(stamp).toBeVisible();
    // The canonical fixture's first verified claim has decimal numerics
    // (e.g. the SURPASS HbA1c treatment differences), so the stamp MUST be
    // the numeric shape "✓ matched <N> of <M> number(s) against ...".
    // (Codex diff iter-1 P2-002: the previous `/matched|verifier passed/`
    // regex was too loose — it would have passed even if the loader
    // mis-classified a numeric claim and fell back to "verifier passed".)
    await expect(stamp).toContainText(/matched\s+\d+\s+of\s+\d+\s+number/i);
    await expect(stamp).toContainText(/source span/i);
  });

  test("tri-state signature pill reflects the bundle's signature state", async ({
    page,
  }) => {
    await page.goto(HOME_PATH);
    const pill = page.getByTestId("proof-sig-pill");
    await expect(pill).toBeVisible();
    const state = await pill.getAttribute("data-state");
    expect(["gpg_verified", "present_unverified", "missing"]).toContain(state);
  });

  test("primary CTA links to /intake with one click", async ({ page }) => {
    await page.goto(HOME_PATH);
    const cta = page.getByTestId("home-primary-cta");
    await expect(cta).toBeVisible();
    await expect(cta).toContainText("Try a verified brief");
    await cta.click();
    await page.waitForURL("**/intake**");
    await expect(page.getByTestId("intake-page")).toBeVisible();
  });

  test("proof-as-CTA card deep-links to /inspector/v1-canonical-success", async ({
    page,
  }) => {
    await page.goto(HOME_PATH);
    const link = page.getByTestId("proof-as-cta-link");
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", /inspector\/v1-canonical-success/);
  });

  test("sign-in link preserved (command palette focus-restore target)", async ({
    page,
  }) => {
    await page.goto(HOME_PATH);
    const link = page.getByTestId("header-sign-in-link");
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/sign-in");
  });

  test("Ctrl+K opens command palette (HomePaletteShell preserves the keybind)", async ({
    page,
  }) => {
    await page.goto(HOME_PATH);
    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();
  });
});
