# Codex BRIEF review — I-p2-006 (#745): source / evidence card

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
A reusable **source / evidence card** (TIER 2; report/audit/source-review pages reuse it) showing a single retrieved source's identity + provenance.

## Verified current state (grounded — avoid inventing fields)
- REAL per-source fields (evidence_pool_table.tsx SourceShape + evidence_span.ts EvidenceSource): `source_id, title, url, domain, tier, authors[], snippet`. THAT is the per-source data.
- NOT per-source (do NOT fabricate onto a source): `sha256`/content hash + `contract_version` are BUNDLE-level (api.ts:303,432); support/contradict is a RUN-level signal (api.ts contradictions[] / ContradictionSignal), not intrinsic to one source.
- #742 tokens: --tier-1/2/3, Canada-red --primary; VerdictChip (#744) for any stance label.

## Acceptance criteria (diff implements; brief reviews the plan)
1. `web/components/source/source_card.tsx`: prop `source` (the real fields above) + OPTIONAL `stance?: "support" | "contradict" | null` + OPTIONAL `contentHash?: string` (rendered ONLY when the consumer passes it — never invented).
2. Renders: tier badge (—tier token + label), title (interactive link to `url` if present — a CARD MAY hold links, unlike a tooltip), domain, authors (if any), snippet excerpt, mono `source_id`. Optional: stance badge (reuse VerdictChip mapping or a small support/contradict badge) + contentHash (mono) ONLY when provided.
3. Honest: render ONLY fields actually present (no "unknown"/fabricated hash/version/stance). Missing optional fields are simply omitted.
4. Frontier-Minimal (white, Canada-red, hairline card, mono for ids/hash); WCAG 2.2 (link focus-visible, AA, target ≥24px).

## Files I have ALSO checked and they're clean
- web/lib/evidence_span.ts (EvidenceSource), web/components/inspector/evidence_pool_table.tsx (SourceShape + existing table render), web/components/verdict/verdict_chip.tsx (#744, reuse for stance), web/app/globals.css (#742 tier tokens).

## Review focus
1. Does the card avoid inventing non-per-source fields (hash/version/stance only when explicitly passed)? Any field shown that isn't real per-source data = a P0/P1 honesty violation.
2. Tier badge mapping to —tier tokens correct + AA?
3. Interactive link a11y (focus-visible, rel=noopener); card vs tooltip distinction sound?
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```
