# D8 transport reliability + raise outline max-tokens — SCOPE + DESIGN (iter-4)

**GitHub:** #1283 (I-beatboth-006), umbrella #1270. P4 reliability fix.
**Mode:** SCOPE + DESIGN only (no source edits in this pass).
**Constraint:** reliability-only, default-safe, away from the faithfulness engine; never silent-degrade — fail loud to a *disclosed* degrade.
**Date:** 2026-06-20.
**Iteration:** design iter-4 — closes the ONE remaining P1 in `.codex/I-beatboth-006/codex_design_verdict_iter3.txt`:
- **P1-A DISCLOSURE PROPAGATION (iter-4 fix)** — the iter-3 design closed per-claim ADJUDICATION (UNSUPPORTED on a faulted Mirror/Judge/Sentinel) but the `<judge_role_unavailable>` / `<sentinel_role_unavailable>` disclosure records were built in the adapter RETURN-TUPLES and then DISCARDED at the call sites (`role_pipeline.py:370` `_judge_records` and `:335` `_sentinel_records` are underscore-bound; `ClaimPipelineResult.records` comes ONLY from `recording.records` `:399`; `RecordingTransport.complete` `:158-163` appends ONLY after a SUCCESSFUL `transport.complete()`, never on the raising path). So the disclosure never reached `ClaimPipelineResult.records` — failing the design's OWN §4.1 harness (`:217-221`) and the line-5 "fail loud to a *disclosed* degrade" constraint. Now closed: `run_claim_pipeline` MERGES the synthetic `<judge_role_unavailable>` (C.2-merge) AND `<sentinel_role_unavailable>` (C.2-merge-sentinel) record into `recording.records` — selective (`served_model is None` + marker), degrade-only, exactly-once (Mirror C.1 already appends its record directly and is unchanged). §6 corrected: `sentinel_adapter.py` was NOT clean — its degrade record was silently dropped by the same discard. The per-claim fail-closed ADJUDICATION is UNCHANGED and not regressed.

*(Iter-2/iter-3 history: P1-A per-role fail-closed adjudication closed for all three roles §3.3+§4.1; P1-B GLM-5.2 STORM-outline routability closed via explicit generator-provider context + gate-enforced single-valued routability proof §3.4+§4.2.)*

---

## 0. One-line summary

Five gaps confirmed by file:line. (A) the **sovereign** role-transport `complete()` POST has no total-deadline force-close (`openai_compatible_transport.py:488`) — a trickle-hung judge socket there hangs the D8 gate (latent on sovereign; the campaign runs OpenRouter). (B) the STORM outline budget is starved (`.env:325 PG_STORM_OUTLINE_MAX_TOKENS=16384`) and GLM-5.2 is in neither reasoning-first model set, so the openrouter_client floor never fires for it — raise to the PROVEN provider-safe reference `64000`. **(C — P1-A, the binding fix)** a force-closed Mirror or Judge `RoleTransportError` is caught by NEITHER `mirror_adapter`/`judge_adapter` NOR `run_claim_pipeline`, so it propagates to `_compute_claim_results`'s `future.result()` → the `except BaseException` at `sweep_integration.py:585` → `cancel_futures=True` tears the WHOLE seam down and re-raises (coverage=0.0, `released_insufficient_safety_evidence`) — this fires on the HOT OpenRouter campaign path TODAY, not just sovereign. Fix: catch a force-close `RoleTransportError` for ALL THREE roles and map it to a PER-CLAIM fail-closed disclosed adjudication (D8 verdict UNSUPPORTED for that claim + a `<role_unavailable>` disclosure record). Placement is HYBRID and mechanism-dictated (§3.3): for the fail-closed VERDICT/RESULT, **Mirror** is handled in `run_claim_pipeline`'s Mirror `except` at `:330` because compose step-1 keys off the `mirror_failed_closed` BOOL (an adapter return would not fire it, and Sentinel+Judge would still run on a hung socket); **Judge** builds its UNSUPPORTED verdict in `judge_adapter` (its verdict flows straight through compose — never None); **Sentinel** builds its fail-closed result in `sentinel_adapter` (already shipped). **DISCLOSURE PROPAGATION (iter-4):** the Judge and Sentinel `<role_unavailable>` records are built in the adapter return-tuples but DISCARDED at the call sites (`:370`/`:335`), so `run_claim_pipeline` MERGES each synthetic marked record into `recording.records` (C.2-merge / C.2-merge-sentinel) — Mirror appends its record directly (C.1) and needs no merge. All three share one flag `PG_ROLE_TRANSPORT_DEGRADE` (default ON). On the flag-OFF / total-exhaustion path an explicit disclosed HARD-HALT manifest status (`abort_role_transport_exhausted`) + halt artifact fires — never a skipped/aborted gate, never coverage=0 from a raw teardown. **(D — P1-B)** tag the STORM outline `generate_structured` call `llm_role("generator")` so `current_role_provider()` resolves to the gate's per-role resolved generator singleton (preflight-resolved for GLM-5.2 → GLM-5.2-routable by construction); the gate's own single-valued served-identity assertion (`pathB_run_gate.py:782-785`) THEN PROVES the outline routed to the same GLM-5.2 provider as the sections, or fails the run. Faithfulness engine untouched on every change.

---

## 1. SCOPE — D8 transport residual reliability

### 1.1 The path (what runs where)

D8 = the single binding 4-role adjudication gate. Driver chain:

- `run_four_role_evaluation` → `_compute_claim_results` (`sweep_integration.py:606`, `:522`) runs claims in parallel on a `ThreadPoolExecutor(max_workers=_CLAIM_WORKERS)` where `_CLAIM_WORKERS = PG_FOUR_ROLE_CLAIM_WORKERS` (default 6, `:91`). The parent drains via `as_completed` / `wait(FIRST_COMPLETED)` (`:531`, `:562`) and `_settle(future)` calls `future.result()` (`:571`, `:532`) which RE-RAISES any worker exception into the parent.
- Each worker runs `run_claim_pipeline(transport, ...)` (`role_pipeline.py:282`) = Mirror → Sentinel → Judge over ONE injected `RoleTransport`.
- Every role adapter funnels through ONE chokepoint — `transport.complete(request)`:
  - `judge_adapter.py:239`, `mirror_adapter.py:366` + `:395`, `sentinel_adapter.py:395`.
  - `role_pipeline.py:158-160` `RecordingTransport.complete` just wraps + delegates to `self._transport.complete()` — adds no network.

### 1.2 What the F3 rebuild (96da78fe) already fixed

Run-5 crashed: `RuntimeError: Cannot send a request, as the client has been closed` → D8 UNADJUDICATED coverage=0.000 → `released_insufficient_safety_evidence`. Root: `_post_with_total_deadline` force-closes the thread-local client on a total-deadline timeout (`openrouter_role_transport.py:479 client.close()`), the rebuild was missable, and the next role POST hit the closed client with a plain `RuntimeError` that matched none of the retry arms. F3 fixed it in two places, both faithfulness-neutral (client lifecycle only):
- `_http_client` getter rebuilds a client that is **closed however it was closed**, not only `None` (`:990-994` — `if client is None or getattr(client, "is_closed", False)`).
- a narrowed `except RuntimeError` arm catches the `"has been closed"` signature, rebuilds, and retries within `transport_retries`, else falls through to the SAME fail-closed `RoleTransportError` (`:1193-1228`). Unrelated RuntimeErrors re-raise unchanged (`:1206-1207`).

