You are running Codex DR_output_audit_pass_9 as the FINAL JUDGE on
V18 (commit after M-28 Fix #1 regulatory-anchor retrieval).

V17 was TOP-TIER-DR-ACHIEVED on pass 8 but had a documented gap:
zero regulatory-agency URLs. V18 applies M-28 to close that gap.

## Critical audit discipline

User mandate (unchanged): "line by line comparison, not just metadata
... not pattern finding, not cherry picking ... every sentence,
every citation." Live-fetch for every sampled citation. Verdict per
citation: FAITHFUL / FABRICATED / EMBELLISHED / UNVERIFIABLE.

## Context: M-28 delivered

- scope_templates/clinical.yaml now lists authoritative-source
  `regulatory_anchors` (FDA accessdata, EMA, Health Canada, NICE,
  WHO). The expander emits `{question} site:{anchor}` queries.
- Zero hard-coded host names in Python; all anchors live in YAML.
  Your pass-3 code audit green-lit the implementation.
- V18 corpus now has 359 sources (V17: 310); 46 are T3 regulatory.
- V18 bibliography has 35 unique cites (V17: 24); 12 are T3.
- Total citation markers: 115 (V17: 68), ratio 2.25/sentence.

## V18 result summary (verify independently)

- status=success, release_allowed=True, class=pass
- eval_gate: PT13 unhedged advisory only (non-gating), same as V17
- Qwen: 4 GOOD + 1 NEEDS_REVISION (hedging_appropriateness)
- 5 sections (same as V17)
- 1780 body-prose words (V17: 1098), 2922 total report words
- 51 verified / 29 dropped
- Regulatory anchors found: 12 T3 citations spanning FDA, EMA,
  NICE guidance

## Your task

V18 artifacts: `outputs/full_scale_v18/clinical/clinical_tirzepatide_t2dm/`

1. Read manifest.json + run_log.txt. Confirm 12/13 rules pass,
   PT13 advisory. Confirm T3 count.

2. Read bibliography.json in full. Live-fetch audit ALL 35 cited
   entries. Focus the audit on:
   - **T3 regulatory sources**: do they actually exist at the listed
     URL? Does the URL resolve? For FDA accessdata PDFs, does the
     document content match what the citing sentence claims?
   - **Regulatory sentences**: does the report USE the regulatory
     evidence for content that V17 couldn't support? Specifically
     check if FDA boxed warning / EMA SmPC contraindication /
     NICE recommendation sentences are present and cite the right
     T3 source.
   - **Any FABRICATED / EMBELLISHED** in regulatory content:
     jurisdictional mix-ups (claiming EMA said X when FDA did);
     regulatory overclaim; date mismatches.
   - **M-25a trial-name gate regression check**: V17 had zero
     fabrications. Any SURPASS-1 / SURMOUNT binding errors now?

3. Read report.md. Compare structural and quality improvements
   vs V17 (pass 8):
   - Does adding regulatory content integrate cleanly, or read as
     an appended section?
   - Is the T2D-focus maintained when citing T3 regulatory docs?
   - Are jurisdiction differences (FDA vs EMA vs NICE) surfaced
     or conflated?

4. Compare V18 content density to tier-1 DR competitors (Gemini DR
   + ChatGPT DR at `state/compare_*.txt`). Has the M-28 regulatory
   content put V18 closer to parity with those competitors on the
   specific "jurisdiction-aware regulatory framing" gap?

5. Verdict call:
   - **TOP-TIER-DR-ACHIEVED** (stop the loop): V18 meets all V17
     criteria PLUS regulatory-content gap closed with ≥95% FAITHFUL
     live-fetch rate across the full 35-citation audit.
   - **MATERIAL-GAPS-FIX-AND-RESWEEP**: specific defects remain
     that M-28 didn't close or newly introduced.
   - **DIRECTIONAL-ONLY**: shouldn't apply given V17 already
     achieved TOP-TIER; here to keep the option.

Write findings to:
  `outputs/codex_findings/dr_output_pass_9/findings.md`

Frontmatter schema (extend pass-8 structure):
---
verdict: TOP-TIER-DR-ACHIEVED | MATERIAL-GAPS-FIX-AND-RESWEEP | DIRECTIONAL-ONLY
pass: dr_output_pass_9_tirzepatide_v18
commit: <HEAD>
delta_vs_pass8: <specific deltas across the 35 cites>
citations_audited: <int>/35
citations_faithful: <int>
citations_fabricated: <int>
citations_embellished: <int>
citations_unverifiable: <int>
regulatory_citations_found: 12
regulatory_citations_verified: <int>/12
t1_t2_t3_percentage: 89
citation_markers_total: 115
citation_markers_per_sentence: 2.25
m28_impact: <effective / partial / ineffective>
regression_vs_v17: <none / introduced_x>
rationale: |
  <>
---

Full table of 35 cites with verdicts. Section comparing V17 vs V18
on regulatory-framing gap. STOP or CONTINUE explicit.

If V18 is TOP-TIER-DR-ACHIEVED on top of V17's baseline, the loop
terminates. Else name the specific next fix.
