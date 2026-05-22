# Codex BRIEF review — I-p2-012 (#751): knowledge-graph visualization — align to #742

HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
Align the EXISTING knowledge-graph viz (claim_graph.tsx + graph_styles.ts, built I-snowball-003/004/005, cytoscape + fcose) to the #742 white+Canada-red design system. NO rebuild, NO new graph lib (cytoscape is installed + working).

## Verified current state (grounded)
- claim_graph.tsx is complete (hover/select/search/snowball/selection-sync/fcose, node+edge counts+hash). Do NOT rebuild it.
- graph_styles.ts STYLESHEET uses HARDCODED pre-#742 colors that CLASH with the white+Canada-red lock: sentence #3b82f6 (blue), source #22c55e (green), section #a3a3a3, frame #f59e0b (amber); selected border #0ea5e9 (sky-blue), snowball #3b82f6 (blue), search-hit #facc15 (yellow); edges cites #60a5fa, contradicts #ef4444, section_member #d4d4d4.
- Cytoscape canvas CANNOT read CSS custom properties → must use CONCRETE values matching #742.

## Acceptance criteria (diff implements; brief reviews the PLAN — colors are the crux)
1. RED reserved for the SELECTION state (scarcity): `node.selected` border → **#c8102e** (Canada-red, 4px). Node TYPES become muted/categorical (not saturated rainbow) so they harmonize with white+red:
   - section #334155 (slate-700, anchor), source #475569 (slate-600), sentence #64748b (slate-500), frame #94a3b8 (slate-400). Labels stay dark (#1e293b) on white — AA.
2. State accents distinct from each other + the node fills: selected #c8102e (red); snowball-neighbor border #1f7a44 (verified-green concrete, "connected"); search-hit border #c98a00 (contradiction-amber concrete, "search mode").
3. Edges: cites #94a3b8 (hairline slate), contradicts #c98a00 (amber — conflict; NOT red, to keep red = selection scarcity), section_member dashed #d4d4d8.
4. G-PERF: cytoscape + fcose already handles ~1k nodes; no change to layout/perf. NO behavior change to claim_graph.tsx logic.

## Files I have ALSO checked and they're clean
- web/app/runs/[runId]/graph/components/claim_graph.tsx (logic — unchanged), graph_styles.ts (the ONLY file edited), web/app/globals.css (#742 token source for the concrete values).

## Review focus (colors are the crux)
1. Do the concrete values faithfully reflect #742 (red=selection scarcity; muted categorical types; amber not red for contradiction so red stays scarce)? Any AA issue (node fills vs white, labels, state borders)?
2. Are the 4 node-type slate shades distinguishable enough (+ size + tooltip)? Are the 3 state borders (red/green/amber) mutually distinct?
3. Any clash I missed; any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 clarification (review scope)
This is a BRIEF / PLAN review, NOT a diff review. graph_styles.ts is INTENTIONALLY still the pre-#742 palette — the recolor is applied AFTER this brief is APPROVE'd (workflow: brief → Codex brief APPROVE → diff → Codex diff APPROVE). An empty git diff / unchanged stylesheet is the EXPECTED pre-implementation state, NOT a defect. Please evaluate the PLAN: are the proposed CONCRETE color values (§ acceptance 1-3) faithful to #742 (red=selection scarcity; muted slate node types; amber-not-red contradiction; green snowball; amber search-hit) and AA-safe; are the 4 slate shades + 3 state borders mutually distinguishable. APPROVE iff the color PLAN is sound; reserve P0/P1 for a wrong/clashing color choice or an AA failure in the PROPOSED values, NOT the absence of the not-yet-applied edit.

---
## iter-3 corrections (concrete values now all ≥3:1 on white)
- **P1 (node fills):** use 4 lightness-tiered slates, ALL ≥3:1 on white, biggest=darkest: section #1e293b (slate-800, ~16:1), source #334155 (slate-700, ~8.6:1), sentence #475569 (slate-600, ~6.4:1), frame #64748b (slate-500, ~4:1). Distinguishable by lightness + node size (30/26/18/22) + hover tooltip. Drops the failing #94a3b8.
- **P1 (amber):** search-hit border + contradicts edge → #a16207 (amber-700, ~4.8:1 on white) — clears 3:1, stays clearly amber + distinct from Canada-red #c8102e and snowball-green #1f7a44.
- selected #c8102e (red, ~5.9:1), snowball-neighbor #1f7a44 (green, ~4.7:1) confirmed ≥3:1. cites edge #64748b (visible hairline), section_member dashed #cbd5e1.
Re-confirm APPROVE or list only true remaining P0/P1.

---
## iter-4 correction (edges all ≥3:1)
- **P1 (section_member edge):** drop #cbd5e1 + the opacity:0.5. Use cites #475569 (slate-600 solid, ~6.4:1, the proof relationships), section_member #64748b (slate-500 DASHED, full opacity, ~4:1 — distinguished from cites by dash + darkness, not by sub-3:1 paleness), contradicts #a16207 (amber, 2px). All edges now ≥3:1; distinction via color + line-style + width.
Re-confirm APPROVE or list only true remaining P0/P1.

---
## iter-5 correction (state precedence — red=selection always wins)
- **P1 (precedence):** in the new graph_styles.ts, ORDER the state selectors so `node.selected` (Canada-red, 4px) comes AFTER `node.search-hit` and `node.snowball-neighbor`. Cytoscape resolves equal-specificity ties by source order (last wins), and snowballNeighbors() includes the selected target — so `.selected` LAST guarantees the selected node always renders Canada-red/4px even when it is also a snowball neighbor / search hit. Preserves red=selection scarcity invariant.
Re-confirm APPROVE or list only true remaining P0/P1.
