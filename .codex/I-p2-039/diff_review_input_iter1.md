# Codex DIFF review — I-p2-039 (#825): auth-aware public/app nav. Iter 1 of 5.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the doc is force-APPROVE'd on remaining non-P0/P1 findings.
- If you're holding back a P1 for the next round — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## You APPROVE'd the brief (iter 2): Option B specs, public/app split, xl breakpoint, full authed contract incl Compare. This is the diff.

## Changes (web/ only)
- `lib/nav.ts`: `NavItem.visibility: "public" | "app"`. Public = Home + **Ask** (renamed
  from "Intake", href stays `/intake`). App = Dashboard/Upload/Benchmark/Compare/Contracts/
  Pin Replay/Memory. New pure `navForAuth(items, authed)` (public always; app iff authed).
  `navForRole` retained (orthogonal, unused-by-default).
- `components/primary_nav.tsx`: auth via `useSyncExternalStore(subscribe, isAuthenticated,
  () => false)` (SSR-safe, same pattern as AuthButton); `navForAuth` filter; inline nav
  breakpoint `md:`→`xl:` (hamburger below xl) so the authed set + brand + Canadian-hosted
  mark + AuthButton don't overflow (your iter-1 P1: lg/1024 overflows).
- `tests/e2e/_nav_auth.ts` (new): Option B helper — `setupAuthedNav` (seed dummy
  `polaris_jwt` + `polaris_jwt_expiry_ms` via addInitScript + 1440 viewport),
  `setupPublicNav`, `expectAuthedNav` (full 9-label contract incl Compare),
  `expectPublicNav` (Home+Ask visible; 7 app labels toHaveCount 0). All assertions
  `exact: true`, scoped to `nav[aria-label='Primary']`.
- 9 `*_g1_g8.spec.ts`: nav-parity tests now `setupAuthedNav → goto → expectAuthedNav`.
  `home_g1_g8` asserts the PUBLIC nav (canonical unauth assertion, P2-3 from your brief).
  `demo_journey`: seeds auth once, asserts authed nav across journey routes.

## Verification (LOCAL prod build — live-authed needs the P1 demo cred)
- `next build` compiled successfully; eslint clean on touched files; prettier `--check` clean.
- Playwright link assertions against `next start`:
  - UNAUTH @1440: `nav[aria-label='Primary']` links = `["Home","Ask"]` (tools hidden ✓, no "Intake").
  - AUTHED @1024: inline nav links = `[]` (hamburger below xl → no overflow ✓).
  - AUTHED @1280 and @1440: links = `["Home","Ask","Dashboard","Upload","Benchmark","Compare","Contracts","Pin Replay","Memory"]` (full set fits, no overflow — screenshot confirms brand+nav+mark+Sign-out fit at 1280 with room).

## HARD CONSTRAINTS preserved
- Honest sovereignty wording untouched (Canadian-hosted + OpenRouter/`/transparency`).
- No nav-item ROUTE removed (only visibility-gated pre-login); no auth/RBAC enforcement
  change (presentation only). Home's own static Sign in left as-is (your P2-3, follow-up).

## Files I have ALSO checked and they're clean
- `app_shell.tsx` / `home_keyboard_shell.tsx` (consume PrimaryNav only — unchanged),
  `auth_button.tsx` (same useSyncExternalStore pattern), `lib/auth.ts` (token keys match the
  helper), `nav_link.tsx` (pure styling). No remaining `"Intake"` label assertion in any spec.

