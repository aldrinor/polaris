import Link from "next/link";

import { PrimaryNav } from "@/components/primary_nav";

/**
 * I-cd-004: the global app shell. A server component that wraps every prod
 * route with a single header + primary nav. The 8 primary nav entries are
 * the Codex-APPROVED prod route map (see docs/web/route_map.md):
 *   Home · Intake · Dashboard · Upload · Benchmark · Contracts · Pin Replay · Memory
 *
 * Out of scope for this issue (each its own later issue per the Seq-N order):
 *  - /sign-in: handled by I-cd-014's auth rebuild; not surfaced in the nav.
 *  - /inspector/[runId] + /runs/[runId]: run-scoped, deep-linked from
 *    /dashboard rather than top-nav entries.
 *  - /audit_live: ABSORBED into /runs/[runId] at I-cd-025; standalone route
 *    retired at that point (not merely hidden — per Codex P2).
 *  - /generation, /retrieval, /sse: CUT-from-prod; prod-build exclusion is
 *    I-cd-015.
 *  - Auth gating of the nav itself is deferred to I-cd-014.
 *  - Per-page rebuilds happen in the I-cd-013..030 series.
 */
// I-p2-029 (#768): PRIMARY_NAV now lives in @/lib/nav (single source of truth,
// shared with HomeKeyboardShell); role-aware via navForRole (presentation-only).

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-border bg-background sticky top-0 z-40 border-b">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
          <Link
            href="/"
            className="text-foreground font-mono text-sm font-semibold tracking-tight"
          >
            POLARIS · Canada
          </Link>
          <PrimaryNav />
          {/* I-p2-023 (#762): sovereign mark — HONEST. Dropped the false
              present-tense "no external AI vendor": production LLM inference
              currently routes via OpenRouter (US, transitional, disclosed in
              /transparency) until the sovereign Canadian GPU cluster lands. The
              VM IS hosted in OVH Québec, so "Canadian-hosted" is true today. */}
          <span
            className="text-muted-foreground border-border ml-auto hidden rounded-full border px-2.5 py-1 text-xs sm:inline-flex"
            title="Hosted in Canada (Québec); public sources fetched via logged Canadian egress. LLM inference is currently routed via OpenRouter (US, disclosed in /transparency) pending the sovereign Canadian GPU cluster."
          >
            ⬡ Canadian-hosted
          </span>
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </>
  );
}
