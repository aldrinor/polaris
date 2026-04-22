# Codex Pass-1 Review: V27 -> V28 Fix Plan

**Verdict**: CONDITIONAL

The plan identifies the right failure class: V27 is evidence-bound but does not reliably turn pivotal primary papers into clinically useful trial frames. I do not approve it as-written because three items overclaim root-cause status: M-46 is a brittle launcher knob for a selector-design problem, M-45 describes adding a backend cascade that the current `live_retriever._fetch_content` docstring already says exists through AccessBypass, and M-44 mostly duplicates an existing trial-specific primary-citation prompt rule without adding scorer/subset pressure. Revise those mechanisms before implementation.

## Per-item verdicts

| Item | Verdict | Reason |
|---|---|---|
| M-48 | root_cause_approved | Retrieval/corpus verification is the earliest preventable point for absent SURPASS-CVOT/SURMOUNT primaries. Acceptance is measurable. Needs minor wording: use per-anchor first-author variants, not a generic "Frías" variant, and preserve population-scope labels for non-T2D SURMOUNT trials. |
| M-46 | needs_revision | Lowering `PG_LIVE_MAX_EV_TO_GEN` to 300 may activate the floor path for V28, but it is a run-parameter workaround. The durable root cause is the selector early-exit path bypassing prioritization/telemetry whenever `pool_size <= max_rows`, despite downstream prompt/token limits. |
| M-45 | needs_revision | Content acquisition is the right stage, and the strict >=100 char contract should remain. But the proposed "add Crawl4AI + Jina + Firecrawl cascade" is not evidence-backed against current code: `refetch_for_extraction()` already calls `_fetch_content()`, whose docstring says AccessBypass includes that concurrent cascade. The fix must diagnose why the existing refetch still yields thin quotes. |
| M-44 | needs_revision | Generator enforcement is necessary, but not sufficient as root cause because an M-20 trial-specific primary-citation rule already exists in the prompt. V28 needs scorer/subset boosting plus validator enforcement; prompt-only rule 13 is too close to a repeated instruction. |
| M-47 | needs_revision | The mechanism gap is evidence-backed, but the validator must prove the quantitative findings come from the cited clamp/PK ev_id, not merely that the section contains three numeric tokens. Regex-only broad validation can false-pass on unrelated dose, N, or percentage values. |
| M-49 | needs_revision | Preservation guard is needed and mostly well scoped, but its tests should be report-output integration checks plus fixture-level unit tests. Some proposed checks are too brittle or under-specified, and M-49 should be explicitly classified as `preservation_guard`, not root cause or band-aid. |

## Specific revisions required

1. **Revise M-46 from launcher knob to selector behavior.**
   Suggested language:
   > "Causal stage: `src/polaris_graph/retrieval/evidence_selector.py` early-exit policy, plus the V28 launcher cap. When floor inputs are configured (`primary_trial_anchors`, mechanism rows, jurisdiction quotas), the selector must still compute floor reservations, ranking, and telemetry even if `len(scored) <= max_rows`; it may return all rows only after applying a deterministic priority ordering and emitting floor notes. V28 also sets `PG_LIVE_MAX_EV_TO_GEN=300` as a sweep-size control, but the permanent fix is removing the floor-bypass early exit."

   Add acceptance:
   > "With a fixture where `pool_size <= max_rows`, selector notes still include applicable `m42e_primary_floor`, `m42c_mechanism_floor`, and `m42d_hc_quota_expand`, and selected row ordering places reserved primary/mechanism/regulatory rows before derivative rows."

2. **Revise M-45 to diagnose the existing AccessBypass/refetch failure.**
   Suggested language:
   > "Prior mechanism gap: M-42b refetch calls `refetch_for_extraction()`, but V27 still produced zero eligible rows. V28 will instrument per-URL refetch backend, returned length, content type, and extraction eligibility; if AccessBypass did not actually invoke Jina/Firecrawl in this path, wire those providers explicitly. If it did, improve extraction by using provider text that contains abstract/results windows and by passing `_m42b_refetched_quote` into the deterministic table/timeline builder only when it meets the strict quote contract."

   Add acceptance:
   > "`refetch_diagnostics.json` records attempted backend(s), character count, and eligibility for every skipped primary row; at least 6 pivotal rows become eligible, or the diagnostic file identifies each remaining URL as paywall/thin/timeout with no contract reversal."

3. **Revise M-44 to include scorer/subset-level primary boosts.**
   Suggested language:
   > "Causal stage: section evidence-subset scoring plus generator validation. Before prompting, section evidence selection must boost M-42e primary rows for Efficacy, Comparative, Safety, Weight Loss, and Cardiovascular sections when the row's anchor matches the section focus or query terms. The generator validator then enforces citation for section-relevant primary rows. This complements, rather than duplicates, the existing M-20 trial-specific citation rule."

   Add test:
   > "Given a section subset candidate pool containing SURPASS-2 primary, SURPASS-2 post-hoc, and a meta-analysis, the selected/prompted subset includes the primary ahead of derivatives, and the generated/validated prose cites the primary when naming SURPASS-2."

4. **Tighten M-44 validator scope.**
   Replace "verify each primary-trial evidence ev_id present in the subset is cited" with:
   > "For each named trial mentioned in the section, if a matching M-42e primary ev_id is present in the section subset, that primary ev_id must be cited in the same sentence or immediately adjacent sentence. For section-relevant primary ev_ids not mentioned, require at least one primary-trial paragraph/table claim across the report, not every ev_id in every section."

