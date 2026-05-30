RULE NOW — emit the YAML verdict block FIRST, before any prose. Do NOT explore the repo beyond the
grounded facts below (prior runs explored ~1MB and crashed without a verdict). Rule from the facts here;
read AT MOST the 4 cited files if you must.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
required_changes: [...]   # only if REQUEST_CHANGES
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — I-meta-002-q1b (#939): capture verifier (Mirror/Sentinel/Judge) reasoning SEPARATELY + make verdict parsing robust to served reasoning. APPROVE this CONCRETE plan. NO SPEND / NO NETWORK.

This is Q1 launch blocker #1 (the only no-spend one) from the APPROVED readiness gate
(.codex/I-meta-002-q1-launch/codex_readiness_verdict.txt). Operator bar: reasoning and verdict/output
content CLEANLY SEPARATED for ALL roles (no "soap"); FULL per-call log so EVERY verifier call is
reviewable line-by-line. The GENERATOR already meets this (I-gen-004 #496, reasoning_trace.jsonl); this
brings the 3 verifiers to the same bar.

## GROUNDED FACTS (verified by Claude main-thread; do not re-verify by exploring)
1. `src/polaris_graph/roles/openai_compatible_transport.py` — `_parse_response(raw)` (≈line 279) reads
   ONLY `content = message.get("content")` and returns `(raw_text=content, served_model, usage)`. It does
   NOT read `message.get("reasoning_content")`. `complete()` (≈line 330-392) calls `_pathb_capture.capture_llm_call(role, messages, raw_response=raw)` then returns
   `RoleResponse(raw_text, served_model, usage, citations=None)`.
2. `src/polaris_graph/benchmark/pathB_capture.py` — `capture_llm_call` stores ONLY
   `{role, prompt_messages_present, request_hash, response_metadata}`; `build_response_metadata` keeps
   only served provider/model/system_fingerprint/_pathb_served.endpoint and DROPS everything else. So no
   verifier content and no reasoning is persisted by capture (request_hash is "presence, not content").
3. `src/polaris_graph/roles/role_transport.py` — `RoleResponse` (line 58: raw_text/served_model/usage/
   citations) and `RoleCallRecord` (line 75: role/model_slug/served_model/raw_text/parsed). Neither has a
   reasoning field.
4. `src/polaris_graph/roles/role_pipeline.py` — `RecordingTransport.complete` (≈line 84) appends
   `RoleCallRecord(role, model_slug, served_model, raw_text=response.raw_text, parsed=None)` per call;
   `ClaimPipelineResult.records` carries them (complete even on fail-closed paths).
5. `src/polaris_graph/roles/sweep_integration.py` — `run_four_role_evaluation` loops claims, calls
   `run_claim_pipeline`, does `all_records.extend(result.records)`, and returns
   `FourRoleEvaluationResult(records=all_records, ...)`. The sweep (`run_honest_sweep_r3.py:3254-3300`)
   writes ONLY release_allowed/held_reasons/final_verdicts/evaluator_agrees to the manifest — it does NOT
   persist `four_role_result.records` to any per-question file. `four_role_claim_audit.json` holds the
   builder's coverage audit_map, NOT role reasoning. So verifier content+reasoning is reviewable NOWHERE.
6. Verdict parsers: `judge_contract.py:45,52` exact-matches the 5-enum after `.strip()` (NO `<think>`
   strip); `mirror_contract.py:121,141` strips only its own `<co>…</co:doc_id>` tags; the transport
   returns Mirror raw_text AS-IS (`<co>` intact) and mirror_adapter owns the `<co>` parse/offset align.

## CONCRETE PROPOSAL (APPROVE or correct)
A. **Read + separate reasoning at the transport** (`openai_compatible_transport._parse_response` →
   return a 4-tuple `(raw_text, served_model, usage, reasoning)`):
   - If `message.get("reasoning_content")` is a non-blank string → `reasoning = reasoning_content`,
     `raw_text = content` UNCHANGED (vLLM separate-field path; e.g. Qwen3 served with a reasoning-parser).
   - ELSE if the stripped `content` STARTS WITH `<think>`: require a closing `</think>`; set
     `reasoning =` the inner text, `raw_text =` the remainder after `</think>`, stripped. If `<think>` has
     NO closing `</think>` → raise `RoleTransportError` (fail-closed; never pass a half-think to a parser).
     Only a LEADING think block is split (never search/replace mid-body) so Mirror `<co>` spans that
     follow are byte-preserved.
   - ELSE → `reasoning = None`, `raw_text = content`.
   - The existing blank-content guard applies to the POST-split bare `raw_text` (a think-only message with
     an empty verdict still raises, as today).
   - `complete()` returns `RoleResponse(..., reasoning=reasoning)`.
B. **Carry reasoning on the response + record**: add `reasoning: str | None = None` to `RoleResponse`
   (role_transport.py:58) and `RoleCallRecord` (role_transport.py:75); `RecordingTransport.complete`
   sets `reasoning=response.reasoning` on the appended record.
C. **Persist verifier reasoning to a reviewable per-question artifact, SEPARATE from the verdict**: in
   `run_four_role_evaluation`, inside the per-claim loop, collect one entry per role call
   `{claim_id, role, model_slug, served_model, raw_text, reasoning}` and write
   `four_role_role_calls.jsonl` under `run_dir` after the loop (one JSON object per line). `reasoning` is
   its OWN field — NEVER concatenated into `raw_text`. This is the verifiers' analogue of the generator's
   reasoning_trace.jsonl. pathB_capture STAYS metadata-only (out of scope; the new artifact is the home).
D. **Verdict parsing is now robust**: with A, the parsers receive the bare verdict whether the model
   emits reasoning as a separate field, inline `<think>`, or none — judge/sentinel/mirror parse unchanged.
E. **Tests (no-spend, socket blocked)**: fixture transport responses for EACH of the 3 roles in 4 shapes —
   (1) separate `reasoning_content`, (2) inline leading `<think>…</think>` + verdict, (3) no reasoning,
   (4) unterminated `<think>` → raises RoleTransportError. Assert: raw_text == bare verdict in (1)(2)(3);
   reasoning captured in (1)(2); the relevant verdict parser parses the bare verdict; and
   `four_role_role_calls.jsonl` is written with reasoning in its own field. Keep existing role tests green.

## Constraints / frozen
- NO SPEND / NO NETWORK. Runtime lock NOT promoted. Untouched: claim_audit_scorer.py, the 5 PR-10
  contracts, served==pinned (M4) logic, Sentinel polarity (yes=UNGROUNDED), Judge 5-enum, the D8 gate.
- snake_case; explicit imports; no `except: pass`; no `unittest.mock` in src (stub in tests); fail-closed.
- ≤200 LOC PR cap (Parts A-E across openai_compatible_transport.py, role_transport.py, role_pipeline.py,
  sweep_integration.py + tests). If you judge it exceeds the cap, say how to split (e.g. A+B+D+E first,
  C as a follow-up) — but C is required before Q1 spend per the readiness gate.

## The only real risks to rule on
1. Does splitting a LEADING `<think>` block at the transport corrupt Mirror's `<co>` span offsets? (Claim:
   NO — mirror_adapter aligns offsets over the SAME post-split `RoleResponse.raw_text` it parses, and only
   a leading prefix is removed, so `<co>` spans in the body stay internally consistent. Confirm or correct.)
2. Is fail-closed-on-unterminated-`<think>` the right call vs. best-effort treating the whole thing as
   content? (Claim: fail-closed — a half-emitted think is a malformed verifier response; better to hold
   than to feed reasoning into the verdict parser. Confirm.)
3. Is `four_role_role_calls.jsonl` (Part C) the right home for verifier reasoning, and is keeping
   pathB_capture metadata-only correct (vs. also threading reasoning into capture)? Name the better home
   if not.
4. Any path where `reasoning` could leak into the SHIPPED report.md or the parsed verdict? (It must not —
   reasoning lives only in the jsonl + the record, never in raw_text after the split.)

APPROVE iff this design cleanly separates verifier reasoning from verdict for all 3 roles, makes parsing
robust to all served-reasoning shapes, persists verifier reasoning to a reviewable artifact, is
no-spend/no-network, leaves the frozen gate/lock/contracts untouched, and is test-proven.
