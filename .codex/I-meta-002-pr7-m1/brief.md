# Codex brief-gate — I-meta-002 PR-7 (M1): real RoleTransport for the 3 self-hosted verifier roles — NO SPEND

> **BRIEF / DESIGN REVIEW, NOT a diff review.** Implementation files do not exist yet — written
> in BUILD after this APPROVE, reviewed at the DIFF-gate. "Files not present" is expected.

HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution/safety risks.
- If you are holding back a P1 for the next round — surface it now; iter 6 does not exist.
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

## HARD CONSTRAINTS (operator-locked, NOT consultable)
- 4-role architecture LOCKED. **NO MONEY this PR. NO real network in code paths exercised by tests** —
  the transport's HTTP client is INJECTED so tests pass an in-process stub (httpx.MockTransport / a
  fake) returning canned responses. No GPU, no Cohere, no Vast, no live endpoint hit in pytest.
- Operator is BLIND — crisp verdict.
- Frozen: `claim_audit_scorer.py`, runtime lock (do NOT promote). Canonical pipeline
  `docs/polaris_pipeline_canonical.md` — do not drift.

## Context — this is M1 of the live-path build (readiness audit 2026-05-29)
The readiness double-check (Claude verify + Codex audit, BOTH NOT_READY) found the 4-role LOGIC is
built + offline-green but the LIVE serving path is unbuilt. M1 is the first live piece: a REAL
`RoleTransport` implementation. The 3 verifier roles (Mirror/Sentinel/Judge) are served on
self-hosted vLLM (per the lock `serving_route: vast_self_host*`); the GENERATOR is NOT in scope —
it already runs live on OpenRouter via `openrouter_client.py` and is upstream of the per-claim
pipeline. So M1's transport serves ONLY mirror/sentinel/judge.

Grounding (read this session, file:line) — REUSE these existing patterns, do NOT reinvent:
- `openrouter_client.py`: request body build (:1389–1502: model/messages/temperature/max_tokens,
  `response_format` json_schema shape :1473–1478, `provider` block :1481–1502), response parse
  (:1677–1830), served-identity extraction (`provider`/`model`/`system_fingerprint` :1281–1286), and
  the capture-hook invocation pattern (:1821–1828). Headers :1064–1068. Timeouts/retry :1507–1676.
- `pathB_capture.py`: `capture_llm_call(*, role, messages, raw_response)` (:191–207),
  `build_response_metadata(raw)` pulls `provider_name`/`model`/`system_fingerprint` (:168–188),
  `llm_role(role)` context manager (:115–124), `is_active()`/`current_llm_role()`.
- sub-PR-4 `role_transport.py`: the `RoleTransport` Protocol `complete(request: RoleRequest) ->
  RoleResponse` (SYNC); `RoleRequest(role, model_slug, messages, params)`; `RoleResponse(raw_text,
  served_model, usage, citations)`. The adapters (`run_mirror/run_sentinel/run_judge`) call
  `transport.complete(request)` synchronously.

## Scope of PR-7/M1 (acceptance criteria)
New module `src/polaris_graph/roles/openai_compatible_transport.py` implementing the sub-PR-4
`RoleTransport` Protocol for the 3 self-hosted verifier roles.

