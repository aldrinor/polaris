# Codex brief — I-p2-058 (#863): Knowledge-graph frontier/lively S-audit

HARD ITERATION CAP: 5. iter 1. APPROVE iff the plan is sound + doesn't break the contract.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context + plan
/runs/[runId]/graph (cred-gated) is the highest visual-impact page. Operator: drill UI to 100% at a
frontier-competitive + LIVELY bar ("if UI is ugly no one looks"). Codex visual audit said it was
"raw Cytoscape in a clean admin page". Plan (palette-safe — near-neutral + scarce-red selection):
semantic node shapes by type, frame-status colours, label halos, directional edges, animated fcose
settle, dot-grid depth, default focal spotlight on load, dim non-neighbours on selection, and the
rail turned into a navigator (type glyphs + arrow links). Preserve the real getRunGraph fetch +
cytoscape interactions + keyboard nav + testids.

## Note
Already gated downstream: visual `-i` APPROVE iter-3 (desktop A- / selected A- / mobile B+); code
diff under review in parallel. This brief records acceptance for the artifact set.