## Review focus
1. Hydration safety of the useSyncExternalStore auth read in PrimaryNav (boolean snapshot stable; getServerSnapshot=false matches first paint).
2. The xl breakpoint genuinely prevents overflow (you flagged lg insufficient) — confirm 1280 is the right threshold given the verified 1280 fit.
3. Option B spec correctness: dummy-token seeding via addInitScript BEFORE goto; unauth public assertion NOT contaminated by an authed token (home has no seed); authed contract includes Compare.
4. Any NEW issue.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## The diff
```diff
diff --git a/web/components/primary_nav.tsx b/web/components/primary_nav.tsx
index 63924d41..42c65de7 100644
--- a/web/components/primary_nav.tsx
+++ b/web/components/primary_nav.tsx
@@ -1,20 +1,38 @@
-// I-p2-034 (#790): responsive primary nav. Inline links on desktop (md+);
-// a hamburger menu below md so the 9 routes never overflow off-screen on a
-// phone (the prior single-row nav clipped half the links). Shared by AppShell
-// + HomeKeyboardShell (single nav source @/lib/nav). a11y: aria-expanded +
-// aria-controls + Escape-to-close + focus-visible; closes on navigation.
+// I-p2-034 (#790): responsive primary nav. Inline links on desktop; a hamburger
+// below the inline breakpoint so the nav never overflows off-screen.
+// I-p2-039 (#825): the nav is AUTH-AWARE — unauthenticated visitors see only the
+// lean public set (Home + Ask); the reviewer tools appear once signed in. Auth is
+// read via useSyncExternalStore (SSR-safe, same pattern as AuthButton): server +
+// first client paint render the public-only nav, then the authed set fills in
+// after mount. The inline breakpoint is `xl` (1280px) — at `lg` (1024) the full
+// authed set + brand + Canadian-hosted mark + AuthButton overflows (Codex P1).
+// a11y: aria-expanded + aria-controls + Escape-to-close + focus-visible; closes
+// on navigation.
 "use client";
 
 import { Menu, X } from "lucide-react";
-import { useEffect, useState } from "react";
+import { useEffect, useState, useSyncExternalStore } from "react";
 
 import { NavLink } from "@/components/nav_link";
-import { PRIMARY_NAV, navForRole } from "@/lib/nav";
-import { DEFAULT_ROLE } from "@/lib/roles";
+import { isAuthenticated } from "@/lib/auth";
+import { PRIMARY_NAV, navForAuth } from "@/lib/nav";
+
+// Cross-tab auth changes fire a `storage` event; same-tab sign-in/out re-mounts
+// the shell on navigation, so the snapshot is re-read either way.
+function subscribe(onChange: () => void): () => void {
+  if (typeof window === "undefined") return () => {};
+  window.addEventListener("storage", onChange);
+  return () => window.removeEventListener("storage", onChange);
+}
 
 export function PrimaryNav() {
   const [open, setOpen] = useState(false);
-  const items = navForRole(PRIMARY_NAV, DEFAULT_ROLE);
+  const authed = useSyncExternalStore(
+    subscribe,
+    () => isAuthenticated(), // client: real auth state
+    () => false, // server / first hydration paint: public-only nav
+  );
+  const items = navForAuth(PRIMARY_NAV, authed);
 
   useEffect(() => {
     if (!open) return;
@@ -27,8 +45,8 @@ export function PrimaryNav() {
 
   return (
     <>
-      {/* Desktop: inline links */}
-      <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
+      {/* Desktop: inline links (xl+ so the full authed header fits) */}
+      <nav className="hidden items-center gap-1 xl:flex" aria-label="Primary">
         {items.map((item) => (
           <NavLink key={item.href} href={item.href}>
             {item.label}
@@ -36,8 +54,8 @@ export function PrimaryNav() {
         ))}
       </nav>
 
-      {/* Mobile: hamburger + dropdown */}
-      <div className="md:hidden">
+      {/* Below xl: hamburger + dropdown */}
+      <div className="xl:hidden">
         <button
           type="button"
           aria-label={open ? "Close menu" : "Open menu"}
diff --git a/web/lib/nav.ts b/web/lib/nav.ts
index e7aee128..98454d4e 100644
--- a/web/lib/nav.ts
+++ b/web/lib/nav.ts
@@ -1,31 +1,51 @@
 // I-p2-029 (#768): single source of truth for the primary nav.
 // Consumed by BOTH AppShell and HomeKeyboardShell so the nav can never drift
 // between shells (previously the PRIMARY_NAV const was duplicated in each).
+//
+// I-p2-039 (#825): the nav is now AUTH-AWARE (public/app split). An
+// unauthenticated visitor sees only the lean public set (Home + Ask); the
+// reviewer tools (Dashboard + the rest) appear only once signed in — so the
+// pre-login product no longer reads like an internal tool suite, and gated
+// links no longer dead-end at /sign-in. This is PRESENTATION only, never an
+// authorization gate (per-route RBAC is the security control).
 
 import type { RoleId } from "@/lib/roles";
 
 export interface NavItem {
   href: string;
   label: string;
-  /** Roles that may SEE this item (presentation-only — not authorization).
-   * Omitted = visible to all roles. */
+  /** I-p2-039: who SEES this item. "public" = always (signed in or not);
+   * "app" = only when authenticated. Presentation-only, not authorization. */
+  visibility: "public" | "app";
+  /** Roles that may SEE this item (presentation-only). Omitted = all roles. */
   roles?: readonly RoleId[];
 }
 
 export const PRIMARY_NAV: readonly NavItem[] = [
-  { href: "/", label: "Home" },
-  { href: "/intake", label: "Intake" },
-  { href: "/dashboard", label: "Dashboard" },
-  { href: "/upload", label: "Upload" },
-  { href: "/benchmark", label: "Benchmark" },
-  { href: "/compare", label: "Compare" },
-  { href: "/contracts", label: "Contracts" },
-  { href: "/pin_replay", label: "Pin Replay" },
-  { href: "/memory", label: "Memory" },
+  { href: "/", label: "Home", visibility: "public" },
+  // "Intake" was internal jargon (I-p2-039) — the public action is "Ask".
+  { href: "/intake", label: "Ask", visibility: "public" },
+  { href: "/dashboard", label: "Dashboard", visibility: "app" },
+  { href: "/upload", label: "Upload", visibility: "app" },
+  { href: "/benchmark", label: "Benchmark", visibility: "app" },
+  { href: "/compare", label: "Compare", visibility: "app" },
+  { href: "/contracts", label: "Contracts", visibility: "app" },
+  { href: "/pin_replay", label: "Pin Replay", visibility: "app" },
+  { href: "/memory", label: "Memory", visibility: "app" },
 ];
 
+/** I-p2-039: presentation-only auth filter. Public items always show; app items
+ * only when authenticated. Pure + isomorphic (safe in server or client). */
+export function navForAuth(
+  items: readonly NavItem[],
+  authed: boolean,
+): readonly NavItem[] {
+  return items.filter((item) => item.visibility === "public" || authed);
+}
+
 /** Presentation-only nav filter by role. Pure + isomorphic (safe in server or
- * client). Items without a `roles` list are visible to every role. */
+ * client). Items without a `roles` list are visible to every role. Orthogonal
+ * to navForAuth; retained for future per-persona nav. */
 export function navForRole(
   items: readonly NavItem[],
   role: RoleId,
diff --git a/web/tests/e2e/_nav_auth.ts b/web/tests/e2e/_nav_auth.ts
new file mode 100644
index 00000000..3c1bc3fc
--- /dev/null
+++ b/web/tests/e2e/_nav_auth.ts
@@ -0,0 +1,72 @@
+// I-p2-039 (#825): shared helpers for the AUTH-AWARE primary-nav contract.
+//
+// The nav is now public/app split: unauthenticated visitors see Home + Ask only;
+// the reviewer tools appear once signed in. lib/auth.isAuthenticated() is a
+// presence/expiry check on a sessionStorage token (NOT a signature check), so a
+// test can seed a dummy non-expired token to exercise the authed nav without real
+// signing. The inline nav is xl-only (≥1280px), so we assert on a desktop viewport.
+
+import { expect, type Page } from "@playwright/test";
+
+export const PUBLIC_NAV_LABELS = ["Home", "Ask"] as const;
+export const APP_ONLY_NAV_LABELS = [
+  "Dashboard",
+  "Upload",
+  "Benchmark",
+  "Compare",
+  "Contracts",
+  "Pin Replay",
+  "Memory",
+] as const;
+export const APP_NAV_LABELS = [
+  ...PUBLIC_NAV_LABELS,
+  ...APP_ONLY_NAV_LABELS,
+] as const;
+
+const DESKTOP = { width: 1440, height: 900 };
+
+/** Seed an authenticated session (matches lib/auth's sessionStorage keys) + a
+ * desktop viewport so the inline (xl) primary nav renders. Call BEFORE page.goto. */
+export async function setupAuthedNav(page: Page): Promise<void> {
+  await page.setViewportSize(DESKTOP);
+  await page.addInitScript(() => {
+    sessionStorage.setItem("polaris_jwt", "e2e-dummy-token");
+    sessionStorage.setItem(
+      "polaris_jwt_expiry_ms",
+      String(Date.now() + 12 * 60 * 60 * 1000),
+    );
+  });
+}
+
+/** Desktop viewport only (no token) for the unauthenticated public-nav test.
+ * Call BEFORE page.goto. */
+export async function setupPublicNav(page: Page): Promise<void> {
+  await page.setViewportSize(DESKTOP);
+}
+
+/** Assert the authed app nav: nav present + every app label visible. */
+export async function expectAuthedNav(page: Page): Promise<void> {
+  const nav = page.locator("nav[aria-label='Primary']");
+  await expect(nav).toBeVisible();
+  for (const label of APP_NAV_LABELS) {
+    await expect(
+      nav.getByRole("link", { name: label, exact: true }),
+    ).toBeVisible();
+  }
+}
+
+/** Assert the unauthenticated public nav: Home + Ask only; app tools absent. */
+export async function expectPublicNav(page: Page): Promise<void> {
+  const nav = page.locator("nav[aria-label='Primary']");
+  await expect(nav).toBeVisible();
+  for (const label of PUBLIC_NAV_LABELS) {
+    await expect(
+      nav.getByRole("link", { name: label, exact: true }),
+    ).toBeVisible();
+  }
+  for (const label of APP_ONLY_NAV_LABELS) {
+    await expect(
+      nav.getByRole("link", { name: label, exact: true }),
+    ).toHaveCount(0);
+  }
+}
diff --git a/web/tests/e2e/benchmark_g1_g8.spec.ts b/web/tests/e2e/benchmark_g1_g8.spec.ts
index 6c4537e6..5fc32d7d 100644
--- a/web/tests/e2e/benchmark_g1_g8.spec.ts
+++ b/web/tests/e2e/benchmark_g1_g8.spec.ts
@@ -1,6 +1,7 @@
 // I-cd-027 (#617): /benchmark route G1-G8 acceptance gates.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -46,21 +47,9 @@ test("G2: /benchmark contains no banned dev-language strings (body + titles + ar
 });
 
 test("G1 nav parity: primary nav visible on /benchmark", async ({ page }) => {
+  await setupAuthedNav(page);
   await page.goto("/benchmark");
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
 
 test("G8: /benchmark renders with zero console errors", async ({ page }) => {
diff --git a/web/tests/e2e/contracts_g1_g8.spec.ts b/web/tests/e2e/contracts_g1_g8.spec.ts
index 2a699543..186dd4c9 100644
--- a/web/tests/e2e/contracts_g1_g8.spec.ts
+++ b/web/tests/e2e/contracts_g1_g8.spec.ts
@@ -1,6 +1,7 @@
 // I-cd-028 (#618): /contracts route G1-G8 acceptance gates.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -48,21 +49,9 @@ test("G2: /contracts contains no banned dev-language strings (body + titles + ar
 });
 
 test("G1 nav parity: primary nav visible on /contracts", async ({ page }) => {
+  await setupAuthedNav(page);
   await page.goto("/contracts");
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
 
 test("G8: /contracts renders with zero console errors", async ({ page }) => {
diff --git a/web/tests/e2e/dashboard_g1_g8.spec.ts b/web/tests/e2e/dashboard_g1_g8.spec.ts
index cc606183..dea5b4dc 100644
--- a/web/tests/e2e/dashboard_g1_g8.spec.ts
+++ b/web/tests/e2e/dashboard_g1_g8.spec.ts
@@ -1,6 +1,7 @@
 // I-cd-024 (#614): /dashboard route G1-G8 acceptance gates.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -30,21 +31,9 @@ test("G2: /dashboard contains no banned dev-language strings", async ({
 });
 
 test("G1 nav parity: primary nav visible on /dashboard", async ({ page }) => {
+  await setupAuthedNav(page);
   await page.goto("/dashboard");
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
 
 test("G8: /dashboard renders with zero console errors", async ({ page }) => {
diff --git a/web/tests/e2e/demo_journey.spec.ts b/web/tests/e2e/demo_journey.spec.ts
index dc460bee..bfcb1157 100644
--- a/web/tests/e2e/demo_journey.spec.ts
+++ b/web/tests/e2e/demo_journey.spec.ts
@@ -10,6 +10,8 @@
 
 import { expect, test } from "@playwright/test";
 
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
+
 test("demo journey: home → intake → dashboard → inspector (canonical fixture)", async ({
   page,
 }) => {
@@ -60,16 +62,9 @@ test("demo journey: home → intake → dashboard → inspector (canonical fixtu
 test("demo journey nav-parity: header + primary nav identical across journey routes", async ({
   page,
 }) => {
-  const PRIMARY_NAV_LABELS = [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ];
+  // I-p2-039 (#825): the demo journey is the AUTHENTICATED reviewer flow, so seed
+  // a session and assert the full authed nav (incl. Compare) on each route.
+  await setupAuthedNav(page);
   for (const path of [
     "/",
     "/intake",
@@ -78,10 +73,6 @@ test("demo journey nav-parity: header + primary nav identical across journey rou
   ]) {
     await page.goto(path);
     await expect(page.locator("header")).toHaveCount(1);
-    const nav = page.locator("nav[aria-label='Primary']");
-    await expect(nav).toBeVisible();
-    for (const label of PRIMARY_NAV_LABELS) {
-      await expect(nav.getByRole("link", { name: label })).toBeVisible();
-    }
+    await expectAuthedNav(page);
   }
 });
diff --git a/web/tests/e2e/home_g1_g8.spec.ts b/web/tests/e2e/home_g1_g8.spec.ts
index f698bee1..80c7cae5 100644
--- a/web/tests/e2e/home_g1_g8.spec.ts
+++ b/web/tests/e2e/home_g1_g8.spec.ts
@@ -4,6 +4,8 @@
 
 import { expect, test } from "@playwright/test";
 
+import { expectPublicNav } from "./_nav_auth";
+
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
   /\bscaffold\b/i,
@@ -22,22 +24,12 @@ test("G1 + G6: home has exactly one header outside <main>, primary nav visible",
   const headers = page.locator("header");
   await expect(headers).toHaveCount(1);
 
-  // Primary nav present + identical to other routes (Home/Intake/Dashboard/
-  // Upload/Benchmark/Contracts/Pin Replay/Memory).
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  // I-p2-039 (#825): home is the UNAUTHENTICATED landing page, so the primary
+  // nav must show only the lean public set (Home + Ask); the reviewer tools
+  // (Dashboard/Upload/Benchmark/Compare/Contracts/Pin Replay/Memory) must NOT
+  // appear pre-login. (This is also the canonical unauth public-nav assertion.)
+  await page.setViewportSize({ width: 1440, height: 900 });
+  await expectPublicNav(page);
 
   // G6 (single main landmark — Codex iter-2 P1 fix).
   const mains = page.locator("main");
diff --git a/web/tests/e2e/intake_g1_g8.spec.ts b/web/tests/e2e/intake_g1_g8.spec.ts
index 069512f8..60fe8db9 100644
--- a/web/tests/e2e/intake_g1_g8.spec.ts
+++ b/web/tests/e2e/intake_g1_g8.spec.ts
@@ -2,6 +2,7 @@
 // state/polaris_ui_rebuild_matrix.md §2. Pattern mirrors home_g1_g8.spec.ts.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -43,17 +44,7 @@ test("G8: /intake renders with zero console errors", async ({ page }) => {
 });
 
 test("G1 nav parity: primary nav is visible on /intake", async ({ page }) => {
+  await setupAuthedNav(page);
   await page.goto("/intake");
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
diff --git a/web/tests/e2e/memory_g1_g8.spec.ts b/web/tests/e2e/memory_g1_g8.spec.ts
index 6dfdb8bc..d7c0983c 100644
--- a/web/tests/e2e/memory_g1_g8.spec.ts
+++ b/web/tests/e2e/memory_g1_g8.spec.ts
@@ -1,6 +1,7 @@
 // I-cd-030 (#620): /memory route G1-G8 acceptance gates.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -45,21 +46,9 @@ test("G2: /memory contains no banned dev-language strings (body + titles + aria-
 });
 
 test("G1 nav parity: primary nav visible on /memory", async ({ page }) => {
+  await setupAuthedNav(page);
   await page.goto("/memory");
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
 
 test("G8: /memory renders with zero console errors", async ({ page }) => {
diff --git a/web/tests/e2e/pin_replay_g1_g8.spec.ts b/web/tests/e2e/pin_replay_g1_g8.spec.ts
index 4da70001..5d002c86 100644
--- a/web/tests/e2e/pin_replay_g1_g8.spec.ts
+++ b/web/tests/e2e/pin_replay_g1_g8.spec.ts
@@ -1,6 +1,7 @@
 // I-cd-029 (#619): /pin_replay route G1-G8 acceptance gates.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -48,21 +49,9 @@ test("G2: /pin_replay contains no banned dev-language strings (body + titles + a
 });
 
 test("G1 nav parity: primary nav visible on /pin_replay", async ({ page }) => {
+  await setupAuthedNav(page);
   await page.goto("/pin_replay");
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
 
 test("G8: /pin_replay renders with zero console errors", async ({ page }) => {
diff --git a/web/tests/e2e/runs_runid_g1_g8.spec.ts b/web/tests/e2e/runs_runid_g1_g8.spec.ts
index bdbfb4f3..7c4624c7 100644
--- a/web/tests/e2e/runs_runid_g1_g8.spec.ts
+++ b/web/tests/e2e/runs_runid_g1_g8.spec.ts
@@ -1,6 +1,7 @@
 // I-cd-025 (#615): /runs/[runId] route G1-G8 acceptance gates.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -67,19 +68,7 @@ test("G8: /runs/[runId] renders with zero console errors", async ({ page }) => {
 test("G1 nav parity: primary nav visible on /runs/[runId]", async ({
   page,
 }) => {
+  await setupAuthedNav(page);
   await page.goto(`/runs/${TEST_RUN_ID}`);
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
diff --git a/web/tests/e2e/upload_g1_g8.spec.ts b/web/tests/e2e/upload_g1_g8.spec.ts
index 756ba0b3..66f8a4c1 100644
--- a/web/tests/e2e/upload_g1_g8.spec.ts
+++ b/web/tests/e2e/upload_g1_g8.spec.ts
@@ -1,6 +1,7 @@
 // I-cd-026 (#616): /upload route G1-G8 acceptance gates.
 
 import { expect, test } from "@playwright/test";
+import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";
 
 const BANNED_DEV_LANGUAGE = [
   /\bslice\b/i,
@@ -44,21 +45,9 @@ test("G2: /upload contains no banned dev-language strings (body + titles + aria-
 });
 
 test("G1 nav parity: primary nav visible on /upload", async ({ page }) => {
+  await setupAuthedNav(page);
   await page.goto("/upload");
-  const nav = page.locator("nav[aria-label='Primary']");
-  await expect(nav).toBeVisible();
-  for (const label of [
-    "Home",
-    "Intake",
-    "Dashboard",
-    "Upload",
-    "Benchmark",
-    "Contracts",
-    "Pin Replay",
-    "Memory",
-  ]) {
-    await expect(nav.getByRole("link", { name: label })).toBeVisible();
-  }
+  await expectAuthedNav(page);
 });
 
 test("G8: /upload renders with zero console errors", async ({ page }) => {

```
