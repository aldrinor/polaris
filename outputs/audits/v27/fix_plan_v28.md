# V27 → V28 Fix Plan (autoloop V2, Claude draft for Codex co-review)

**Context**. V27 cross-reviewed deep content audit (both Codex and
Claude, line-by-line PRISMA/AMSTAR-2 pass) converged on:
- ChatGPT 4 topic wins (SURPASS-2, SURPASS-CVOT, SURPASS-4, Contradictions)
- V27 1 topic win (Regulatory)
- Gemini 1 topic win (Mechanism)

V27 is **rigorously bound but materially incomplete** for a clinical
audience. Root causes are generator-level (primary-trial under-citation)
+ infrastructure-level (dormant M-42 floors, suppressed M-42b table)
+ corpus-level (paywalled primary PDFs yielding thin direct_quote).

**Stop criterion** (unchanged). BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR
on 7 dimensions head-to-head. V28 target: 4-5 BEAT_BOTH + 2-3 BEAT_ONE
+ 0 LOSE_BOTH on cross-reviewed content audit.

**Dimension-preservation statement (whole plan)**.
- Regulatory BEAT_BOTH (V27 win): preserved. M-48 does not touch
  regulatory_anchors; M-49 test `test_nice_coverage_preserved ≥4`
  and `test_hc_coverage_preserved ≥3` are hard floors.
- Jurisdictional BEAT_ONE/BOTH: preserved via same M-49 floors.
- Contradiction handling BEAT_BOTH: preserved. No changes to the
  detector or Contradiction-disclosures section; M-49 test
  `test_contradiction_enumeration_preserved` asserts 13-item
  enumeration remains present.
- Per-sentence [ev_id] provenance: preserved. All V28 items are
  additive to prose/structure, not replacements for strict_verify.

## Items (ordered by Codex-recommended implementation sequence)

### [1st] M-48 — SURMOUNT + SURPASS-CVOT anchor verification (retrieval)

**Causal stage**. `config/scope_templates/clinical.yaml`
(`per_query_primary_trial_anchors`) + `src/polaris_graph/retrieval/
primary_trial_expander.py`.

**Prior mechanism gap**. V27 omitted SURPASS-CVOT entirely and all
four SURMOUNT trials despite the research question asking about "weight
loss in adults with T2D" (SURMOUNT-2 is exactly that — T2D + obesity).
Anchor list may be correct on paper; evidence is whether primary NEJM/
Lancet publications actually land in the live_corpus.

**Fix**.
1. Verify `clinical.yaml` anchor list contains: SURPASS-1, -2, -3, -4,
   -5, -6, -CVOT, SURMOUNT-1, -2, -3, -4 (11 anchors; M-43 cap=12 fits).
2. Retrieval-only test run (no generator): assert live_corpus contains
   ≥1 primary publication per anchor. Primary = title contains anchor
   token AND URL is NEJM/Lancet/JAMA/Nat Med/Diabetes Care DOI OR host
   (matches M-42e `_m42e_detect_primary_for_anchor`).
3. For each anchor where no primary lands after retrieval, widen the
   expander query form: currently "SURPASS-2 tirzepatide type 2
   diabetes"; add "SURPASS-2 Frías NEJM" (first-author variant) and
   "SURPASS-2 primary publication". 3 query variants per anchor
   (current 1 → 3 = extra ~22 Serper queries, ~$0.002).

**Acceptance**. V28 live_corpus_dump.json contains ≥1
`_m42e_detect_primary_for_anchor`-positive row for each of the 11
anchors. Pre-flight script `scripts/v28_retrieval_preflight.py` runs
this assertion before full V28 sweep.

**Test coverage**. New `tests/polaris_graph/test_m48_anchor_retrieval.py`
with retrieval fixture asserting all 11 anchors produce primary matches.

**Classification**. `root_cause`. Fixes the "anchor fires but primary
doesn't land" retrieval-to-corpus flow gap.

### [2nd] M-46 — Drop max_rows 600→300 to activate dormant M-42 floors

**Causal stage**. `scripts/run_full_scale_v28.py` env
`PG_LIVE_MAX_EV_TO_GEN=300`.

**Prior mechanism gap**. V27 forensic finding: selector short-circuits
when `pool_size <= max_rows`. V27 pool=422 < max_rows=600 → short-circuit
path bypassed the tier-balancing + floor-reservation branch. M-42c/d/e
floors were in code but never gated selection.

