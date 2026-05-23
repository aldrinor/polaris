// I-p2-039 (#825): shared helpers for the AUTH-AWARE primary-nav contract.
//
// The nav is now public/app split: unauthenticated visitors see Home + Ask only;
// the reviewer tools appear once signed in. lib/auth.isAuthenticated() is a
// presence/expiry check on a sessionStorage token (NOT a signature check), so a
// test can seed a dummy non-expired token to exercise the authed nav without real
// signing. The inline nav is xl-only (≥1280px), so we assert on a desktop viewport.

import { expect, type Page } from "@playwright/test";

export const PUBLIC_NAV_LABELS = ["Home", "Ask"] as const;
export const APP_ONLY_NAV_LABELS = [
  "Dashboard",
  "Upload",
  "Benchmark",
  "Compare",
  "Contracts",
  "Pin Replay",
  "Memory",
] as const;
export const APP_NAV_LABELS = [
  ...PUBLIC_NAV_LABELS,
  ...APP_ONLY_NAV_LABELS,
] as const;

const DESKTOP = { width: 1440, height: 900 };

/** Seed an authenticated session (matches lib/auth's sessionStorage keys) + a
 * desktop viewport so the inline (xl) primary nav renders. Call BEFORE page.goto. */
export async function setupAuthedNav(page: Page): Promise<void> {
  await page.setViewportSize(DESKTOP);
  await page.addInitScript(() => {
    sessionStorage.setItem("polaris_jwt", "e2e-dummy-token");
    sessionStorage.setItem(
      "polaris_jwt_expiry_ms",
      String(Date.now() + 12 * 60 * 60 * 1000),
    );
  });
}

/** Desktop viewport only (no token) for the unauthenticated public-nav test.
 * Call BEFORE page.goto. */
export async function setupPublicNav(page: Page): Promise<void> {
  await page.setViewportSize(DESKTOP);
}

/** Assert the authed app nav: nav present + every app label visible. */
export async function expectAuthedNav(page: Page): Promise<void> {
  const nav = page.locator("nav[aria-label='Primary']");
  await expect(nav).toBeVisible();
  for (const label of APP_NAV_LABELS) {
    await expect(
      nav.getByRole("link", { name: label, exact: true }),
    ).toBeVisible();
  }
}

/** Assert the unauthenticated public nav: Home + Ask only; app tools absent. */
export async function expectPublicNav(page: Page): Promise<void> {
  const nav = page.locator("nav[aria-label='Primary']");
  await expect(nav).toBeVisible();
  for (const label of PUBLIC_NAV_LABELS) {
    await expect(
      nav.getByRole("link", { name: label, exact: true }),
    ).toBeVisible();
  }
  for (const label of APP_ONLY_NAV_LABELS) {
    await expect(
      nav.getByRole("link", { name: label, exact: true }),
    ).toHaveCount(0);
  }
}
