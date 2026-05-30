# Codex DIFF-gate — I-meta-002 sub-PR-4 — iter 2 of 5

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Reserve P0/P1 for real execution/safety risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

## What changed since your iter-1 diff review
Your iter-1 verdict was REQUEST_CHANGES, zero P0, ONE P1:

> mirror_adapter.py:88 — Empty-string doc_ids can be accepted if the supplied evidence set
> contains EvidenceDocument(doc_id=""), because valid_doc_ids is built from raw doc.doc_id values
> and the validator only rejects an empty doc_ids tuple. A structured citation with doc_ids=("",)
> then survives and satisfies grounding, violating the required rejection of empty/missing doc_ids.

**Fix applied (two layers, defense in depth):**
1. `valid_doc_ids` now EXCLUDES empty/whitespace doc_ids:
   `valid_doc_ids = {doc.doc_id for doc in evidence_documents if doc.doc_id and doc.doc_id.strip()}`
   — so an `EvidenceDocument(doc_id="")` can never put `""` into the identity pool.
2. `_validate_citation_binding` now also rejects a span if ANY of its doc_ids is empty/whitespace
   (`if any((not doc_id or not doc_id.strip()) for doc_id in span.doc_ids): continue`), before the
   membership check. An empty/whitespace doc_id is never grounding.

**Regression tests added:**
- `test_empty_doc_id_in_evidence_set_does_not_launder_empty_citation_codex_diff_p1` — your exact
  case: evidence set contains `EvidenceDocument(doc_id="")`, citation span doc_ids=("",) ->
  MirrorCitationError (no laundering); pass-2 never reached.
- `test_whitespace_doc_id_span_is_rejected` — a whitespace-only doc_id echoed in the evidence set
  is still rejected.

## Smoke (serialized, §8.4)
- `pytest tests/roles tests/architecture tests/dr_benchmark -q` -> 254 passed, 0 failed.
- `verify_lock --consistency` -> exit 0.
- No network anywhere; transport injected; mock transport only in tests.

## Review ask
Re-probe the Mirror grounding-integrity guard: can ANY citation that does not bind to a real,
non-empty supplied evidence doc_id survive into a grounded `MirrorPass1` and satisfy the content
binding? APPROVE iff empty/whitespace/hallucinated/mixed doc_ids are all rejected and a claim with
no valid grounded citation fails closed.

## DIFF (full sub-PR-4 diff, citation-binding fix included)
