# Per-commit Codex brief — `3cf4737`

**Commit:** `3cf4737 PL: v6.2 F-7+F-8 + cycle-2 audit/cross-review`
**Format:** v2 minimal
**Files changed (5):**
- `web/app/dashboard/page.tsx` (-1/+1) — F-7
- `web/app/inspector/[runId]/page.tsx` (-1/+1) — F-7
- `web/components/ui/button.tsx` (-1/+1) — F-8
- `outputs/audits/continuous/909eb4c_audit.md` (new) — cycle-2 audit deliverable
- `outputs/audits/continuous/909eb4c_cross_review.md` (new) — my cross-review

## What this commit does

Closes the cycle-2 audit's only P1 (un-enumerated lone `text-destructive` surfaces) and the P3.3 latent landmine in the destructive Button variant. Both are root_cause fixes per `memory/autoloop_v2_audit_cross_review.md` (band_aid would be RED).

**F-7** (`text-destructive` on light bg → light-bg-clean pattern):
- `dashboard/page.tsx:324` — "remove" button on upload list. Was 4.04:1 contrast.
- `inspector/[runId]/page.tsx:315` — "Dropped: <reason>" annotation. Same.
- Both: now `text-foreground font-medium` (cleared pattern from cycle-1 F-1).

**F-8** (`button.tsx` `variant="destructive"`):
- Was `bg-destructive/10 text-destructive` — exactly the cycle-1 P1.1 hazardous pattern.
- Currently 0 usages (`grep -rn 'variant="destructive"' web/` returns nothing) so no UI change today.
- New: `border-destructive/60 text-foreground font-medium` — first user can now adopt safely.

Cycle-2 audit + cross-review committed alongside (peer artefacts to `4fe03f7_*`).

Verified: 25/25 e2e (a11y + inspector + perf + hover) PASS in 30s. typecheck clean.

## Acceptance criteria

1. **Same root-cause approach as F-1**: mechanical class-string swap to the proven-clean light-bg pattern. Identical pattern across all newly-fixed surfaces. Codex grep `text-destructive` in `web/app/` should return zero hits in static (non-test) production code paths.
2. **Button variant hardened preemptively** even though dead code today. Future contributor can use `variant="destructive"` without re-introducing the cycle-1 bug.
3. **No new tests in this commit**. F-7b (test coverage for the failure paths that render the now-fixed surfaces) ships as a separate commit. Reviewer should treat the test gap as `guardrail` work pending in F-7b.
4. **Audit + cross-review files are durable.** Now under git tracking via the `outputs/audits/` exemption added in commit `b012a17`.
5. **No regression in existing tests**: 25/25 e2e PASS post-build.

## Codex focus

- **P0:** Run `grep -rEn "text-destructive[^-]" web/app/ web/components/` after this commit lands. Any hits = miss. (`text-destructive-foreground` is OK; that's a different token.)
- **P1:** F-8 changes the destructive Button visual identity from "tinted-red surface" to "border-only red border" — visual-design choice that future UI work might want to revisit. Not a regression today (zero usages) but worth flagging for the design audit.
- **P2:** Should we add a CI gate that fails on any `text-destructive` literal in `web/app/`? E.g., a custom ESLint rule. Defends against the F-1/F-7 enumeration-miss class entirely.

## Cross-review

Lands at `outputs/audits/continuous/3cf4737/cross_review.md`. **Counter at 5/5** (post-909eb4c batch: dbe62e0, cc10303, 8ae03b6, 9fe4de9, 3cf4737). Cycle-3 adversarial subagent fires after the next substrate commit (likely F-7b a11y tests).