1. `OpenAICompatibleRoleTransport` (implements `RoleTransport`): SYNC `complete(request: RoleRequest)
   -> RoleResponse` that POSTs an OpenAI-compatible `/v1/chat/completions` to a PER-ROLE `base_url`.
   The HTTP client is INJECTED (constructor takes an `httpx.Client` or a transport) so tests pass a
   stub — NO network in tests.
   - **(iter-2 fix, Codex P1) Payload normalization — messages OR prompt.** VERIFIED against the
     adapters: Sentinel sends `request.messages`; Judge + Mirror pass-1 + Mirror pass-2 send
     `request.prompt` (a string). The transport MUST normalize: if `request.messages` is set, use it;
     ELSE build `messages=[{"role":"user","content":request.prompt}]` (prepend a system message if
     `request.params` carries one). The NORMALIZED messages are what get POSTed AND what is passed to
     `capture_llm_call(messages=...)` — so a prompt-only role never sends/captures an empty payload.
   - Pass `request.params` through as TOP-LEVEL request keys (Codex P2): `structured_outputs`/
     `response_format` for Judge, `documents` for Mirror. Reuse the openrouter_client body shape.
   - **(iter-3 fix, Codex P1) Model-VISIBILITY of params on a plain vLLM endpoint.** A plain vLLM
     `/v1/chat/completions` model sees ONLY the `messages` — a top-level `documents` or `pass2_input`
     key is NOT guaranteed model-visible. So during normalization the transport MUST serialize the
     model-relevant params INTO the normalized messages: render `params["documents"]` as an explicit
     evidence context message (each doc_id + text), and render `params["pass2_input"]` (the Mirror
     pass-2 binding: pass-1 answer + `content_hash`) as an explicit message the model must classify.
     Keep them ALSO as top-level keys (for a managed server that consumes them + for test/contract
     introspection), but the messages are the source of truth for what the model reads. Without this,
     live Mirror pass-2 never sees the pass-1 artifact/content_hash and the binding is meaningless.
   - **(iter-4 fix, Codex P1) Citation-OUTPUT contract must be model-visible too.** Mirror pass-1
     sets `params["citations"]=True` — a flag, NOT an output instruction a plain vLLM model obeys.
     When `params["citations"]` is true, the transport MUST render an explicit citation-output
     instruction into the normalized messages: require the answer to cite supported spans in the
     EXACT self-host form `<co>covered text</co:doc_id>` using ONLY the supplied `documents` doc_ids.
     Without this the live model returns plain prose with no `<co>` spans, `parse_cohere_citations`
     finds nothing, `MirrorCitationError` fails closed on EVERY claim, and the whole run holds.
     (Generalizes the rule: for the plain-vLLM convention the transport renders the role's full
     model-visible serving contract — evidence, binding, AND required output format — into `messages`.)
   - Parse the response: `raw_text` = assistant message content; `served_model` = response `model`;
     `usage` = the usage dict.
   - **(iter-2 fix, Codex P1) Cohere `<co>` citation/raw_text invariant.** The transport does NOT
     pre-parse `<co>` spans. For the self-host path it returns `raw_text` AS-IS (tags intact) and
     `citations=None`; `mirror_adapter` parses `<co>` and strips, owning the offset alignment (it
     already handles both the structured-citations and `<co>` paths). NEVER return parsed citations
     alongside un-stripped raw_text — offsets index the TAG-STRIPPED text, so that combination breaks
     the Mirror citation contract. (A future MANAGED transport returning STRUCTURED citation spans
     could fill `RoleResponse.citations` — those are not text-offset; out of scope for M1 self-host.)
2. **Per-role endpoint config** (LAW VI): a resolver `role_endpoint(role) -> (base_url, api_key,
   model_slug)` reading env `PG_<ROLE>_BASE_URL` + `PG_<ROLE>_API_KEY` (fallback OPENROUTER_API_KEY)
   + the lock-sourced model slug. Generator is excluded (not served here).
3. **Capture integration + served ENDPOINT (iter-3 fix, Codex P1):** every `complete()` wraps the
   call in `llm_role(request.role)` and invokes `capture_llm_call(role=request.role,
   messages=normalized_messages, raw_response=raw)` so the Path-B served==pinned gate can later
   verify the live call. served_model is the response `model` (served identity), not the request slug.
   - A self-host vLLM response carries NO `provider_name` and NOT the endpoint it was served from —
     but M4's served==pinned check for a self-host role needs the ENDPOINT. So M1 captures it NOW:
     before calling capture, the transport augments the raw dict with an explicit served block
     `raw["_pathb_served"] = {"endpoint": base_url, "model": served_model}`, and `build_response_metadata`
     in `pathB_capture.py` is extended (small additive, backward-compatible) to surface an optional
     `endpoint` from `_pathb_served` when present. Do NOT fabricate a `provider_name` for vLLM. A test
     asserts the captured record carries the endpoint so M4 can consume it.
4. **Fail LOUD:** an HTTP error / non-200 / malformed body raises a clear `RoleTransportError`
   (never a silent empty RoleResponse that a downstream fail-closed parser would mis-handle). Reuse
   the openrouter_client timeout default (`PG_LLM_TIMEOUT_SECONDS`).
