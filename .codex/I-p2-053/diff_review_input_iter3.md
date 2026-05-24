# Codex DIFF review — I-p2-053 (#853): Memory rebuild + S-tier tracker — iter 3 of 5

HARD ITERATION CAP: 5. iter 3. iter-2 APPROVE'd the memory page. This iter the canonical diff is
re-cut to ALSO include the docs change the PR carries (the codex-required CI gate's canonical sha
covers everything except .codex/<id>/ + outputs/audits/<id>/, so docs/web/s_tier_design_system.md
must be reviewed too — it was committed alongside but not in the iter-2 reviewed diff).

## What's in this canonical diff (2 files)
1. web/app/memory/page.tsx — unchanged since the iter-2 APPROVE (design-system rebuild + state-kit
   + IIFE-in-effect lint fix). Re-review for completeness.
2. docs/web/s_tier_design_system.md — appends a "Cred-gated pages" subsection to the per-screen
   tracker recording Dashboard (#849, A/A-/A), Benchmark (#851, A/A-/A-/A-/A) and Memory (#853,
   A/A-/A) grades + a note that source-review + Plan→Run→Compare remain. Documentation only.

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

## Already gated
- Visual `-i` APPROVE iter-2 (desktop A / mobile A- / empty A). Code diff APPROVE iter-2 (page).
- canonical-diff-sha256: 8844a3f68e2f7f50da36a90fe634694815f1bc3457fac1a11be84616cb3978cd
- VERIFIED LOCALLY: eslint app/memory/page.tsx clean; tsc clean; prettier clean.

