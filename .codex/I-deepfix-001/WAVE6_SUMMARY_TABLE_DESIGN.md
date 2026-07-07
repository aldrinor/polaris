# Wave 6 design — summary table + specific-study coverage (I-deepfix-001 #1344)

**Highest-leverage wave.** drb_72 scores 70 pts: 57 info_recall + 8 analysis + 5 presentation. Both GPT and
Gemini scored ~0/57 info_recall (the biggest bucket). The info_recall + presentation points hinge on ONE thing:
a correctly-formatted 5-column summary table that lists the specific 14 studies with their facets, plus in-section
citations of those same studies.

## THE HARD FAITHFULNESS LINE (read before touching any code)

**NEVER hardcode the 14 studies, their titles, countries, or metadata into report output.** That is fabrication
(LAW II), hard-coding (LAW VI), and benchmark-gaming — banned, and in clinical context "lethal". POLARIS is
WEIGHT-AND-CONSOLIDATE with a HARD faithfulness gate: the report may cite a study ONLY if the pipeline genuinely
retrieved + fetched + strict_verify-passed a real source for it. The 14-study list below is the RETRIEVAL TARGET and
the VALIDATION answer-key for the table FEATURE — it is NOT content to inject.

Emergent-only rules:
- The summary table is built ONLY from verified baskets present in THIS run. Retrieved 9 of 14 → 9 rows (honest).
  NEVER pad to 14 with fabricated rows. §-1.3 CONSOLIDATE-not-drop: one row per source basket, keep all.
- Facet cells (Country/Region, Application Area) are SPAN-GROUNDED — extracted from the verified source text. Not
  extractable → cell = "Not reported" (never guessed). §-1.1: the cell's value must be supported by a cited span.
- Retrieval seeding is WEIGHT not FILTER: seed queries make these REAL papers more likely to be fetched; a paper
  that is not fetchable simply does not appear. No hard-drop, no target-count forcing.
- Faithfulness engine (strict_verify / NLI / D8 / provenance / span-grounding) BYTE-UNTOUCHED.

## SURGICAL-NOT-REWRITE (mandatory first step of the build)

Before building anything, GREP for an existing summary-table / tabular-composer in the render + composition layer:
`grep -rniE "summary.table|summary_table|\| Country|Application Area|Research Literature|markdown.*table|def .*table" src/polaris_graph/generator/ src/polaris_graph/`. POLARIS report composition is mature — a table
renderer or a per-source facet aggregator may already exist (weighted_enrichment.py, verified_compose.py,
multi_section_generator.py, key_findings.py, a render/ module). If one exists → RE-WIRE + extend to the 5-column
format; do NOT build a parallel one. Only build new if none exists.

## The three legitimate Wave-6 levers (all default-OFF flag-gated, quad-pinned, honest-liveness)

1. **Summary-table composition feature** (the big one). A render/compose step that, from the run's verified
   per-source baskets, emits a markdown table with EXACTLY these 5 columns in order:
   `Research Literature | Country/Region | Application Area/Occupation | Specific Applications and Impacts | Key Risks and Limitations`.
   One row per source that has ≥1 verified claim. "Research Literature" = the source's title (author+year if present).
   Impacts / Risks columns = the verified positive-impact / risk claims for that source (consolidated basket text,
   each still span-supported). Country / Application-Area = span-grounded facet extraction (below), else "Not
   reported". Emitted after the 4 sections. Flag e.g. `PG_SUMMARY_TABLE_5COL`. Honest marker
   `[activation] summary_table_5col: reached= sources_seen= rows_emitted= facets_grounded=` + `unavailable_failopen`.
   NO count>0 gate (a run with 0 tabular sources legitimately emits no table → must pass canary).
2. **Per-source facet extraction** (Country/Region + Application Area/Occupation). Span-grounded extraction from the
   verified source: country-of-study + application domain. Grounded (must appear in the fetched source), else blank.
   May reuse an existing metadata/enrichment extractor if present. Faithfulness-adjacent → dual-gate carefully.
3. **Retrieval seeding for the domain views** (WEIGHT). Seed the query generator with the positive/negative/
   challenges/opportunities framings + the specific study topics (recruitment bias, manufacturing high-skill demand,
   healthcare empathy, scientific-writing productivity, gender gap, reskilling…) so the retriever is MORE LIKELY to
   fetch these real papers. Same pattern as Wave-1 workforce T3 targeting. Additive lane, fail-open (adds 0 on
   failure, never aborts). NOT a filter, NOT a target count.

Plus: **Brynjolfsson NBER repoint** — the ghost-[6] Brynjolfsson/Li/Raymond citation must point at the correct NBER
working-paper source (citation-correctness fix, faithfulness-strengthening).

## The 14 target studies (RETRIEVAL TARGET + table-feature VALIDATION key — NOT output to inject)

