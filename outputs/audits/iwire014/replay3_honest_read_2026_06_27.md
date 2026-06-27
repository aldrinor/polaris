# I-wire-013 #1327 — replay3 honest line-by-line read (2026-06-27, overnight)

**Verdict: NOT CLEAN. NOT CERTIFIABLE. Do NOT launch the paid fresh run on this code state.**

Report read: `outputs/iwire014_replay3/workforce/drb_72_ai_labor/report.md` (179,154 chars, 777 lines).
Run: back-half replay on banked drb_72 corpus, BOTH deterministic source-fixes active
(span-boundary-snap 8da7994a + PDF front-matter-strip efb9aeaa) + render-seam iter-3a unblind (2cf382b9) + canary enforce.
Run reached render cleanly (no death, token-resolver clamps working — the qwen-judge-400 that previously held the report is fixed).
`[render-seam] removed 40 chrome/truncated unit(s)` fired — but **dozens survived**.

## Quantified surviving defects (deterministic whole-report scan)

| Class | Count | Examples |
|---|---|---|
| **CWF junk bullets** (DOMINANT) | ~160 | `clm_2aa1b69494a914f2 — 1 verified independent source(s)`, `industry- level — 2 verified`, `high- risk`, `macro- level`, `comment accuracy — 6 verified` |
| journal HTML chrome | 13 | JEL Classification, Keywords, View All Journal Metrics, Associated Records, References Biographies, Cite Cite Cite, Receive email alerts |
| semicolon-glued broken words | ~3 real | `Governan; ce`, `Agricultural Oc; b` (de-hyphenation/OCR artifact; "span; it" matches are FALSE positives) |
| affiliation chrome | 5 | "are affiliated with ESRI", "Federal Reserve Bank of Boston", "Principal investigator:", "Conflict of Interest Disclosure" |
| paywall/preview chrome | 4 | "Member-only story", "What you'll learn: -", "Feature Story" |
| mid-word truncation | 4 | `usand workers` (thousand), `restricted to s.`, `Frey and Osborne, 2017, p.[16]` |
| cookie/consent chrome | 2 | "the region that you are in", "content references language" |
| orphan citation fragments | 9 | `.[17][18][19]`, "a chatbot developed by OpenAI." |
| degenerate repetition | — | Empirical_Displacement restates "probability of computerisation" ×13, "exposure measure" ×5 |

## Root causes (multi-class, render+compose path — NOT fetch)

1. **CWF surfacing bug (biggest).** The "Corroborated Weighted Findings" weighted_enrichment surfacing renders ~160 raw rows of `**<cluster-key>** — N verified independent source(s)` where cluster-key is a hash ID (`clm_…`) or a 2-word noun phrase with a stray hyphen-space (`industry- level`, de-hyphenation artifact). This is the BREADTH-surfacing path rendering its internal index as "findings." It should render the corroborated CLAIM PROSE, not the cluster keys+counts.
2. **render-seam predicate class gaps.** `is_render_chrome_or_unrenderable` (weighted_enrichment.py:936) catches base junk + new categories + truncation markers, but does NOT recognize: journal HTML chrome (JEL/Keywords/Metrics/Associated Records/email alerts), author-affiliation lines, paywall/preview chrome (Member-only/What you'll learn), cookie-consent chrome. Only 4 chrome-rule anchors present.
3. **render-seam SCOPE gap.** The canary/screen runs on TOP-LEVEL bullets + per-citation units. The bulk of body-section PROSE chrome (welded mid-paragraph) is not bullet-form → not screened.
4. **non-head truncation classes.** `usand`/`restricted to s.` come from window-boundary or sentence-splitter cuts, NOT the head-slice my span-snap fix addresses. Semicolon-glued words are a separate de-hyphenation artifact.
5. **degenerate repetition** — abstractive writer pads by restating one sentence ~10×. Compose-layer quality defect, independent of chrome.

## Why a fresh PAID run would NOT fix this
Defects 1,2,3,5 are render/compose-path — independent of fetch. The source-fixes only help truncation classes, and only on re-fetched shells. A paid run would reproduce the CWF junk dump, the journal/paywall/cookie chrome, and the repetition. That is exactly the "half-ass run" the operator banned. **Paid run is HELD until these are fixed and a replay proves clean.**

## PROGRESS (2026-06-27) — FIX-A DONE + a decisive reframe

**FIX-A (CWF header) — COMPLETE, gated, behaviorally proven.** GH #1334, commits f0fde5b0 + iter-2.
- Diagnostic `scripts/iwire014_cwf_header_diagnostic.py`: 1/155 → 147/155 real headers, 0 hashes.
- Render-proof `iwire014_render_proof.py` (renders the real `_basket_corroboration_block`): 155 bullets, **0 clm_ hashes, 0 chrome headers**, 147 real titles/sentences, 8 clean terse labels.
- Codex diff gate: **APPROVE iter 2** (`.codex/I-wire-014/codex_diff_audit.txt`); closed an ellipsis-leak P1 + a screen-failure P2.
- Unit test `tests/polaris_graph/test_cwf_header_prose_selection.py` (14 assertions).

**DECISIVE REFRAME (quantified):** the diagnostic proved **154/155 basket representative spans
are END/START-truncated in the BANKED corpus** (pre span-snap/front-matter). 154/155 reuse
banked, non-re-fetched spans. ⇒ **the banked replay STRUCTURALLY CANNOT validate the
truncation/chrome source-fixes** — they only fire on FRESH fetch. So the chrome/truncation
still visible in replay3's body is EXPECTED on a banked replay; it is NOT evidence the
source-fixes fail. The ONLY true validation of span-snap (8da7994a) + front-matter (efb9aeaa)
is a FRESH front-half run. FIX-A is the exception: fetch-independent, hence fully validated now.

## Recommended fix path (surgical, render/compose only — faithfulness engine untouched)
- **FIX-A (CWF surfacing):** render corroborated-finding PROSE, not cluster-key+count index rows. Suppress `clm_…` hash rows and bare 2-word `X- Y` fragments from the claim surface.
- **FIX-B (predicate classes):** extend `is_render_chrome_or_unrenderable` with the journal-HTML / affiliation / paywall / cookie-consent / de-hyphenation classes (FLAG-not-drop per §-1.3 — withhold from rollup, keep in evidence).
- **FIX-C (scope):** route ALL rendered claim surfaces (body prose per-citation units + CWF) through the ONE predicate at the render seam, not just rollup bullets.
- **FIX-D (repetition):** dedup near-identical restatements in the body composer.
- Then: re-replay on banked corpus → honest read → only when CLEAN, propose the paid fresh front+back run to the operator.
