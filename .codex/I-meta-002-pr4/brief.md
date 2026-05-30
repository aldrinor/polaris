# Codex brief-gate — I-meta-002 sub-PR-4: 3 role adapters (Mirror/Sentinel/Judge), mock-tested — NO SPEND

> **THIS IS A BRIEF / DESIGN REVIEW, NOT A DIFF REVIEW.** The implementation files
> (`src/polaris_graph/roles/role_transport.py`, `sentinel_adapter.py`, `judge_adapter.py`,
> `mirror_adapter.py`, `tests/roles/test_*_adapter.py`) DO NOT EXIST YET — by design. They are
> written in the BUILD step AFTER this brief is APPROVE'd, and their code is reviewed at the
> separate DIFF-gate (the standard brief→build→diff cycle, same as sub-PR-1/2/3 which you already
> APPROVE'd this way). Do NOT request changes on the grounds that the code is absent — review the
> ACCEPTANCE CRITERIA / design below for correctness and clinical safety. "Files not present" is
> expected and is NOT a finding.

HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution/safety risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
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
- 4-role architecture LOCKED (Generator deepseek-v4-pro / Mirror cohere/command-a-plus / Sentinel
  ibm-granite/granite-guardian-4.1-8b / Judge qwen/qwen3.6-35b-a3b).
- **NO MONEY this PR. NO network calls in code OR tests.** The transport is INJECTED (a Protocol);
  every test passes a MOCK transport returning canned raw strings. No base_url, no HTTP, no GPU,
  no Cohere/Vast. Live transport wiring is sub-PR-5; live calls are Gate-B (post-spend).
- Operator is blind — keep the verdict crisp.
- Canonical pipeline = docs/polaris_pipeline_canonical.md (stages 14 Mirror / 15 Sentinel /
  16 Judge); do not drift it.

## Context — implements YOUR I-meta-002 design iter-2 serving facts
sub-PR-1 (lock), sub-PR-2 (contracts), sub-PR-3 (D8 release policy) committed + Codex-APPROVED.
This is sub-PR-4. Your iter-2 design verdict gave PR4 this scope ("PR4 adapters: Cohere managed
Mirror, Granite self-host Sentinel, Qwen FP8 Judge with bounded context") and confirmed these
serving facts (quoted):

> F3: Granite Guardian 4.1 groundedness ... calling convention is assistant claim + final user
> `<guardian>` block + `documents`; output is `<score>yes|no</score>`, not JSON. Use only the
> prescribed yes/no scoring mode.
> F2: Cohere `response_format` is NOT supported with `documents`/`tools`, so the two-pass Mirror
> design is technically correct (pass-1 RAG-with-citations, pass-2 JSON classification). Self-host
> emits `<co>...</co:...>` spans.
> F4: self-hosted vLLM choice-constrained decoding is the right hard-enum mechanism; current
> spelling is `structured_outputs.choice` / `StructuredOutputsParams(choice=...)` (guided_choice is
> the DEPRECATED spelling). Bound Qwen context (max_model_len) — do not assume unbounded.

## Grounding (already read)
- sub-PR-2 contracts (REUSED, the adapters' parse step): `roles/sentinel_contract.parse_sentinel_score`
  (fail-closed, ASCII strict envelope), `roles/judge_contract.parse_judge_verdict` + `JUDGE_CHOICES`
  (5-enum hard-fail), `roles/mirror_contract` (`MirrorPass1`, `MirrorPass2`, `build_pass2_input`,
  `verify_pass2_binding`, `parse_cohere_citations`).
- `openrouter_client.py`: existing live LLM client (used by the Generator + the legacy path). It is
  the model the REAL transport (sub-PR-5) will follow; PR4 does NOT import it (transport injected).
- `live_judge.py`: the existing per-axis judge call pattern is the shape the real transport mirrors.

## Scope of sub-PR-4 (acceptance criteria)
New adapters in `src/polaris_graph/roles/`. Each adapter is request-builder + transport-caller +
contract-parser + role-tagger. Transport is dependency-injected.

1. **Shared transport + result types** (`roles/role_transport.py`):
   - `RoleTransport` Protocol: `complete(request: RoleRequest) -> RoleResponse` (sync; the real
     impl is sub-PR-5). `RoleRequest` (role: str, model_slug: str, messages/prompt payload,
     params dict incl. structured-output spec). `RoleResponse` (raw_text: str, served_model: str
     | None, usage dict | None, **`citations: list[CitationSpan] | None = None`** — see item 4
     P1-b). No network here — just the data contracts + Protocol.
   - `RoleCallRecord` (role, model_slug, served_model, raw_text, parsed: Any) for the capture/
     identity gate (sub-PR-5).
   - **(iter-3 fix, Codex P1-a) ONE RoleCallRecord PER transport completion.** Every `run_*`
     adapter returns `(result, list[RoleCallRecord])` — a single-call role (Sentinel, Judge)
     returns a 1-element list; Mirror (two passes) returns a 2-element list (pass-1, pass-2). The
     Path-B identity gate (sub-PR-5) must check served==pinned for EVERY completion, so no call may
     be hidden inside an adapter without its own record.

2. **Sentinel adapter** (`roles/sentinel_adapter.py`):
   - `build_sentinel_request(claim, evidence_documents, *, model_slug)` -> RoleRequest tagged
     role="sentinel", in the Granite prescribed mode: assistant turn carrying the claim + a final
     user `<guardian>` groundedness block + the `documents`. (No JSON/structured-output — Granite
     emits `<score>`.)
   - `run_sentinel(transport, claim, evidence_documents, *, model_slug) -> (SentinelResult, list[RoleCallRecord])`
     (1-element list): calls transport, parses raw via `parse_sentinel_score` (FAIL CLOSED — a
     malformed/empty/error response yields UNGROUNDED, parsed_ok=False; NEVER GROUNDED). Polarity
     yes=UNGROUNDED is lethal.

3. **Judge adapter** (`roles/judge_adapter.py`):
   - `build_judge_request(claim, evidence, mirror_verdict, sentinel_verdict, *, model_slug)` ->
     RoleRequest tagged role="judge" with the hard-enum spec `structured_outputs.choice =
     JUDGE_CHOICES` (current vLLM spelling; NOT guided_choice) and an explicit bounded
     `max_tokens`/context note. The terminal-arbiter prompt includes the Mirror + Sentinel signals.
   - `run_judge(transport, ...) -> (Verdict, list[RoleCallRecord])` (1-element list): parses raw via
     `parse_judge_verdict` (raises JudgeEnumError on any non-enum — no silent default).

4. **Mirror adapter** (`roles/mirror_adapter.py`) — TWO PASS:
   - Pass 1: `build_mirror_pass1_request(claim, evidence_documents, *, model_slug)` -> RoleRequest
     role="mirror" RAG-with-`documents` (citations on; NO response_format — incompatible with
     documents per F2).
   - **(iter-3 fix, Codex P1-b) Citation normalization — no silent empty.** Pass-1 parsing draws
     citations from an EXPLICIT contract: if `RoleResponse.citations` is provided (structured
     spans — the normalized/managed path) use it; ELSE parse `<co>...</co:doc_ids>` from
     `raw_text` via `parse_cohere_citations` (our self-host route per F2).
   - **(iter-4 fix, Codex P1) Citations MUST bind to a real supplied evidence document.** After
     extraction, validate every citation span against the set of doc_ids in `evidence_documents`
     (so `evidence_documents` carries a stable `doc_id` per document, passed into the normalizer):
     REJECT a span with empty/missing `doc_ids`, and REJECT any `doc_id` not present in the
     supplied documents (a hallucinated citation identity). A span like `<co>covered</co:>` (empty
     doc_id) or one citing a doc_id never provided does NOT count as grounding. If, after this
     validation, NO valid grounded citation remains for a grounding-required claim, raise
     `MirrorCitationError` (fail closed) — never let a non-empty-but-ungrounded citation set satisfy
     the binding. This is the grounding-integrity guard: citations must point at real evidence, not
     merely be syntactically present.
   - Pass 2: `build_mirror_pass2_request(pass1, *, model_slug)` using `build_pass2_input(pass1)` so
     the request embeds the composite content_hash; JSON classification (response_format ok now,
     no documents). Parse into `MirrorPass2`; `verify_pass2_binding(pass1, pass2)` MUST hold or the
     result fails closed (binding mismatch -> raise `MirrorBindingError`, never trust pass-2).
   - `run_mirror(transport, claim, evidence_documents, *, model_slug) -> (MirrorPass2, list[RoleCallRecord])`
     orchestrates the two passes (two transport calls) and returns BOTH RoleCallRecords (pass-1 and
     pass-2) so the identity gate can verify served==pinned for each.

5. **Role tagging:** every RoleRequest carries `role` and `model_slug`; every RoleCallRecord echoes
   the served identity. This is what sub-PR-5's Path-B identity gate consumes (served==pinned).

6. **Tests** (`tests/roles/test_*_adapter.py`), all with a MOCK transport (a small fake returning
   canned RoleResponse): Sentinel request has the guardian block + documents and NO structured
   output; Sentinel fail-closed on malformed transport output; Sentinel returns a 1-element record
   list; Judge request carries structured_outputs.choice==JUDGE_CHOICES and bounded max_tokens,
   parses each enum, raises on non-enum, returns a 1-element record list; Mirror does TWO transport
   calls and returns a **2-element record list (pass-1 AND pass-2), both asserted**; pass-2 request
   embeds the pass-1 composite hash; binding-mismatch -> MirrorBindingError; **(iter-3) citation
   normalization: structured `RoleResponse.citations` path parsed; `<co>` raw_text path parsed; and
   the empty-both case surfaces (MirrorCitationError / empty flag) rather than a silent empty
   MirrorPass1 that trivially passes the binding**; **(iter-4) a span with an empty doc_id is
   rejected, a span citing a doc_id NOT in evidence_documents is rejected, and a claim left with no
   valid grounded citation raises MirrorCitationError; a span citing a real supplied doc_id is
   accepted**.

7. Hygiene: snake_case, explicit imports, named constants, no `except: pass`, NO unittest.mock in
   `src/` (mock transport lives in tests/), no real network anywhere.

## Files I have ALSO checked and they are clean / relevant
- sub-PR-2 contracts — consumed as the parse step; not modified.
- `openrouter_client.py` / `live_judge.py` — NOT imported by the adapters (transport injected); the
  real transport that wraps them is sub-PR-5.
- `pathB_runner.py` `_role_pins()` — still 2 roles; the 4-role pin + capture wiring is sub-PR-5.
- D8 `release_policy.py` (sub-PR-3) — consumes Judge verdicts downstream; not touched here.

## iter-3 changelog (addresses your iter-2 P1s)
- **P1-a (one record per completion):** every `run_*` now returns `(result, list[RoleCallRecord])`;
  Mirror returns BOTH pass-1 and pass-2 records so the Path-B identity gate can verify served==pinned
  for every completion. Sentinel/Judge return a 1-element list. See items 1–4 + tests.
- **P1-b (Mirror citation normalization):** added `RoleResponse.citations` (structured-span path) +
  an explicit precedence (structured citations else `<co>` raw spans), and made the empty-both case
  surface a `MirrorCitationError` / empty-flag instead of silently producing an empty-citation
  MirrorPass1 that trivially passes the hash binding. See item 4 + tests.
- Your iter-2 P2s noted: provider.require_parameters stays in sub-PR-5 (real transport); the
  injected-transport/no-spend boundary is kept.

## Questions for Codex (iter-3)
1. Confirm `(result, list[RoleCallRecord])` with one record per transport completion (Mirror = 2)
   gives the Path-B gate everything it needs to check served==pinned per call.
2. Confirm the citation-normalization precedence (structured `RoleResponse.citations` else `<co>`
   raw spans) with a non-silent empty-both failure is the right anti-silent-drop contract.
3. Any remaining served-identity field missing from RoleCallRecord for the sub-PR-5 identity gate.
4. Any residual correctness/safety gap in the three request formats or the fail-closed wiring.

Hand me APPROVE iff the injected-transport boundary, the per-call records, the citation
normalization, the three request formats, and the fail-closed parse wiring are correct and safe.
