Diff review iter 2 for GH#423 Phase 2. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Iter-1 P1 status

## P1-1 RESOLVED — kept_sentences are SentenceVerification, not strings
```python
# OLD: kept_sentences_pre_resolve=list(report.kept_sentences)
# NEW: kept_sentences_pre_resolve=[sv.sentence for sv in report.kept_sentences]
```
Now the dedup pipeline receives raw sentence strings, matching the fact_dedup module API. TypeError eliminated.

## P1-2 RESOLVED — rewrites bypass strict_verify

New behavior: after dedup_pass produces deduped_sections, the orchestrator:
1. Identifies NEW (rewrite) sentences vs UNCHANGED originals via set diff against `original_set = set(sr.kept_sentences_pre_resolve)`.
2. Re-runs `strict_verify` ONLY on the rewrite candidates (joined as newline-delimited prose).
3. Accepts a rewrite IFF `sv.sentence in verified_rewrite_set` (i.e., strict_verify kept it).
4. Drops rewrites that failed strict_verify; PRIMARY-only behavior survives in those cases.
5. Final section sentence list = originals that survived dedup + verified rewrites.

Telemetry now includes `n_rewrites_strict_verify_pass` and `n_rewrites_strict_verify_drop` so the safety gate is observable.

This means: an LLM rewrite that introduces unsupported content gets dropped exactly the same way upstream strict_verify drops unsupported sentences. No clinical-safety bypass.

# Iter-1 P2 — acknowledgements + partial fixes

## P2-1 (M-44/M-47 regen later overwrites dedup) — ACKNOWLEDGED, deferred
Dedup runs at line 3522 (right after section_results assembly), BEFORE M-44 regen at line 3613. M-44 regen can recompose individual sections (it's a primary-citation-validator regen, runs only when M-44 detects missing primary cites). If M-44 regen fires AFTER dedup, the regen overwrites the deduped content. This is a real follow-up concern (`fact_dedup_after_m44` would be cleaner) but: (a) M-44 regen rarely fires in policy/pharmacare sweeps (no SURPASS-N triggers); (b) the cleaner fix is to move dedup AFTER both M-44 + M-47 regens — straightforward but separate iteration. Captured as known limit in telemetry comment; tracked for follow-up issue.

## P2-2 (contract sections never populate kept_sentences_pre_resolve) — ACKNOWLEDGED, partial
Contract sections (V30 path) go through `run_contract_section` in contract_section_runner.py which builds SectionResult without populating the new field. They effectively skip dedup. Q5 Pharmacare did NOT use V30 contracts (its template is policy, not the V30 clinical bakeoff lane). For Carney delivery, none of the 5 priority questions trigger V30 contracts. Captured for follow-up if/when V30 lane is used for clinical reports.

## P2-3 (sentences_dropped not updated on dedup-drop) — FIXED
Added:
```python
sr.sentences_dropped += (
    len(sr.kept_sentences_pre_resolve) - len(final_sents)
    if len(final_sents) < len(sr.kept_sentences_pre_resolve) else 0
)
```
plus `sr.dropped_due_to_failure = True` when final_sents is empty.

## P2-4 (dedup LLM call not counted in token totals) — ACKNOWLEDGED, deferred
The dedup `_dedup_llm_callable` returns a response object with input_tokens/output_tokens; the orchestrator doesn't currently accumulate them into `total_in_tok` / `total_out_tok`. Cosmetic telemetry issue, not a functional defect. Captured for follow-up.

# Test results

```
PYTHONPATH=src python -m pytest tests/polaris_graph/test_fact_dedup.py \
  tests/polaris_graph/test_section_prompt_gh422.py \
  tests/polaris_graph/test_multi_section_gap4.py \
  tests/polaris_graph/test_multi_section_limitations_r1.py
44 passed in 3.74s
```

# Diff at `.codex/I-gen-002-phase2/codex_diff.patch` — current state

```
$ git diff --stat src/polaris_graph/generator/multi_section_generator.py
src/polaris_graph/generator/multi_section_generator.py | 135 +++++++++++++++++++
```

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
