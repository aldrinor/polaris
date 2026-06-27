# I-wire-014 final reconfirm3 — §-1.1 honest read (2026-06-27)

Run: `outputs/iwire014_reconfirm3` (banked back-half replay, drb_72 AI-labor snapshot, all
committed fixes + full prod flags PG_CONSOLIDATION_NLI + _PROSE + FACT_DEDUP_PROSE +
RENDER_CHROME_SCREEN + CWF_HEADER_PROSE + PDF_FRONTMATTER_STRIP + TRAFILATURA_SUBPROCESS,
GLM-5.2 all-roles). Report: 25,860 words, 862 lines.

## VERDICT: NOT §-1.1-clean → 2 parallel runs NOT launched.

The committed fixes are working, but the end-to-end render surfaces blocking residuals in the
LEGACY/ENRICHMENT sections that the per-component validations did not catch. This is exactly the
"green/harness ≠ usable" gap; reporting honestly (no cheerleading).

## WHAT IS FIXED + PROVEN (firing in the real rendered output)
- **#4b contract-section repetition (keep-first-verbatim dedup):** FIRED on all 3 contract
  sections — `11→8 (redundants=3)`, `28→22 (redundants=6)`, `19→19`. The operator's flagged
  degenerate cluster collapsed: "novel methodology…702 occupations / Gaussian process classifier"
  ×~12 (reconfirm2) → 1; "probability of computerisation" ×21 → 4. `rewrites_applied=0`
  (verbatim, no LLM rewrite); every citation preserved. Codex diff-gate APPROVE iter-3.
- **FIX-A hash dump:** 0 hash-dump lines (was 154/155).
- **Chrome screen + render-seam:** removed 46 chrome/truncated units; 0 cookie/paywall furniture.
- **Native heap-corruption crash:** none (thread-clamp holding across mineru VLM + concurrent pools).
- **mineru25 / PyMuPDF:** VLM predictor parsing PDFs cleanly; A15 re-fetch recovered 16/20 shells.
- **qwen-judge token fix:** token-limit-resolver clamps max_tokens → no HTTP-400 hold.
- **multi_section B11 same-span dedup:** collapsed 48 (`Corroborated Weighted Findings` 424→376)
  + 2 + 2.

## BLOCKING RESIDUALS (the report is NOT clean — these must be fixed + gated first)

### R1 (ROOT CAUSE — sharpened) — K-span fallback BYPASSES the chrome screen
The decisive log line, repeated for 15+ baskets:
`[abstractive_writer] basket=clm_XXX all SUPPORTS members screened as chrome -> writer skipped (K-span fallback)`
So the 35 undrafted baskets (89/124) are NOT a timeout — their SUPPORTS members are ALL chrome,
the chrome screen correctly flags them, the abstractive writer correctly skips them… and then the
**K-span (verified-span) fallback renders that very raw chrome span verbatim.** The chrome screen
is wired into the writer-SKIP decision but is NOT applied to the K-span fallback render, so a
flagged all-chrome basket dumps its chrome anyway. Per §-1.3 an all-chrome basket should be
WITHHELD from the rollup (kept in evidence, not rendered as a finding) — not dumped.
This is what makes `Background` / `Evidence and Analysis` / `Comparative Assessment` /
`Corroborated Weighted Findings` read like source dumps:
- truncated mid-word/mid-sentence fragments: "restricted to s.[89]", "entrepreneurs face un[57]",
  "Current Pillars of Industry 4.0.[27]", "differentiating the two concepts[19]…](https://.[20]"
- raw bibliographic / metadata chrome glued into prose: "is listed as an author.[40]",
  "has received 3258 accesses, 16 citations, and 7 altmetric mentions[73]",
  "Vol.:(0123456789) RESEARCH ARTICLE", journal vol/issue/page strings
- malformed markdown/URLs spliced mid-sentence
- leaked doc-structure paragraph numbers: `4.18`, `4.19`, `4.27`, `4.9` glued to text
This is the core "wide but not clean" failure. Fix target: abstractive writer coverage/wall
(so baskets get synthesized, not dumped) AND/OR a much stronger chrome+truncation screen on the
raw-span fallback path.

### R2 — CWF "Key Findings"/"Tension" callout headers select chrome/truncated sentences
10 bold-label callouts; several pick chrome/truncated text from the raw-span content:
- L66 `**Key Findings** The article is titled Impacts of generative artificial intelligence…outlines
  sections on background, research gap, rationale, materials and methods…` (metadata, not a finding)
- L88 `**Key Findings** Scope of the Review Overall, the scope was restricted to s.[89]` (truncated)
- L80 `**Key Findings** A review on information fusion…concepts[19] [https://doi.org/…](https://.[20]`
  (raw URL + truncation)
FIX-A killed the hash dump but header CONTENT quality still leaks chrome/truncation. Downstream
of R1 (the candidate pool is the raw-span text); fixing R1 shrinks this, but the header selector
should also reject chrome/truncated candidates.

### R3 — quantified differentiator NO-OP this run
`quantified_analysis NO-OP (spec_validation_rejected): input_both_modeled_and_sourced:productivity_gain`
— fail-closed (correct, not fabrication) but the differentiator produced nothing. Assertion (h)
likely FAIL. Needs the writer to emit a valid spec (not mixing modeled+sourced inputs).

### R4 (minor) — cross-section verbatim repeats
dedup is same-section-guarded, so a few claims repeat across sections (e.g. the Midjourney
"idea frontier" sentence ×3). By-design for the dedup, but visible. Lower priority.

## NEXT (per the binding directive — fix+gate ALL via Claude Codex Workflow before 2 parallel runs)
1. R1 is the keystone: investigate abstractive_writer coverage (124-basket sections blow the 720s
   wall → raw-span fallback). Options: raise/parallelize the writer budget; OR gate the raw-span
   fallback through a strict chrome+truncation screen so a dump never renders. Research 2025/26
   best practice, benchmark candidates, then wire+gate.
2. R2 rides on R1 + a header-candidate chrome/truncation reject.
3. R3 writer-spec validity.
4. Re-run reconfirm; honest-read until the rendered report is §-1.1-clean. THEN (operator-gated)
   the 2 parallel runs.