### 1.3 The OpenRouter path IS bounded — but the bound RAISES a `RoleTransportError` that Mirror/Judge do NOT catch (P1-A root)

`OpenRouterRoleTransport.complete()` routes its POST through `_post_with_total_deadline(self._http_client, url, ..., timeout=_TIMEOUT_SECONDS, total_s=_role_transport_total_s())` (`:1158-1162`). That wrapper (`:467-485`) runs the blocking POST on a 1-worker executor, waits at most `total_s` (`PG_ROLE_TRANSPORT_TOTAL_S`, default 900s, `:449-454`), and on expiry **force-closes the socket** (`:479`) so the orphaned worker's blocked C-level read errors out and the thread exits. Two further backstops bound the COMPOSITION: the #1226 wall-clock watchdog over the whole retry loop (`PG_ROLE_CALL_TIMEOUT_S`, default 3600s, `:1089-1096`, `:550-561`) and the blank-retry ceiling (`PG_ROLE_BLANK_MAX_RETRIES`, `:541-547`). On every exhaustion path a fail-closed `RoleTransportError` fires.

**This is the P1-A root, on the HOT path, TODAY.** The OpenRouter transport DOES force-close a hung Mirror/Judge socket into a `RoleTransportError` — but that `RoleTransportError` is then UNCAUGHT by `mirror_adapter` / `judge_adapter` and by `run_claim_pipeline`. So the force-close that was supposed to make D8 resilient instead delivers a clean fail-closed exception straight into the seam teardown (§1.4 below). The bound exists; the per-role HANDLING of the bound's output is the gap. This is NOT sovereign-only — the live beat-both campaign runs `serving_route: openrouter`, so a slow Mirror/Judge on any one claim aborts the entire D8 gate on the paid run.

### 1.4 THE SEAM-TEARDOWN MECHANISM (P1-A, confirmed by file:line)

A `RoleTransportError` raised inside `run_mirror` (`role_pipeline.py:326`) or `run_judge` (`role_pipeline.py:370`) is NOT caught:
- `run_claim_pipeline` catches only `(MirrorCitationError, MirrorBindingError, MirrorParseError)` around the Mirror call (`role_pipeline.py:330`) — a `RoleTransportError` is none of those (the comment at `:321` even says "any OTHER exception propagates"). The Judge call (`:370`) has NO surrounding try at all. Sentinel runs between them and DOES catch `RoleTransportError` (`sentinel_adapter.py:426`, gated by `PG_SENTINEL_TRANSPORT_DEGRADE`, default ON) — so ONLY Sentinel is protected.
- The propagated `RoleTransportError` exits `run_claim_pipeline` → exits the worker → `_settle(future)` calls `future.result()` (`sweep_integration.py:571` / `:532`) which RE-RAISES it on the parent thread → the `except BaseException` block (`sweep_integration.py:585-591`) runs `pool.shutdown(wait=False, cancel_futures=True)` and `raise`. This CANCELS every still-pending claim and re-raises out of `_compute_claim_results`.
- Upstream, `run_four_role_evaluation` has no per-claim guard around the `_compute_claim_results` call (`sweep_integration.py:709-716`); the re-raised error propagates to the sweep's top-level handler, which records coverage_fraction=0.0 → `released_insufficient_safety_evidence` — the EXACT run-5 failure signature, now reachable from a hung Mirror/Judge rather than a closed client.

**Net:** one trickle-hung Mirror or Judge socket on ONE claim discards the ~177 successfully-adjudicated OTHER claims and holds the whole report. This is precisely the seam-wide abort the Sentinel adapter's `PG_SENTINEL_TRANSPORT_DEGRADE` was built to prevent (`sentinel_adapter.py:427-438`) — but Mirror and Judge have no equivalent.

### 1.5 THE SOVEREIGN RESIDUAL (latent): the sovereign transport POST is unbounded

`openai_compatible_transport.py:488` (the self-host / sovereign `RoleTransport.complete()` used when `serving_route` is the sovereign vLLM endpoint) makes a **bare** synchronous POST:

```python
http_response = self._http_client.post(
    url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS  # line 489
)
```

There is **no `_post_with_total_deadline` wrapper, no force-close, no total wall-deadline.** The `timeout=_TIMEOUT_SECONDS` is the per-call httpx timeout — and as the OpenRouter-side comment documents (`openrouter_role_transport.py:438-441`), httpx's read timeout is a per-BYTE gap that a **trickle-fed / keep-alive socket resets indefinitely**. So a trickle-hung sovereign socket on a D8 claim worker hangs that worker forever; the parent's `as_completed` never sees it complete and the whole D8 gate stalls. It is the identical failure class `_post_with_total_deadline` was built to close on the OpenRouter side, still open on the sovereign side. The dress-rehearsal/Carney sessions are sovereign (`I-C-08..10`, `I-D-03`), so this is a known unbounded paid-path hang — in scope to close now (small, surgical, faithfulness-neutral).

### 1.6 Out of scope (named so a reviewer sees they were checked, not missed)

- **`PG_PARALLEL_VERIFY`** (the grep the task asked for) lives in `provenance_generator.py` (the strict_verify / NLI verify path), NOT the D8 4-role path. D8 parallelism is governed by the **separate** `PG_FOUR_ROLE_CLAIM_WORKERS` knob (`sweep_integration.py:91`). The loop_state forensic note ("D8 serial, PG_PARALLEL_VERIFY=16 may not engage on D8"; FIX-C 41b74341) is a **throughput/serial-ness** concern on a different knob — explicitly **out of scope** for this *reliability* issue.
- **The faithfulness engine** (strict_verify / NLI / 4-role verdict logic / coverage / release_policy): untouched. Every change here is transport client lifecycle, role-fault disclosure, token budget, or provider-context tagging only.

---

## 2. SCOPE — STORM outline max_tokens starvation

### 2.1 The outline call

`_generate_outline_from_conversations` (`storm_interviews.py:1113`) is the ONE STORM call with `reasoning_enabled=True` (it needs structural reasoning to cluster 8-15 thematic sections from the multi-perspective interviews). It calls:

```python
result = await asyncio.wait_for(
    client.generate_structured(
        prompt=prompt, schema=StormOutlinePlan,
        max_tokens=PG_STORM_OUTLINE_MAX_TOKENS,   # line 1205
        reasoning_enabled=True,
    ),
    timeout=float(os.getenv("PG_STORM_OUTLINE_CALL_TIMEOUT_S", "300")),  # line 1208
)
```

On any exception (incl. truncation-to-invalid-JSON or the 300s timeout) it falls through to `_fallback_outline` (`:1234`, `:1238`) — a DISCLOSED degrade that emits **one bland section per perspective** instead of the real 8-15 thematic clusters. That is a real breadth/quality loss surfacing as a "thin outline."

### 2.2 The starvation (confirmed)

