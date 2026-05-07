# Codex Brief Review — I-f5-003 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f5-003 — Inspector: source span + URL + tier + retrieval trace
**Phase:** 1 / **Feature:** F5
**LOC budget:** 180 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict consumed

- P1 (generation_runner pool threading binding): RESOLVED iter 2 — generation_runner.tsx EDIT promoted to binding acceptance criterion 4. `<VerifiedReportView report={state.report} pool={state.pool} ... />`.
- P1 (snippet fallback span extraction): RESOLVED iter 2 — `text = source.full_text ?? source.snippet ?? ""; span = text.slice(start, end);` plus out-of-range guard rendering "(span out of range: {start}-{end} of {text.length})" if `end > text.length`.
- P2 #1 (test must assert retrieval trace fields): RESOLVED iter 2 — Playwright assertion includes title, domain, publication_date.
- P2 #2 (source-not-in-pool path): RESOLVED iter 2 — second test scenario clicks a sentence whose token references `src-ghost` (not in pool); asserts `inspector-source-missing` testid visible.

## Mission

Per breakdown: highlighted span; tier badge with rationale; retrieval steps. Playwright Inspector content correct.

## Substrate (HONEST at HEAD)

- I-f5-002 ships `sentence_inspector.tsx` Sheet with sentence_text + provenance_tokens + drop_reason.
- `web/lib/api.ts:466-478` `RetrievalSource` (source_id, url, domain, tier T1/T2/T3, title, snippet, full_text).
- `[#ev:<source_id>:<start>-<end>]` token format — needs frontend parser to extract source_id + start/end.
- Tier rationale: T1=regulatory/Cochrane (highest), T2=peer-reviewed primary, T3=registries/guidelines.

## Approach

**Part 1 — `web/lib/provenance_tokens.ts`** (NEW, ~30 LOC):
- `parseProvenanceToken(token: string): { source_id, start, end } | null` — regex `/^\[#ev:([a-zA-Z0-9_\-]+):(\d+)-(\d+)\]$/`.
- `parseAllTokens(tokens: string[]): ParsedToken[]` — filters nulls.

**Part 2 — `web/app/generation/components/sentence_inspector.tsx`** (EDIT, ~60 LOC):
- Accept `pool: EvidencePool | null` prop alongside sentence/sentence_id.
- For each parsed token, find matching source by source_id; render:
  - source URL (anchor)
  - tier badge (T1/T2/T3 with color + rationale tooltip)
  - highlighted span: `text = source.full_text ?? source.snippet ?? ""; span = text.slice(start, end)` with out-of-range guard
  - retrieval trace: section showing source.title + domain + publication_date + authors[0..2]
- `data-testid="inspector-span-{i}"`, `data-testid="inspector-tier-{T}"`, `data-testid="inspector-source-url-{i}"`.

**Part 3 — `web/app/generation/components/verified_report_view.tsx`** (EDIT, ~5 LOC):
- Pass `pool` prop through to SentenceInspector.

**Part 4 — `web/app/generation/components/generation_runner.tsx`** (EDIT, ~3 LOC):
- BINDING: pass `pool={state.pool}` to `<VerifiedReportView />`.

**Part 5 — `web/app/sentence_hover_test/_demo.tsx`** (EDIT, ~30 LOC):
- Add synthetic EvidencePool with 1 source (`src-7` matching token). Pass pool prop.

**Part 6 — `web/tests/e2e/sentence_inspector_source.spec.ts`** (NEW, ~40 LOC):
- Click sentence with provenance token; assert tier badge visible, source URL visible (`href` matches), highlighted span visible.

## Acceptance criteria (binding)

1. `web/lib/provenance_tokens.ts` NEW.
2. `web/app/generation/components/sentence_inspector.tsx` EDIT — pool-aware rendering.
3. `web/app/generation/components/verified_report_view.tsx` EDIT — accept + thread pool prop.
4. `web/app/sentence_hover_test/_demo.tsx` EDIT — synthetic pool fixture.
5. `web/tests/e2e/sentence_inspector_source.spec.ts` NEW.

## Planned diff shape

```
web/lib/provenance_tokens.ts                          NEW +30
web/app/generation/components/sentence_inspector.tsx  EDIT +60
web/app/generation/components/verified_report_view.tsx EDIT +8
web/app/sentence_hover_test/_demo.tsx                 EDIT +30
web/tests/e2e/sentence_inspector_source.spec.ts       NEW +40
```

LOC: +168 net. Under breakdown 180 budget by 12; under CHARTER §1 200-cap by 32.

## Out of scope

- Two-family evaluator agreement signal → I-f5-004.
- Live retrieval-trace event stream → reuse F4 SSE substrate in I-f5-005+.

## Risks for Codex Red-Team

1. **`generation_runner.tsx` already passes pool** — verify and thread if missing.
2. **`full_text` may be null** — fall back to snippet for highlighted span.
3. **`source_id` not in pool** — show "Source not in pool" badge; don't crash.
4. **Tier badge colors** consistent with existing palette.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 168 net.
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
