# I-cred-010 (#1159) — Phase 10: dissent-recall query builder (pure module) — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 2 of 5. (See §8 ITER-1 RESOLUTIONS — minority-targeting via the Phase-6 weight signal supersedes §2/§3.)
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining-non-P0/P1; no iter 6.
- Surface any held-back P1 NOW. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Reviewing a DESIGN BRIEF (acceptance-criteria correctness), not a diff.

## 0. HARD CONSTRAINTS (operator-locked)

- **ADDITIVE / advisory ONLY.** Dissent-recall ADDS retrieval breadth for the MINORITY side of a contested claim. Everything it brings back still passes the EXISTING gates — `tier_classifier`, `authority_model.score_source_authority`, `evidence_selector` (tier quotas + `PG_RELEVANCE_FLOOR`), and `strict_verify` (the only binding faithfulness gate). It NEVER lowers adequacy thresholds, NEVER injects sources that bypass authority/relevance scoring, NEVER changes `strict_verify`.
- **DEFAULT-OFF byte-identical:** `PG_SWEEP_DISSENT_RECALL` (no production caller; the saturation-loop wiring is the follow-up I-cred-010b).
- **Pure**, snake_case, explicit imports, no network in the builder itself, no input mutation, LAW VI.

## 1. SCOPE (confirm the split)

This issue ships the pure **dissent-query + stratification-plan BUILDER** only. The saturation-loop integration (calling the builder, appending its queries to the next gap round, passing the stratification hint to the runner — `retrieval/saturation.py:377/425`) is the gate-adjacent follow-up I-cred-010b. **Q1:** confirm.

## 2. Goal

`src/polaris_graph/retrieval/dissent_recall_builder.py`: given the Phase-5 contradiction edges + atomic claims, emit (a) dissent-SEEKING query strings that go looking for the minority/contrary side, and (b) a source-type stratification plan (advisory per-backend quota hints) — so a contested claim ends with real evidence on EACH side, not just the majority. Mirrors the pure-helper pattern of `retrieval/query_decomposer.py`.

## 3. Contract

```python
PG_SWEEP_DISSENT_RECALL  # flag + dissent_recall_enabled() + _OFF_VALUES frozenset (match siblings)

def build_dissent_queries(
    contradiction_edges: list,     # Phase-5 ContradictionEdge (subject, predicate, claim_cluster_ids, severity)
    claims: list,                  # Phase-5 AtomicClaim (subject, predicate, text) for richer phrasing
    *,
    max_queries: int = 8,          # env-overridable cap (PG_DISSENT_QUERIES_MAX) — prevents query explosion
    query_fn=None,                 # optional injected (subject, predicate, text) -> list[str]; default = deterministic templates
) -> list[str]:
    """Pure. For each CONTESTED (subject, predicate), emit deterministic dissent-seeking queries
    (e.g. '<subject> no effect', '<subject> contrary evidence', 'criticism of <subject> <predicate>',
    'limitations of <subject>'). Deduped, capped at max_queries. Returns [] for no edges (byte-identity
    when OFF). An optional query_fn lets a flagged caller inject an LLM dissent-query generator later
    (mirrors the Phase-2 injected-judge pattern) — the pure default builds NO network call."""

def build_source_stratification_plan(
    contested_count: int,
    available_backends: list,      # e.g. ['serper', 's2', 'openalex', 'domain']
    *,
    per_type_quota: dict | None = None,  # env/operator override
) -> dict:
    """Pure. Emit an ADVISORY per-source-type quota plan (a hint, not enforcement) so dissent retrieval
    is stratified across web / academic / open-access / regulatory — not all from one source type. Empty
    plan when contested_count == 0 (byte-identity)."""
```

## 4. Acceptance criteria (offline, deterministic, no network)

1. Flag default-OFF helper (matches siblings).
2. No contradiction edges → `build_dissent_queries(...) == []` AND stratification plan empty (byte-identity precondition).
3. One contested (subject="vaccine", predicate="reduces hospitalization") → ≥1 dissent-seeking query that targets the CONTRARY side (e.g. contains 'no effect' / 'contrary' / 'criticism' / 'limitation'), deterministic + deduped.
4. `max_queries` cap is honored (many edges → output length ≤ max_queries); env knob changes it.
5. Injected `query_fn` is used when provided; its output is deduped + capped; a `query_fn` that raises falls back to the deterministic templates for that edge (fail-soft, no crash) — the builder is offline by default (no network unless a caller injects one).
6. `build_source_stratification_plan` returns per-backend quotas summing to a sane budget; only listed `available_backends` get quotas; empty for `contested_count == 0`.
7. Purity: inputs not mutated; deterministic ordering; no faithfulness import; the builder makes NO retrieval call (it only BUILDS queries/plan — execution is the caller's, through the existing gates).
8. Safety doc-as-test: a comment/test asserts the builder returns QUERIES ONLY and never fetches/selects/scores (the existing gates remain the sole path for what comes back).

## 5. Files I have ALSO checked and they're clean (substrate scan — please VERIFY)

- `retrieval/query_decomposer.py:111` `decompose_question(...)` + `build_amplified_query_list(...)` — the pure-helper + query-group-prepend pattern P10 mirrors.
- `retrieval/saturation.py:305,377,425` `drive_saturation_loop` / `gap_sub_queries` / `run_round_fn` — the EXISTING gap-driven multi-round seam the wiring (I-cred-010b) appends dissent queries to. NOT touched here.
- `synthesis/claim_graph.py:152` `ContradictionEdge{subject, predicate, claim_cluster_ids, severity}` — the contested-claim signal.
- `retrieval/evidence_selector.py:31,98` `PG_RELEVANCE_FLOOR` + tier quotas — the gate dissent sources still pass. P10 does NOT change it.
- `authority/authority_model.py` `score_source_authority` + `retrieval/tier_classifier.py` — applied to every dissent source post-fetch. Unchanged.
- `clinical_generator/strict_verify.py` — the binding gate. Unchanged.

## 6. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## 7. Questions

Q1 scope split (pure builder now; saturation wiring I-cred-010b)? Q2 are deterministic dissent templates acceptable for v1 with an injectable LLM `query_fn` seam for later, or do you want the LLM generator in-scope now? Q3 stratification plan as an ADVISORY hint (not a hard quota override) — right, so it can't starve the consensus side?