- In-code default: `PG_STORM_OUTLINE_MAX_TOKENS = int(os.getenv("PG_STORM_OUTLINE_MAX_TOKENS", "32768"))` (`storm_interviews.py:128`). The 32768 was deliberately raised from 4096 in #1253 to clear V4-Pro's ~17-18k reasoning footprint so the outline JSON does not truncate (`:124-127`).
- **`.env:325` overrides it DOWN to `PG_STORM_OUTLINE_MAX_TOKENS=16384`** — HALF the in-code default, and below the §9.1.8 reasoning-first floor. This is the active live-campaign config. A reasoning-first generator that burns ~17-18k tokens on reasoning before content can have the multi-perspective JSON outline **truncate mid-structure** → JSON parse fail → silent fall to the one-section-per-perspective fallback. **This is a direct §9.1.8 "reasoning effort + max_tokens ALWAYS go MAX; never starve" violation.**
- **GLM-5.2 floor gap.** The campaign generator is now `z-ai/glm-5.2` (`relevance_judge.py:70,84`; `polaris_runtime_lock.yaml` GLM-5.2 arm; `P2_DECISIONS.md`). But `z-ai/glm-5.2` is in **neither** `_ALWAYS_REASON_MODELS` (`openrouter_client.py:798-800`) **nor** `_REASONING_FIRST_MODELS` (`:808-812`). So on the `generate_structured(reasoning_enabled=True)` path GLM-5.2 takes the branch-2 `elif reasoning_enabled:` arm (`:1784`), and the `if self.model in _REASONING_FIRST_MODELS:` floor/cap block (`:1802-1808`) is **SKIPPED**. The outline keeps its raw caller `max_tokens` with no reasoning-first floor backstop — so the `.env` 16384 is honored verbatim for GLM-5.2, with no safety floor. GLM models are known to burn reasoning budget (the xhigh "mirror blank" pattern), so a low budget here is doubly dangerous for the GLM-5.2 arm.

### 2.3 The real provider cap + why a raise is SAFE — arm-specific, NOT one universal claim

The token-MAX governance (§9.1.8) says: set `max_tokens` to the model's REAL served limit, reconcile vs the serving provider's actual cap. **The 404-safety of an outline raise is DIFFERENT for the two campaign generator arms** — a naive "the resolver clamp protects it" claim is FALSE for the deepseek arm and must not be made.

**Background — run #7 truncation (real, must be respected).** `P2_DECISIONS.md`: "deepseek-v4-pro hit a real ReasoningFirstTruncationError [FATAL] in run #7 (DeepInfra ~16384 cap)." That was a **section** call truncating because the generator chain *can* land on DeepInfra's fp4/16384 endpoint. So a blind raise is dangerous IF the request can reach DeepInfra.

