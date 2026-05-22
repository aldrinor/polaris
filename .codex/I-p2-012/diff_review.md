# Codex DESIGN+DIFF review — I-p2-012 (#751): KG stylesheet aligned to #742

HARD ITERATION CAP: 5. iter 2 (iter-1 P1: section/frame labels reverted to dark — cytoscape valign=top, labels on white). APPROVE iff zero P0/P1 (the brief-locked palette implemented faithfully + ordering correct). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `151d0e39a8a2fbf0f71123143ebd3a67ce7604a7380e75d0d27570283ebd212c`. web/ only. Single file: graph_styles.ts (claim_graph.tsx logic unchanged). Visual verifies in-context at the KG page #758.

## Diff implements the iter-5-APPROVE'd plan
- node fills lightness-tiered slates (all >=3:1): sentence #475569, source #334155, section #1e293b (light label #f8fafc), frame #64748b (light label #f8fafc). sentence/source labels stay dark below-node on white.
- state borders ORDERED search-hit #a16207 → snowball #1f7a44 → selected #c8102e LAST (red wins precedence).
- edges cites #475569, contradicts #a16207 (amber not red), section_member #64748b dashed full-opacity.
- bibliography_missing fill #94a3b8 + dashed border #475569.

## Review focus
1. Faithful to the iter-5 plan? selected ordered LAST (red always wins over snowball/search)? all values >=3:1 on white (incl. light labels on dark section/frame)?
2. contradiction amber not red (red stays scarce = selection only)?
3. No claim_graph.tsx logic change. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
