## Codex review brief — I-bug-946 (GH#932) Path-B gate per-role provider — iter 2

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (bound)

```yaml
verdict: APPROVE | REQUEST_CHANGES
choice: A | B | C | other
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Iter 1 verdict (REQUEST_CHANGES — choice=C)

Codex caught two real P1 blockers in my iter-1 plan:

- **P1#1**: C must control real request routing, not just preflight pins. `openrouter_client.py:1400-1410` still reads the global candidate env order on every call; Path-B calls must SEND a singleton resolved per-role provider in the request body.
- **P1#2**: My brief incorrectly said `entailment_judge.py` wraps `OpenRouterClient`. It posts directly at `entailment_judge.py:162-175` with NO `provider` block. That evaluator-family path must also receive the resolved provider, otherwise C is nondeterministic and post-run can fail.

Plus 4 P2 implementation items (all addressed below).

## Revised plan (iter 2)

C remains the architectural choice. The mechanism is now end-to-end:

### Step 1 — Endpoint resolver (preflight)

`scripts/dr_benchmark/pathB_run_gate.py` adds:

```python
def resolve_role_provider(model_slug: str, provider_order: list[str]) -> str:
    """Resolve a role's served provider via GET /api/v1/models/<id>/endpoints.

    Parses `data.endpoints` (real shape, verified against OpenRouter docs).
    Eligible providers: status == 0 OR status field absent. Status != 0 means
    degraded/lower-priority/fallback-only per OpenRouter for-providers docs;
    skipped from the intersection.

    Intersects eligible providers (case-insensitive) with provider_order.
    Returns the catalog-cased provider_name of the FIRST match in
    provider_order. Raises GateError with diagnostic if no match.

    Fails closed if endpoints list is empty (model offline/unsupported).
    """
```

Fail-closed diagnostic carries: role, model_slug, env-provider-order, available endpoint list.

### Step 2 — Per-role pin population (preflight)

`scripts/dr_benchmark/pathB_run_gate.py:preflight()`:

- Drop the strict singleton check at `:194-196` (currently rejects multi-provider order). Replace with: `provider_order must be non-empty AND each role's resolved provider must exist`.
- For each `RolePin`, call `resolve_role_provider(rp.model_slug, provider_order)`; populate `rp.provider_name` with the catalog-cased result. Preserves catalog spelling per P2#3.
- Pin record in `pathB_gate_pin.json` records per-role `provider_name` — the audit anchor remains exact.

### Step 3 — Gate-scoped contextvar for per-role routing

New module-level in `scripts/dr_benchmark/pathB_run_gate.py` (or a small companion):

```python
import contextvars
_active_role_provider: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "pathB_role_provider", default=None,
)

def set_role_providers(role_to_provider: dict[str, str]) -> contextvars.Token:
    return _active_role_provider.set(role_to_provider)

def get_role_provider(role: str) -> str | None:
    mapping = _active_role_provider.get()
    return None if mapping is None else mapping.get(role)
```

`gate_around_question()` in `src/polaris_graph/benchmark/pathB_runner.py` sets this contextvar with the resolved per-role mapping after preflight, resets it on exit.

Async-safe per P2#1 (contextvars propagate correctly across `async`/`await` and `asyncio.create_task`).

### Step 4 — Route the request (openrouter_client + entailment_judge)

**`src/polaris_graph/llm/openrouter_client.py`**:
- Inside the call site that builds `provider_block` (currently `:1400`), check `get_role_provider(role)` where `role` is determined from the caller's role context. If override present, force `provider_block["order"] = [<resolved>]` (singleton list), preserving `allow_fallbacks=False`.
- Threading caller role: the openrouter_client is instantiated for the generator role. Either (a) the client gains a `role` parameter at construction (current single-instance-per-role pattern supports this), or (b) we wrap the contextvar lookup in a helper that takes role as arg.

**`src/polaris_graph/llm/entailment_judge.py`**:
- The direct httpx post at `:162-175` gains a `provider` block in the JSON body:
  ```python
  json_body = {"model": self._model, "messages": [...], ...}
  resolved = get_role_provider("evaluator")
  if resolved:
      json_body["provider"] = {
          "order": [resolved],
          "allow_fallbacks": False,
          "require_parameters": True,
      }
  ```
- This makes the evaluator family go through the same resolved-singleton routing as the generator.

### Step 5 — Tests

`tests/dr_benchmark/test_pathB_run_gate.py`:

1. `test_resolve_role_provider_returns_first_in_order_match` — endpoint list mocked; provider_order=`["fireworks","novita"]`; gemma endpoints=`[novita, deepinfra]` → returns "Novita" (catalog spelling).
2. `test_resolve_role_provider_fails_closed_on_no_intersection` — order=`["fireworks"]`, gemma endpoints lack fireworks → GateError with diagnostic listing available.
3. `test_resolve_role_provider_skips_degraded_endpoints` — provider with `status=-5` excluded; another with `status=0` selected.
4. `test_resolve_role_provider_fails_closed_on_empty_endpoints` — empty endpoints list → GateError.
5. `test_resolve_role_provider_case_insensitive_with_catalog_spelling` — `order=["Fireworks","novita"]`; endpoints have `Novita` (title) → returns "Novita" preserving catalog case.
6. `test_preflight_pins_per_role_from_resolution` — mock resolver; pin has per-role provider_name populated from endpoint resolution.
7. `test_preflight_accepts_multi_provider_order_when_disjoint_roles` — order=`fireworks,novita`; generator pins fireworks, evaluator pins novita.
8. `test_contextvar_propagates_role_provider` — set + get + reset semantics.

`tests/polaris_graph/test_entailment_judge_pathB_routing.py` (NEW):
- Mock httpx client; assert the posted JSON body has `provider.order=["Novita"]` when contextvar is set to `{"evaluator": "Novita"}`.

## Adjacent files I have ALSO checked and they're clean

- `scripts/dr_benchmark/score_run.py:51` — consumes pin's provider_name; per-role resolution is additive.
- `scripts/dr_benchmark/aggregate_systems.py:149,153` — final-report rendering; additive.
- `src/polaris_graph/benchmark/pathB_capture.py` — captures served metadata; no compare.
- `src/polaris_graph/benchmark/pathB_runner.py:_role_pins()` — _role_pins's `provider_name` field becomes "" pre-preflight; preflight fills it.

## P2 items from iter 1 — addressed

- **P2#1 async-safe**: contextvar (not process env), per Step 3 above.
- **P2#2 endpoint shape + empty**: resolver parses `data.endpoints`; raises GateError on empty list.
- **P2#3 case-insensitive + catalog spelling**: lower-case for intersection, return catalog-cased provider_name in pin (preserved through assert_post_run via existing I-bug-944 `.lower()` compare).
- **P2#4 endpoint status**: eligible only when `status` absent or `0`; degraded providers (status != 0 e.g. `-5`, `-2`) skipped. Diagnostic when no eligible match.

## Required from Codex (iter 2)

1. APPROVE/REQUEST_CHANGES on the revised plan.
2. Confirm gate-scoped contextvar is the right mechanism (vs constructor-time `role` plumbing into the OpenRouterClient instance — sister project precedent?).
3. Any edge case in `entailment_judge.py:162-175` routing that the revised plan misses (e.g., other direct-httpx call sites in the evaluator path that also bypass OpenRouterClient).

Question: APPROVE choice=C with this revised plan?