**The resolver clamp does NOT save the deepseek arm.** `generate_structured` → `_call_impl` applies `_resolve_allowed_max_tokens(self.model, prompt_tokens, requested_mt, apply_completion_cap=...)` to every call (`openrouter_client.py:1898-1914`), clamping DOWN to `min(provider_completion_cap?, context_length - prompt - margin)` (`token_limit_resolver.py:281-372`). BUT it sets `apply_completion_cap = self.model not in _REASONING_FIRST_MODELS` (`:1908`). deepseek-v4-pro IS in `_REASONING_FIRST_MODELS` → `apply_completion_cap=False` → the clamp uses ONLY `context_length - prompt - margin` and **deliberately IGNORES the provider completion cap** (the #1253 regression guard, `:1901-1906`). So for deepseek the clamp will NOT clamp a 64000 request down to a 16384-capped provider — it would send 64000. The clamp is therefore NOT what makes the deepseek raise safe.

**What ACTUALLY makes the deepseek arm safe: the Path-B provider pin excludes DeepInfra.** Verified: `.env:19 OPENROUTER_PROVIDER_ORDER=` is EMPTY, so on the benchmark run gate the generator provider is resolved by the Path-B override (`openrouter_client.py:1932-1955`): a Path-B singleton from preflight `/endpoints` resolution, else `role_provider_routing("generator")`. That generator chain (`config/settings/openrouter_provider_routing.yaml:7-22`) is the fp8 FULL-CAP chain `order: [wandb, siliconflow, baidu, novita, streamlake, gmicloud, deepseek]` + `ignore: [atlas-cloud, parasail, fireworks, digitalocean, together]` with `allow_fallbacks:False` — and the comment is explicit: "**DeepInfra (fp4/16384) stays excluded**" (`:21`). So the deepseek arm **cannot land on the 16384 provider**; its binding ceiling is the fp8 chain's >=384000.

**The glm-5.2 arm IS protected by the clamp.** glm-5.2 is NOT in `_REASONING_FIRST_MODELS` → `apply_completion_cap=True` → the clamp reconciles DOWN to `min(provider_completion_cap, context_length - prompt - margin)`. glm-5.2 (1M ctx, Friendli) keeps a generous outline budget.

**The proven provider-safe reference value.** `PG_SECTION_MAX_TOKENS` default = 64000 (`multi_section_generator.py:447`), and sections render successfully on the live run against this SAME generator chain — empirical proof the live generator chain serves >> 16384. **Align the outline budget to this proven 64000 reference**, not an arbitrary 131072.

**Consequence — the empirical seal (strongest proof, lead with this):** the SECTION generator calls `_call_impl` over the IDENTICAL provider-block resolution (`:1932-1955`), same model, same provider selection, and renders successfully at 64000 on the live run. The outline at 64000 rides the same path, same model, same provider selection → safe BY CONSTRUCTION. If the Path-B singleton resolution could ever land deepseek on DeepInfra, the sections would already 404 at 64000 — and they do not. Underneath, safety holds on BOTH arms via TWO DISTINCT mechanisms — glm-5.2 via the clamp, deepseek-v4-pro via the DeepInfra-excluding provider pin — NOT via one universal "clamp protects everything" claim. **Dependency flagged:** this relies on the Path-B provider pin being active on the run path; a run that explicitly sets `OPENROUTER_PROVIDER_ORDER` to include DeepInfra would re-expose run-#7. That is the same provider-cap dependency the SECTIONS already carry.

> **§3.4 cross-link (P1-B):** the outline-routing tag in §3.4 STRENGTHENS this argument: once the outline call carries `llm_role("generator")`, its provider is resolved from the SAME gate-pinned generator singleton the sections use (not the bare `role_provider_routing("generator")` deepseek chain), so "same provider as the sections" becomes gate-ENFORCED, not merely asserted by parity.

---

## 3. DESIGN — the fixes

### 3.1 Fix A — total-deadline force-close on the sovereign role-transport POST

**Goal:** the sovereign `complete()` POST is bounded by the SAME proven force-close wall-deadline the OpenRouter path uses, so a trickle-hung sovereign socket cannot hang the D8 gate — it force-closes, the worker unblocks, and the resulting `RoleTransportError` is consumed by Fix C's per-role fail-closed handler (§3.3), never silently.

**Change (surgical, `openai_compatible_transport.py`):**
1. Reuse the EXISTING proven helper. Lift `_post_with_total_deadline` + `_role_transport_total_s` into a shared `role_transport_deadline.py` helper module that BOTH transports import (pure: executor + force-close; already battle-tested; keeps the two transports symmetric).
2. Replace the bare POST at `:488-490` with the wrapped call:
   ```python
   http_response = _post_with_total_deadline(
       self._http_client, url, json_body=body, headers=headers,
       timeout=_TIMEOUT_SECONDS, total_s=_role_transport_total_s(),
   )
   ```
3. Add the SAME bounded-retry arms the OpenRouter path has, so a force-close rebuilds + retries within a bounded budget then fails closed:
   - `except concurrent.futures.TimeoutError`: force-close already happened inside the helper; rebuild this transport's client, retry up to `PG_ROLE_TRANSPORT_RETRIES`, else raise the EXISTING `RoleTransportError` (fail-closed).
   - `except RuntimeError` (the `"has been closed"` signature): same F3 defense-in-depth arm — rebuild + retry, else fail-closed `RoleTransportError`. Narrow to the closed-client signature so an unrelated RuntimeError re-raises unchanged (LAW II §9.4).
   - keep the existing `except httpx.HTTPError` fail-closed arm (`:491-494`).
4. **Client lifecycle:** if the sovereign transport holds a single injected client and the sweep runs sovereign D8 across `PG_FOUR_ROLE_CLAIM_WORKERS` worker threads, the Codex-P1 cross-worker cascade applies — a force-close on one worker must not tear down a sibling's in-flight POST. So the sovereign transport must also be **thread-local** (mirror `openrouter_role_transport.py:955-999`). Verify the construction site in the sweep wiring; if single-threaded, document that and keep the thread-local change as defense-in-depth (byte-identical on the single-thread path).

**LAW VI:** every knob env-driven and already exists (`PG_ROLE_TRANSPORT_TOTAL_S`, `PG_ROLE_TRANSPORT_RETRIES`, `PG_VERIFIER_LLM_TIMEOUT_SECONDS`). No new magic numbers.

**Faithfulness:** none touched. On every exhaustion path the UNCHANGED fail-closed `RoleTransportError` fires → consumed by Fix C → D8 adjudicates per-claim disclosed. Healthy path is byte-identical.

### 3.2 Fix B — raise the STORM outline max_tokens to a generous, provider-reconciled default

**Goal:** the outline gets a MAX, never-starved budget per §9.1.8, generator-agnostic, with no 404.

**Changes (surgical):**
1. **`.env:325`** — raise `PG_STORM_OUTLINE_MAX_TOKENS=16384` → **`64000`** (the PROVEN reference `PG_SECTION_MAX_TOKENS` uses, `multi_section_generator.py:447`). Env knob (LAW VI).
2. **`storm_interviews.py:128`** — raise the in-code DEFAULT 32768 → 64000 so a deploy that forgets the env override is not silently starved. (Keep it env-overridable.)
3. **GLM-5.2 floor gap — outline-scoped, flag the broader tradeoff:** keep the fix outline-scoped: the resolver clamp at `_call_impl:1898-1914` already reconciles the budget DOWN to glm-5.2's real served cap regardless of model-set membership, so an explicit generous `PG_STORM_OUTLINE_MAX_TOKENS` is honored up to that real cap. No model-set edit needed. **Tradeoff flagged for the lock owner:** glm-5.2's *absence* from `_REASONING_FIRST_MODELS` is a broader latent gap (other glm-5.2 generate_structured callers that pass a small max_tokens get no floor) — a separate model-governance issue, not this reliability fix.
4. **No faithfulness touch** — the outline is an ORGANIZATIONAL scaffold; its fallback is already a disclosed degrade. Widening the budget only converts a silent truncate-to-fallback into the real full outline.

### 3.3 Fix C (P1-A) — per-role fail-closed disclosed handling of a force-close `RoleTransportError` for ALL THREE roles + a disclosed HARD-HALT exhaustion path

**Goal:** a force-closed Mirror OR Judge OR Sentinel `RoleTransportError` (the output of the bounded transport in §3.1 / §1.3) NEVER tears the seam down. It maps to a PER-CLAIM fail-closed disclosed adjudication (D8 verdict UNSUPPORTED for that claim + a `<role_unavailable>` disclosure record THAT REACHES `ClaimPipelineResult.records`), so D8 keeps adjudicating every other claim — extending the per-claim *adjudication* resilience the Sentinel adapter already had to Mirror and Judge, AND closing the disclosure-propagation gap that affected ALL THREE roles (iter-4: the Judge/Sentinel disclosure records were built in the adapter return-tuples but discarded at the call sites; now merged into `recording.records`, see C.2-merge / C.2-merge-sentinel). On the flag-OFF / total-exhaustion path it emits an explicit DISCLOSED hard-halt manifest status — never a raw seam teardown with coverage=0.

**Placement decision — HYBRID, dictated by HOW each role's fail-closed is SIGNALED (mechanism-checked against `role_pipeline.py:325-334` + `_compose_final_verdict:241-279`), NOT by surface symmetry.** The two roles are NOT symmetric in how `_compose_final_verdict` (LOCKED) reads a fail-closed signal, so the handling site differs:

- **Compose step-1 (`role_pipeline.py:261`) keys off the `mirror_failed_closed` BOOL**, and that bool is set ONLY by the `except (MirrorCitationError, MirrorBindingError, MirrorParseError)` arm at `role_pipeline.py:330`. A *returned* fail-closed `MirrorPass2` tuple does NOT raise → `mirror_failed_closed` stays `False` → step-1 is SKIPPED, the `if not mirror_failed_closed:` short-circuit at `:334` is `True`, so **Sentinel + Judge still run** (two more transport calls on a claim whose transport may be globally hung) AND the `assert raw_judge_verdict is not None` invariant at `:266` is reached on a path it was not designed for. **So a returned-tuple Mirror handler does NOT achieve per-claim fail-closed.** The Mirror fault MUST drive the `mirror_failed_closed` bool. The natural and ONLY site that sets that bool is `run_claim_pipeline`'s `except` arm at `:330`. → **Mirror is handled by a small `run_claim_pipeline` change (Change C.1), NOT in the adapter.** This DELIBERATELY revises the iter-1 "no `run_claim_pipeline` body change" stance — the mechanism requires it (see §6 reconciliation note).
- **The Judge verdict flows straight through compose's grounded path** (`_compose_final_verdict:258,279` returns `raw_judge_verdict`), so a `run_judge` that RETURNS a fail-closed UNSUPPORTED verdict is correctly composed without any `run_claim_pipeline` change to the VERDICT path. → **Judge's fail-closed VERDICT is built in the adapter (Change C.2).** The Judge's DISCLOSURE record, however, is NOT auto-propagated (the adapter's returned record-list is discarded at `:370`), so the disclosure record is merged into `recording.records` by a small call-site change (Change C.2-merge). Sentinel is identical: its fail-closed RESULT is built in the adapter (existing), but its disclosure record is discarded at `:335` and must likewise be merged (Change C.2-merge-sentinel). So "handled in the adapter" applies to the VERDICT/RESULT only; the DISCLOSURE record for both Judge and Sentinel is propagated at the pipeline.

Rationale for the shared flag: the knob `PG_SENTINEL_TRANSPORT_DEGRADE` already exists as the precedent; this fix generalizes it to a single shared `PG_ROLE_TRANSPORT_DEGRADE` (default ON) read by the Mirror catch site, the Judge adapter, and the Sentinel adapter, so the operator has ONE switch for the whole D8 seam degrade behavior. (Keep `PG_SENTINEL_TRANSPORT_DEGRADE` honored as a back-compat alias for the Sentinel arm.)

