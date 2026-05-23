# Codex diff review — I-p2-038 (#821): global app-shell top-tier pass (footer + auth button)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this diff does (umbrella issue #821 = top-tier visual overhaul across ALL P2 pages)

Two every-page top-tier defects found by screenshotting the live site:
1. Only the home route had a `<footer>`; every AppShell route (intake, upload,
   contracts, pin_replay, dashboard, benchmark, memory, compare, …) ended in an
   empty void below the fold — the operator's explicit "empty space" complaint.
2. The auth affordance was inconsistent: home had a static "Sign in" button;
   every AppShell route had NONE (no way to sign in once off home), and there
   was NO "Sign out" anywhere in the product.

Fix:
- NEW `web/components/site_footer.tsx`: ONE shared footer used by home + AppShell.
- NEW `web/components/auth_button.tsx`: hydration-safe Sign in / Sign out for the
  AppShell header.
- `web/components/app_shell.tsx`: mount `<AuthButton/>` in header + `<SiteFooter/>`
  after `<main>` (sticky footer via the existing `body.flex.min-h-full.flex-col`
  + `main.flex-1`).
- `web/app/page.tsx`: replace the thin inline home footer with `<SiteFooter/>`.

## HARD CONSTRAINTS (operator-locked / project law — do NOT reopen)
- **Honesty (CLAUDE.md §-1.1 + LAW II):** the footer microcopy must NOT overclaim
  sovereignty. Production LLM inference is currently OpenRouter (US, transitional).
  Verify the footer says exactly that and links /transparency — no "no US vendor",
  no false present-tense sovereignty. This is the SAME honest framing already
  shipped in the header "Canadian-hosted" mark (app_shell.tsx title attr).
- **No nav-item-visibility change.** I deliberately did NOT touch PRIMARY_NAV or
  hide gated nav items, because the G1 nav-parity e2e specs assert all nav labels
  are visible unauthenticated. That redesign is a separate future issue. Confirm
  this diff does not break that contract.
- Next.js 16 App Router; server vs client component boundaries matter.

## Files I have ALSO checked and they're clean (verify, don't rediscover)
- `web/app/layout.tsx`: `body` is `flex min-h-full flex-col`; `main` is `flex-1`
  → footer after main pins to the bottom (sticky-footer). Confirmed.
- `web/components/app_shell_gate.tsx`: CHROMELESS_ROUTES = `/` and `/sign-in`
  (+ `/runs/<id>/graph|audit`). So AppShell (and thus the new AuthButton +
  SiteFooter) does NOT render on home or sign-in → no double Sign-in on home
  (home keeps its own button), and sign-in stays chromeless. Verified by
  screenshot: home shows ONE Sign in; /upload shows the AppShell Sign in + footer.
- `web/lib/auth.ts`: `isAuthenticated()` (reads sessionStorage token+expiry),
  `clearToken()`, exist and are exported. AuthButton uses them.