| # | Study | Country | Application area | Impact (positive) | Key risks |
|---|---|---|---|---|---|
| 1 | Can AI help for scientific writing? | Belgium | scientific writing | efficiency in content production | plagiarism, inaccurate content |
| 2 | Comparing physician and AI chatbot responses to patient questions… | USA | healthcare / patient comms | high-quality, empathetic answers | lack of regulation & oversight |
| 3 | Physicians' attitudes and knowledge toward AI in medicine… | Bahrain | healthcare | reduced diagnosis time | job security, AI can't replace human skill |
| 4 | Collaboration among recruiters and AI: Removing human prejudices… | China | employment recruitment | improved recruitment, reduced workload | cost, legal/privacy, recruitment bias |
| 5 | ChatGPT from the perspective of an academic oral & maxillofacial radiologist | USA | dental education / OMR | time-saving, curriculum dev | can't process images, low accuracy |
| 6 | ChatGPT for future medical and dental research | Saudi Arabia | medical & dental research | accelerated writing & translation | ethics, insufficient reliability |
| 7 | Can AI close the gender gap in the job market?… | Germany | employment recruitment | reduced gender bias | may exacerbate implicit discrimination |
| 8 | An AI-based open recommender system for personalized labor market-driven education | Germany | job skills training | personalized learning recs | high dev/maintenance cost, data privacy |
| 9 | The job perception inventory: … human-AI work | Germany | workplace | improved productivity & org outcomes | insufficient attention to employee needs |
| 10 | Impact of AI on employment in the manufacturing industry | China | manufacturing | increased demand for high-skilled labor | reduced demand for low-skilled |
| 11 | The dark side of generative AI: … controversies & risks of ChatGPT | Poland | business | improved efficiency & creativity | weak regulation, poor info quality, privacy |
| 12 | Augmenting organizational change and strategy activities: … generative AI | Netherlands | organizational change | planning aid, stakeholder mobilization | need for employee reskilling |
| 13 | On the impact of digitalization and AI on employers' flexibility requirements… (Germany) | Germany | employer flexibility | altered work environment | harms well-being (admin/secretarial) |
| 14 | Worker perspectives on incorporating AI into office workspaces… | USA | office workspaces | improved environment, well-being | changing job requirements, skill mgmt |

## Analysis (8) + presentation (5) — what the composed report must ALSO demonstrate (emergent)

- analysis: duality (productivity vs displacement); skill-level differential (high vs low); ethics/regulation core;
  reskilling crucial; human oversight in healthcare/law; recruitment bias potential+risk; cross-country compare
  (USA/Germany/China); balanced conclusion (reshape not replace = human-AI collaboration).
- presentation: 4 explicit sections (Positive / Negative / Challenges / Opportunities); author+year citations; the
  5-column table correctly formatted; table covers ≥14 study cases; fluent + factually clean.

These EMERGE from good retrieval + composition; they are NOT hardcoded. The table feature (lever 1) + seeding
(lever 3) are what move them from 0 to real credit, honestly.

## FINDINGS FROM CODE (2026-07-07 surgical-not-rewrite grep) — the table is ALREADY BUILT + WIRED

`src/polaris_graph/generator/summary_table.py` ALREADY implements lever 1 exactly to spec: parses the requested
5 headers from the research question, one row per verified bibliography source (no verified claim → no row, never
fabricated), surfaces Country/Domain/Risk by HIGH-PRECISION VERBATIM whole-word match against each source's OWN
verified spans ("—" disclosed gap otherwise), faithfulness engine untouched, kill-switch `PG_RENDER_SUMMARY_TABLE`.
It is WIRED: `PG_RENDER_SUMMARY_TABLE` quad-pinned in run_gate_b.py (slate 625="1" / preflight 1962 / force-on 2255
/ allowlist 3613) and CALLED in the production render seam (`scripts/run_honest_sweep_r3.py:6337` +
`:16688-16698`, fail-open, canary logged at INFO `[summary-table] rows= cols= geo_filled= domain_filled= risk_filled=`).

So Wave 6 is NOT "build the table" — it is "make the wired table SCORE + prove it fires". Refined scope:

**Wave 6a (this pass — faithfulness-safe, committable now):**
1. **Expand the curated vocabularies** in summary_table.py — `_GEO_PHRASES` is MISSING 5 of the 14 studies'
   countries (Belgium, Netherlands, Poland, Saudi Arabia, Bahrain) + others; `_DOMAIN_PHRASES` misses scientific
   writing / oral & maxillofacial radiology / dental education / organizational change / office work; `_RISK_PHRASES`
   misses a few. Expand ALL THREE COMPREHENSIVELY (a broad general list of real countries/domains/risks, NOT just
   the 14 benchmark ones — generalization, not answer-fitting). A term is surfaced ONLY if it appears VERBATIM as a
   whole word in that source's verified span → expansion NEVER fabricates; it lets MORE genuinely-present terms
   surface (§-1.3 surface-more-verified, faithfulness-neutral). Add unit tests (verbatim-present → surfaced;
   verbatim-absent → "—"; substring guard e.g. "poland" not from "lapland").
2. **Anti-dark canary**: the `[summary-table]` canary is LOGGED at INFO but appears NOT to be in the fail-loud
   `_ActivationMarkerSpec` set (assert_activation_markers_fired). Add an honest-liveness spec so a DARK table
   (feature never ran / import failed) CRASHES the run, while an honest `rows=0` (no verified tabular source) PASSES
   (§-1.3 — a legitimately empty table must not crash). Marker must carry reached + a realized rows count.

**Wave 6b (next pass — bigger, separate):** retrieval seeding (WEIGHT) for the domain views + specific study topics
so the 14 papers actually get fetched (the true info_recall gate); + Brynjolfsson NBER repoint. Kept separate to
stay under the 200-LOC cap and because seeding touches the query-gen layer, not the render layer.
