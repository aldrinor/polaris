# Codex Brief Review — I-f7-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan.

## Pre-flight

- **Context:** I-f7-003 — each gap row is clickable. Click opens a detail panel showing:
  - The gap entity_name + reason label + reason_detail.
  - A documented "unblock action" — a per-reason-enum copy-to-clipboard suggestion (e.g. for `paywalled`: "Search PMC OA mirror for `<entity_name>`"; for `no_oa`: "Email author for preprint of `<entity_name>` Cochrane review").
  - Copy-to-clipboard button with confirmation.
- **Constraints:** No backend change — UI-only addition consuming I-f7-002's frozen enum.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Frontend
1. `web/app/generation/components/frame_coverage_panel.tsx`:
   - Add `UNBLOCK_ACTION: Record<GapReason, string>` mapping each reason to a per-entity actionable suggestion template (use `${entity_name}` placeholder).
   - Wrap each gap `<li>` as a clickable row (role="button", tabIndex, onClick, Enter/Space keyboard support).
   - Add local state `selectedGap: number | null`. On click, set selectedGap to that gap's index.
   - Render a detail Sheet (reuse existing @base-ui/react Sheet from sentence_inspector) when `selectedGap !== null`, containing:
     - Heading: entity_name + GAP_REASON_LABEL[reason].
     - Detail paragraph: reason_detail (or "No additional detail provided.").
     - Action text: substituted UNBLOCK_ACTION[reason] template.
     - Copy-to-clipboard button using `navigator.clipboard.writeText`. Testid `frame-gap-copy-button`.
     - "Copied!" confirmation that flashes for 2s after click.
2. `web/tests/e2e/frame_coverage_panel.spec.ts`: add 2 new tests:
   - Click gap → detail Sheet visible with `frame-gap-detail-sheet` testid + UNBLOCK_ACTION text containing entity_name.
   - Click copy button → "Copied!" badge flashes (`frame-gap-copy-confirm`).

## Risks for Codex Red-Team
1. **navigator.clipboard requires HTTPS or localhost:** Playwright tests use http://127.0.0.1 — works. Production deploys must be HTTPS — already required for SSE per F4.
2. **Sheet re-use:** import the same Sheet primitive used by sentence_inspector to avoid divergent patterns.
3. **Keyboard a11y:** role="button" + tabIndex={0} + Enter/Space handler per existing SentenceRow pattern (I-f5-002).
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~130 LOC. Under 200.

## Acceptance criteria

1. Each gap row is clickable + keyboard-activatable.
2. Detail Sheet renders with entity_name + reason label + detail.
3. UNBLOCK_ACTION mapping covers all 9 GapReason enum values.
4. Action text substitutes `${entity_name}` placeholder.
5. Copy-to-clipboard button with confirmation badge.
6. 2 new Playwright tests cover open + copy.
7. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-7.

**Completeness check:** list files actually read.

## Output schema

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
