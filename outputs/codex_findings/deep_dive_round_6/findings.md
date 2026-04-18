---
target_bug: M-201
scope: retrieval/generator evidence divergence
verdict: confirmed
severity: medium
strategy_chosen: B
tests_required: 6
rationale: |
  Corpus approval and adequacy reason over `retrieval.classified_sources` plus the full `retrieval.evidence_rows`, but generation receives only `retrieval.evidence_rows[:PG_LIVE_MAX_EV_TO_GEN]` in inherited retrieval order. The live retriever does not relevance-rank or tier-balance evidence rows before this slice. It appends candidates by query/backend order, truncates candidates by fetch cap, classifies every fetched candidate, and only appends evidence rows with non-starved content. The result is that gates certify one corpus/evidence pool while synthesis and evaluator evidence lookup operate on a smaller, order-biased pool.
---

## 1. Finding

BUG-M-201 is confirmed.

The generator-visible evidence pool is controlled by one environment variable and one raw list slice:

| Control | Location | Behavior |
|---|---:|---|
| `PG_LIVE_MAX_EV_TO_GEN` | `scripts/run_honest_sweep_r3.py:766` | Defaults to `20`. |
| `retrieval.evidence_rows[:max_ev]` | `scripts/run_honest_sweep_r3.py:767` | Takes the first N evidence rows exactly as stored. |
| `generate_multi_section_report(... evidence=evidence_for_gen ...)` | `scripts/run_honest_sweep_r3.py:781-783` | Synthesis sees only that sliced pool. |
| `ev_pool = {ev["evidence_id"]: ev for ev in evidence_for_gen}` | `scripts/run_honest_sweep_r3.py:942` | Rule evaluation also validates against the same sliced pool, not all retrieved evidence. |

There is no sort, relevance score, tier quota, source-family quota, contradiction-aware selection, or deterministic balancing at the generator handoff.

## 2. Divergence Path

The live retriever preserves backend/query append order:

| Stage | Location | Effect on order/pool |
|---|---:|---|
| Serper hits appended first per effective query | `src/polaris_graph/retrieval/live_retriever.py:420-438` | Search-engine order enters the candidate list directly. |
| Semantic Scholar hits appended after Serper for the same query | `src/polaris_graph/retrieval/live_retriever.py:440-454` | Academic hits can be pushed behind Serper hits. |
| Domain backend candidates appended after generic backends | `src/polaris_graph/retrieval/live_retriever.py:459-484` | Domain-specific evidence can be late in the list. |
| Optional off-topic filter keeps order | `src/polaris_graph/retrieval/live_retriever.py:493-501` | No ranking is introduced. |
| Fetch cap slices candidates | `src/polaris_graph/retrieval/live_retriever.py:503-504` | Candidate truncation is order-based. |
| Every fetched candidate is classified | `src/polaris_graph/retrieval/live_retriever.py:531-553` | `classified_sources` can include URLs that never become generator evidence. |
| Evidence rows are appended only when content is usable | `src/polaris_graph/retrieval/live_retriever.py:561-583` | Content-starved rows disappear from generation evidence, but their classified source still contributes to corpus tier distribution. |

The gates then use broader inputs than generation:

| Gate/check | Location | Input |
|---|---:|---|
| Corpus tier distribution | `scripts/run_honest_sweep_r3.py:476-485` | `retrieval.classified_sources` |
| Corpus adequacy | `scripts/run_honest_sweep_r3.py:487-493` | `dist.tier_counts` from classified sources plus `len(retrieval.evidence_rows)` |
| Completeness | `scripts/run_honest_sweep_r3.py:508-514` | Full `retrieval.evidence_rows` |
| Post-expansion adequacy | `scripts/run_honest_sweep_r3.py:604-610` | Full merged classified/evidence pools |
| Generation | `scripts/run_honest_sweep_r3.py:765-783` | First N evidence rows only |