**Change C.1 — `role_pipeline.py` `run_claim_pipeline`, the Mirror `except` arm at `:330` (NOT the adapter — mechanism above):**
- Extend the catch to `except (MirrorCitationError, MirrorBindingError, MirrorParseError, RoleTransportError) as exc:` and, when the caught exception is a `RoleTransportError` AND `PG_ROLE_TRANSPORT_DEGRADE` is ON, set `mirror_failed_closed = True` (exactly as the other three do) and append a disclosure `RoleCallRecord(role="mirror", served_model=None, raw_text="<mirror_role_unavailable>{type}: {exc}</mirror_role_unavailable>", parsed=<fail-closed>)` to `recording.records` so the served-identity / audit layer sees the Mirror was unavailable for THIS claim. `mirror_failed_closed=True` → compose step-1 returns UNSUPPORTED AND the `if not mirror_failed_closed:` short-circuit at `:334` skips Sentinel + Judge (fast-fail — no further transport calls on a hung socket). This is the verdict-correct per-claim fail-closed for Mirror.
- When `PG_ROLE_TRANSPORT_DEGRADE` is OFF: do NOT swallow the `RoleTransportError` — re-raise it (keep the existing `MirrorCitationError/Binding/Parse` catch behavior unchanged for the non-transport faults). The re-raised `RoleTransportError` is then caught by the §3.3 seam hard-halt branch (Change C.3), NOT a raw teardown.
- `_compose_final_verdict` (LOCKED) is UNTOUCHED — this only feeds it the existing `mirror_failed_closed=True` input it already handles. `RecordingTransport` already holds the served-identity attempt for any Mirror POST that fired before the fault, so identity capture is intact; the synthetic `<mirror_role_unavailable>` text record is the added disclosure.

**Change C.2 — `judge_adapter.py` (`run_judge`, around `transport.complete()` `:239`):**
- Add the SAME `except RoleTransportError as exc:` arm (after a `BudgetExceededError` re-raise; the existing `JudgeEnumError` fail-LOUD on a non-enum token is UNCHANGED — a transport fault is NOT a verdict-parse fault). When ON: emit `RoleCallRecord(role="judge", served_model=None, raw_text="<judge_role_unavailable>{type}: {exc}</judge_role_unavailable>", parsed=<fail-closed>)` as the SOLE element of the returned record-list (`return UNSUPPORTED, [record]`) and return a fail-closed Judge verdict for this claim. **Critical (advisor-flagged): the returned verdict must be a CONCRETE disclosed verdict, never `None`.** `_compose_final_verdict` returns `raw_judge_verdict` on the sentinel-grounded path (`role_pipeline.py:276,279`); a `None` there yields no valid verdict. Return `Verdict = UNSUPPORTED` (the same fail-closed verdict the Mirror-fail and Sentinel-unsafe paths already converge on), so the claim is disclosed UNSUPPORTED and counts as a non-credited (uncovered) claim — never a synthesized PASS, never None.
- Flag OFF → `raise` → caught by Change C.3.

**Change C.2-merge — `role_pipeline.py` `run_claim_pipeline`, the Judge call site at `:370` (the binding disclosure-propagation fix): MERGE the synthetic Judge-unavailable record into `recording.records`.**
The adapter (C.2) builds the `<judge_role_unavailable>` `RoleCallRecord` inside its returned tuple `(UNSUPPORTED, [record])`, but the call site at `role_pipeline.py:370` binds the record-list to the underscore-discarded local `_judge_records` and `ClaimPipelineResult.records` is sourced ONLY from `recording.records` (`:399`). `RecordingTransport.complete` (`:158-163`) appends ONLY after a SUCCESSFUL `transport.complete()` — so on the `RoleTransportError` fault path the synthetic record is NEVER recorded by `RecordingTransport` and is then dropped with `_judge_records`. The disclosure therefore never reaches `ClaimPipelineResult.records`, failing the design's OWN §4.1 harness and the line-5 "fail loud to a *disclosed* degrade" constraint. **Fix:** consume `_judge_records` instead of discarding it and append ONLY the synthetic marked record(s) to `recording.records`:
```python
raw_judge_verdict, judge_records = run_judge(recording, ...)   # was `_judge_records`
for _rec in judge_records:
    if _rec.served_model is None and "_role_unavailable>" in (_rec.raw_text or ""):
        recording.records.append(_rec)   # degrade-only, exactly-once
judge_result = raw_judge_verdict
```
**Selective, NOT wholesale (advisor-flagged double-count guard):** do NOT extend `recording.records` with the WHOLE `judge_records` list. On the SUCCESS path `run_judge`'s served call already transited `RecordingTransport.complete()` → its `{parsed=None}` record is ALREADY in `recording.records`; the adapter ALSO returns a `{parsed=verdict}` record in `_judge_records` for the SAME call. Appending the whole list would record that served call TWICE. The synthetic unavailable record is uniquely identifiable: it is built ONLY in the adapter's `except RoleTransportError` arm with `served_model=None` AND a `<…_role_unavailable>` marker, and by construction NEVER transited a successful `transport.complete()` (the call raised), so `RecordingTransport` never recorded it → appending exactly the marked record yields it exactly once. This mirrors Mirror C.1's pattern (append the synthetic record ONLY in the except arm); the Judge difference is that the marked record is carried back in the adapter's return tuple rather than constructed at the pipeline catch site, so the pipeline EXTRACTS-and-appends it instead of CONSTRUCTING it.

**Change C.2-merge-sentinel — `role_pipeline.py` `run_claim_pipeline`, the Sentinel call site at `:335` (the SAME defect, already-shipped Sentinel arm): MERGE the synthetic Sentinel-unavailable record into `recording.records`.**
The already-shipped Sentinel degrade (`sentinel_adapter.py:445-452`, `PG_SENTINEL_TRANSPORT_DEGRADE`) builds its `<sentinel_role_unavailable>` `RoleCallRecord` (`served_model=None`) and returns it inside `[*blank_records, record]` — but the call site at `role_pipeline.py:335` binds the list to the underscore-discarded local `_sentinel_records`, so that disclosure record is silently dropped by the IDENTICAL discard mechanism (this is the §6 correction below — the existing Sentinel arm was NOT clean). **Fix:** consume `_sentinel_records` and append ONLY the marked record(s) with the SAME selective predicate:
```python
sentinel_result, sentinel_records = run_sentinel(recording, ...)   # was `_sentinel_records`
for _rec in sentinel_records:
    if _rec.served_model is None and "_role_unavailable>" in (_rec.raw_text or ""):
        recording.records.append(_rec)   # degrade-only, exactly-once
```
Same double-count guard applies: the Sentinel `blank_records` (`sentinel_adapter.py:406-412`) carry a REAL `served_model` (each blank-200 already transited `RecordingTransport.complete()` → already in `recording.records`), so the `served_model is None` + marker predicate selects ONLY the synthetic unavailable record, never a blank-retry record. (The Mirror arm — C.1 — needs NO merge step: it constructs and appends its `<mirror_role_unavailable>` record DIRECTLY into `recording.records` at the pipeline catch site, so it is already wired.)

**Change C.3 — the disclosed HARD-HALT exhaustion path (`sweep_integration._compute_claim_results` `except BaseException` `:585-591` + `run_four_role_evaluation`):**
- The flag-ON path above means a force-close fault is consumed in-adapter and NEVER reaches `future.result()` as a `RoleTransportError`, so the seam keeps adjudicating. But the flag-OFF path (operator explicitly disabled degrade) and any GENUINELY-unexpected propagated transport exception must STILL be a DISCLOSED outcome, not a raw teardown with a bare coverage=0. Change the seam so a propagated `RoleTransportError` (flag OFF) is caught explicitly and converted to a disclosed `abort_role_transport_exhausted` manifest status + a `state/halt_<utc>_role_transport_exhausted.md` artifact (§3.0 halt-marker convention) recording the faulted role/claim_id, BEFORE the generic teardown. This is the "explicit disclosed HARD HALT artifact path" the verdict demands for the propagated-fault branch. The generic `except BaseException` (BudgetExceededError, etc.) is otherwise UNCHANGED.
- **Never a skipped/aborted gate:** with the flag ON (default) the gate ADJUDICATES every claim (faulted roles disclosed UNSUPPORTED per-claim); with the flag OFF the gate HALTS LOUDLY with a disclosed status + artifact. There is no path where a hung Mirror/Judge silently skips or vacuously passes the D8 gate.