- `web/app/components/home_keyboard_shell.tsx`: home's own static Sign in button +
  command-palette focus ref left UNTOUCHED (out of scope this iter; noted as
  follow-up that home's button is not yet auth-aware).
- e2e specs `tests/e2e/{dashboard,contracts,benchmark}_g1_g8.spec.ts` +
  `demo_journey.spec.ts`: assert header count==1, main count==1, and that
  `nav[aria-label='Primary']` shows all labels. This diff adds a `<footer>` and a
  header button but does NOT change nav items or add a second header/main → these
  assertions still hold. No spec asserts footer-absence (grepped: none).
- `/transparency` returns 200 on the live site; `/intake` and
  `/inspector/v1-canonical-success` are public → footer links are not dead-ends.
- Local `next build` (prod) is GREEN with these changes; prettier (local 3.8.3,
  matches CI) `--check` clean on all 4 files.

## Review focus
1. Honesty of footer microcopy (no sovereignty overclaim) — clinical/Carney bar.
2. Hydration safety of AuthButton (server/first-client render must match — does
   `useState(false)` + post-mount `setAuthed(isAuthenticated())` avoid mismatch?).
3. Header layout: I dropped the sovereign mark's `ml-auto` reliance by wrapping
   AuthButton in `ml-auto sm:ml-0`. Confirm right-alignment works at mobile
   (mark hidden) AND desktop (mark visible) without overflow.
4. Any a11y regression (footer `<nav aria-label>`, focus-visible on links/button).
5. Sticky-footer correctness on short pages.

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
diff --git a/web/app/page.tsx b/web/app/page.tsx
index 10bc8e70..2d5f9e23 100644
--- a/web/app/page.tsx
+++ b/web/app/page.tsx
@@ -4,6 +4,7 @@ import { HomeKeyboardShell } from "@/app/components/home_keyboard_shell";
 import { ProofShowcase } from "@/app/components/proof_showcase";
 import { RecentRunsStrip } from "@/app/components/recent_runs_strip";
 import { MapleLeafSignatureLazy } from "@/components/signature/maple_leaf_signature_lazy";
+import { SiteFooter } from "@/components/site_footer";
 import { Button } from "@/components/ui/button";
 import { Input } from "@/components/ui/input";
 
@@ -187,12 +188,9 @@ export default function HomePage() {
           <RecentRunsStrip />
         </main>
 
-        <footer className="border-border bg-background border-t">
-          <div className="text-muted-foreground mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4 text-xs">
-            <span>POLARIS · Sovereign Canadian deep research</span>
-            <span>Two-family verified evidence</span>
-          </div>
-        </footer>
+        {/* I-p2-038 (#821): shared SiteFooter — replaces the thin inline home
+            footer so home + every AppShell route render one identical footer. */}
+        <SiteFooter />
       </HomeKeyboardShell>
     </div>
   );
diff --git a/web/components/app_shell.tsx b/web/components/app_shell.tsx
index 7bfc496d..f0774b6d 100644
--- a/web/components/app_shell.tsx
+++ b/web/components/app_shell.tsx
@@ -1,6 +1,8 @@
 import Link from "next/link";
 
+import { AuthButton } from "@/components/auth_button";
 import { PrimaryNav } from "@/components/primary_nav";
+import { SiteFooter } from "@/components/site_footer";
 
 /**
  * I-cd-004: the global app shell. A server component that wraps every prod
@@ -45,9 +47,16 @@ export function AppShell({ children }: { children: React.ReactNode }) {
           >
             ⬡ Canadian-hosted
           </span>
+          {/* I-p2-038 (#821): auth affordance was MISSING on every non-home
+              route. ml-auto on the sovereign mark above is dropped to sm: only,
+              so on mobile (mark hidden) this button still right-aligns. */}
+          <div className="ml-auto sm:ml-0">
+            <AuthButton />
+          </div>
         </div>
       </header>
       <main className="flex-1">{children}</main>
+      <SiteFooter />
     </>
   );
 }