**Fix**. Lower max_rows to 300. Pool size typically 400-500 → selector
takes the full floor-gated path. Downstream effect: mechanism-rich T1+T2
rows reserved (M-42c), HC quota fires (M-42d), primary-trial T1 floor
fires (M-42e). All three dim improvements become real at runtime.

**Acceptance**. V28 manifest.evidence_selection.notes contains entries
`m42e_primary_floor ...`, `m42c_mechanism_floor ...`, and
`m42d_hc_quota_expand ...` (at least one of each where applicable).

**Test coverage**. Integration test in V28 preflight: run selector on
V27 pool (fixture) with max_rows=300 and assert all three notes present.

**Classification**. `root_cause`. Addresses why the M-42 bundle that
was Codex-approved never actually fired.

### [3rd] M-45 — M-42b refetch cascade (Crawl4AI → Jina → Firecrawl)

**Causal stage**. `src/polaris_graph/retrieval/live_retriever.py
::refetch_for_extraction` + builder call in
`multi_section_generator.build_trial_summary_and_timeline_from_evidence`.

**Prior mechanism gap**. M-42b's strict direct_quote ≥100 char contract
correctly rejected thin quotes from paywalled NEJM/Lancet PDFs. V27
trial table suppressed (0 rows emitted) → Structural depth LOSE_BOTH.
The refetch path existed but only tried a single backend with default
timeout.

**Fix (preserving the strict contract — NOT a contract reversal)**.
1. Upgrade `refetch_for_extraction(url, max_chars)` to a 3-backend
   concurrent cascade: Crawl4AI (existing) + Jina Reader + Firecrawl.
   All three called in parallel with 30s timeout; first to return
   ≥100 char content wins. No sequential fallback — the existing
   single-backend cascade is the baseline.
2. If all three return thin content, row remains
   `extraction_ineligible=True` and is skipped (strict contract holds).
3. Cache the refetched content on the evidence row as
   `_m42b_refetched_quote` for the remainder of the run.

**Preservation risk**. Refetch timeout could extend sweep wall-clock.
Mitigation: per-row 30s hard cap with `asyncio.wait`; no retry loop.
Expected impact <5 min on total sweep time.

**Acceptance**. V28 report.md contains Trial Summary table with ≥6
rows (≥4/7 cells each) AND Trial Program Timeline with ≥6 entries.

**Test coverage**. `tests/polaris_graph/test_m45_refetch_cascade.py`:
(a) all 3 backends return thin → row skipped, (b) Jina returns fat →
row accepted, (c) timeout: returns thin gracefully (no hang).

**Classification**. `root_cause`. Addresses "primary PDFs are
paywalled → direct_quote thin → M-42b suppresses" at the earliest
preventable stage (content acquisition).

### [4th] M-44 — Primary-trial citation hard floor in generator

**Causal stage**. `SECTION_SYSTEM_PROMPT_TEMPLATE` new rule 13
+ post-generation validator in
`src/polaris_graph/generator/multi_section_generator.py`.

**Prior mechanism gap**. Generator's relevance scorer preferred T4
post-hocs and T2 meta-analyses over T1 primaries. V27 cited
SURPASS-2 via T4 post-hoc, SURPASS-4 via meta-analysis mention, and
omitted SURPASS-CVOT + SURMOUNT trials entirely despite their
presence in the evidence subset.

**Fix**.
1. New prompt rule 13 (applies to Efficacy, Comparative, Safety, Weight
   Loss sections, NOT Regulatory/Contradictions/Limitations):
   > "When the section's evidence subset contains an M-42e-tagged
   > primary-trial row (verified via `is_primary_trial=True` metadata),
   > the section MUST cite that row at least once. A section that
   > mentions a named trial by its short-name (SURPASS-2, SURMOUNT-1,
   > etc.) MUST cite the PRIMARY publication of that trial when present
   > in the evidence subset, NOT a post-hoc or meta-analysis derivative.
   > Preference order: T1 primary > T1 review > T2 meta-analysis >
   > T4 post-hoc. If only a non-primary source is available, phrase
   > the mention as 'In a post-hoc analysis of [STUDY NAME]...' or
   > 'A meta-analysis including [STUDY NAME]...' to signal the
   > evidence tier honestly."