## Review focus
- The docs claims match what shipped (the recorded grades + the honest "LIVE-populated verify
  deferred" framing). No overclaim. No code risk in the docs change.

## The full canonical diff (memory page + docs)
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index ed30c1e0..a13da376 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -119,6 +119,28 @@ span highlights, and verdict badges appear consistently across the product.
 
 **All 7 PUBLIC pages now at the A bar** (Inspector A/A-/A/A- · Home A/A-/A- · Intake A-/A- ·
 Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Codex-gated
-(visual `-i` + code) → merged → deployed → verified live. Remaining UI: the cred-gated journey
-(dashboard / benchmark / memory / source-review / Plan→Run→Compare) — blocked on demo creds in
-the VM `.env`.
+(visual `-i` + code) → merged → deployed → verified live.
+
+### Cred-gated pages (rendered locally via seeded session + route-mocked fixture; LIVE-populated verify deferred to reviewer creds)
+
+- **Dashboard / Runs** (#849, I-p2-051): **desktop A / mobile A- / empty A** (Codex visual iter-1
+  APPROVE). Fixed a real CJK-date locale bug (`toLocaleDateString(undefined)` → `"en-CA"`; same
+  fix on Home's `recent_runs_strip`), elevated the runs list (`shadow-card`), mobile title
+  `line-clamp-2`.
+- **Benchmark** (#851, I-p2-052): **desktop A / mobile A- / empty A- / error A- / list A** (Codex
+  visual iter-2 APPROVE). Replaced dev-language amber/rose state cards (leaked
+  `POLARIS_BENCHMARK_RESULTS_DIR` / `scripts/run_benchmark.py`) with the state-kit + tokens;
+  headline tally, brand POLARIS column, tabular-nums, `--verified` winners, dash + "POLARIS-only"
+  for unreported peer dims, readable stacked mobile. Removed a hardcoded "scores 1.0" overclaim
+  (LAW II) — capability claim, scores come from the published scoreboard. The empty state is the
+  live-visible state.
+- **Memory** (#853, I-p2-053): **desktop A / mobile A- / empty A** (Codex visual iter-2 APPROVE).
+  Was the rawest cred-gated page (raw controls, raw enum labels, `bg-blue-500`/`bg-rose-500`, NO
+  loading/error/empty states). Rebuilt to the design system: Card form (human kind labels, raw
+  option values preserved for the e2e), state-kit states, meaning-tinted kind chips
+  (preferred=verified / rejected=refusal / rest neutral, brand reserved for the Remember action),
+  3-line rows + "SAVED MEMORY · N". Fixed a `react-hooks/set-state-in-effect` lint blocker (Codex
+  diff P1) via the codebase IIFE-in-effect idiom.
+
+Remaining cred-gated UI: source-review + the Plan→Run→Compare journey. LIVE-populated verification
+of all cred-gated pages awaits the demo reviewer credential.
diff --git a/web/app/memory/page.tsx b/web/app/memory/page.tsx
index 57f4f024..cbc96d27 100644
--- a/web/app/memory/page.tsx
+++ b/web/app/memory/page.tsx
@@ -1,7 +1,16 @@
 "use client";
 
+import { Brain, Trash2 } from "lucide-react";
 import { useEffect, useState } from "react";
 
+import {
+  EmptyState,
+  ErrorState,
+  LoadingState,
+} from "@/components/states/state_kit";
+import { Button } from "@/components/ui/button";
+import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
+import { cn } from "@/lib/utils";
 import {
   forgetMemory,
   listMemory,
@@ -12,29 +21,95 @@ import {
 import { formatRelative } from "@/lib/relative_time";
 
 const WS = "ws_demo";
-const KINDS: MemoryKind[] = [
-  "user_preference",
-  "domain_assumption",
-  "prior_run_summary",
-  "rejected_source",
-  "preferred_source",
-];
+
+// Human-readable labels — the raw enum value stays the <option value> (the
+// memory_page_controls e2e selects by value, e.g. "rejected_source").
+const KIND_LABELS: Record<MemoryKind, string> = {
+  user_preference: "Preference",
+  domain_assumption: "Domain assumption",
+  prior_run_summary: "Prior run",
+  preferred_source: "Preferred source",
+  rejected_source: "Rejected source",
+};
+const KINDS = Object.keys(KIND_LABELS) as MemoryKind[];
+
+// Meaning-only tinting (tokens, never raw palette): a preferred source reads as
+// verified-positive, a rejected source as refusal-neutral, the rest neutral.
+const KIND_TONE: Record<MemoryKind, string> = {
+  user_preference: "border-border bg-muted/50 text-muted-foreground",
+  domain_assumption: "border-border bg-muted/50 text-muted-foreground",
+  // Brand red is reserved for the single primary action (Remember); a prior run
+  // gets a stronger-neutral chip, not the accent.
+  prior_run_summary: "border-foreground/15 bg-foreground/5 text-foreground",
+  preferred_source: "border-verified/30 bg-verified/10 text-verified",
+  rejected_source: "border-refusal/30 bg-refusal/10 text-refusal",
+};
+
+const FIELD_CLASS =
+  "border-input bg-transparent focus-visible:border-ring focus-visible:ring-ring/70 w-full rounded-lg border px-2.5 py-1.5 text-sm transition-colors outline-none focus-visible:ring-3";
+
+const MEMORY_UNAVAILABLE_MESSAGE =
+  "The workspace memory service did not respond.";
+
+type LoadState =
+  | { kind: "loading" }
+  | { kind: "ok"; entries: MemoryEntry[] }
+  | { kind: "error"; message: string };
 
 export default function MemoryPage() {
-  const [entries, setEntries] = useState<MemoryEntry[]>([]);
+  const [state, setState] = useState<LoadState>({ kind: "loading" });
   const [content, setContent] = useState("");
   const [kind, setKind] = useState<MemoryKind>("user_preference");
+  const [saving, setSaving] = useState(false);
+
+  // reload is used by the save/forget handlers (event handlers, not effects). On
+  // reload we keep the current list visible until fresh data arrives (no flash);
+  // the initial useState is already "loading" so first mount shows the skeleton.
+  const reload = async () => {
+    try {
+      setState({ kind: "ok", entries: await listMemory(WS) });
+    } catch (err) {
+      setState({
+        kind: "error",
+        message:
+          err instanceof Error ? err.message : MEMORY_UNAVAILABLE_MESSAGE,
+      });
+    }
+  };
 
+  // Initial load: an inline async IIFE with a cancelled guard. setState happens
+  // inside the IIFE (after the await), not synchronously in the effect body —
+  // the codebase's data-fetching-effect idiom, clean under
+  // react-hooks/set-state-in-effect.
   useEffect(() => {
-    listMemory(WS).then((d) => queueMicrotask(() => setEntries(d)));
+    let cancelled = false;
+    void (async () => {
+      try {
+        const data = await listMemory(WS);
+        if (!cancelled) setState({ kind: "ok", entries: data });
+      } catch (err) {
+        if (!cancelled)
+          setState({
+            kind: "error",
+            message:
+              err instanceof Error ? err.message : MEMORY_UNAVAILABLE_MESSAGE,
+          });
+      }
+    })();
+    return () => {
+      cancelled = true;
+    };
   }, []);
 
-  const reload = async () => setEntries(await listMemory(WS));
-
   const onSave = async () => {
-    await rememberMemory(WS, { kind, content });
-    setContent("");
-    await reload();
+    setSaving(true);
+    try {
+      await rememberMemory(WS, { kind, content });
+      setContent("");
+      await reload();
+    } finally {
+      setSaving(false);
+    }
   };
 
   const onForget = async (id: string) => {
@@ -42,102 +117,180 @@ export default function MemoryPage() {
     await reload();
   };
 
+  const entries = state.kind === "ok" ? state.entries : [];
   const sorted = [...entries].sort((a, b) =>
     b.created_at.localeCompare(a.created_at),
   );
-  const recent_runs = sorted.filter((e) => e.kind === "prior_run_summary");
+  const recentRuns = sorted.filter((e) => e.kind === "prior_run_summary");
 
-  // I-cd-030 (#620): /memory rebuild — G1+G6 fix. Page no longer renders
-  // its own <main>; AppShell (via AppShellGate from I-cd-022) is the
-  // single landmark provider. G2 fix: remove Issue-id breadcrumb
-  // ("I-f14-002b") from user-visible copy.
   return (
-    <section data-testid="memory-page" className="mx-auto max-w-3xl px-6 py-8">
-      <h1 className="text-2xl font-semibold tracking-tight">
-        Workspace memory
-      </h1>
-      <p
-        data-testid="memory-banner"
-        className="text-muted-foreground mt-2 text-sm"
-      >
-        Demo workspace <code>{WS}</code>. Save and forget actions are live;
-        additional pin controls land in a follow-up release.
-      </p>
-      {recent_runs.length > 0 ? (
-        <section
-          data-testid="recent-runs"
-          className="border-border mt-4 rounded border p-3"
+    <section
+      data-testid="memory-page"
+      className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-10"
+    >
+      <div className="flex flex-col gap-1">
+        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
+          Workspace memory
+        </h1>
+        <p
+          data-testid="memory-banner"
+          className="text-muted-foreground text-sm"
         >
-          <h2 className="text-sm font-semibold">Recent research</h2>
-          <ul className="mt-2 space-y-1 text-sm">
-            {recent_runs.map((e) => (
+          What this workspace carries between runs — preferences, domain
+          assumptions, and the sources it has learned to trust or reject. Save
+          and forget are live in demo workspace <code>{WS}</code>; richer pin
+          controls land in a follow-up release.
+        </p>
+      </div>
+
+      {/* Remember something */}
+      <Card>
+        <CardHeader>
+          <CardTitle className="text-base">Remember something</CardTitle>
+        </CardHeader>
+        <CardContent className="flex flex-col gap-3">
+          <div className="flex flex-col gap-1.5">
+            <label
+              htmlFor="memory-kind"
+              className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
+            >
+              Kind
+            </label>
+            <select
+              id="memory-kind"
+              data-testid="memory-save-kind"
+              value={kind}
+              onChange={(e) => setKind(e.target.value as MemoryKind)}
+              className={FIELD_CLASS}
+            >
+              {KINDS.map((k) => (
+                <option key={k} value={k}>
+                  {KIND_LABELS[k]}
+                </option>
+              ))}
+            </select>
+          </div>
+          <div className="flex flex-col gap-1.5">
+            <label
+              htmlFor="memory-content"
+              className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
+            >
+              What should the workspace remember?
+            </label>
+            <textarea
+              id="memory-content"
+              data-testid="memory-save-content"
+              value={content}
+              onChange={(e) => setContent(e.target.value)}
+              rows={3}
+              placeholder="e.g. Prefer Health Canada and CMHC as primary sources."
+              className={cn(FIELD_CLASS, "min-h-20 resize-y")}
+            />
+          </div>
+          <Button
+            type="button"
+            data-testid="memory-save"
+            onClick={onSave}
+            disabled={content.trim().length < 4 || saving}
+            className="self-start"
+          >
+            {saving ? "Saving…" : "Remember"}
+          </Button>
+        </CardContent>
+      </Card>
+
+      {/* Prior research surfaced from memory */}
+      {recentRuns.length > 0 ? (
+        <Card data-testid="recent-runs">
+          <CardHeader>
+            <CardTitle className="text-base">Prior research</CardTitle>
+          </CardHeader>
+          <CardContent>
+            <ul className="flex flex-col gap-2">
+              {recentRuns.map((e) => (
+                <li
+                  key={e.entry_id}
+                  data-testid={`recent-run-${e.entry_id}`}
+                  className="text-muted-foreground flex flex-wrap items-baseline gap-x-2 text-sm"
+                >
+                  <span className="text-foreground">{e.content}</span>
+                  <span className="text-xs">
+                    · {formatRelative(e.created_at)}
+                  </span>
+                </li>
+              ))}
+            </ul>
+          </CardContent>
+        </Card>
+      ) : null}
+
+      {/* The memory list */}
+      {state.kind === "loading" ? (
+        <LoadingState label="Loading workspace memory…" rows={4} />
+      ) : null}
+
+      {state.kind === "error" ? (
+        <ErrorState
+          title="Couldn't load workspace memory"
+          message={state.message}
+        />
+      ) : null}
+
+      {state.kind === "ok" && sorted.length === 0 ? (
+        <EmptyState
+          icon={Brain}
+          title="This workspace remembers nothing yet"
+          description="Save a preference, a domain assumption, or a source to trust — it will be reused on the next run and shown here, fully editable."
+        />
+      ) : null}
+
+      {state.kind === "ok" && sorted.length > 0 ? (
+        <div className="flex flex-col gap-2">
+          <h2 className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
+            Saved memory · {sorted.length}
+          </h2>
+          <ul className="flex flex-col gap-2" data-testid="memory-list">
+            {sorted.map((e) => (
               <li
                 key={e.entry_id}
-                data-testid={`recent-run-${e.entry_id}`}
-                className="text-muted-foreground"
+                data-testid={`memory-row-${e.entry_id}`}
+                className="border-border bg-card shadow-card flex flex-col gap-2 rounded-xl border p-4 text-sm"
               >
-                <span className="text-foreground">{e.content}</span>{" "}
-                <span>· {formatRelative(e.created_at)}</span>
+                {/* Row 1: kind chip (left) + Forget (right) — never squeezed. */}
+                <div className="flex items-start justify-between gap-3">
+                  <span
+                    className={cn(
+                      "rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase",
+                      KIND_TONE[e.kind],
+                    )}
+                  >
+                    {KIND_LABELS[e.kind]}
+                  </span>
+                  <button
+                    type="button"
+                    data-testid={`memory-forget-${e.entry_id}`}
+                    onClick={() => onForget(e.entry_id)}
+                    aria-label={`Forget: ${e.content}`}
+                    className="border-border text-muted-foreground hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive focus-visible:ring-ring/70 ease-standard inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none"
+                  >
+                    <Trash2 aria-hidden className="h-3.5 w-3.5" />
+                    Forget
+                  </button>
+                </div>
+                {/* Row 2: content. Row 3: meta footer. */}
+                <p className="text-foreground break-words">{e.content}</p>
+                <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
+                  <span className="font-mono">{e.entry_id.slice(0, 8)}</span>
+                  <span>· {formatRelative(e.created_at)}</span>
+                  {e.use_count > 0 ? (
+                    <span>· reused {e.use_count}×</span>
+                  ) : null}
+                </div>
               </li>
             ))}
           </ul>
-        </section>
+        </div>
       ) : null}
-      <div className="border-border mt-4 space-y-2 rounded border p-3">
-        <select
-          data-testid="memory-save-kind"
-          value={kind}
-          onChange={(e) => setKind(e.target.value as MemoryKind)}
-          className="border-border bg-background w-full rounded border px-2 py-1 text-sm"
-        >
-          {KINDS.map((k) => (
-            <option key={k} value={k}>
-              {k}
-            </option>
-          ))}
-        </select>
-        <textarea
-          data-testid="memory-save-content"
-          value={content}
-          onChange={(e) => setContent(e.target.value)}
-          rows={2}
-          placeholder="What should the workspace remember?"
-          className="border-border bg-background w-full rounded border px-2 py-1 text-sm"
-        />
-        <button
-          type="button"
-          data-testid="memory-save"
-          onClick={onSave}
-          disabled={content.length < 4}
-          className="border-border rounded border px-3 py-1 text-sm hover:bg-blue-500/10 disabled:opacity-50"
-        >
-          Save
-        </button>
-      </div>
-      <ul className="mt-4 space-y-2" data-testid="memory-list">
-        {sorted.map((e) => (
-          <li
-            key={e.entry_id}
-            data-testid={`memory-row-${e.entry_id}`}
-            className="border-border flex items-start justify-between gap-3 rounded border p-3 text-sm"
-          >
-            <div>
-              <div className="text-muted-foreground text-xs">
-                {e.kind} · {e.entry_id.slice(0, 8)}
-              </div>
-              <div>{e.content}</div>
-            </div>
-            <button
-              type="button"
-              data-testid={`memory-forget-${e.entry_id}`}
-              onClick={() => onForget(e.entry_id)}
-              className="border-border shrink-0 rounded border px-2 py-1 text-xs hover:bg-rose-500/10"
-            >
-              Forget
-            </button>
-          </li>
-        ))}
-      </ul>
     </section>
   );
 }

# canonical-diff-sha256: 8844a3f68e2f7f50da36a90fe634694815f1bc3457fac1a11be84616cb3978cd

```
