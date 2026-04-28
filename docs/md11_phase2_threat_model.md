# M-D11 phase 2 — pin replay execution boundary

**Status:** v1 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/pin_replay.py`
**Tests:** `tests/polaris_graph/test_md11_phase2_pin_replay.py` (23 passing)
**Pairs with:** M-D11 phase 1 (commit 6c2f17f, schema v4) — empirical verification of the asymptote-stop schema decision
**Substrate:** stdlib + `model_pin` only — no LLM client coupling

---

## Scope

Phase 2 ships **the empirical test of phase 1's locked
schema**. If `verify_replay()` returns no mismatches after
`apply_replay_plan()`, the schema captured everything the
runtime configuration cares about. If it reports drift, the
schema is incomplete (and a v5 bump is needed) or the
replayer is skipping a field (a phase 2 implementation bug).

Phase 2 v1 ships:
- `build_replay_plan(pin) -> ReplayPlan` — pure derivation
- `apply_replay_plan(plan)` — reversible context manager
- `verify_replay(pin) -> tuple[ReplayMismatch, ...]` —
  empirical check after replay
- `replay_pin(pin, *, require_prompt_text, prompt_text)` —
  validation wrapper enforcing the prompt-text contract

Phase 2 v2 (deferred):
- Worker-process isolation for concurrent replays
- Operator-side prompt-text restoration glue
- LLM-client cache invalidation guards
- validation-set content-addressable storage hookup
- M-D9 regression-lab integration: pin a baseline, replay,
  diff outputs

---

## Phase 2 v1 boundaries (NOT FIXED — DELIBERATE)

### 1. Single-threaded only

`os.environ` is process-global. Two concurrent replays of
different pins WILL stomp each other's env state. The
`apply_replay_plan` context manager is reversible *for the
caller's pin* — but if a second pin's apply runs inside the
first's `with` block, the second's prior-state snapshot
captures the first pin's mutations, so the restore on inner
exit lands the env back at the FIRST pin's values, not
pre-replay.

The included test `test_concurrent_replays_stomp_each_other_
documented_boundary` exercises this empirically as
documentation.

**Mitigation**: phase 2 v2 may add a process-pool isolation
pattern (worker subprocess per replay). Until then, callers
must serialize replays.

### 2. Prompt-hash is verification-only, not restoration

`pin.prompt_version_hashes` records SHA-256 hashes of the
captured prompts. Hashes let downstream code *verify* a
current prompt matches, NOT *restore* a prompt. Restoring a
prompt requires the original text, which is not in the pin —
it's expected to be in the operator's audit bundle (M-16) or
a separate prompt registry.

If a caller invokes `replay_pin(pin, require_prompt_text=True,
prompt_text=...)` without supplying text for every role with
a captured hash, replay raises `MissingPromptTextError`
listing the unmatched roles. This fails loudly rather than
papering over the gap.

If a caller invokes `replay_pin(pin)` without
`require_prompt_text`, the returned plan handles env-only
restoration. The downstream pipeline must source the prompt
text itself (typically by passing `system_prompt=...` to the
synthesizer call).

**Mitigation**: phase 2 v2 may add a prompt-registry
integration that resolves hash → text from M-16 audit
bundles.

### 3. Model swap is env-level only

`replay_pin` mutates env vars like `OPENROUTER_DEFAULT_MODEL`,
`OPENROUTER_PROVIDER_ORDER`. Downstream LLM clients may have
read the env at import time and cached the value — replay's
effect is only observable on subsequent process starts or via
client re-instantiation.

Replay does NOT introspect or mutate client internals. This
is a deliberate boundary: M-D11 phase 1's schema captures
runtime *configuration*; restoring runtime *state* (initialized
clients, in-memory caches) is out of scope.

**Mitigation**: operators should re-import the LLM client
module, restart the worker process, or use a fresh subprocess
for replay-driven runs. Phase 2 v2 may add documented client
re-init helpers.

### 4. validation_set_hash is verify-only

The pin records a SHA-256 of the validation-set file. Replay
does NOT restore the file from this hash; that's
content-addressable storage territory. The hash is for drift
detection (run M-D9 regression-lab to compare a fresh hash
against the pinned hash).

**Mitigation**: operators must supply the validation-set file
out-of-band. If the file's hash doesn't match the pin's
`validation_set_hash`, the regression-lab pin-diff (M-D9)
will flag it as RED (validation_set_hash drift = schema-
severity per M-D9 v3 GREEN-locked).

### 5. No LLM client imports

`pin_replay.py` imports only stdlib + `model_pin`. The
OpenRouter / inductor / verifier clients pick up the env on
their next call; pin_replay never touches their internals.

**Why**: M-D11 phase 1 shipped clean by avoiding LLM-internal
coupling. Phase 2 preserves that — replay is a substrate
primitive, not a runtime orchestrator.

---

## Empirical verification contract

After `apply_replay_plan(plan)` returns and the caller is
inside the `with` block:

```python
mismatches = verify_replay(pin)
if mismatches:
    raise ReplayVerificationError(...)
```

`verify_replay` captures a fresh env_snapshot using the same
var names the source pin captured, builds a fresh pin reusing
the source pin's non-env fields (which phase 2 v1 doesn't
restore — see boundaries 2-4), and calls
`pins_equivalent_for_replay()`.

**What this proves**: the env_snapshot round-trips. If
`build_replay_plan` skipped a var or `apply_replay_plan` set
the wrong value, `verify_replay` reports the drifted key.

**What this doesn't prove**: that the LLM call after replay
will use the captured config. That's runtime-state territory
(boundary 3).

---

## Codex review trail

Round-1 brief incoming. Phase 2 v1's tight scope + threat-
model-with-v1-commit pattern (per advisor + M-D7/M-D10
precedent) targeted at 2-round convergence.

---

## Lock note

Phase 2 v1 GREEN-lock is the target after Codex round 1-2.
v2 work (process-pool isolation, prompt registry, M-D9 round-
trip integration) tracked separately under M-D11 phase 2 v2.
