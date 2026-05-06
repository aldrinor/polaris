# Codex Brief Review — I-f2-003 (ITER 3 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-003 — Backend: disambiguation API endpoint
**LOC budget:** 120 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-2 verdict resolution (REQUEST_CHANGES → addressed in this iter 3)

**P1 #1 (`min_cluster_size=1` → HDBSCAN 500):** ADDRESSED. Constraint changed to `Field(default=2, ge=2)`. HDBSCAN requires `min_cluster_size > 1` or it raises ValueError; the route now rejects 1 at Pydantic.

**P1 #2 (`generate()` returns LLMResponse, not str):** ADDRESSED. Adapter pivots from `OpenRouterClient.generate()` to a direct `httpx.Client` call mirroring `real_completion.py` (sync, simpler lifecycle, no asyncio at all). Extracts the response content via the existing `_extract_text` helper imported from `polaris_graph.generator2.real_completion`. Fails loudly on empty content (raises RuntimeError before label_clusters sees an empty string).

**P1 #3 (test #6 non-hermetic w.r.t. ambient OPENROUTER_API_KEY):** ADDRESSED. Test #6 explicitly sets `app.dependency_overrides[get_label_client] = lambda: None` so the test never reads env. Default-dep path is exercised only by the import-time smoke (`_make_openrouter_label_client()` call with monkey-patched `os.environ` cleared).

**P2 #1 (mount-in-create_app smoke):** ADDRESSED. New test #8 imports `polaris_v6.api.app.create_app`, builds the real app, asserts `/api/disambiguation/health` is in `app.openapi()['paths']`.

**P2 #2 (sync httpx adapter to avoid asyncio leak):** ADDRESSED. Adapter now uses `httpx.Client()` directly per `real_completion.py:189-205` pattern. No asyncio in this PR.

## Mission

Add `src/polaris_graph/api/disambiguation_route.py` — POST `/api/disambiguation` accepts a list of candidate snippets + their pre-computed embeddings, runs them through `cluster_candidates()` (I-f2-001) → `label_clusters()` (I-f2-002), and returns a structured response the frontend modal (I-f2-004) consumes. Mount in `src/polaris_v6/api/app.py` so the running app exposes the endpoint.

## Substrate (HONEST)

- I-f2-001 + I-f2-002 merged: `cluster_candidates`, `label_clusters`, `ClusterLabelClient` Protocol.
- `src/polaris_graph/api/retrieval_route.py` is the canonical FastAPI route pattern.
- `src/polaris_v6/api/app.py:33-93` already imports + mounts each slice's router under `/api`.
- `src/polaris_graph/generator2/real_completion.py:60-205` provides the canonical sync httpx-to-OpenRouter pattern, including `_extract_text(response_json)` which handles both string-content and multipart-content shapes and raises RuntimeError on empty. We reuse `_extract_text` directly.

## Acceptance criteria (binding)

1. **`src/polaris_graph/api/disambiguation_route.py`** (NEW): `router = APIRouter(tags=["disambiguation"])`.
   - Pydantic models:
     ```python
     class CandidateSnippet(BaseModel):
         text: str = Field(min_length=1)
         embedding: list[float] = Field(min_length=1)

     class DisambiguationRequest(BaseModel):
         candidates: list[CandidateSnippet] = Field(min_length=1)
         min_cluster_size: int = Field(default=2, ge=2)
         max_snippets_per_cluster: int = Field(default=3, ge=1)

     class ClusterPayload(BaseModel):
         cluster_id: int
         label: str
         sample_snippets: list[str]

     class DisambiguationResponse(BaseModel):
         is_ambiguous: bool
         num_clusters: int
         clusters: list[ClusterPayload]
         server_time_utc: str
     ```
   - Route behavior (POST /disambiguation):
     - Empty/short candidates → HTTP 422 by Pydantic (`min_length=1`).
     - All embeddings same dim, else HTTP 400 `{code:"embedding_dim_mismatch"}`.
     - Stack to `np.ndarray((K, D))`, call `cluster_candidates(min_cluster_size=req.min_cluster_size)`.
     - If `num_clusters in (0, 1)`: SKIP labeling, return `is_ambiguous=False`, `clusters=[]`. (Both 0 and 1 are unambiguous; LLM call avoided.)
     - Else (`num_clusters >= 2`): if `client is None` → HTTP 503 `{code:"label_client_unavailable"}`. Otherwise call `label_clusters(...)` → map to ClusterPayload list.
   - Health endpoint: `GET /disambiguation/health` returns `{"status":"ok","stages":["cluster_candidates","label_clusters"],"label_client":"sentinel"|"openrouter"}`.
   - Production label-client wiring (sync httpx adapter):
     ```python
     class _OpenRouterLabelClient:
         def __init__(self, api_key: str, model: str): ...
         def complete(self, prompt: str, *, max_tokens: int = 50) -> str:
             body = {
                 "model": self.model,
                 "messages": [{"role": "user", "content": prompt}],
                 "temperature": 0.0,
                 "max_tokens": max_tokens,
             }
             headers = {"Authorization": f"Bearer {self.api_key}", ...}
             with httpx.Client() as client:
                 r = client.post(OPENROUTER_ENDPOINT, json=body, headers=headers, timeout=30.0)
                 r.raise_for_status()
             text = _extract_text(r.json())  # imported from real_completion
             if not text.strip():
                 raise RuntimeError("OpenRouter returned empty label")
             return text
     ```
   - `def _make_openrouter_label_client() -> ClusterLabelClient | None`: reads `OPENROUTER_API_KEY` env. If unset → returns None. Else returns `_OpenRouterLabelClient(key, OPENROUTER_DEFAULT_MODEL or "z-ai/glm-5.1")`.
   - `def get_label_client() -> ClusterLabelClient | None`: dep wrapping the factory. Tests override.
   - LOC: ~105.

