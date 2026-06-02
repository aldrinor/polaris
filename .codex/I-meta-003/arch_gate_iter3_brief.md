HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex gate iter 3 — full-power architecture doc, the §5 cost/sovereignty P1 fixed

iter 2 was APPROVE-but-for one continuing P1: §5 still read "$2.63 = full-power run" while discussing EU-sovereign
wall-clock, re-muddying the Mode A/B split. §5 (docs/full_power_polaris_architecture_2026_05_31.md, "## 5. RUNTIME +
COST") has now been rewritten to strictly separate the two modes. READ §5 + §0. Output YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
p1_closed: <true|false>
remaining_issues: [...]
honest_one_line: "<for the operator>"
```

## The fix to confirm
§5 now has two clearly-labeled cost models:
- MODE A (PoC, non-sovereign): ≈$2.63/run — Writer+Mirror+Judge via OpenRouter, only Sentinel self-host; the $0.62
  golden-5 verifier-API + Writer-token + amortized Sentinel GPU. The budget Mode A holds.
- MODE B (sovereign, all 4 self-hosted): ≈$129-770/run GPU-cluster model; $2.63 does NOT apply.
- The "biggest risk" (EU-sovereign verifier wall-clock unmeasured at N>=200, ~$250-920 GPU) is now explicitly
  attributed to MODE B, NOT the $2.63 Mode-A envelope; each envelope confirmed against its own mode's run.

## Your ruling
APPROVE iff the §5 Mode-A/Mode-B cost split is now clean (no "$2.63 = full-power" generic claim, no EU-sovereign
wall-clock attached to the $2.63 figure) and no new P0/P1. This doc commits to docs/ + closes GH #980 on APPROVE.
