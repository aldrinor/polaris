HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL findings. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex gate iter 2 — full-power architecture doc, the 5 iter-1 corrections applied

You REQUEST_CHANGES'd iter 1 (competitor citations were REAL, framing honest, no safety holes — 5 fixes needed).
Verify the fixes in docs/full_power_polaris_architecture_2026_05_31.md (READ IT). Output YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
fixes_landed: [...]
remaining_issues: [...]
honest_one_line: "<for the operator>"
```

## The 5 iter-1 corrections — confirm each landed:
1. **Gemini word count 4,932 → 4,887** (all occurrences). [was: local file is 4,887]
2. **Sovereignty/cost split (THE one correction):** §0 now states TWO runtime modes explicitly — Mode A PoC
   (Writer+Mirror+Judge via OpenRouter US, only Sentinel self-host, ≈$2.63/run, NON-sovereign + labeled) vs Mode B
   sovereign (all 4 self-hosted, ~$129-770/run, no US vendor). The "$2.63" is now scoped to Mode A only. Confirm the
   doc no longer claims both cheap-OpenRouter AND no-US-vendor-verification at once.
3. **evidence_selector line ref** → now `:893,:976,:1500` (the actual truncation+selection points), not just :976.
4. **Stage 9 narrowed:** now states NUMERIC contradictions are ALREADY fed to generation (`run_honest_sweep_r3.py:2613`)
   + PT08 evaluator-gated; only QUALITATIVE conflicts are the real gap full-power closes. Confirm not overstated.
5. **Gemini MTC row reclassified** from WINS to PARITY→WINS(presentation), reworded so it's not called a fabrication.
6. **Build list item 1 split:** corpus_funnel instrumentation FIRST; cap-removal only AFTER map-reduce wired; explicit
   "do NOT send uncapped raw rows through the current generator." Confirm.

## Your ruling
APPROVE iff all 5 corrections landed cleanly and no NEW P0/P1 introduced. This doc commits to docs/ on APPROVE.
