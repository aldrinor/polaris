# I-wire-014 step-3 confirm replay — honest read (2026-06-27)

Run: `outputs/iwire014_confirm` (banked drb_72 back-half, all fix-flags active, offline).
Report: 189,139 chars. render-seam removed 30 chrome units; span-gate withheld 6 from rollups.

## Scorecard (apples-to-apples vs replay3 baseline)

| Defect | replay3 | confirm | verdict |
|---|---|---|---|
| CWF `clm_` hash headers | ~19 | **0** | ✅ FIX-A confirmed in output |
| CWF 2-word stub headers | ~8 | **0** | ✅ FIX-A confirmed |
| journal_html chrome | 13 | **1** | ✅ FIX-B/C confirmed |
| cookie chrome | 2 | **0** | ✅ |
| paywall_preview chrome | 4 | 2 | ✅ reduced |
| affiliation chrome | 5 | 2 | ✅ reduced |
| midword truncation | ~91 | 6 | ✅ (better A15 recovery + source-fixes) |
| semicolon-glued | ~3 | 13 | ⚠️ mostly "span; it" FALSE POSITIVES (legit disclaimer prose); real glued-tokens ~0 |
| **"probability of computerisation"** | **13** | **13** | ❌ **FIX-D does NOT fire on contract sections** |

## FIX-D failure — root cause (the confirm replay caught it)
The "probability of computerisation … Gaussian process classifier" ×8 restatement cluster is in
`### Empirical_Displacement`, a **CONTRACT section** (m63 `contract_section_runner`). The FIX-D
prose-dedup (#1335) + the existing B11 same-span dedup run in `fact_dedup.dedup_pass`, wired ONLY into
the multi_section path (`multi_section_generator.py:7675`). Contract sections explicitly run NO dedup
(`contract_section_runner.py:1696` "No dedup pass runs on contract sections"). B11 logged collapses
for the multi_section sections (CWF 428→380, Implications 9→8) but never the contract sections.
GH #1336.

## Other forensic findings (issues spotted early)
- **mineru25 (clinical-PDF winner) tensor crash → Docling skip → PyMuPDF NOT installed** → 1 PDF lost
  (disclosed, no fabrication). W4-CANARY flagged `clinical_pdf_winner_degraded=true`. Matters for
  clinical PDFs on the fresh run — needs PyMuPDF installed + mineru25 GPU-host verify.
- ~15+ OpenRouter "Connection error, retrying" during generation — flaky API this run; resilient
  (abandoned=0) but watch for retry-exhaustion on the paid run.
- 2 contract slots gap-disclosed (theory_4ir_framing, genai_exposure) — honest gaps, banked corpus.

## Net
FIX-A + FIX-B/C (the chrome / CWF-header concerns — the "30 seconds from certified" defect) are
**CONFIRMED firing in the real rendered output**. FIX-D (repetition) works on multi_section sections
but **misses the contract-section path** → the headline Empirical_Displacement repetition survives.
NEXT: wire the dedup (consolidate-keep-all) onto the contract-section path → re-confirm → then
step-4 slate wiring → step-5 preflight → step-6 paid front+back run.
