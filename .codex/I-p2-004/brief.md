# Codex BRIEF review — I-p2-004 (#743): citation chip + hover source card

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
A reusable **citation chip + hover source card** component (TIER 2; pages reuse it). The chip is the inline provenance marker; hovering reveals the source card with the EXACT cited span.

## Verified current state (reuse, don't reinvent)
- `web/lib/provenance_tokens.ts`: `parseProvenanceToken("[#ev:<id>:<start>-<end>]")` → {source_id, start, end}.
- `web/components/inspector/verified_report_sections.tsx` already resolves a token → evidencePool source → full_text.slice(start,end) (the #734 logic) — extract/reuse the resolver.
- Design-system tokens (#742): Canada-red accent, --tier-1/2/3, --proof-token, mono for tokens; hairlines.
- shadcn has a hover-card primitive pattern; check web/components/ui for hovercard/tooltip (evidence-tooltip.tsx exists).

## Acceptance criteria (diff implements; brief reviews the plan)
1. `web/components/citation/citation_chip.tsx` (or similar): props = a provenance token (or {source_id,start,end}) + the evidence pool (or a resolver). Renders a compact chip: mono index/id + a tier dot (--tier-1/2/3). Keyboard-focusable, accessible.
2. On hover/focus → a source card: source title, tier badge, the **exact span quote** (full_text[start:end]), timestamp/url if present. Honest fallback ("span not in this bundle") when unresolved — NO synthetic proof.
3. Frontier-Minimal (white, Canada-red, mono token, hairline); WCAG 2.2 (focus-visible, hover AND keyboard, target ≥24px); reduced-motion.
4. Reuses parseProvenanceToken + the existing token→span resolver (extract to a shared util if cleaner). No duplicate parsing logic.

## Files I have ALSO checked and they're clean
- web/lib/provenance_tokens.ts (the parser), web/components/inspector/verified_report_sections.tsx (the existing resolver to reuse), web/components/ui/evidence-tooltip.tsx (existing tooltip pattern).

## Review focus
1. Is reusing/extracting the #734 resolver correct, or will a second copy drift? Recommend the shared-util boundary.
2. Hover-card a11y: keyboard + hover + touch + reduced-motion + focus; not hover-only.
3. No-synthetic-proof honored (resolved-span or honest fallback)?
4. Any P0/P1.

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
- **P1 (resolver premise false):** correct — the #734 token→span resolver is on the UNMERGED bot/I-ui-014-proof-replay branch, NOT on polaris. So #743 CREATES a NEW shared util `web/lib/evidence_span.ts`: `resolveSpan(token|parsed, evidencePool) → { source, start, end, quote|null }` (parse via parseProvenanceToken → find evidencePool.sources[source_id] → full_text.slice(start,end); honest null when unresolved). The citation chip consumes it; the inspector/Proof-Replay (#756) reuses the SAME util (no second copy). web/lib/evidence_span.ts is the single resolver boundary.
- **P2 (evidence-tooltip):** reuse evidence-tooltip.tsx for the INTERACTION pattern only; do NOT inherit its 240-char truncation — the source card shows the EXACT span untruncated (scroll if long).
- **P2 (touch):** explicit acceptance — tap opens the source card, dismiss is predictable (tap-away/Esc), chip target ≥24px.
Re-confirm APPROVE or list only true remaining P0/P1.

---
## iter-3 corrections (resolver contract locked)
- **P1-1 (array lookup):** `EvidencePool.sources` is an ARRAY (api.ts:705). resolveSpan looks up via `sources.find(s => s.source_id === id)` (or a prebuilt Map), NEVER `sources[source_id]`. Matches existing verified_report_view.tsx:130 / multi_source_panel.tsx:129.
- **P1-2 (unresolved guard, NO synthetic proof):** return `quote: null` (→ honest "span not renderable" fallback) when ANY of: source not found; `full_text` null/undefined/empty; `start < 0`; `end > full_text.length`; `start > end`. NEVER `full_text.slice(start,end)` without these guards (slice silently clamps = synthetic partial proof). Only return a quote when bounds are fully valid against the actual body.
Re-confirm APPROVE or list only true remaining P0/P1.
