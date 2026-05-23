# Codex diff review (ITER 3/5) — I-p2-038 (#821): app-shell footer + auth button

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings. No drip-feeding. Same quality bar each iter.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Don't bank a P1 for a later round — surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Trajectory
- iter 1: APPROVE (zero P0/P1; one deferred P2 = header tablet budget).
- iter 2: APPROVE (after fixing the auth_button setState-in-effect lint error → useSyncExternalStore).
- iter 3 (this): ONE more change — the SiteFooter honesty fix (below).

## ITER-3 DELTA (the ONLY change since iter-2 APPROVE)
The separate Codex BRIEF review flagged a P1 honesty issue (AC2): the footer said
"Sovereign Canadian deep research" (tagline + bottom bar), which overclaims
sovereignty while production LLM inference is OpenRouter (US). Fixed: both
instances now read "Canadian-hosted deep research" — matching the header
"Canadian-hosted" mark + the footer's OpenRouter/`/transparency` disclosure. No
other change. The brief review re-ran → APPROVE. Footer now contains NO "Sovereign"
string.

Please CONFIRM:
1. The footer copy is now honest (no sovereignty overclaim) and §-1.1 / LAW II compliant.
2. No NEW issue introduced by the copy change.
3. Verdict for the FULL diff below (this is exactly what will merge).

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

## The full diff (what merges)
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
index 00000000..e4a4d9e1
--- /dev/null
+++ b/web/components/auth_button.tsx
@@ -0,0 +1,62 @@
+// I-p2-038 (#821): auth-aware Sign in / Sign out for the AppShell header.
+// Before this, AppShell (every non-home route) had NO auth affordance at all —
+// an unauthenticated reviewer who navigated off the home page had no way to
+// sign in, and a signed-in reviewer had no way to sign out anywhere.
+//
+// Auth state lives in sessionStorage (not React state), so we read it via
+// useSyncExternalStore: SSR-safe (getServerSnapshot returns the unauthenticated
+// "Sign in" view, matching the first client paint → no hydration mismatch) and
+// without a setState-in-effect (which the react-hooks/set-state-in-effect lint
+// rule forbids — see #805).
+"use client";
+
+import Link from "next/link";
+import { useRouter } from "next/navigation";
+import { useSyncExternalStore } from "react";
+
+import { Button } from "@/components/ui/button";
+import { clearToken, isAuthenticated } from "@/lib/auth";
+
+// Cross-tab auth changes fire a `storage` event; same-tab sign-in/out re-mounts
+// the shell on navigation, so the snapshot is re-read either way.
+function subscribe(onChange: () => void): () => void {
+  if (typeof window === "undefined") return () => {};
+  window.addEventListener("storage", onChange);
+  return () => window.removeEventListener("storage", onChange);
+}
+
+export function AuthButton() {
+  const router = useRouter();
+  const authed = useSyncExternalStore(
+    subscribe,
+    () => isAuthenticated(), // client: real auth state (boolean — stable by value)
+    () => false, // server / first hydration paint: always "Sign in"
+  );
+
+  if (authed) {
+    return (
+      <Button
+        variant="ghost"
+        data-testid="appshell-sign-out"
+        onClick={() => {
+          clearToken();
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
index 00000000..429800e0
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
+            Canadian-hosted deep research. Every claim in a POLARIS brief is
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
+          <span>© {year} POLARIS · Canadian-hosted deep research</span>
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
