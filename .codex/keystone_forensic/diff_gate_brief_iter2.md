# Codex DIFF-gate iter 2 — keystone distiller P2 hardening (#1217)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Same quality bar. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context
You APPROVED this diff at iter 1 (`.codex/keystone_forensic/diff_gate_verdict.txt`: zero P0/P1, mergeable_now_with_followup=true, density_gap_is_blocker=false) but flagged `faithfulness_fuzzy_gate_sound: false` + perf_blocks_scaling=true + a cache-key gap as P2s. I implemented ALL THREE now (not deferred). This iter asks you to confirm the fixes are correct and that `faithfulness_fuzzy_gate_sound` is now TRUE. The full updated diff is at `.codex/keystone_forensic/diff_gate_input.patch`; live in `src/polaris_graph/generator/evidence_distiller.py` + `tests/polaris_graph/generator/test_evidence_distiller_iperm016.py`. Read ONLY those two files + the patch; do NOT grep the whole repo (it has access-denied `codex_*` temp dirs that crash exploration).

## The 3 P2 fixes
1. **Negation-safe fuzzy span (your faithfulness P2, ref :525).** `_fuzzy_locate_span` no longer SHRINKS to the first/last matched content word (which could drop a leading "not"). It now localizes to the matched content-word region then EXPANDS each side to the nearest sentence terminator (`. ! ? \n`), so leading negation/qualifier function words stay in the span before the entailment check. Verified on the REAL CDC source: both "...are not recommended for ... immunocompromised ..." claims recover a span that RETAINS "not recommended". New regression test `test_fuzzy_locate_preserves_leading_negation_1217`.
2. **Perf (your perf P2, ref :753).** `_validate_finding` now calls `verify_sentence_provenance` ONLY for `locate_method == "fuzzy"` (where the entailment is BLOCKING). For exact/whitespace (verbatim, entailment was non-blocking) the slow verifier call is SKIPPED entirely — `finding_entailed = True`, finding kept, final strict_verify is the authority. This removes the per-finding LLM call that made MAXEV=40 prohibitive.
3. **Cache key (your cache P2, ref :336).** `_cache_key` now includes `fuzzy_min_overlap=<PG_DISTILL_FUZZY_MIN_OVERLAP>` so retuning the threshold misses the cache. Also bumped `DISTILLER_VERSION` v3→v4 (span-expand + perf-skip change validation outcome).

## Tests
21/21 distiller tests pass; 100/100 generator-dir tests pass. New negation regression added.

## Questions
1. Is `faithfulness_fuzzy_gate_sound` now TRUE — i.e., does expand-to-sentence-boundary reliably keep negation/quantifier context in the span the entailment judge sees? Any residual way a fuzzy span loses meaning?
2. Is skipping `verify_sentence_provenance` for exact/whitespace findings correct (no faithfulness loss — they were non-blocking; the only thing lost is the fail-closed verifier-ERROR guard for verbatim findings, which the final strict_verify on REDUCE prose still backstops)?
3. Any correctness bug in the new span-expand boundary math (off-by-one, window-relative offsets, empty-match) or the cache-key change?

## OUTPUT SCHEMA
```yaml
verdict: APPROVE | REQUEST_CHANGES
faithfulness_fuzzy_gate_sound: true | false
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