Real artifact check: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/run_log.txt` currently shows `[corpus] total=20`, `[adequacy] decision=expand`, and `[generation] ... evidence=4...`. The tier mix in this workspace copy is `T1=40%, T4=30%, T7=30%`, not the prompt's older `T1=0% T2=0% T3=5% T5=50%` example, but the divergence is the same: gates reasoned over 20 classified sources while generation received 4 evidence rows.

## 3. Fix Choice

Choose **B: add explicit tier-balanced and relevance-ranked evidence selection**.

Do not choose A as the primary fix. Computing all gates over the generator-visible pool would make certification honest, but it throws away useful retrieved evidence solely because of prompt budget. It would also make adequacy sensitive to a budget knob rather than retrieval quality.

Do not choose C as the primary fix. Raising `PG_LIVE_MAX_EV_TO_GEN` reduces observed divergence for small pools but preserves the core bug. It also increases prompt cost and can fail again as retrieval expands.

Strategy B keeps corpus-level gates meaningful while making the generator-visible subset a deterministic, representative projection of the approved pool.

## 4. Fix Specification

Add a dedicated selector, for example `select_evidence_for_generation(...)`, and use it before contradiction extraction, generation, manifest telemetry, and evaluator pool construction.

Required behavior:

1. Join `evidence_rows` to `classified_sources` by URL so each selectable row has tier, tier confidence, source/backend, URL domain, original retrieval index, and content length.
2. Compute a deterministic relevance score for each evidence row. Minimum viable scoring can use lexical overlap between the research question/protocol anchors and `statement + direct_quote`, with stable tie-breakers. If an embedding reranker is available locally, put it behind an explicit optional flag, not a hidden network dependency.
3. Allocate tier-aware quotas from the full evidence-row tier distribution, with floors for high-value tiers present in the pool. The selector should not blindly mirror bad distributions, but it should prevent a generator slice from omitting present high-quality tiers because they arrived late.
4. Select within each tier by relevance score, then fill remaining slots globally by relevance while enforcing URL/domain dedupe limits where possible.
5. Preserve stable `evidence_id` values. Do not renumber selected evidence unless every downstream citation path is updated.
6. Emit selection telemetry in `manifest.json`: `evidence_total`, `evidence_selected`, `selection_strategy`, selected tier counts, full tier counts, and dropped counts/reasons.
7. Pass selected evidence to all downstream consumers that reason about generated claims: `generate_multi_section_report`, external evaluator `ev_pool`, and any report-level citation metrics.
8. Keep corpus approval/adequacy over the full classified/evidence pools, but add a generator-pool adequacy warning if the selected pool cannot satisfy minimum tier/topic coverage. A hard abort should be reserved for cases where the full pool itself is inadequate or no representative selected subset can be formed.

Recommended selector signature:

```python
def select_evidence_for_generation(
    *,
    research_question: str,
    protocol: dict[str, Any],
    classified_sources: list[CorpusSource],
    evidence_rows: list[dict[str, Any]],
    max_rows: int,
) -> EvidenceSelection:
    ...
```

`EvidenceSelection` should include `selected_rows`, `full_counts`, `selected_counts`, `dropped_rows`, and human-readable `notes`.

## 5. Tests

1. `test_generator_selection_not_raw_prefix`: build 25 synthetic evidence rows where the first 20 are low-tier/low-relevance and later rows include high-tier/high-relevance evidence. Assert selected rows are not equal to `evidence_rows[:20]` and include the late high-value rows.
2. `test_generator_selection_tier_balances_present_tiers`: create a full pool with T1/T2/T5 evidence and a max smaller than the pool. Assert selected tier counts include available high-quality tiers according to the quota rules.
3. `test_selector_is_stable_for_equal_scores`: with equal relevance scores, assert ordering is deterministic using original index/evidence_id tie-breakers.
4. `test_selection_joins_classified_sources_by_url`: include a classified source whose content was starved and therefore has no evidence row. Assert it contributes to corpus distribution but is not selectable, and no missing-join crash occurs.
5. `test_generation_and_evaluator_use_same_selected_pool`: monkeypatch `generate_multi_section_report` and `run_external_evaluation`; assert both receive/build pools from the selector output, not full evidence rows and not raw prefix rows.
6. `test_manifest_records_evidence_selection_telemetry`: run a small orchestrator fixture and assert manifest contains full vs selected evidence counts, selected tier counts, strategy name, and dropped count.

## 6. Residual Risk

Tier-balanced selection is only as good as the relevance signal. The first implementation should prefer a simple deterministic lexical scorer plus transparent telemetry over a complex scorer that is hard to test. If later quality data shows lexical ranking is weak, the selector boundary gives a clean place to add a stronger reranker without changing gate semantics again.
