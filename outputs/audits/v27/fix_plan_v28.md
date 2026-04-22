# V27 → V28 Fix Plan — PASS-2 (post Codex pass-1 CONDITIONAL)

**Pass history**
- Pass-1 (Claude draft, committed e9e8f6c): 6 items, M-48/M-46/M-45/M-44/M-47/M-49.
- Codex pass-1 verdict (`outputs/codex_findings/v28_fix_plan_review_pass1/findings.md`):
  CONDITIONAL. 1 approved (M-48 w/ minor tweak), 5 needs_revision
  (M-46 selector-level not launcher-knob; M-45 AccessBypass already
  exists → diagnose first; M-44 needs scorer/subset boost not
  prompt-only; M-47 needs evidence-linked validator; M-49 tests need
  normalized matchers). **+1 new item requested**: M-50 per-trial
  subsection generator (to reach 4+ BEAT_BOTH instead of just killing
  LOSE_BOTH).

Pass-2 incorporates every Codex requirement. All 6 original items
revised + M-50 added.

## Stop criterion (unchanged)

BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR on 7 dimensions, cross-reviewed
content audit. V28 target (revised after Codex input): **4 BEAT_BOTH
+ 3 BEAT_ONE + 0 LOSE_BOTH** (previously 3 BB + 4 BO + 0 LB — M-50
adds the 4th BEAT_BOTH via per-trial subsections).

## Dimension-preservation statement (whole plan, unchanged)

- Regulatory BEAT_BOTH: preserved via M-49 floors (NICE ≥4, HC ≥3).
- Jurisdictional BEAT_BOTH: preserved (same M-49 floors).
- Contradiction handling BEAT_BOTH: preserved (no detector changes;
  M-49 test asserts 13-item enumeration present).
- Per-sentence [ev_id] provenance: preserved across all items.

## Items (Codex-recommended implementation order, pass-2 revised)

### [1st] M-48 — SURMOUNT + SURPASS-CVOT anchor verification (root_cause, Codex approved)

**Causal stage**. `config/scope_templates/clinical.yaml`
(`per_query_primary_trial_anchors`) +
`src/polaris_graph/retrieval/primary_trial_expander.py`.

**Prior mechanism gap**. V27 omitted SURPASS-CVOT and all SURMOUNT
trials despite presence of anchors. Retrieval-side gap: anchor fires
but primary doesn't land in the corpus-ready form.

