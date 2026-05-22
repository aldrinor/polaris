# Codex BRIEF review — I-p2-011 (#750): empty / loading / error states kit

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
A reusable **empty / loading / error states kit** every page uses — so states are consistent + honest (G-CONTENT: no generic "Something went wrong" / bare spinners).

## Verified current state (grounded)
- NO existing EmptyState/LoadingState/ErrorState/Skeleton components (only sonner toast). Build from scratch.
- #742 tokens; G-CONTENT gate (operational + specific copy); G-PERF (reduced-motion); G-RESP.

## Acceptance criteria (diff implements; brief reviews the plan)
1. `web/components/states/state_kit.tsx` exporting 3 components:
   - `EmptyState`: props {title, description?, icon?: LucideIcon, action?: ReactNode}. Centered, hairline, muted — neutral (not an error). Specific title (caller supplies; no generic placeholder).
   - `LoadingState`: props {label?: string, rows?: number}. Skeleton rows (animate-pulse) OR a labeled spinner; `role="status"` + `aria-busy` + an accessible label (default "Loading…", caller can specialise e.g. "Retrieving sources…"); **reduced-motion**: no pulse/spin under prefers-reduced-motion (static placeholder).
   - `ErrorState`: props {title?: string, message: string (REQUIRED — the specific error), onRetry?: () => void}. `role="alert"`; the message is shown verbatim (no generic "Something went wrong"); optional Retry button (focus-visible). Uses --destructive sparingly (not full-red panel).
2. Honest copy (G-CONTENT): ErrorState requires a specific message prop (the type makes generic impossible); LoadingState label is operational; EmptyState is neutral not alarming.
3. Frontier-Minimal; WCAG 2.2 (role=status/alert, reduced-motion, focus-visible, AA); responsive.

## Files I have ALSO checked and they're clean
- web/app/globals.css (#742 tokens + the prefers-reduced-motion handling), web/components/ui/ (no existing state primitives — confirmed), web/components/verdict/verdict_chip.tsx (lucide usage pattern).

## Review focus
1. Does the API force honest states (ErrorState.message REQUIRED so generic copy is impossible; reduced-motion on the loader)?
2. a11y: role=status/aria-busy on loading, role=alert on error, focus-visible on retry, reduced-motion?
3. Right tokens (destructive sparingly; empty=neutral). Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 corrections (all iter-1 findings folded)
- **P1 (scope):** #750 ships the reusable KIT only. Pages ADOPT it as they are rebuilt in #752-762 (each page's design audit checks adoption); legacy/retiring pages (audit_live, sse — being cut) are NOT migrated here (avoids churn + scope creep). The brief's "every page uses the kit" = the kit is the standard pages adopt going forward, NOT a same-PR migration of all existing pages. State this scope explicitly in the issue.
- **P1 (generic-copy guardrail):** ErrorState adds a DEV-ONLY guard: if `message` matches a generic blocklist (/something went wrong|unknown error|failed to load|an error occurred/i) AND `process.env.NODE_ENV !== "production"`, `console.warn` a G-CONTENT reminder. Type still requires `message`; the warn catches lazy generic copy in dev. (Full enforcement = the per-page G-CONTENT design audit.)
- **P2 (reduced-motion):** handle LOCALLY — skeleton/spinner use `motion-reduce:animate-none` (Tailwind variant) so reduced-motion users get a static placeholder; do NOT rely on globals.css (it has no prefers-reduced-motion rule).
Re-confirm APPROVE or list only true remaining P0/P1.
