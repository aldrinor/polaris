# Codex Brief Review — I-f5-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f5-002 — Click → Inspector pane (Sheet, 40% width)
**Phase:** 1 / **Feature:** F5
**LOC budget:** 130 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: shadcn Sheet from right. Playwright click sentence → Sheet opens.

## Substrate (HONEST at HEAD)

- `web/components/ui/sheet.tsx` exists at HEAD (Sheet, SheetContent, SheetHeader, SheetTitle, etc., wrapping @base-ui/react Dialog).
- I-f5-001 wired hover-highlight via `data-sentence-id` attribute on each `<li>`.

## Approach

**Part 1 — `web/app/generation/components/sentence_inspector.tsx`** (NEW, ~70 LOC):
- `SentenceInspector({ sentence_id, sentence, open, onOpenChange })` Client component.
- Renders `<Sheet open={open} onOpenChange={onOpenChange}>` with `<SheetContent side="right" className="w-2/5 sm:max-w-none">` (40% width).
- Header: `<SheetTitle>` showing sentence_id, sentence_text excerpt.
- Body: provenance tokens, drop_reason if present, placeholder for source span/URL/tier (I-f5-003).
- `data-testid="sentence-inspector-sheet"`.

**Part 2 — `web/app/generation/components/verified_report_view.tsx`** (EDIT, ~30 LOC):
- Add click handler on each `<li>`: `onClick={() => setInspector({ sentence_id, sentence })}`.
- Maintain `inspector` state at top level; pass `open` + sentence to `<SentenceInspector />`.

**Part 3 — `web/tests/e2e/sentence_inspector.spec.ts`** (NEW, ~30 LOC):
- Navigate `/sentence_hover_test`; click `[data-sentence-id="sec_x:5"]`; assert `sentence-inspector-sheet` visible within 500ms; assert sentence-id text present in sheet.

## Acceptance criteria (binding)

1. `web/app/generation/components/sentence_inspector.tsx` NEW.
2. `web/app/generation/components/verified_report_view.tsx` EDIT — click handler + Inspector mount.
3. `web/tests/e2e/sentence_inspector.spec.ts` NEW.

## Planned diff shape

```
web/app/generation/components/sentence_inspector.tsx   NEW +70
web/app/generation/components/verified_report_view.tsx EDIT +30
web/tests/e2e/sentence_inspector.spec.ts               NEW +30
```

LOC: +130 net. AT breakdown 130 budget. Under CHARTER §1 200-cap by 70.

## Out of scope

- Source span + URL + tier rendering → I-f5-003.
- Two-family evaluator agreement signal → I-f5-004.

## Risks for Codex Red-Team

1. **Sheet from @base-ui/react Dialog** — wrap in Suspense not needed (no useSearchParams).
2. **Click handler vs hover** — onClick + onMouseOver coexist; click does not trigger hover-highlight removal.
3. **State at SectionCard or top-level?** Must be top-level (VerifiedReportView) for one Sheet shared across all sections.
4. **40% width** — tailwind `w-2/5` (40%); on small screens default to full width per shadcn sheet behavior.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 130 net.
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