**Fix (pass-2 tightened per Codex revision #7)**.
1. Verify anchor list: SURPASS-1..6, SURPASS-CVOT, SURMOUNT-1..4
   (11 total; M-43 cap=12 fits).
2. Per-anchor first-author variants (NOT a single generic):
   - SURPASS-1 → "Rosenstock Lancet tirzepatide"
   - SURPASS-2 → "Frías NEJM tirzepatide semaglutide"
   - SURPASS-3 → "Ludvik Lancet tirzepatide insulin degludec"
   - SURPASS-4 → "Del Prato Lancet tirzepatide glargine"
   - SURPASS-5 → "Dahl JAMA tirzepatide glargine"
   - SURPASS-6 → "Rosenstock JAMA tirzepatide glargine premeal"
   - SURPASS-CVOT → "Nicholls tirzepatide cardiovascular outcomes"
   - SURMOUNT-1 → "Jastreboff NEJM tirzepatide obesity"
   - SURMOUNT-2 → "Garvey Lancet tirzepatide obesity diabetes"
   - SURMOUNT-3 → "Wadden Nature Medicine tirzepatide maintenance"
   - SURMOUNT-4 → "Aronne JAMA tirzepatide maintenance"
3. Retrieval-only pre-flight: `scripts/v28_retrieval_preflight.py`
   asserts ≥1 `_m42e_detect_primary_for_anchor`-positive row per
   anchor.
4. **Population-scope labels (Codex revision #7)**: SURMOUNT-2 is
   T2D+obesity (direct). SURMOUNT-1/3/4 are obesity-only unless row's
   population label includes T2D; the selector and generator must
   tag these as `indirect_for_t2d=True` so weight-loss claims don't
   merge non-T2D estimates into direct T2D efficacy prose.

**Acceptance**. V28 live_corpus_dump.json contains ≥1 primary row per
anchor AND each SURMOUNT row has `indirect_for_t2d` metadata set
correctly.

**Test coverage**. `tests/polaris_graph/test_m48_anchor_retrieval.py`:
(a) 11 anchors produce ≥1 primary match in fixture, (b) SURMOUNT-1/3/4
tagged indirect, (c) SURMOUNT-2 tagged direct.

**Classification**. `root_cause`.

### [2nd] M-46 — Selector early-exit fix + V28 cap (root_cause, pass-2 revised)

**Causal stage** (per Codex revision #1). `src/polaris_graph/retrieval/
evidence_selector.py` early-exit policy + V28 launcher cap.

**Prior mechanism gap**. Claude pass-1 was a launcher knob
(PG_LIVE_MAX_EV_TO_GEN=300). Codex correctly pointed out the durable
root cause is the selector itself: when `pool_size <= max_rows`, the
early-exit branch bypasses floor reservations, ranking, and telemetry.
A run with a small corpus silently loses the M-42e/c/d benefits.

**Fix (pass-2 per Codex verbatim language)**.
1. Selector behavior: when floor inputs are configured
   (`primary_trial_anchors` non-empty, mechanism rows ≥4, or
   jurisdiction quotas active), the selector must compute floor
   reservations, ranking, and telemetry **even if
   `len(scored) <= max_rows`**. It may return all rows only after
   applying deterministic priority ordering (M-42e reserved first,
   then M-42c mechanism, then M-42d HC, then relevance) and emitting
   floor notes.
2. V28 launcher still sets `PG_LIVE_MAX_EV_TO_GEN=300` as a sweep-
   size control, but the permanent fix is the selector change.

**Preservation risk**. Fully-ordered output replaces arbitrary tier
order when pool_size ≤ max_rows. Mitigation: existing selector
consumers only read the selected list in order for downstream prompts,
so stability improves (primaries appear first in the prompt window).

**Acceptance (Codex verbatim)**. "With a fixture where
`pool_size <= max_rows`, selector notes still include applicable
`m42e_primary_floor`, `m42c_mechanism_floor`, and
`m42d_hc_quota_expand`, and selected row ordering places reserved
primary/mechanism/regulatory rows before derivative rows."

**Test coverage**. `tests/polaris_graph/test_m46_selector_no_bypass.py`:
(a) fixture pool=50, max_rows=100, anchors configured → notes present,
order correct, (b) fixture pool=300, max_rows=100 (no short-circuit)
→ identical note pattern, (c) no anchors configured → no notes
(backward compat).

**Classification**. `root_cause`.

### [3rd] M-44 — Scorer/subset primary boost + same-sentence validator (root_cause, pass-2 revised)

**Causal stage** (per Codex revision #3). Section-level evidence-
subset scoring in `multi_section_generator._select_evidence_for_section`
PLUS post-generation validator. **NOT prompt-only** (Codex
correctly noted M-20 trial-specific rule already exists — adding
another would be duplication).

**Prior mechanism gap**. Section-subset scorer ranks evidence by
generic relevance; primaries lose to post-hocs that have more
semantic overlap with the section heading. V27 evidence:
SURPASS-2 primary (NEJM) was in the corpus but SURPASS-2 post-hoc
(T4) was higher-ranked and was what the generator cited. Prompt-only
enforcement (Claude pass-1 rule 13) repeats M-20; Codex wants
pre-prompt pressure at the scoring stage.

**Fix (pass-2)**.
1. **Scorer boost** in section evidence selection: for Efficacy,
   Comparative, Safety, Weight Loss, Cardiovascular sections, add
   `+0.3` score bonus to rows with `is_primary_trial=True` (M-42e
   tag) when the row's anchor token matches section focus (e.g.
   SURPASS-2 in Efficacy → boost; SURPASS-CVOT in Cardiovascular →
   boost). No boost for Regulatory / Contradictions / Limitations /
   Methods sections (primaries not authoritative there).
2. **Subset composition**: after scoring, ensure section subset
   contains the primary row when present. If primary is ranked but
   would be truncated by the section's evidence cap, swap the lowest-
   scored non-primary row for the primary.
3. **Post-generation validator (Codex revision #4)**: for each named
   trial mentioned in the section, if a matching M-42e primary
   ev_id is in the section subset, that primary ev_id must be cited
   in the SAME sentence or the IMMEDIATELY ADJACENT sentence. For
   section-relevant primary ev_ids NOT mentioned by name, require
   at least one primary-trial citation per report-level major trial
   (not every ev_id in every section — that would bloat).
4. Trigger one regen if validator fails; emit
   `m44_primary_citation_incomplete` telemetry if still missing.

**Preservation risk**. Scorer boost could push non-primary reviews
off the subset. Mitigation: boost is +0.3 (relative), not absolute
displacement; reviews still rank above thin snippets.

**Acceptance**. V28 report cites primary publications for ≥7 of 11
named pivotal trials with primary cite in same/adjacent sentence as
the trial name.

**Test coverage (Codex revision #3 verbatim test)**. `tests/polaris_
graph/test_m44_scorer_subset_primary_boost.py`:
- Given section subset candidate pool with SURPASS-2 primary +
  SURPASS-2 post-hoc + meta-analysis, selected subset includes primary
  ahead of derivatives.
- Generated prose citing SURPASS-2 by name must cite primary in
  same/adjacent sentence.

**Classification**. `root_cause` (combined scorer + validator).

### [4th] M-45 — Refetch diagnostics then targeted fix (root_cause, pass-2 revised)

**Causal stage** (per Codex revision #2). Diagnosis first of
`live_retriever._fetch_content` AccessBypass cascade behavior, then
targeted acquisition fix based on diagnostics.

**Prior mechanism gap**. Claude pass-1 assumed no cascade existed.
Codex correctly pointed out `refetch_for_extraction()` already
routes through `_fetch_content` which documents an AccessBypass
concurrent cascade (Crawl4AI + Jina + Firecrawl). V27 still yielded
thin quotes despite this — the question is WHY, not whether to add
a cascade.

**Fix (pass-2)**.
1. **Diagnostics phase**: instrument `refetch_for_extraction` to emit
   per-URL `refetch_diagnostics.json` with:
   - attempted backends (Crawl4AI / Jina / Firecrawl flags)
   - returned char count per backend
   - content-type header per backend
   - final eligibility (≥100 char direct_quote)
   - failure mode if ineligible: paywall (403/401) / thin / timeout /
     non-text
2. Run a 20-URL diagnostic sweep against V27 primary-trial URLs.
3. **Targeted fix based on findings**. Three likely branches:
   - If AccessBypass is NOT actually invoking Jina/Firecrawl in this
     path → wire those providers explicitly.
   - If it IS invoking but provider returns non-abstract content
     (e.g., generic article shell without results) → use provider
     text that contains abstract/results windows via
     `_build_provenance_quote` head-plus-decimal-windows.
   - If all providers paywall cleanly → mark row extraction_ineligible
     and skip (strict contract maintained, no statement fallback).
4. Pass `_m42b_refetched_quote` into the deterministic table/timeline
   builder ONLY when it meets the strict ≥100 char quote contract.

**Preservation risk**. Strict contract holds. No statement fallback.
No generated-prose fallback.

**Acceptance (Codex verbatim)**. "`refetch_diagnostics.json` records
attempted backend(s), character count, and eligibility for every
skipped primary row; at least 6 pivotal rows become eligible, OR
the diagnostic file identifies each remaining URL as paywall/thin/
timeout with no contract reversal."

**Test coverage**. `tests/polaris_graph/test_m45_refetch_diagnostics.py`:
(a) diagnostic emission schema valid, (b) post-fix: mocked fat Jina
response → row eligible, (c) all-paywall → skipped with diagnostic.

**Classification**. `root_cause` (diagnosis-driven, no band-aid).

### [5th] M-47 — Evidence-linked clamp/PK quantitative validator (root_cause, pass-2 revised)

**Causal stage** (per Codex revision #5). Mechanism-section prompt
sub-rule 8d + post-gen validator that is **evidence-linked** (not
regex-only on the section).

**Prior mechanism gap**. Claude pass-1 used regex counting on the
whole Mechanism section — would false-pass on dose, N, or percentage
values unrelated to the clamp paper. Codex wants the validator to
extract allowed values/units from the cited clamp row's direct_quote
and then require those same values/fields to appear in verified prose
with the clamp ev_id citation.

**Fix (pass-2, Codex verbatim language)**.
1. Prompt rule 8d: when a clamp/PK primary paper is in section subset,
   report ≥3 quantitative findings inline with [ev_X] citation
   (M-value, insulin-secretion rate, glucagon-suppression %, half-
   life, Tmax, receptor-affinity ratio, clamp duration, N).
2. **Evidence-linked validator**:
   - Extract candidate quantitative fields from cited clamp/PK row's
     `direct_quote` (or accepted refetched quote), normalizing units
     (mg/dL vs mmol/L; pp vs %; hours vs days).
   - Check that ≥3 of THOSE SAME values/fields appear in verified
     Mechanism section WITH the clamp/PK ev_id cited in the same
     sentence.
   - Broad numeric counts in the section do NOT satisfy the rule.
3. Trigger one regen if <3 linked findings; emit
   `m47_mechanism_extraction_incomplete` if still missing.

**Preservation risk**. Stricter validator could fail legitimate
prose that paraphrases findings without exact token match.
Mitigation: fuzzy numeric matching (±5% tolerance) and unit
normalization handle reasonable paraphrases.

**Acceptance**. V28 Mechanism section reports ≥3 quantitative fields
from cited clamp paper with evidence-linked citation (not just
loose numeric tokens). Mechanism word count ≥350 when evidence
supports (M-42c conditional target unchanged).

**Test coverage**. `tests/polaris_graph/test_m47_evidence_linked_
extraction.py`:
(a) fixture: direct_quote "M-value increased 63% with tirzepatide
15 mg" + prose "...tirzepatide 15 mg increased M-value by 63%
[ev_clamp]" → validator pass, (b) fixture: prose "...tirzepatide
is effective [ev_clamp]" (no linked numbers) → validator fail,
(c) fuzzy match: prose "63.2% M-value rise" vs direct_quote "63%"
→ within ±5% → pass.

**Classification**. `root_cause`.

### [6th] M-50 — Per-trial subsection generator (root_cause, NEW per Codex completeness review)

**Causal stage**. Outline-template extension in
`src/polaris_graph/generator/multi_section_generator._compose_outline`.

**Prior mechanism gap**. V27 has no per-trial subsections. Gemini
wins Narrative depth via named SURPASS-1..6 + SURMOUNT-2 subsections;
ChatGPT wins Structural depth via its trial table. M-45 adds the
table, but per-trial subsections are a distinct artifact that
ChatGPT also provides (e.g., ChatGPT dedicates paragraphs per trial
in the body).

**Fix**. Outline-template extension:
1. When Efficacy section's evidence subset contains ≥2 M-42e primary
   rows (M-44 ensures this), branch Efficacy into named subsections.
2. Candidate trials (gated on primary available): SURPASS-2,
   SURPASS-4, SURPASS-CVOT, SURMOUNT-2 (T2D-direct only;
   SURMOUNT-1/3/4 remain in body-level obesity-related paragraph
   per M-48 population-scope labels).
3. Each subsection covers: N + population + comparator + endpoint +
   timepoint + effect-estimate-with-uncertainty + safety caveat
   (the 7 elements Codex specified).
4. Subsection template inherits M-42a claim-frame rule; M-44
   primary-citation floor; M-41c trial-name framing.

**Preservation risk**. Longer report (7 subsections × ~120 words
≈ 840 additional words). Risk: diluting key findings across many
subsections. Mitigation: subsections ONLY when M-42e primary
available for that trial; no placeholder subsections.

**Acceptance**. V28 report has Efficacy subsections for SURPASS-2,
SURPASS-4, SURPASS-CVOT, SURMOUNT-2 (gated on primary availability)
with all 7 PICO+effect elements each. If <2 primaries available
after M-44/M-45, subsections do not render (strict gating).

**Test coverage**. `tests/polaris_graph/test_m50_per_trial_subsections.py`:
(a) 4 primaries available → 4 subsections rendered, (b) 1 primary
available → no subsections (below 2-trial threshold), (c) each
subsection has all 7 elements.

**Classification**. `root_cause` for the 4th BEAT_BOTH (Structural
depth + Narrative depth).

### [7th] M-49 — Preservation/integration suite with normalized matchers (preservation_guard, pass-2 revised)

**Classification tag change per Codex revision #6**: `preservation_guard`
not `root_cause` (correct classification).

**Causal stage**. `tests/polaris_graph/test_m42_preservation.py`
extended. Baseline fixture `tests/fixtures/v27_baseline.json`.

**Fix (pass-2, Codex revision #6 verbatim for SURPASS-2 test)**.

New tests:
- `test_surpass_2_primary_etd_present`: accepts normalized numeric
  values `-0.15`, `-0.39`, `-0.45` with unit variants (`%`,
  `percentage points`, `pp`); sentence must cite SURPASS-2 primary
  bibliography entry.
- `test_surpass_4_frame_present`: N=1,995 OR 104-week durability
  language appears with Del Prato Lancet citation.
- `test_surpass_cvot_noninferiority_present`: "HR 0.92" + "noninferiority"
  phrasing + Nicholls citation.
- `test_surmount_1_primary_cited`: Jastreboff NEJM 2022 present.
- `test_surmount_2_t2d_subsection`: SURMOUNT-2 named + T2D+obesity
  population label + Garvey citation.
- `test_mechanism_section_word_count_gte_350`.
- `test_trial_summary_table_rows_gte_6`.
- `test_per_trial_subsections_gte_2` (M-50 gate).
- `test_nice_coverage_preserved_from_v27` (NICE ≥4).
- `test_hc_coverage_preserved_from_v27` (HC ≥3).
- `test_contradiction_enumeration_preserved` (13-item enumeration).
- `test_fda_count_at_or_above_v25` (existing, refresh baseline to 7).
- `test_surmount_1_3_4_indirect_labeled` (no merging into T2D
  efficacy claims).

All tests skip gracefully when V28 output missing (existing
partial-run-safety pattern).

**Classification**. `preservation_guard`.

## Per-item summary table (pass-2)

| Item | Stage | Addresses | Classification | Pass-1 Codex verdict | Pass-2 state |
|---|---|---|---|---|---|
| M-48 | Retrieval + config | Anchor retrieval + population labels | root_cause | approved | tightened (first-author variants + indirect labels) |
| M-46 | Selector code | Early-exit bypass of floors | root_cause | needs_revision | Fixed at selector level, not env |
| M-44 | Scorer + validator | Primary under-citation | root_cause | needs_revision | Scorer boost + same-sentence validator |
| M-45 | Diagnostics + acquisition | Thin direct_quote on paywalled PDFs | root_cause | needs_revision | Diagnose first, targeted fix |
| M-47 | Prompt + evidence-linked validator | Mechanism extraction | root_cause | needs_revision | Evidence-linked (not regex-only) |
| **M-50** | **Outline extension** | **Per-trial subsections** | **root_cause** | **NEW** | **Added per Codex completeness review** |
| M-49 | Test suite | Encode V27 wins as V28 floors | preservation_guard | needs_revision | Normalized matchers + classification fix |

**No band-aid items.** Every fix at earliest preventable stage,
preservation risk acknowledged, acceptance criteria measurable,
test coverage evidence-linked.

## Revised expected V28 outcome

| Dim | V27 | V28 pass-1 projection | V28 pass-2 projection | Rationale |
|---|---|---|---|---|
| 1. Citations | BEAT_ONE | BEAT_BOTH | **BEAT_BOTH** | M-44 scorer boost + M-48 primaries |
| 2. Regulatory | BEAT_BOTH | preserved | **preserved** | M-49 floors |
| 3. Jurisdictional | BEAT_BOTH | preserved | **preserved** | M-49 floors |
| 4. Claim frames | LOSE_BOTH | BEAT_ONE | **BEAT_BOTH** | M-44 scorer + M-45 table + M-50 subsections |
| 5. Structural depth | LOSE_BOTH | BEAT_ONE | **BEAT_BOTH** | M-45 table + M-50 subsections |
| 6. Contradiction handling | BEAT_BOTH | preserved | **preserved** | No detector changes |
| 7. Narrative depth | LOSE_BOTH | BEAT_ONE | BEAT_ONE | M-47 Mechanism + M-50 depth (still Gemini-deeper on receptor pharmacology) |

**Projected aggregate (pass-2)**: **5 BEAT_BOTH + 2 BEAT_ONE + 0 LOSE_BOTH**.
Honest close-to-top-tier; matches or beats both competitors on 5 of
7 dims. Not SHIPPABLE (needs 7/7) but clean, defensible, and
preservation-guarded.

## AMSTAR-2 / GRADE / PRISMA additions (Codex completeness review)

Codex flagged three possible additions:
- **GRADE-style certainty per major claim**: deferred to V29 scope.
  Adding now would require a certainty-rating module that is out of
  scope for the M-44..M-50 cycle.
- **Compact risk-of-bias table**: partial win achievable via M-49
  test `test_contradiction_enumeration_preserved` (already covers
  risk-of-bias signals at the contradictions layer). Explicit ROB
  table deferred to V29.
- **Full PRISMA flow diagram**: not in V28 scope.

V28 bundle stays focused on the 7 content items above.

## Implementation order (Codex-approved, pass-2)

1. M-48 retrieval anchor verification + first-author variants +
   population-scope labels.
2. M-46 revised: selector early-exit fix + V28 cap.
3. M-44 revised: scorer/subset primary boost + same-sentence
   validator.
4. M-45 revised: diagnostics phase → targeted acquisition fix.
5. M-47 revised: evidence-linked clamp/PK extraction validator.
6. M-50 new: per-trial subsection generator.
7. M-49 revised: preservation/integration suite with normalized
   matchers.
8. V28 sweep launch.

Each item: implement → unit + integration tests → individual Codex
code audit → proceed on READY (established pattern from M-42e/a+b/c/d,
M-43).

## Next step per V2 runbook

Resubmit this pass-2 plan to Codex for step 6 pass-2 review. Expected
ping-pong budget: 2 remaining of 3 per §7 trigger #11. On APPROVED:
begin M-48 implementation.
