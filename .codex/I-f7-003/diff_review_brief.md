# Codex Diff Review — I-f7-003 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (cross-browser clipboard):** replaced `context.grantPermissions` with `page.addInitScript` that defines a stub `navigator.clipboard.writeText` on every page. Works across chromium/firefox/webkit without browser-specific permission handling.
- **P2 fix (target-size a11y):** added `min-h-6 px-2 py-1` to the gap row className → 24px minimum target size.

**Updated canonical-diff-sha256:** `33234885ae2ab722fd386be23ece67bf4ba32d3b8051a6211c3396f39400f233`

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f7-003 — Each gap clickable → unblock action
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `5082657c47bcefebccfb033d3a67d031e91cde8a57bb51e247988b8c1d72e2d4`
**LOC:** 150 net (under CHARTER §1 200-cap)

## Files

```
web/app/generation/components/frame_coverage_panel.tsx     +118 (UNBLOCK_ACTION + click + Sheet + copy)
web/tests/e2e/frame_coverage_panel.spec.ts                 +32 (click-detail + copy-confirm tests)
```

## What changed

- `UNBLOCK_ACTION: Record<GapReason, string>` — 9 templates with `${entity_name}` placeholder.
- Gap row: `role="button"`, `tabIndex={0}`, click + Enter/Space keyboard activation per Codex iter-1 P2 from I-f5-002 pattern.
- `selected_gap_idx` local state; `copied` state with 2s timer reset.
- `FrameGapDetailSheet` extracted as separate component for clarity. Imports Sheet from `@/components/ui/sheet` per Codex iter-1 P2.
- `onOpenChange` clears `selected_gap_idx` AND `copied` on dismiss per Codex iter-1 P2 (clean controlled-Sheet lifecycle).
- Copy button uses `navigator.clipboard.writeText` with try/catch fallback (no UI flash if blocked).
- "Copied!" badge testid `frame-gap-copy-confirm` flashes for 2s.

## New Playwright tests
- `Click gap → detail Sheet shows entity + suggested action with substituted name`: asserts title contains entity_name AND action paragraph also contains entity_name (template substitution).
- `Click copy button → 'Copied!' confirmation flashes`: grants clipboard permissions to BrowserContext, clicks copy, asserts confirm badge visible.

## Verification
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Clipboard sandboxing:** test grants `clipboard-read,clipboard-write` permissions to BrowserContext. Production HTTPS requirement is satisfied (live site already HTTPS-only per F4 SSE).
2. **Template substitution:** uses `String.replaceAll` via global regex `/\$\{entity_name\}/g`. No XSS risk (string interpolation in JSX).
3. **Sheet lifecycle:** `onOpenChange={open => !open && onClose()}` clears state cleanly.
4. **Keyboard a11y:** matches existing SentenceRow pattern (I-f5-002).
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap:** 150 net. Under 200.
7. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