**Faithfulness:** NONE relaxed. A transport-faulted role for a claim makes that claim fail CLOSED (UNSUPPORTED — never VERIFIED, never credited into coverage). `_compose_final_verdict` (LOCKED) is UNTOUCHED — Mirror returns its existing fail-closed shape, Judge returns the existing UNSUPPORTED verdict, both of which the LOCKED composition already maps to UNSUPPORTED. This can only TIGHTEN a claim's verdict, never loosen it. The change is reliability + disclosure: it converts a seam-wide crash into a per-claim disclosed fail-closed, identical in spirit to the already-shipped Sentinel degrade.

**LAW VI:** `PG_ROLE_TRANSPORT_DEGRADE` (default ON) — the single seam degrade switch; `PG_SENTINEL_TRANSPORT_DEGRADE` honored as a back-compat alias. No magic numbers.

### 3.4 Fix D (P1-B) — make the GLM-5.2 outline call provably generator-routable via an explicit generator role context

**Goal:** the STORM outline `generate_structured` call resolves its provider from the gate's per-role resolved generator singleton (preflight-resolved against `PG_GENERATOR_MODEL` = GLM-5.2 → GLM-5.2-routable BY CONSTRUCTION), not the deepseek-specific `role_provider_routing("generator")` chain — and the gate's own served-identity assertion PROVES it.

**The mechanism (confirmed by file:line):**
- `current_role_provider()` (`pathB_capture.py:112-127`) reads the `_ROLE` contextvar; if `_ROLE` is unset it returns None → `openrouter_client.py:1937-1957` falls to `role_provider_routing("generator")` (the deepseek fp8 chain) — the verdict's exact concern.
- The gate publishes a per-role resolved provider mapping `role_provider_map` (`pathB_runner.py:184-189`) via `set_role_providers`, keyed by role; the `"generator"` entry is preflight-resolved against `PG_GENERATOR_MODEL` (= GLM-5.2) at `pathB_run_gate.py` `resolve_role_provider` → the ACTUAL GLM-5.2 served provider singleton.
- The STORM call runs inside an ISOLATED `copy_context()` snapshot (`run_honest_sweep_r3.py:5292`, `:5296-5299`) taken WHILE the gate scope is active, so that snapshot CARRIES the `_ROLE_PROVIDER` mapping and the capture `_SINK`. What it lacks is a `_ROLE` value of `"generator"`.

**Change D.1 (surgical, `storm_interviews.py`, scoped to JUST the outline call `:1202-1208` — advisor-flagged: do NOT tag `run_storm_interviews` wholesale):**
- Wrap ONLY the outline `client.generate_structured(...)` call in `pathB_capture.llm_role("generator")`:
  ```python
  from src.polaris_graph.benchmark import pathB_capture as _pathb
  ...
  with _pathb.llm_role("generator"):
      result = await asyncio.wait_for(
          client.generate_structured(prompt=prompt, schema=StormOutlinePlan,
                                     max_tokens=PG_STORM_OUTLINE_MAX_TOKENS,
                                     reasoning_enabled=True),
          timeout=float(os.getenv("PG_STORM_OUTLINE_CALL_TIMEOUT_S", "300")))
  ```
  Now `current_role_provider()` resolves to `role_provider_map["generator"]` = the GLM-5.2 singleton → the request `provider.order=[<GLM-5.2 provider>]` (`openrouter_client.py:1940-1942`), `allow_fallbacks=False`. The outline rides the EXACT provider the sections ride.
- **Import safety (advisor-flagged, verified):** `storm_interviews.py` does NOT currently import pathB_capture, and `pathB_capture.py` imports NOTHING from `agents/`, `generator/`, or `multi_section` — so `agents/storm_interviews → benchmark/pathB_capture` introduces NO cycle. `pathB_capture` is the clean source of `llm_role` (re-exported by `pathB_runner`, but import the source module directly to avoid pulling the runner).
- **Gate-OFF behavior:** outside a gate run `_ROLE_PROVIDER` is None → `current_role_provider()` still returns None → falls to `role_provider_routing("generator")`. The verdict notes this chain is deepseek-specific; under the GLM-5.2 campaign lock the gate is ON (the benchmark run gate), so the singleton path is the live one. For a gate-OFF GLM-5.2 run, the resolver clamp (§2.3) still reconciles the budget to GLM-5.2's real cap, so the worst case is a sub-optimal provider ORDER, NOT a 404 — and the campaign always runs gated. (Flag for the lock owner: a generic GLM-5.2 generator chain in `openrouter_provider_routing.yaml` would close the gate-OFF gap, but that is a model-governance addition, not this reliability fix.)