2. Post-generation validator: for each section, enumerate primary-trial
   evidence ev_ids present in the subset; verify each is cited at
   least once in the section's verified prose. If any uncited, trigger
   one regeneration with explicit "the following primary-trial
   citations are REQUIRED: [ev_X, ev_Y, ...]" appended to the prompt.

**Preservation risks**.
- Over-citation: forcing all primary ev_ids could bloat sections.
  Mitigation: rule 13 says "at least once" not "exhaustively"; one
  citation per primary ev_id satisfies the rule.
- Forcing regen could increase cost. Cap at 1 regen per section
  (existing pattern), then emit telemetry flag
  `m44_primary_citation_incomplete` if still missing after regen.

**Acceptance**. V28 report body cites primary publications for ≥7 of
11 named tirzepatide pivotal trials (SURPASS-1..6, SURPASS-CVOT,
SURMOUNT-1..4). V27 baseline: 4/11.

**Test coverage**. `tests/polaris_graph/test_m44_primary_citation_floor.py`:
(a) section prompt contains rule 13, (b) validator flags missing
primary cite, (c) regen loop terminates after 1 retry.

**Classification**. `root_cause`. The generator prompt is the earliest
preventable stage for "primary paper in evidence subset but not cited".

### [5th] M-47 — Mechanism-paper data extraction into prose

**Causal stage**. `SECTION_SYSTEM_PROMPT_TEMPLATE` Mechanism-section
sub-rule 8d + post-gen validation.

**Prior mechanism gap**. V27's Mechanism section cited Thomas 2022
Lancet D&E clamp paper [27] as "direct mechanistic evidence" but did
not extract its findings (63% M-value increase, biphasic insulin
secretion). Gemini won Mechanism dim by mining clamp data from the
same paper; V27 wrapped it without summarizing.

**Fix**. Add Mechanism-section sub-rule 8d:
> "When a clamp-study, hyperinsulinemic-euglycemic study, or PK/PD
> primary paper is in the section's evidence subset, the Mechanism
> section MUST extract at least 3 quantitative findings from that
> paper's direct_quote and report them inline with [ev_X] citation.
> Target quantitative fields (report whichever are in the direct_quote):
> M-value (insulin sensitivity), insulin secretion rate (first-phase,
> second-phase), glucagon suppression %, half-life (hours/days), Tmax,
> receptor-affinity ratio GIP:GLP-1, clamp duration, participant N.
> A Mechanism section that cites a clamp paper but reports <3 of
> these fields will be flagged incomplete and regenerated."

Post-gen validator: scan Mechanism section for quantitative patterns
(regex for M-value, pmol/L, half-life, etc.) from clamp-paper ev_ids.
Flag if <3 found; trigger one regen.

**Preservation risk**. Longer Mechanism section risks more
under-framed mechanism claims. Mitigation: M-41c already fires on
trial-name tokens; sub-rule 8d operates only when clamp-paper
ev_id is in subset — no effect when evidence thin.

**Acceptance**. V28 Mechanism section reports ≥3 quantitative
findings from Thomas 2022 (or equivalent primary clamp paper) with
citations. Mechanism word count ≥350 when evidence supports it
(M-42c conditional target).

**Test coverage**. `tests/polaris_graph/test_m47_clamp_data_extraction.py`:
(a) rule 8d present in Mechanism prompt, (b) validator regex
correctly identifies clamp findings, (c) regen fires when
findings <3.

**Classification**. `root_cause`. Addresses "paper cited but findings
not extracted" at the prompt level.

### [6th] M-49 — Preservation regression suite extension

**Causal stage**. `tests/polaris_graph/test_m42_preservation.py`
extended. Also new baseline file `tests/fixtures/v27_baseline.json`
captured from V27 manifest.

**Prior mechanism gap**. M-42 preservation suite caught V26's NICE
regression but doesn't encode V27's content-level wins (regulatory
breadth, contradiction enumeration). Without these, V28 could
regress silently.

**Fix**. Add tests:
- `test_surpass_cvot_primary_cited` — regex search for "SURPASS-CVOT"
  in report + validate bibliography contains NEJM 2025 primary.
- `test_surmount_1_primary_cited` — Jastreboff 2022 NEJM cited.
- `test_surpass_2_primary_etd_present` — one of "-0.15%", "-0.39%",
  "-0.45%" appears in report (SURPASS-2 primary ETDs).
