# Codex Diff Review — I-f2-003 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-003 — Backend: disambiguation API endpoint
**Branch:** bot/I-f2-003
**Brief:** APPROVED iter 3 (iter1 REQ_CH 2P1 → iter2 REQ_CH 3P1 → iter3 APPROVE 0P0/0P1, 2 P2 advisories addressed in implementation)
**Canonical-diff-sha256:** `8e0b55f298ba71d55ed096c8d836a13632a992ea400617eb78f9ef2df3a421c5`
**LOC:** 200 net (CHARTER §1 hard cap = 200; exact)
**Local tests:** 8/8 PASS

## Files

```
src/polaris_graph/api/disambiguation_route.py        NEW +104
src/polaris_v6/api/app.py                            EDIT +3
tests/polaris_graph/api/test_disambiguation_route.py NEW +93
```

## What changed

`POST /api/disambiguation` accepts `DisambiguationRequest(candidates: list[CandidateSnippet], min_cluster_size=2 (ge=2), max_snippets_per_cluster=3 (ge=1))`. Pipeline:

1. Validate uniform embedding dim — else HTTP 400 `code=embedding_dim_mismatch`.
2. Stack to `np.ndarray((K, D))`, call `cluster_candidates(min_cluster_size=req.min_cluster_size)`.
3. If `num_clusters in (0, 1)` → return `is_ambiguous=False, clusters=[]` (LLM never called).
4. Else if `client is None` → HTTP 503 `code=label_client_unavailable` (LAW II — never silently substitute).
5. Else call `label_clusters(...)` → map to `ClusterPayload` list → return `is_ambiguous=True`.

`GET /api/disambiguation/health` returns `{status, stages, label_client: "openrouter"|"sentinel"}`.

`_OpenRouterLabelClient` (sync httpx adapter, mirrors `real_completion.py:189-205`):
- POSTs to `OPENROUTER_ENDPOINT` with chat-completion body; reuses `_extract_text` from `real_completion` for response parsing (handles string-content + multipart-content shapes).
- Empty content → `RuntimeError("OpenRouter returned empty disambiguation label")`.

`_make_openrouter_label_client()`: env-driven factory; returns None when `OPENROUTER_API_KEY` is unset; else `_OpenRouterLabelClient(api_key=..., model="z-ai/glm-5.1" or OPENROUTER_DEFAULT_MODEL)`.

`src/polaris_v6/api/app.py`: imports + mounts `disambiguation_router` under `/api`. Additive; no existing route changed.

## Tests (`test_disambiguation_route.py`, 8 tests, all hermetic)

1. `test_post_returns_clusters` — 6-candidate 2-cluster payload → ClusterPayloads in id order; FakeClient.calls == 2.
2. `test_single_cluster_unambiguous_skips_labeling` — 4 dense candidates → `is_ambiguous=False, clusters=[]`; FakeClient.calls == 0.
3. `test_no_clusters_skips_labeling` — 1 candidate → `num_clusters=0, clusters=[]`; FakeClient.calls == 0.
4. `test_embedding_dim_mismatch_400` — mismatched dims → 400 + `code=embedding_dim_mismatch`.
5. `test_empty_candidates_422` — `candidates=[]` → 422 (Pydantic).
6. `test_no_label_client_503_only_when_ambiguous` — explicit `app.dependency_overrides[get_label_client] = lambda: None` + ambiguous payload → 503 + `code=label_client_unavailable`.
7. `test_health_endpoint` — GET /api/disambiguation/health → 200 + `status=ok` + `label_client` field.
8. `test_create_app_mounts_router_and_env_unset_factory_returns_none` — monkeypatches all relevant env vars absent (SERPER, OPENROUTER, GPG, OTEL, S2); asserts `_make_openrouter_label_client() is None`; calls `create_app()`; asserts `/api/disambiguation` and `/api/disambiguation/health` in `app.openapi()['paths']`.

## Iter-3 brief P2 advisories — addressed in implementation

- **P2 #1 (test #8 leaks env state):** `monkeypatch.delenv` for SERPER, OPENROUTER, GPG, OTEL, S2 BEFORE `create_app()`.
- **P2 #2 (default-dep-path needs hermetic check):** `_make_openrouter_label_client() is None` asserted in same test (saves a separate-test LOC).

## Risks for Codex Red-Team

1. **HDBSCAN `min_cluster_size` boundary.** `Field(default=2, ge=2)` hard-rejects 1 at Pydantic. Confirmed via brief iter-2 P1 #1 fix.

2. **Adapter fail-loud.** `if not text.strip(): raise RuntimeError(...)`. Empty content from OpenRouter never reaches `label_clusters`. LAW II.

3. **Sync httpx lifecycle.** `with httpx.Client() as client:` ensures connection cleanup. No asyncio.

4. **Reuse of `_extract_text`.** Single-source-of-truth response parser. If OpenRouter shape changes, both `real_completion` and `disambiguation_route` adapt together.

5. **Pydantic Field constraints.** `min_length=1` on candidates list rejects empty payloads at the boundary. `min_length=1` on `embedding` rejects zero-length lists.

6. **Embedding dim mismatch path.** `any(...)` short-circuits on first mismatch; raises clean 400 with explicit dim in message.

7. **Short-circuit on `num_clusters in (0, 1)`.** Both unambiguous; LLM never called. Saves cost. Test #2 + #3 cover.

8. **None-client + ambiguous → 503.** Test #6 explicitly overrides `lambda: None`. LAW II "no silent fallbacks" preserved.

9. **app.py mount additive.** Test #8 asserts via OpenAPI introspection that the production factory registers the route. No existing route modified.

10. **No `unittest.mock` in `src/`.** `_OpenRouterLabelClient` is a regular class. Tests use FakeClient regular class.

11. **Test hermeticity.** All 8 tests use `app.dependency_overrides` or monkeypatched env. None touch real httpx network. `test_create_app_mounts_router_and_env_unset_factory_returns_none` explicitly clears all env vars that would otherwise alter `create_app` behavior.

12. **CHARTER §1 LOC cap.** 200 exact.

13. **`get_label_client` is a one-line `def`.** Returns `_make_openrouter_label_client()`. The factory reads env at call-time so tests overriding the dep see fresh state.

14. **Numeric stability.** Embeddings are `list[float]` from JSON; cast to `np.float64` ndarray before HDBSCAN. No precision loss at typical embedding dimensions.

## Out of scope (do NOT regress on these)

- Frontend modal → I-f2-004.
- BPEI 3-cluster real-LLM smoke → I-f2-005.
- Wiring the intake page client to /api/disambiguation → I-f2-004.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
