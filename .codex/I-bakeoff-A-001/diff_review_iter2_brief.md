## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 2 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Iter-1 P1+P2 disposition

| Iter-1 finding | Iter-2 fix |
|---|---|
| **P1** Pool loader doesn't accept canonical EvidencePool (sources[*].source_id, full_text/snippet); verified-sentences only reads obj['sentence']. | **FIXED.** New `_normalize_pool()` accepts: legacy {evidence_id + direct_quote}, canonical {source_id + full_text/snippet}, {sources: [...]} wrapper, already-keyed dict. New `_normalize_sentence()` accepts: {sentence: ...}, {sentence_text: ...}, raw string. CLI fails loudly if non-empty input produces 0 sentences. Regression tests `test_canonical_evidencepool_source_id_schema` + `test_canonical_verified_sentence_field_normalization`. |
| **P2** REVIEW vocab vs ACCEPT/REJECT/INVESTIGATE | **FIXED.** Below-threshold-no-alert maps to INVESTIGATE; vocab now strictly ACCEPT / REJECT / INVESTIGATE per brief. |
| **P2** Audit table doesn't expose cited span quote | **FIXED.** `audit_sentence()` now records `span_text` (truncated to 200 chars) per token; `_render_audit_md()` adds "Cited span quote" column. Regression test `test_audit_md_includes_cited_span_quote`. |

17 tests pass.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
