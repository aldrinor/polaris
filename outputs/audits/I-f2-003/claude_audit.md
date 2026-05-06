# Claude Architect Audit — I-f2-003 (disambiguation route)

**Branch:** bot/I-f2-003 / **Diff SHA256:** `8e0b55f298ba71d55ed096c8d836a13632a992ea400617eb78f9ef2df3a421c5`
**LOC:** 200 net (at CHARTER §1 200-cap, exact)
**Tests:** 8/8 PASS

## Files

```
src/polaris_graph/api/disambiguation_route.py        NEW +104
src/polaris_v6/api/app.py                            EDIT +3
tests/polaris_graph/api/test_disambiguation_route.py NEW +93
```

## Iter-3 brief P2 advisories — both addressed in implementation

- **P2 #1 (test #8 calls `create_app()` without clearing unrelated env vars):** `test_create_app_mounts_router_and_env_unset_factory_returns_none` uses `monkeypatch.delenv` for `SERPER_API_KEY`, `OPENROUTER_API_KEY`, `POLARIS_GPG_KEY_ID`, `OTEL_SEMCONV_STABILITY_OPT_IN`, `SEMANTIC_SCHOLAR_API_KEY` BEFORE calling `create_app()`. Smoke is hermetic; cannot leak GPG/observability state.
- **P2 #2 (default-dep-path needs hermetic check):** Same test asserts `_make_openrouter_label_client() is None` after the env clear. Two assertions in one test for LOC-economy.

## Architecture review

1. **Pattern adherence.** Mirrors `retrieval_route.py:33-156` exactly: `APIRouter(tags=...)`, Pydantic Request/Response, `Depends()` for client injection, `HTTPException(detail={...})` for structured errors, ISO-8601-Z `server_time_utc`.

2. **Sync httpx adapter (Codex iter-2 P1 #2 fix).** `_OpenRouterLabelClient.complete()` uses `with httpx.Client() as client:` mirroring `real_completion.py:189-205`. No asyncio. Reuses `_extract_text` from `real_completion` for response parsing — single source of truth, no duplicated multipart-content handling.

3. **Pydantic Field constraints (Codex iter-2 P1 #1 fix).** `min_cluster_size=Field(default=2, ge=2)` rejects `1` at the Pydantic boundary; HDBSCAN never sees an invalid value. Empty candidates list rejected via `Field(min_length=1)`.

4. **Short-circuit on `num_clusters in (0, 1)` (Codex iter-1 P2 #3 fix).** Both 0 and 1 are unambiguous; LLM never called; response carries `clusters=[]`. Saves cost + bypasses 503 trigger when client is None on unambiguous queries.

5. **None-client + ambiguous → 503 (LAW II).** Test #6 explicitly overrides `get_label_client → lambda: None` (Codex iter-2 P1 #3 fix); never silently substitutes a stub label.

6. **Embedding-dim guard before numpy.** `if any(len(c.embedding) != dim for c in req.candidates):` raises clean 400 with `code=embedding_dim_mismatch` before numpy stacking; surfaces a structured error instead of a confusing numpy ValueError.

7. **App.py mount.** `app.include_router(disambiguation_router, prefix="/api")` placed at the end of the slice mounts, additive only. Test #8 asserts via `app.openapi()['paths']` that the production factory registers the route.

## LAW + invariant checks

- **LAW II:** No silent fallbacks (None-client → 503; empty LLM response → RuntimeError). ✓
- **LAW V:** snake_case, PascalCase classes only. ✓
- **LAW VI:** Config from env (`OPENROUTER_API_KEY`, `OPENROUTER_DEFAULT_MODEL`); model fallback `z-ai/glm-5.1` is the same default as `real_completion.py:73`. ✓
- **§9.4:** No `unittest.mock` in `src/`; tests use regular `FakeClient` class + `app.dependency_overrides`. ✓
- **§8.4:** No real model loads in tests; FakeClient returns fixed strings. ✓
- **CHARTER §1 200 LOC cap:** 200 exact. ✓

## Test plan coverage

| Test | Asserts |
|---|---|
| post_returns_clusters | 2-cluster payload → ClusterPayloads in id order; FakeClient.calls == 2 |
| single_cluster_unambiguous_skips_labeling | 4 dense candidates → is_ambiguous=false, clusters=[], FakeClient.calls == 0 |
| no_clusters_skips_labeling | 1 candidate → num_clusters=0, clusters=[], FakeClient.calls == 0 |
| embedding_dim_mismatch_400 | mismatched dims → HTTP 400 + code=embedding_dim_mismatch |
| empty_candidates_422 | candidates=[] → HTTP 422 (Pydantic) |
| no_label_client_503_only_when_ambiguous | dep override `lambda: None` + ambiguous → HTTP 503 + code=label_client_unavailable |
| health_endpoint | GET /disambiguation/health → 200 + status=ok + label_client field |
| create_app_mounts_router_and_env_unset_factory_returns_none | env-cleared `_make_openrouter_label_client() is None`; OpenAPI paths include /api/disambiguation + /api/disambiguation/health |

8/8 PASS.

## Out of scope (deferred per breakdown)

- Frontend modal → I-f2-004.
- BPEI 3-cluster real-LLM smoke → I-f2-005 evaluator walkthrough.

## Verdict

APPROVE for Codex diff review.