5. **Tests** (`tests/roles/test_openai_compatible_transport.py`), ALL with an injected
   `httpx.MockTransport` (no network): per-role base_url is hit (generator NOT routable here -> raises);
   **(iter-2) a prompt-only request (Judge/Mirror) is normalized to messages AND the SAME normalized
   messages reach capture (assert capture got non-empty messages, not an empty prompt)**; the request
   carries Judge `structured_outputs`/Mirror `documents` when present; response parses to RoleResponse
   (raw_text/served_model/usage); **(iter-3) a Mirror pass-2 request's normalized messages CONTAIN the
   pass-1 `content_hash` (model-visible, not just a params key), and `documents` are rendered into the
   messages; the captured record carries the served `endpoint` (base_url) for M4;** **(iter-4) a
   Mirror pass-1 request (params['citations']=True) normalizes messages containing BOTH the documents
   AND the explicit `<co>covered text</co:doc_id>` citation-output instruction referencing the
   supplied doc_ids;** **(iter-2) a Cohere `<co>` response returns raw_text AS-IS (tags
   intact) with `citations=None` — the transport does NOT pre-parse/strip**; `capture_llm_call` is
   invoked with the right role + served metadata (assert via a registered capture sink); a 500 /
   malformed body raises RoleTransportError.
6. Hygiene: snake_case, explicit imports, named constants, no `except: pass`, no unittest.mock in
   `src/`, no real network anywhere, no `datetime.now()` in library code.

## Files I have ALSO checked / relevant
- `openrouter_client.py` — REUSED patterns (request/response/served-identity/capture); the generator
  stays on its existing async path, NOT routed through this transport. Not modified by M1.
- `pathB_capture.py` — consumed (llm_role + capture_llm_call) + a SMALL ADDITIVE change in this PR:
  `build_response_metadata` surfaces an optional `endpoint` from `_pathb_served` (backward-compatible;
  existing 3-key behavior unchanged when absent). This is the only edit to an existing file.
- sub-PR-4 adapters + role_transport.py Protocol — consumed as-is; this is the concrete impl they
  were designed to accept. The mock transport in tests already proves the adapters; M1 is the real one.
- `role_pipeline.py` RecordingTransport — wraps ANY transport incl. this one; unchanged.

## iter-4 changelog (addresses your iter-3 P1)
- **P1 (Mirror pass-1 `<co>` OUTPUT contract not model-visible):** when `params["citations"]` is
  true, the transport now renders an explicit `<co>covered text</co:doc_id>` citation-output
  instruction (referencing the supplied doc_ids) INTO the normalized messages — so the live model
  is actually told to emit `<co>` spans, not just handed the evidence. Without it every live Mirror
  pass-1 returned plain prose and fail-closed. Tested. See scope item 1.

## iter-3 changelog (addresses your iter-2 P1s; iter-1/P2 retained)
- **P1 (Mirror pass-2 model-visibility):** the transport now SERIALIZES model-relevant params into the
  normalized messages — `documents` rendered as an evidence message, `pass2_input` (pass-1 answer +
  content_hash) rendered as a message the model classifies — because a plain vLLM model sees only
  `messages`. Tested: the pass-2 request's messages contain the content_hash. See scope item 1.
- **P1 (served endpoint for M4):** the transport augments the captured raw with
  `_pathb_served={"endpoint": base_url, "model": served_model}` and `build_response_metadata` is
  extended (small additive) to surface `endpoint`; no fabricated `provider_name`. Tested: captured
  record carries the endpoint. See scope item 3.
- iter-2 retained: prompt→messages normalization (same messages to body AND capture); Cohere `<co>`
  raw_text-as-is + citations=None (mirror_adapter owns parse/strip). iter-1/P2 retained: SYNC new
  module; generator HARD-excluded; top-level keys for response_format/documents/structured_outputs;
  injected MockTransport (no network).

## Questions for Codex (iter-2)
1. Confirm the prompt→messages normalization (same normalized messages to body AND capture) fully
   closes the empty-payload gap for Judge/Mirror.
2. Confirm raw_text-AS-IS + citations=None (mirror_adapter owns `<co>` parse/strip) is the correct
   citation invariant — no offset-misalignment risk remains.
3. Served identity for a self-host vLLM endpoint: served `model` + base_url, NO synthesized
   provider_name — confirm this is what the Path-B served==pinned check (M4) should consume, and that
   M1 should NOT fabricate a provider slug.
4. Any residual correctness/network-in-tests risk.

Hand me APPROVE iff the prompt-normalization, the citation invariant, the served-identity decision,
the injected-no-network-test boundary, and the fail-loud contract are correct.