- `test_mechanism_section_word_count_gte_350`.
- `test_trial_summary_table_rows_gte_6`.
- `test_nice_coverage_preserved_from_v27` (NICE ≥4).
- `test_hc_coverage_preserved_from_v27` (HC ≥3).
- `test_contradiction_enumeration_preserved` (13-item enumeration
  in report).
- `test_fda_count_at_or_above_v25` (existing, refresh baseline to 7).

All tests skip when V28 output directory missing (partial-run
safety per Codex pass-2 finding on M-42 suite).

**Classification**. `preservation` (not root_cause — this IS the
regression guard itself).

## Per-item summary table

| Item | Stage | Addresses | Classification |
|---|---|---|---|
| M-48 | Retrieval + config | Missing primaries in corpus | root_cause |
| M-46 | Env / launcher | Dormant M-42 floors | root_cause |
| M-45 | Content acquisition | Paywalled PDF thin quotes | root_cause |
| M-44 | Generator prompt + validator | Primary-trial under-citation | root_cause |
| M-47 | Mechanism prompt + validator | Cited paper, findings not extracted | root_cause |
| M-49 | Test suite | Encode V27 wins as V28 floors | preservation |

**No band-aid items.** Every fix at earliest preventable stage,
preservation risk acknowledged, acceptance criteria stated, test
coverage planned.

## Expected V28 outcome (honest projection)

| Dim | V27 | V28 projection | Rationale |
|---|---|---|---|
| 1. Citations | BEAT_ONE | BEAT_BOTH | M-44 forces primary-trial citation → deeper bibliography |
| 2. Regulatory | BEAT_BOTH | BEAT_BOTH preserved | M-49 floors hold NICE/HC |
| 3. Jurisdictional | BEAT_BOTH | BEAT_BOTH preserved | Same |
| 4. Claim frames | LOSE_BOTH | BEAT_ONE | M-44 primary ETDs + M-45 trial table |
| 5. Structural depth | LOSE_BOTH | BEAT_ONE | M-45 trial table + timeline; Gemini still deeper on per-trial subsections |
| 6. Contradiction handling | BEAT_BOTH | BEAT_BOTH preserved | No changes to detector |
| 7. Narrative depth | LOSE_BOTH | BEAT_ONE | M-47 Mechanism + M-44 deeper trial coverage |

**Projected aggregate**: 3 BEAT_BOTH + 4 BEAT_ONE + 0 LOSE_BOTH.
Not SHIPPABLE (which requires 7/7 BEAT_BOTH) but eliminates all
LOSE_BOTH — a clean "close-to-top-tier" result. Remaining path to
BEAT_BOTH on narrative/structural would require V29 per-trial
subsection generator (outline-template overhaul — out of scope here).

## Questions for Codex plan review

Per V2 §6 protocol, the following self-critical questions surface for
your response:

1. **Is M-44 truly root_cause or a retrieval-side band-aid?** Arguable
   that the "correct" fix is at the scorer (inflate T1 primary score
   by 2x) rather than at the prompt. Trade-off: scorer change affects
   all sections; prompt rule scoped to specific sections.

2. **Is the M-45 refetch cascade a contract reversal on M-42b's
   ≥100 char strict rule?** No — contract remains; cascade just
   increases probability of obtaining ≥100 chars legitimately.

3. **Is M-47's "≥3 quantitative findings" rule brittle?** Regex-based
   validation could miss prose that states findings without the
   specific tokens. Alternative: LLM-based self-check. Preference:
   regex for determinism; LLM self-check as V29 evolution.

4. **Are preservation tests too strict?** `test_surpass_2_primary_etd_present`
   hard-codes three decimal values. If Codex agrees these are the
   correct SURPASS-2 primary ETDs (Frías NEJM 2021), lock them; else
   propose alternatives.

5. **Order of implementation risk**: M-48 and M-46 are retrieval /
   infra; M-44/M-45/M-47 are generation. If retrieval/infra succeed
   but generation items stall, partial ship still reaches 2-3
   BEAT_BOTH. Good roll-forward profile.

## Next step per V2 runbook

Submit to Codex for pass-1 plan review. Expected ping-pong ≤3 passes
per §7. On APPROVED: implement items in order 48→46→45→44→47→49,
each with individual Codex code audit before proceeding to next.

---
**Draft by Claude**. Codex input requested before any implementation.
