# I-perm-023 (#1215) — diversity-aware selection + SourceEvidencePack cache: forensic (durable)

Forensic by the parallel Claude agent (2026-06-11), persisted so it is not lost.

## 0. Ground-truth correction (reframes the issue's drb_76 example)
The issue says map-reduce over-selects clear/long/easy sources (drb_76: 1 fiber meta + 1
colibactin + 1 safety). The real `outputs/audits/beatboth8/drb_76/manifest.json` shows a
THREE-LAYER conflation:
- `evidence_selection.selection_strategy = "tier_balanced_v1_all_m46_ordered"` — the SHORT-POOL
  branch ran (`_m46_short_pool_ordered_selection`, evidence_selector.py:876).
- evidence_total=46, evidence_selected=46, dropped_count=0 → the selector dropped NOTHING (pass-
  through because pool 46 <= max_rows 150).
- The collapse is UPSTREAM of the selector: discovery_funnel 906 fetch → 629 ok, yet only 46 rows
  reach the selector (~90% loss in extraction, owned by I-perm-007).
- The "1 fiber + 1 colibactin + 1 safety" is `manifest.finding_dedup.clusters` (corroboration_count=1)
  = finding-level concentration, NOT row over-selection.

### Three-layer scope fence (binding)
| Layer | Defect | In #1215 scope? | Owner |
|---|---|---|---|
| Selector ranking | relevance×authority / tier-balanced top-K, ZERO coverage/family/class/entity term → monoculture WHEN pool>cap | YES (diversity half) | this issue |
| Distiller MAP | MAPs each source once PER SECTION (cost/latency) | YES (cache half) | this issue |
| Finding-level concentration on drb_76 | each source yields one dominant finding; no entity/safety-class coverage credit | NO | coverage_binder / RequiredEntityLedger (#1212/#1213), distiller #1209/#1218 |

This is a FORWARD GUARD: constrained-greedy changes nothing at drb_76 scale (no-op when pool<=cap);
it only diversifies once I-perm-007 grows the post-extraction pool past the cap (the 1000-URL target).

## 1. Root cause (file:line)
Tier-balanced truncating path in `select_evidence_for_generation` (evidence_selector.py):
- Ranking is relevance-only within tier (`_row_relevance` 406-423; within-tier sort `(-score, idx)`
  + soft recency 1364-1367). NO coverage_gain term → two T1 rows on the SAME sub-topic both win and
  crowd out a T1 row on a different required entity/safety-category.
- Relevance-floor path (`_relevance_floor_selection` 1076-1138, Gate-B `PG_USE_FINDING_DEDUP`) ranks
  by -(relevance×authority) (1110) — again no coverage/family/entity diversification.
- Existing diversity passes are WRONG-AXIS: `_apply_domain_cap` (824) caps by registrable DOMAIN;
  `_reserve_subqueries` (765) by sub-query origin. Neither covers entity/safety_category/evidence_class
  → 3 different domains all on "fiber→SCFA" pass the domain cap yet are a topical monoculture.
- Ad-hoc floors (M-51 min-1-primary-per-anchor 1611-1707; M-41d/M-42d jurisdiction 1513-1607;
  M-42c ≥3 mechanism 1389-1414) are siloed; #1215's constrained-greedy UNIFIES them.

## 2. Design (two default-OFF PRs — the combined diff exceeds the 200-LOC cap)
### PR-1: constrained-greedy selector (flag `PG_SELECT_CONSTRAINED_GREEDY`)
NEW third top-level branch in `select_evidence_for_generation` that OWNS selection when ON (do NOT
retrofit into the floor stack — risks double-applying #956 + breaking byte-identical-off). Pure
DETERMINISTIC facility-location greedy (no RNG/DPP — reproducibility invariant).
Per-candidate marginal score vs already-selected S:
```
gain(row|S) = w_rel*relevance + w_cov*coverage_gain(entity∪safety_cat∪ev_class novel buckets)
            + w_auth*authority_bonus - w_red*redundancy(lexical Jaccard) - w_fam*family_overcap_penalty
```
All weights env knobs (PG_GREEDY_W_*; LAW VI). Hard constraints (feasibility filters): max N per
source family (_row_domain); min 1 per required evidence class; min 1 primary anchor per required entity
(reuse `_m42e_detect_primary_for_anchor`). Greedy: (1) mandatory reservation pass for each min-1
constraint, (2) free fill argmax gain, ties `(-relevance, tier_priority, original_idx)`. Telemetry:
diversity_score, per-family counts, covered classes/entities into EvidenceSelection.notes + to_dict().
Reuse predicates: `_row_domain`:740, `_row_jurisdiction`:174, `_m42c_row_is_mechanism_rich`:334,
`_m42e_detect_primary_for_anchor`:356, `v30_entity_id` field. NEW deterministic `_row_safety_category`
keyword predicate (FDA/DailyMed SPL taxonomy) + guideline/real-world class predicates (env-overridable
vocab, no LLM). Insert at TOP of truncating path AFTER the relevance_floor early-return (1244).
Byte-identical-off: flag truthy-only default OFF → zero new code runs.

### PR-2: SourceEvidencePack cache + MAP de-sectioning (flag `PG_DISTILL_SOURCE_PACK`)
NEW frozen `SourceEvidencePack` dataclass in evidence_distiller.py: {source_hash=sha256(direct_quote),
question_hash=sha256(research_question), findings[validated DistilledFinding], spans, bindings
(entity/safety/ev_class precomputed), versions}. SECTION-INDEPENDENT cache key:
sha256(source_hash, question_hash, map_prompt=MAP_PROMPT_VERSION, finding_schema=DISTILLER_VERSION,
model, taxonomy=TAXONOMY_VERSION, fuzzy=_distill_fuzzy_min_overlap_frac()) → MAP runs ONCE per
source/question (not per section). REDUCE filters pack findings by section facets (section decision
moves MAP-time → REDUCE-filter-time). De-sectioning the MAP is BEHAVIORAL (extraction yield up) →
faithfulness-NEUTRAL (final strict_verify unchanged) but its proof is the §-1.1 paid audit, NOT a
unit test (riskier of the two PRs). 5 version axes bind the key (the #1217 DISTILLER_VERSION lesson
generalized).

## 3. Faithfulness
- Selector (PR-1) CLEAN: only changes WHICH rows reach the generator (the candidate menu). strict_verify
  (multi_section_generator.py:2413) re-checks every sentence over the FULL evidence_pool; 4-role + D8
  unchanged. Selection cannot relax a gate. Unit test suffices.
- Cache/distiller (PR-2) HONEST/WEAKER: de-sectioning changes WHAT is extracted (recall up). Faithfulness
  holds because final per-sentence strict_verify on REDUCE prose is the SOLE publication authority + the
  per-finding fuzzy-entailment gate (`_validate_finding`) unchanged. But yield shifts → proof is the
  §-1.1 line-by-line audit on REAL output, not a green unit test.

## 4. Open question for Codex/operator (DoD #5)
A paid smoke at drb_76 scale shows NO selector delta (pool 46 < cap; selector is a no-op there).
Two honest options: (a) run the paid smoke on a corpus where pool>cap to show a live selector delta;
OR (b) scope the paid smoke to the cache half (MAP-once + no fabrication §-1.1 audit) + no-regression,
accept selector delta shown offline only until I-perm-007 grows the pool. BINDING scope question.

## 5. Honesty caveats
1. The selector is a FORWARD GUARD, not a drb_76 fix (no-op until pool>cap, I-perm-007 territory).
2. The drb_76 monoculture is a finding-level/upstream-extraction problem (I-perm-007 + coverage_binder/
   RequiredEntityLedger), NOT this issue. Do not let the plan absorb it.
3. `_row_safety_category` + guideline/real-world predicates are NEW keyword matchers (versioned; affect
   only WHICH sources are preferred, never what passes a gate — a miss costs diversity, never faithfulness).
4. De-sectioning the MAP is behavioral → PR-2 faithfulness rests on the §-1.1 audit, not the unit test.
5. TWO PRs (200-LOC cap); selector + cache are independent flags shipped separately.
6. Greedy != DPP (deterministic argmax + total-ordered tiebreaks preserve reproducibility).
7. authority_score is a sidecar (added by dedup_by_finding), default 1.0 when absent.

Key files: evidence_selector.py (PR-1; root cause 1276+, ranking 406-423/1110), evidence_distiller.py
(PR-2; _cache_key:378, DISTILLER_VERSION:74, distill_section_evidence:1141), multi_section_generator.py
(call site 2369-2375), run_gate_b.py (slate: wire both flags), docs/drb76_downstream_solutions.md
(items #4 selector, #6 cache), manifest.json (ground truth), test patterns test_m201_evidence_selection.py
/ test_m46_selector_no_bypass.py / test_m51_selector_primary_custody.py.
