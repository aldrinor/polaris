# POLARIS DR Auto-Loop — TOP-TIER-DR-ACHIEVED (2026-04-20)

## HEADLINE

**V17 (commit `14b50a9`) achieved Codex verdict: TOP-TIER-DR-ACHIEVED.**

The autonomous loop terminates per the user directive ("GREEN at
GPT-5.4-DR / Gemini-3.1-Pro-DR top-tier quality → STOP"). 8 Codex
DR passes + 17 full-scale sweeps over ~18 hours autonomous
iteration (commits `5502ddb` → `14b50a9`).

## V17 final metrics

- status=success, release_allowed=True, class=pass
- **eval_gate.reasons=[] EMPTY** — no advisory warnings
- **13/13 rule checks pass** — PT13 also clean
- 5 sections, 1098 words, 32 verified, 27 dropped
- 24 unique citations, 68 citation markers (2.12/sentence)
- T1+T2 = 70.8% of bibliography
- Qwen: 4 GOOD + 1 NEEDS_REVISION (hedging, non-gating)
- Cost: $0.0071 / $10 cap

## Codex pass 8 live-fetch verdict

**TOP-TIER-DR-ACHIEVED**

- 24/24 citations live-audited (100% coverage)
- **23 FAITHFUL / 0 FABRICATED / 0 EMBELLISHED / 1 UNVERIFIABLE**
- 95.8% faithful rate (>95% threshold)
- 1 UNVERIFIABLE: access-gated PubMed entry, not a fabrication —
  sentence has redundant support from other cited trials
- M-25a hardening confirmed effective: pass-7 SURMOUNT-1→-3
  binding class did not recur
- vs GPT-5.4 DR: "Matches expected DR-grade threshold"
- vs Gemini 3.1 Pro DR: "Should be accepted as top-tier"

## Trajectory

| Pass | Sweep | Verdict | Faithful | Fabricated | Embellished | Unverifiable | Release |
|------|-------|---------|---------:|-----------:|------------:|-------------:|---------|
| 4 | V10 | MATERIAL-GAPS | 18 | 1 | 1 | 4 | No |
| 5 | V11 | MATERIAL-GAPS | 16 | 0 | 1 | 3 | No |
| 6 | V13 | MATERIAL-GAPS | 21 | 0 | 3 | 2 | Yes |
| 7 | V16 | MATERIAL-GAPS | 23 | 1 | 1 | 5 | Yes |
| **8** | **V17** | **TOP-TIER** | **23** | **0** | **0** | **1** | **Yes** |

## Key fixes driving the outcome

| Commit | Fix | Impact |
|--------|-----|--------|
| `59b8f4a` | M-25a trial-name match | Caught 1 fabrication in V11 |
| `5df838f` | M-25b outline ≥5 retry | 3→5 sections in V12/V13 |
| `451f382` | M-25e PT08 enumeration | First release_allowed=True (V13) |
| `16ee8c7` | M-27 multi-source citation | 2x marker density (V16) |
| `14b50a9` | M-25a hardening (statement/title only) | V17 zero fabrications |

## Fixes attempted but reverted

- `1ad30a1` M-26a T6 exclusion → reverted at `1f88be9`.
  Caused V14/V15 3-section regression. T6 rows carry topic-diversity
  signals the outline LLM uses to justify 5 sections.

## Artifacts

- V17 report: `outputs/full_scale_v17/clinical/clinical_tirzepatide_t2dm/report.md`
- V17 bibliography: `outputs/full_scale_v17/clinical/clinical_tirzepatide_t2dm/bibliography.json`
- V17 manifest: `outputs/full_scale_v17/clinical/clinical_tirzepatide_t2dm/manifest.json`
- Pass 8 findings: `outputs/codex_findings/dr_output_pass_8/findings.md`
- Test suite: 668 passed / 0 fail
- Branch: `PL-honest-rebuild-phase-1` at commit `14b50a9`
  (plus pass-8 findings commit)

## Open items (for user, post-STOP)

1. **Single query proof**: V17 validates on one clinical query
   (tirzepatide/T2D). Multi-query validation across 8 domains
   still pending.
2. **T1+T2 mix**: 70.8% T1+T2 in V17 bibliography is strong but
   less than V13's 84.6%. M-27 increased density at slight cost to
   tier purity. Further selector work could recover both.
3. **Coverage gaps flagged non-blocking**: tier hygiene, cardiovascular
   outcome language preferring NEJM SURPASS-CVOT once available.

## Cost summary

Total autonomous cycle: ~$0.10 in OpenRouter sweeps + ~$0.10 in
Codex audits = ~$0.20 to reach TOP-TIER on a DR-grade clinical
question.

## Timeline

- 00:00 Session resumed post-compaction
- 00:06 Pass 4 MATERIAL-GAPS (V10)
- 02:02 Pass 5 MATERIAL-GAPS (V11)
- 05:15 Pass 6 MATERIAL-GAPS (V13, first release=True)
- 12:08 Pass 7 MATERIAL-GAPS (V16, 1 fabrication slipped)
- 13:50 **Pass 8 TOP-TIER-DR-ACHIEVED (V17)** — LOOP TERMINATES
