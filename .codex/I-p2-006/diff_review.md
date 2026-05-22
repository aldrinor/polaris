# Codex DESIGN+DIFF review — I-p2-006 (#745): source / evidence card

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1 (code + design rubric, esp. HONESTY). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `4dba0c5b8328fdbdb94d145e7335011fb4aaed6749089e9d24aeffde9e578ac9`. web/ only.

## Design-audit note (component, no standalone page)
Display card; visual renders in-context on report/audit/source-review pages (#756/#759/#770). Audit code + rubric honesty/a11y dims here.

## Diff
- NEW web/components/source/source_card.tsx: SourceCardSource (own optional-field shape, per brief P2). Renders ONLY present fields: tier badge (—tier token), title (interactive link if url, else text), domain, authors, snippet (line-clamp-3), mono source_id. OPTIONAL stance (dedicated StanceBadge support=green/contradict=amber, NOT VerdictChip per brief P2) + contentHash (mono) — rendered ONLY when passed (never invented).

## Review focus (rubric: provability/HONESTY, a11y, visual)
1. HONESTY (P0/P1 if violated): does the card invent any field? hash/version/stance only when explicitly passed; missing fields omitted (no "unknown"/fabrication)?
2. Tier token mapping + AA; stance badge 3-signal (icon+label+color)?
3. Interactive link a11y: focus-visible ring /70, rel=noopener, ExternalLink aria-hidden?
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
