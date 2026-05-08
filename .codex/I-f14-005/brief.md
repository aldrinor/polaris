# Codex Brief Review — I-f14-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f14-005 — Cited recall. Scope: when memory contributes, surface which past run + claim. Acceptance: Playwright shows cite-in-current. LOC estimate 100.
- **Substrate today:** I-f14-004 added `ev_memory_*` evidence_id prefix for prior_run_summary entries surfaced into the evidence pool. `verified_report_view.tsx:127` already parses `\[#ev:([a-zA-Z0-9_\-]+):` from provenance_tokens. No memory-specific badge yet.
- **Honest framing per CLAUDE.md §9.4:** detect provenance tokens whose evidence_id starts with `ev_memory_` and render an inline "from prior run" badge under the sentence. The badge text comes from frontend-derived data (the evidence_id itself) since the page doesn't yet have direct access to the source MemoryEntry — production wiring of "click-through to the prior run" is follow-up I-f14-005b.

## Plan

### `web/app/generation/components/verified_report_view.tsx` (extend)

1. Inside `SentenceItem`, add boolean `cites_memory` = `parsed_tokens.some(t => t.source_id.startsWith("ev_memory_"))`.
2. When non-dropped + `cites_memory`, render `<span data-testid="prior-run-badge-{sentence_id}" title="...">from prior run</span>` inline below the provenance line.
3. Badge style: small purple chip ("border-purple-500/40 bg-purple-500/5 text-purple-700 dark:text-purple-300"), left-aligned next to existing badges.

### Tests

4. Frontend unit OR Playwright spec — issue acceptance says "Playwright shows cite-in-current". Add `web/tests/e2e/cited_recall_badge.spec.ts` — uses an existing fixture page (or a new minimal preview page if needed). Plan: extend `web/app/sentence_hover_test/evidence_tooltip` fixture page to include a sentence whose provenance_tokens contain `ev_memory_xxx`, and assert the badge renders with that sentence's testid.

### Out of scope

- Click-through to the prior run's full report (follow-up I-f14-005b).
- Backend wiring that auto-promotes prior_run_summary entries (follow-up since I-f14-004b).

## Risks for Codex Red-Team

1. **Token regex:** existing `parseAllTokens` accepts source_id with `[a-zA-Z0-9_\-]`; `ev_memory_<hex12>` matches.
2. **Honest framing:** badge is "from prior run" not specific date — acceptance only requires "cite-in-current" which is the badge.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** estimated +20 in verified_report_view + ~50 spec + perhaps small fixture extension = ~80. Comfortable under 200.

## Acceptance criteria

1. SentenceItem renders inline `prior-run-badge-{sentence_id}` when any provenance token's source_id starts with `ev_memory_`.
2. Playwright spec asserts the badge renders for a sentence with a memory-prefix evidence_id.
3. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-3.
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