diff --git a/web/components/auth_button.tsx b/web/components/auth_button.tsx
new file mode 100644
index 00000000..1369c145
--- /dev/null
+++ b/web/components/auth_button.tsx
@@ -0,0 +1,54 @@
+// I-p2-038 (#821): auth-aware Sign in / Sign out for the AppShell header.
+// Before this, AppShell (every non-home route) had NO auth affordance at all —
+// an unauthenticated reviewer who navigated off the home page had no way to
+// sign in, and a signed-in reviewer had no way to sign out anywhere.
+//
+// Hydration-safe: the server render and the FIRST client render both show the
+// unauthenticated "Sign in" link (the token lives in sessionStorage, which the
+// server can't see). Only AFTER mount do we read the real auth state and, if
+// signed in, swap to "Sign out". This avoids a server/client markup mismatch.
+"use client";
+
+import Link from "next/link";
+import { useRouter } from "next/navigation";
+import { useEffect, useState } from "react";
+
+import { Button } from "@/components/ui/button";
+import { clearToken, isAuthenticated } from "@/lib/auth";
+
+export function AuthButton() {
+  const router = useRouter();
+  const [authed, setAuthed] = useState(false);
+
+  useEffect(() => {
+    setAuthed(isAuthenticated());
+  }, []);
+
+  if (authed) {
+    return (
+      <Button
+        variant="ghost"
+        data-testid="appshell-sign-out"
+        onClick={() => {
+          clearToken();
+          setAuthed(false);
+          router.push("/");
+        }}
+      >
+        Sign out
+      </Button>
+    );
+  }
+
+  return (
+    <Button
+      variant="outline"
+      nativeButton={false}
+      render={
+        <Link href="/sign-in" data-testid="appshell-sign-in-link">
+          Sign in
+        </Link>
+      }
+    />
+  );
+}
diff --git a/web/components/site_footer.tsx b/web/components/site_footer.tsx
new file mode 100644
index 00000000..4306d518
--- /dev/null
+++ b/web/components/site_footer.tsx
@@ -0,0 +1,71 @@
+// I-p2-038 (#821): the shared global footer — the SINGLE source of truth for
+// both the home shell and AppShell (every non-chromeless route). Before this,
+// only the home page had a footer, so every other page ended in an empty void
+// below the fold. Honest sovereignty microcopy that matches the header
+// "Canadian-hosted" mark: the VM is hosted in OVH Québec; public sources are
+// fetched via logged Canadian egress; every brief is integrity-hashed. NO
+// overclaim — production LLM inference is currently OpenRouter (US, transitional)
+// and that is disclosed at /transparency, linked here. Every link points at a
+// PUBLIC route (no auth-gated dead-ends in the footer).
+import Link from "next/link";
+
+const FOOTER_LINKS = [
+  { href: "/intake", label: "Ask a question" },
+  { href: "/inspector/v1-canonical-success", label: "See a verified brief" },
+  { href: "/transparency", label: "Transparency & disclosure" },
+] as const;
+
+export function SiteFooter() {
+  const year = new Date().getFullYear();
+  return (
+    <footer className="border-border bg-muted/20 mt-16 border-t">
+      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10 md:flex-row md:items-start md:justify-between">
+        <div className="flex max-w-md flex-col gap-2">
+          <span className="text-foreground font-mono text-sm font-semibold tracking-tight">
+            POLARIS · Canada
+          </span>
+          <p className="text-muted-foreground text-xs leading-relaxed">
+            Sovereign Canadian deep research. Every claim in a POLARIS brief is
+            verified — span by span — against its primary source by an
+            independent evaluator family.
+          </p>
+          <span className="text-muted-foreground/80 mt-1 inline-flex items-center gap-1.5 text-[11px]">
+            <span aria-hidden>⬡</span> Hosted in Canada (Québec) · public
+            sources via logged Canadian egress
+          </span>
+        </div>
+
+        <nav
+          aria-label="Footer"
+          className="flex flex-col gap-2 md:items-end md:text-right"
+        >
+          {FOOTER_LINKS.map((link) => (
+            <Link
+              key={link.href}
+              href={link.href}
+              className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/70 w-fit rounded text-xs underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none md:self-end"
+            >
+              {link.label}
+            </Link>
+          ))}
+        </nav>
+      </div>
+
+      <div className="border-border/60 border-t">
+        <div className="text-muted-foreground/70 mx-auto flex w-full max-w-7xl flex-col gap-1 px-6 py-4 text-[11px] sm:flex-row sm:items-center sm:justify-between">
+          <span>© {year} POLARIS · Sovereign Canadian deep research</span>
+          <span>
+            LLM inference is currently routed via OpenRouter (US), disclosed at{" "}
+            <Link
+              href="/transparency"
+              className="hover:text-foreground underline underline-offset-2"
+            >
+              /transparency
+            </Link>
+            .
+          </span>
+        </div>
+      </div>
+    </footer>
+  );
+}

```