2. **`tests/polaris_graph/api/test_disambiguation_route.py`** (NEW): 8 tests via FastAPI TestClient + `app.dependency_overrides[get_label_client]`.
   - `test_post_returns_clusters`: 6 candidates → 2 clusters → 2 ClusterPayloads; FakeClient call count == 2.
   - `test_single_cluster_unambiguous_skips_labeling`: 4 dense candidates → `is_ambiguous=false, clusters=[]`; FakeClient call count == 0.
   - `test_no_clusters_skips_labeling`: 1 candidate → `num_clusters=0, clusters=[]`; FakeClient call count == 0.
   - `test_embedding_dim_mismatch_400`: HTTP 400 + `code=embedding_dim_mismatch`.
   - `test_empty_candidates_422`: HTTP 422.
   - `test_no_label_client_503_only_when_ambiguous`: explicit `app.dependency_overrides[get_label_client] = lambda: None`; AMBIGUOUS payload → HTTP 503 + `code=label_client_unavailable`.
   - `test_health_endpoint`: `GET /api/disambiguation/health` → 200 + `label_client` field.
   - `test_create_app_mounts_router`: `from polaris_v6.api.app import create_app`; `app = create_app()`; `assert "/api/disambiguation" in {p for p in app.openapi()["paths"]}` — proves the production app factory registers the route. (NOT a TestClient HTTP test; introspects the OpenAPI schema.)
   - LOC: ~85.

3. **`src/polaris_v6/api/app.py`** (EDIT): add `from polaris_graph.api.disambiguation_route import router as disambiguation_router` next to the slice imports; add `app.include_router(disambiguation_router, prefix="/api")` next to the slice include_router calls.
   - LOC: +3.

## Planned diff shape

```
src/polaris_graph/api/disambiguation_route.py        NEW +105
tests/polaris_graph/api/test_disambiguation_route.py NEW +85
src/polaris_v6/api/app.py                            EDIT +3
```

LOC: +193 net. Under CHARTER §1 200-cap by 7 lines.

## Out of scope (deferred per breakdown)

- Frontend modal → I-f2-004.
- BPEI 3-cluster real-LLM integration (smoke against the live API) → I-f2-005 evaluator walkthrough.
- Wiring `/api/disambiguation` into the intake page client → I-f2-004.

## Risks for Codex Red-Team

1. **HDBSCAN `min_cluster_size >= 2` constraint.** Pydantic `ge=2` rejects 1 at the boundary; HDBSCAN never sees an invalid value. Confirmed in iter-2 P1 #1 fix.

2. **Adapter return-type fix.** `_extract_text(response_json)` returns `str`, mirroring `real_completion.py:208` behavior. If OpenRouter returns empty content → RuntimeError raised before `label_clusters` consumes the value. LAW II preserved.

3. **Test hermeticity.** All 8 tests use `app.dependency_overrides[get_label_client]` — none read env vars. Default path (`_make_openrouter_label_client()`) is exercised only by the test #8 introspection (which calls `create_app()` but never calls the labeler — the introspection short-circuits before the route handler runs).

4. **Sync httpx lifecycle.** `with httpx.Client() as client:` ensures no connection leak. No async, no `asyncio.run`.

5. **Short-circuit on num_clusters in {0, 1}.** Both unambiguous; `clusters=[]`; LLM never called. Confirmed in #2 + #3 tests.

6. **None-client + ambiguous → 503.** Test #6 with explicit `lambda: None` override.

7. **embedding_dim check before numpy.** Single iteration through candidates — surfaces clean 400 instead of numpy ValueError.

8. **app.py mount idempotency.** Additive include_router; no behavior change to existing routes. Test #8 asserts presence in OpenAPI schema.

9. **No `unittest.mock` in `src/`.** `_OpenRouterLabelClient` is a regular class. Tests use `FakeClusterLabelClient` regular class.

10. **Determinism in clustering tests.** Small fixed-vector embeddings, no RNG. HDBSCAN deterministic.

11. **CHARTER §1 LOC cap.** Estimated 193 net; under 200. If implementation drifts above, brief author commits to docstring trim BEFORE diff review.

12. **OpenAPI validity.** Auto-generated from Pydantic. Test #8 introspects `app.openapi()['paths']`.

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