5. **Tighten M-47 quantitative validation.**
   Suggested language:
   > "The validator extracts candidate quantitative fields from the cited clamp/PK evidence row's `direct_quote` or accepted refetched quote, normalizes units/patterns, and then checks that at least three of those same values/fields appear in the verified Mechanism section with the clamp/PK ev_id citation. Broad numeric counts in the section do not satisfy the rule."

6. **Revise M-49 brittle checks.**
   Suggested language:
   > "`test_surpass_2_primary_etd_present` accepts the SURPASS-2 primary HbA1c treatment differences as normalized numeric values (`-0.15`, `-0.39`, `-0.45`) with unit variants (`%`, `percentage points`, `pp`), and requires the sentence to cite the SURPASS-2 primary bibliography entry. Add parallel checks for SURPASS-4 N=1,995 or 104-week durability and SURPASS-CVOT HR 0.92 / noninferiority wording."

7. **Add explicit population-scope mitigation for SURMOUNT.**
   Suggested language:
   > "SURMOUNT-2 is direct T2D+obesity evidence. SURMOUNT-1/3/4 are related obesity/weight-management evidence unless the row's population includes T2D; the generator must label them as indirect/related for a T2D question and must not merge their weight-loss estimates into direct T2D efficacy claims."

## Answers to Claude's 5 self-critical questions

1. **Is M-44 truly root_cause or retrieval-side band-aid?**  
   As written, no. It is necessary enforcement, but not root-cause-complete because the current prompt already contains a trial-specific primary-citation rule and V27 still failed. Make M-44 a combined section-scorer/subset boost plus validator. Then it becomes root-cause: it handles "primary present but derivative cited" at the earliest generation-selection boundary.

2. **Is M-45 a contract reversal on M-42b's >=100 char strict rule?**  
   No, if it remains refetch-or-skip. The concern is not contract reversal; it is stale mechanism description. Current code already appears to route refetch through AccessBypass. M-45 must prove what failed in V27 and improve that path without allowing statement-only or generated-prose fallback.

3. **Is M-47's >=3 quantitative findings rule brittle?**  
   Yes, if implemented as generic section regex. It is acceptable if the validator is evidence-linked: extract allowed values/units from the cited clamp/PK row, then require those fields in verified prose. Keep regex deterministic, but make it row-grounded.

4. **Are preservation tests too strict?**  
   The SURPASS-2 values are clinically appropriate anchors, but exact string checks are too strict. Normalize signs, decimals, unit spellings, and "percentage point"/"pp" variants. Also require primary-source citation in the same sentence; otherwise a copied number from a derivative source could pass.

5. **Order of implementation risk.**  
   The broad order is right, but revise it to avoid building on brittle assumptions: M-48 -> M-46(selector revision, not only cap) -> M-44 scorer/subset boost -> M-45 refetch diagnostics/fix -> M-47 mechanism extraction -> M-49 preservation suite. M-45 can run in parallel with M-44 only after diagnostics confirm the actual refetch failure.

## Completeness review

V28 can probably preserve the existing 3 BEAT_BOTH dimensions and convert the two LOSE_BOTH dimensions to BEAT_ONE. It is not yet likely to reach 4-5 BEAT_BOTH.

- **Per-trial subsection outline generator**: add a small V28 item if the goal is a fourth BEAT_BOTH. M-45's table + timeline likely moves Structural depth from LOSE_BOTH to BEAT_ONE, but ChatGPT still wins on per-trial PICO/effect details and Gemini still wins on narrative trial subsections. Minimal acceptance: subsections for SURPASS-2, SURPASS-4, SURPASS-CVOT, and SURMOUNT-2 with N, population, comparator, endpoint/timepoint, effect estimate, uncertainty/interpretation, and safety caveat.
- **Scorer-level primary-paper boost**: yes, M-44 should include it. Without it, rule 13 is just another prompt instruction after M-20 already failed in practice.
- **AMSTAR-2 / GRADE / PRISMA additions**: GRADE-style certainty per major claim is the highest-leverage V28 addition. A full PRISMA flow diagram is probably not worth V28 scope unless the manifest already makes it trivial. A compact risk-of-bias table for pivotal open-label/sponsor-funded trials would strengthen Contradictions/uncertainty and protect against ChatGPT's sponsorship/open-label advantage.

## Implementation order confirmation or revision

Recommended order:

1. **M-48** retrieval anchor verification and per-anchor query variants.
2. **M-46 revised** selector early-exit/floor telemetry fix plus V28 cap.
3. **M-44 revised** scorer/subset primary boost plus same-sentence primary validator.
4. **M-45 revised** refetch diagnostics, then targeted acquisition fix based on diagnostics.
5. **M-47 revised** evidence-linked clamp/PK quantitative extraction validator.
6. **M-49 revised** preservation/integration suite after the output contracts are final.

If Claude wants V28 to target 4+ BEAT_BOTH rather than merely remove LOSE_BOTH, add a seventh item before M-49: **M-50 per-trial subsection generator** with the minimal SURPASS-2 / SURPASS-4 / SURPASS-CVOT / SURMOUNT-2 acceptance above.
