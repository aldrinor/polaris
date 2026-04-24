You are diagnosing WHY only 4 evidence_rows survived upstream filtering
for V23, despite a 20-source corpus that cleared every adequacy
threshold except evidence_rows (8 T1, 9 T1+T2+T3, 20 total sources).

## Narrow scope — do NOT enumerate archive/, logs/, state/

Look ONLY at:
1. `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/live_corpus_dump.json` (V23 corpus)
2. `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/corpus_adequacy.json`
3. `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/manifest.json` (already summarized below)
4. `src/polaris_graph/retrieval/evidence_selector.py`
5. `src/polaris_graph/retrieval/live_retriever.py` (evidence-row emission path)
6. `src/polaris_graph/generator/multi_section_generator.py` (how evidence is received)

Also compare against V22's working state:
- `outputs/full_scale_v22/clinical/clinical_tirzepatide_t2dm/live_corpus_dump.json`
- `outputs/full_scale_v22/clinical/clinical_tirzepatide_t2dm/corpus_adequacy.json`

Do NOT grep archive/ or logs/. Do NOT write code. Diagnostic only.

## Known facts (do not re-investigate)

- V22 (good, at full_scale_v22/): 38 citations, 54 verified sentences,
  1928 words, status=success.
- V23 (regression, at honest_sweep_r3/): 7 citations, 22 verified
  sentences, 688 words, status=partial_qwen_advisory.
- V23 corpus tier distribution: T1=8, T3=1, T4=6, T5=1, T7=4 (total 20).
- V23 adequacy findings[5] says: name=evidence_rows, observed=4,
  threshold=6, ok=false, severity=warn.
- All other V23 adequacy thresholds PASS (total_sources, t1_count,
  t1_plus_t2, t1_plus_t2_plus_t3, low_quality_fraction, t7_fraction).
- Only binding change M-33 made: `section_max_tokens` 1200→2400 in
  scripts/run_honest_sweep_r3.py. No retrieval or evidence code was
  modified.

## Your task

Trace the narrowing from 20 sources → 4 evidence_rows in V23.

Specifically answer:

A. What field in corpus_adequacy.json reports evidence_rows? Is
   "evidence_rows" counting rows after some filter, or the raw count
   of content-extracted rows?

B. Look at `live_corpus_dump.json`: how many of the 20 sources have
   content payloads populated (non-empty body/extract)? Are 16 of
   them dropped because fetch failed, or because content was filtered
   as noise?

C. Compare to V22's `live_corpus_dump.json`: how many sources did
   V22 have in the same corpus_dump, and of those how many passed
   through to the generator? What changed between V22 and V23 runs
   that would narrow the evidence pool so sharply?

D. One-line root cause: is the V23 `evidence_rows=4` bottleneck
   (i) a retrieval-side content-fetch failure (most sources returned
   empty payloads), (ii) an extraction-side filter (content quality
   gate or prefetch off-topic filter rejecting sources), (iii) a
   tier-selection cap, (iv) or a code path that M-33 inadvertently
   affected (unlikely but possible)?

Keep each answer ≤ 150 words. No code changes, no speculation beyond
what the artifacts show.

## Verdict format

Write `outputs/codex_findings/v23_evidence_bottleneck/findings.md`:

```
# V23 evidence bottleneck diagnosis

## A. What does evidence_rows count?
<answer with code line citation>

## B. V23 live_corpus_dump content payload state
<answer with concrete numbers>

## C. V22 vs V23 delta in corpus_dump
<answer with numbers>

## D. Root cause (one line)
<answer>
```

Return READY_FOR_FIX or NEED_MORE_DIAGNOSIS at the end.