**The routability PROOF (gate-enforced, the verdict's "assert in §4.2"):** `assert_post_run` (`pathB_run_gate.py:782-785`) requires the served-identity surrogate (= `provider_name` + `model`, `pathB_runner.py:105`) to be **SINGLE-VALUED per role across the whole run**. With Change D.1 the outline call is captured under role `"generator"` (the sink snapshot is in the isolated context) and its served surrogate is added to `surrogate_by_role["generator"]` ALONGSIDE the section calls. If — and only if — the outline routed to the SAME GLM-5.2 provider as the sections does the set stay single-valued and the gate PASS. If the outline had fallen to the deepseek chain (the bug), its surrogate would DIFFER → `surrogate-identity drifted across calls` GateError → run INVALID. **So the gate mechanically PROVES the outline is generator-routable; a mis-route fails the run loudly rather than silently mis-routing.** This is a stronger guarantee than a static assertion: it is enforced on every gated run. (Completeness check at `:704-706` is unaffected — `"generator"` is already a pinned role that appears via the section calls; the extra outline call only adds to an existing role, never an unpinned one, so no `role not pinned` error at `:711-713`. No call-count assertion exists, so an extra generator call is tolerated.)

**Faithfulness:** none touched. This is provider-routing context only — it changes WHICH provider serves the same GLM-5.2 outline call, not the outline content, the schema, or any verify gate.

---

## 4. §-1.4 behavioral replay-harness (acceptance = effect FIRES in real output, fail-loud)

Per §-1.4 + the wiring-acceptance gate: "committed + green + Codex-approve ≠ fired." Behavioral fail-loud (non-zero-exit) checks, each must FAIL before the fix and PASS after.

### 4.1 D8 force-close + per-role fail-closed adjudication check (Fix A + Fix C — covers hung Mirror AND hung Judge)

- **The existing F3 test is insufficient** as the behavioral gate: `test_role_client_rebuild_iarch011.py` uses a MockTransport that returns instantly, so the total-deadline NEVER fires — it proves client-rebuild, not the hang bound or the per-role fail-closed.
- **New harness `test_d8_role_transport_failclosed.py`:** inject a transport stub whose `.post` for a TARGET role blocks past `PG_ROLE_TRANSPORT_TOTAL_S` (set the deadline small in-test and have the stub sleep/trickle longer). Run a banked D8 claim set through `run_four_role_evaluation` / `_compute_claim_results` with `PG_FOUR_ROLE_CLAIM_WORKERS>1`. Run the harness THREE times: target = **Mirror**, target = **Judge** (the two the verdict names verbatim), and target = **Sentinel** (regression — must still degrade as today). For EACH:
  - ASSERT the whole call **returns within ~deadline + margin** (the force-close fired, the worker unblocked) — NOT hangs/times out.
  - **DISCLOSURE-PROPAGATION assertion at the PIPELINE-UNIT level (the binding iter-4 fix, run this DIRECTLY against `run_claim_pipeline`): with a hung Judge POST AND, separately, a hung Sentinel POST (and the Mirror case), ASSERT the synthetic `<{role}_role_unavailable>` `RoleCallRecord` (`served_model is None`, marker in `raw_text`) IS PRESENT in the returned `ClaimPipelineResult.records`** — the pipeline-unit output the merge directly produces. This assertion MUST be CURRENTLY-FAILING pre-fix (today `_judge_records`/`_sentinel_records` are underscore-discarded → the record is absent from `recording.records` → absent from `ClaimPipelineResult.records`) and PASS post-fix — that is what makes the harness load-bearing for THIS disclosure-propagation fix per §-1.4. ALSO assert it appears EXACTLY ONCE (the selective merge does not double-count) and that the SUCCESS path (no fault) produces NO `<…_role_unavailable>` record and NO duplicated served-call record.
  - ASSERT the **other claims still ADJUDICATE** — `run_four_role_evaluation` returns a `D8ReleaseDecision`; the faulted claim's `final_verdict == "UNSUPPORTED"` with a `<{role}_role_unavailable>` disclosure record in its records; NO seam-wide `coverage_fraction=0.0` teardown, NO `released_insufficient_safety_evidence` from a transport crash, NEVER a synthesized PASS.
  - ASSERT the force-close path logged loudly (the F3 / #1264 warning lines).
  - **Flag-OFF branch:** with `PG_ROLE_TRANSPORT_DEGRADE=0`, ASSERT the run HALTS with manifest status `abort_role_transport_exhausted` + a `state/halt_*_role_transport_exhausted.md` artifact — a DISCLOSED hard halt, NOT a bare coverage=0 teardown.
  - Run BOTH the OpenRouter and sovereign transports (the OpenRouter path is the HOT campaign path TODAY; sovereign is the latent path Fix A bounds).
  - FAIL LOUD (non-zero exit) if the harness times out (hang not bounded), the seam tore down all claims, or D8 returned a vacuous pass.

### 4.2 Outline-renders-full + provably-generator-routed check (Fix B + Fix D)

- **New harness `test_storm_outline_renders_full.py`:** run `_generate_outline_from_conversations` with a banked multi-perspective conversation fixture against the configured generator (glm-5.2 AND deepseek-v4-pro), with the raised `PG_STORM_OUTLINE_MAX_TOKENS=64000`, the resolver + provider pin in play, AND a gate `set_role_providers({"generator": <resolved-singleton>, ...})` active so the role-context path is exercised.
  - ASSERT returns the **real LLM outline** (8-15 thematic clusters), NOT `_fallback_outline` (detect the fallback's one-section-per-perspective shape / disclosed marker).
  - ASSERT the outline JSON is **complete / parseable** (not truncated mid-structure → the starvation symptom).
  - **ROUTABILITY assertion (Fix D, the verdict's "assert in §4.2"):** assert the outline call's RESOLVED provider == the gate's `role_provider_map["generator"]` singleton (the GLM-5.2 served provider), NOT the deepseek `role_provider_routing("generator")` chain. Concretely: capture the outgoing request `provider.order` (or the served `provider_name` via the path-B sink) under an active `llm_role("generator")` and assert it equals the generator singleton. ALSO assert that WITHOUT the `llm_role("generator")` tag (the pre-fix behavior) the resolved provider is the deepseek chain — i.e. the harness FAILS on the un-tagged baseline and PASSES on the tagged fix (proves the tag is load-bearing).
  - **PROVIDER-CAP assertion (advisor blind-spot guard — an offline stub `/models` table would NOT catch a DeepInfra 404):** assert the body's **post-clamp `max_tokens` <= the served provider's REAL completion cap**. For the deepseek arm specifically, assert the resolved provider is NOT DeepInfra (the pin / `ignore` list active). An offline-only harness that sends 64000 against a stub and sees no 404 is INSUFFICIENT.
  - FAIL LOUD (non-zero exit) if the fallback fired, the JSON truncated, the outline did NOT route to the generator singleton, a provider 404 occurred, OR the post-clamp `max_tokens` exceeds the resolved provider's real completion cap.
- Then **replay all banked corpora end-to-end** (`scripts/resume_from_corpus_textmode.sh`, `state/iarch007_corpus_checkpoints.json`) and §-1.1-read the rendered outline: the report sections must reflect the real STORM-clustered outline, not the bland per-perspective fallback.

### 4.3 Final gate

One fresh GATED run that COMPLETES + RENDERS, then a §-1.1 line-by-line read confirming (a) D8 adjudicated cleanly even when a role transport-faulted on some claim (per-claim disclosed UNSUPPORTED, no `released_insufficient_safety_evidence` from a transport crash), (b) the gate's served-identity assertion PASSED — proving the outline routed to the generator singleton (Fix D), and (c) the outline rendered full (real thematic sections, not the fallback). Per `state/iarch_wiring_acceptance_checklist.md`, the part is DONE only when the effect behaviorally fires in the real rendered output.

---

## 5. Files in scope

| File | Change | Faithfulness |
|---|---|---|
| `src/polaris_graph/roles/openai_compatible_transport.py` | wrap POST in `_post_with_total_deadline` + bounded TimeoutError/RuntimeError retry arms + thread-local client (Fix A) | none (client lifecycle + wall-deadline) |
| `src/polaris_graph/roles/role_transport_deadline.py` (NEW) | shared `_post_with_total_deadline` + `_role_transport_total_s` helper, imported by BOTH transports | none (pure) |
| `src/polaris_graph/roles/role_pipeline.py` | (1) extend the Mirror `except` arm at `:330` to catch `RoleTransportError` → set `mirror_failed_closed=True` + append `<mirror_role_unavailable>` disclosure directly to `recording.records` (flag ON) / re-raise (flag OFF) (Fix C.1 — the bool is the ONLY signal compose step-1 reads; an adapter return would not fire it). (2) at the Judge call site `:370` (C.2-merge) and the Sentinel call site `:335` (C.2-merge-sentinel) CONSUME the adapter record-list (was the underscore-discarded `_judge_records`/`_sentinel_records`) and append ONLY the synthetic `<…_role_unavailable>` record (`served_model is None` + marker) into `recording.records` — selective, degrade-only, exactly-once — so the disclosure reaches `ClaimPipelineResult.records` | none (feeds the LOCKED compose its existing `mirror_failed_closed` input; merge is disclosure-record propagation only; can only tighten) |
| `src/polaris_graph/roles/judge_adapter.py` | add `except RoleTransportError` → fail-closed disclosed Judge-unavailable, return UNSUPPORTED (never None) + the `<judge_role_unavailable>` record as the SOLE returned record (the pipeline C.2-merge then propagates it into `recording.records`) per-claim (Fix C.2) | none (per-claim fail-CLOSED, can only tighten) |
| `src/polaris_graph/roles/sweep_integration.py` | flag-OFF / propagated `RoleTransportError` → disclosed `abort_role_transport_exhausted` + halt artifact, not a bare teardown (Fix C.3) | none (disclosure path only) |
| `.env:325` | raise `PG_STORM_OUTLINE_MAX_TOKENS` 16384 → 64000 (Fix B) | none (token budget) |
| `src/polaris_graph/agents/storm_interviews.py` | raise in-code default 32768 → 64000 (Fix B); wrap the outline call in `llm_role("generator")` (Fix D) | none (token budget + provider-routing context) |
| `tests/.../test_d8_role_transport_failclosed.py` (NEW) | §-1.4 hung-Mirror + hung-Judge + hung-Sentinel fail-closed harness | n/a (test) |
| `tests/.../test_storm_outline_renders_full.py` (NEW) | §-1.4 outline-not-truncated/not-fallback + provably-generator-routed harness | n/a (test) |

## 6. Files I have ALSO checked and they're clean (no change needed)

- `openrouter_role_transport.py` — already bounded (`_post_with_total_deadline` at `:1158`, F3 rebuild at `:990-994` + `:1193-1228`); the OpenRouter transport's OWN POST needs NO change. (Its force-close OUTPUT — a `RoleTransportError` — is now consumed per-role by Fix C; the transport itself is correct.)
- `sentinel_adapter.py:426-452` — already has the `RoleTransportError` degrade arm (`PG_SENTINEL_TRANSPORT_DEGRADE`) that BUILDS the correct `<sentinel_role_unavailable>` record and returns it in `[*blank_records, record]`; Fix C generalizes the SAME degrade pattern to Mirror + Judge under a shared `PG_ROLE_TRANSPORT_DEGRADE` (Sentinel flag honored as alias). The adapter's BODY needs no change. **Correction vs iter-3 (the binding iter-4 fix): the Sentinel arm is NOT actually clean end-to-end today — its `<sentinel_role_unavailable>` disclosure record is SILENTLY DROPPED.** The record is returned in the adapter tuple but the call site at `role_pipeline.py:335` binds the list to the underscore-discarded local `_sentinel_records`, and `ClaimPipelineResult.records` comes ONLY from `recording.records` (`:399`), to which `RecordingTransport.complete` (`:158-163`) appends ONLY after a SUCCESSFUL `transport.complete()` (never on the raising `RoleTransportError` path). So the synthetic record never reaches `recording.records` — the SAME discard defect as Judge. The fix lives at the call site (C.2-merge-sentinel in `role_pipeline.py`, table row above), NOT in the adapter; the adapter's degrade logic is the unchanged template.
- `role_pipeline.py` — `RecordingTransport` delegates; no direct network. `_compose_final_verdict` is LOCKED and UNTOUCHED. **Correction vs iter-3:** the iter-3 design's C.1/C.2 closed the per-claim ADJUDICATION (UNSUPPORTED on a faulted role) but NOT the DISCLOSURE PROPAGATION — the synthetic `<judge_role_unavailable>` / `<sentinel_role_unavailable>` records built in the adapter return-tuples were discarded at `:370` / `:335` (`_judge_records` / `_sentinel_records` are underscore-bound and never merged; `ClaimPipelineResult.records` is sourced ONLY from `recording.records`). So Fix C DOES make small, surgical `run_claim_pipeline` changes: (a) the Mirror `except` arm at `:330` catches `RoleTransportError`, sets `mirror_failed_closed`, and appends `<mirror_role_unavailable>` DIRECTLY to `recording.records` (the bool is the ONLY signal compose step-1 reads; a returned adapter tuple would NOT fire it and Sentinel+Judge would still run on a hung socket — see §3.3 mechanism); (b) the Judge call site `:370` (C.2-merge) and Sentinel call site `:335` (C.2-merge-sentinel) CONSUME the adapter record-list and append ONLY the synthetic marked `<…_role_unavailable>` record (`served_model is None` + marker — selective, exactly-once) into `recording.records`. These are the minimal changes that achieve BOTH the per-claim fail-closed AND the disclosed-degrade the verdict demands; they feed the LOCKED compose its existing inputs unchanged and change no composition logic. Judge (C.2) and Sentinel (existing) keep their fail-closed VERDICT/result construction in their adapters because those flow through compose without the bool; only the DISCLOSURE record is propagated at the pipeline.
- `pathB_capture.py` — provides `llm_role` / `current_role_provider` / `set_role_providers`; consumed as-is by Fix D. Imports nothing from agents/generator → no cycle.
- `pathB_runner.py` / `pathB_run_gate.py` — the gate's single-valued served-identity assertion (`:782-785`) is what PROVES Fix D's routability; surrogate fields are `("provider_name","model")` (`pathB_runner.py:105`); NO call-count assertion, completeness is "every pinned role appears ≥ once" (`:704-706`) — an extra generator-tagged call is tolerated. No change.
- `token_limit_resolver.py` — provides the clamp that makes the GLM-5.2 arm safe (apply_completion_cap=True); no change. (The clamp does NOT protect the deepseek arm — that arm is safe via the provider pin, §2.3.)
- `openrouter_client.py:1898-1957` — already applies the resolver clamp AND the Path-B / generator provider pin on the generate_structured path; the outline raise + the `llm_role("generator")` tag ride BOTH. The `_REASONING_FIRST_MODELS` glm-5.2 floor-gap is a SEPARATE model-governance item (flagged for the lock owner), not this fix.
- `config/settings/openrouter_provider_routing.yaml:7-22` — the generator chain that EXCLUDES DeepInfra (the deepseek-arm 404 guard); consumed as-is.
- `run_honest_sweep_r3.py:5260-5324` — the STORM invocation block: the isolated `copy_context()` snapshot (`:5292`) carries `_ROLE_PROVIDER` + the capture `_SINK` (both set in the active gate scope), so Fix D's `llm_role("generator")` resolves correctly inside it. The cost-envelope isolation (`:5267-5288`) is orthogonal — it discards STORM's SPEND from the parent, not the routing/capture contextvars. No change here (the tag lives at the outline call site, §3.4).
- `provenance_generator.py` (`PG_PARALLEL_VERIFY`) — different verify path / different knob; D8 throughput is out of scope.

## 7. Out of scope (explicit)

- D8 throughput / serial-vs-parallel (`PG_PARALLEL_VERIFY` engaging on D8, FIX-C 41b74341) — separate performance concern, not reliability.
- The faithfulness engine (strict_verify / NLI / 4-role verdict / coverage / release_policy) — never touched.
- Adding glm-5.2 to `_REASONING_FIRST_MODELS` — broader model-governance decision for the lock owner.
- The STORM **interview** Q&A calls (`reasoning_enabled=False`, `storm_interviews.py:557,804,902`) routing — a SEPARATE latent concern; Fix D scopes the `llm_role("generator")` tag to JUST the outline call (the verdict's P1-B target), not `run_storm_interviews` wholesale, so STORM's auxiliary calls stay untagged/excluded from the gate capture exactly as today. Flag for the lock owner.
- A generic GLM-5.2 generator chain in `openrouter_provider_routing.yaml` (would close the gate-OFF routing gap for Fix D) — model-governance addition, not this reliability fix; the campaign always runs gated.
