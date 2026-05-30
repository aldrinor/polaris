# Codex brief-gate — I-meta-002 PR-8 (M2): self-host serving artifacts for the 3 verifier roles — NO SPEND

> **BRIEF / DESIGN REVIEW, NOT a diff review.** Implementation files do not exist yet — written in
> BUILD after this APPROVE, reviewed at the DIFF-gate. "Files not present" is expected.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution/safety risks.
- If holding back a P1 for the next round — surface it now; iter 6 does not exist.
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
- 4-role architecture LOCKED. **NO MONEY this PR.** M2 builds serving CONFIG + a health/identity
  PROBE + a launch runbook + tests — all offline. The actual paid Vast GPU deploy/serve is the
  later operator-triggered ONE-QUESTION CANARY (Codex full-readiness ruling c), explicitly OUT OF
  SCOPE here. NO real network in code exercised by tests (probe uses an injected httpx stub).
- Operator is BLIND — crisp verdict.
- Frozen: claim_audit_scorer.py, runtime lock (do NOT promote). Canonical pipeline doc — no drift.

## Context — Codex full-readiness ruling (2026-05-29), ordered work item 2
Codex (decision-maker) ruled NOT_READY for spend and gave the ordered no-spend work. Item 1
(Gate-A green) reconfirmed (318 tests PASS, dry run PASS). This is item 2 (M2). Codex rulings that
bind M2: verifier roles are LOCKED to `vast_self_host*` (no OpenRouter-verifier shortcut); generator
stays OpenRouter unchanged; only the 3 verifier roles need new self-host serving.

Grounding (read this session, file:line):
- Lock `config/architecture/polaris_runtime_lock.yaml`: mirror=cohere/command-a-plus
  serving_route vast_self_host_bf16; sentinel=ibm-granite/granite-guardian-4.1-8b vast_self_host;
  judge=qwen/qwen3.6-35b-a3b vast_self_host_fp8.
- Serving sizes (docs/vast_ai_budget_i_meta_002.md): Mirror bf16 = 8xH100 (~438GB weights); Sentinel
  ~1xA100 80GB; Judge fp8 = 1xH100.
- M1 `openai_compatible_transport.role_endpoint` reads env `PG_<ROLE>_BASE_URL` + `PG_<ROLE>_API_KEY`
  (ROLE in {MIRROR,SENTINEL,JUDGE}); the served `model` must equal the locked slug (M4 served==pinned).
- Existing substrate (to REPLACE/EXTEND, not reuse blindly): `config/provisioning/vast_dev_cluster.yaml`
  (generic single H100 DeepSeek dev box — NOT the 3 roles); `docker-compose.yml` vllm service (OLD
  Gemma 2-LLM stub); `scripts/provision_vast_dev_cluster.py` (--apply NotImplemented, substrate-only).

## Scope of PR-8/M2 (acceptance criteria)
1. **Per-role serving config** `config/serving/verifier_roles.yaml` (declarative, LAW VI): one block
   per verifier role (mirror/sentinel/judge) with: model_slug (lock-sourced), gpu spec (Mirror
   8xH100 bf16; Sentinel 1xA100; Judge 1xH100 fp8), the vLLM launch args (served-model-name == the
   locked slug, tensor-parallel-size, quantization, max-model-len bounded — Judge needs
   structured-outputs/choice support per the lock; Mirror serves plain chat for `<co>` citations), and
   the env var it populates (`PG_MIRROR_BASE_URL` etc.). NO secrets in the file (keys via env).
2. **Health / identity probe** `scripts/dr_benchmark/verify_serving_identity.py`: given the 3 role
   base URLs (from env), query each endpoint's `/v1/models` (and optionally a 1-token completion) and
   assert the SERVED model id == the locked slug for that role. FAIL LOUD on mismatch / unreachable /
   wrong model (this is what M4 served==pinned will trust). The HTTP client is INJECTED so tests use
   a stub — NO real network. Emits a structured report (per-role: reachable, served_model, matches_lock).
3. **Launch runbook** `docs/serving/verifier_serving_runbook.md`: the exact operator steps to rent the
   Vast boxes + launch vLLM per role + set the env vars + run the identity probe — clearly marked as
   the PAID step (the one-question canary), NOT executed here.
4. **Tests** `tests/dr_benchmark/test_verify_serving_identity.py` (+ a config-shape test): the config
   parses + has all 3 roles with lock-matching slugs; the probe (injected stub) PASSES when served==slug
   for all 3, FAILS LOUD when a served model != the locked slug, when an endpoint is unreachable, and
   when a role base_url env is unset. NO network.
5. Hygiene: snake_case, explicit imports, named constants, no `except: pass`, no unittest.mock in src/
   /scripts (stub in tests), no real network anywhere, no `datetime.now()` in library code.

## Files I have ALSO checked / relevant
- M1 `openai_compatible_transport.role_endpoint` — the env convention M2's config must match
  (PG_<ROLE>_BASE_URL / PG_<ROLE>_API_KEY); the served-model==slug invariant M2's probe enforces and
  M4 will consume. Not modified by M2.
- `config/architecture/polaris_runtime_lock.yaml` — READ for slugs/serving_route; NOT modified.
- `docker-compose.yml` / `provision_vast_dev_cluster.py` — old single-box / Gemma stub; M2 adds the
  3-role serving config separately (does not delete the legacy generator dev box).

## Questions for Codex
1. Serving config as one declarative `config/serving/verifier_roles.yaml` (vLLM args per role) +
   a runbook for the paid launch — right shape, or do you want docker-compose service defs / a Vast
   launch script generator? (Paid deploy is the canary; M2 is config + probe + tests only.)
2. The identity probe asserting served `/v1/models` id == locked slug, fail-loud, injected HTTP client
   (no network in tests) — correct, and is `/v1/models` the right identity surface for vLLM (vs a
   tiny completion echoing the model)?
3. Judge needs structured-outputs/choice on its vLLM server; Mirror serves plain chat (for `<co>`).
   Confirm the per-role vLLM arg differences M2's config must encode.
4. Anything that would force real spend or a real network call in M2 (must stay no-spend/no-network).

Hand me APPROVE iff the no-spend boundary, the per-role serving config + lock-matching identity probe
(fail-loud, no-network-test), and the canary-deferred paid deploy are correct.
