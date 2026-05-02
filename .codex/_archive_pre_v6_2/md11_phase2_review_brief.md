M-D11 phase 2 review (commit 1ba9144).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase D M-D11 phase 2 (pin replay execution). Empirical test
of M-D11 phase 1's locked v4 schema (commit 6c2f17f, 5-round
asymptote-stop). Substrate already locked: model_pin v4 schema
+ env_snapshot None/"" semantics + 46 replay-critical env
vars. Per advisor: tight scope (env-only), threat-model doc
shipped with v1, 2-round target.

## Files

`src/polaris_graph/audit_ir/pin_replay.py`:
  - EnvMutation (set/delete + value)
  - ReplayPlan (pure description; pin + tuple of mutations)
  - build_replay_plan(pin) -> ReplayPlan: derives mutations
    from pin.env_snapshot honoring v4 None/"" distinction
  - apply_replay_plan(plan): @contextmanager, REVERSIBLE.
    Captures prior os.environ, applies mutations, restores
    on __exit__ (success + exception)
  - verify_replay(pin) -> tuple[ReplayMismatch, ...]:
    fresh-captures env, builds fresh pin reusing source
    pin's non-env fields, calls
    pins_equivalent_for_replay
  - replay_pin(pin, *, require_prompt_text, prompt_text):
    validation wrapper. Raises MissingPromptTextError if
    require=True and any role's prompt text missing/whitespace

`docs/md11_phase2_threat_model.md`: 5 boundaries documented
upfront:
  1. Single-threaded only (os.environ stomp empirical demo)
  2. Prompt-hash verification-only, not restoration
  3. Model swap env-level only (clients may have cached)
  4. validation_set_hash verify-only, no restore
  5. No LLM client imports (substrate primitive)

## Your job

GREEN / PARTIAL / DISAGREE.

1. **Reversibility correctness**: apply_replay_plan captures
   prior state for every var the plan touches, restores in
   finally. On exception inside the `with` block, env is
   restored. Any race condition or restore gap?

2. **None/"" fidelity through round-trip**: build_replay_plan
   emits delete for None and set("") for empty string. After
   apply_replay_plan, verify_replay should see equivalent
   pins. Edge case I missed?

3. **Empirical verification scope**: verify_replay reuses
   source pin's non-env fields when building the fresh pin
   (because phase 2 v1 doesn't restore them — boundaries
   2-4). Does this make the verify too loose? E.g. operator
   could pass a pin whose llm_models doesn't match runtime
   reality and the verify would still pass.

4. **MissingPromptTextError contract**: prompt hashes are
   verification-only. require_prompt_text=True forces
   operator to supply text for every captured prompt role.
   Whitespace counts as missing. Right contract?

5. **Boundary 1 (single-threaded)**: documented + tested
   demo of the stomp. Should phase 2 v1 add a process-wide
   lock (filesystem flock, or threading.Lock at module
   level) to make concurrent replays a hard error rather
   than silent stomp?

6. **Boundary 3 (client caching)**: documented but not
   enforced. Should replay attempt to detect already-imported
   LLM clients and warn?

7. **No LLM coupling boundary 5**: confirm pin_replay.py
   imports only stdlib + model_pin.

## Output

`outputs/codex_findings/md11_phase2_review/findings.md`:

```markdown
# Codex review of M-D11 phase 2 v1 (commit 1ba9144)

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [reversibility concern, if any]
- [None/"" fidelity concern, if any]
- [verify scope concern, if any]
- [prompt-text contract concern, if any]
- [boundary 1 enforcement concern, if any]
- [boundary 3 enforcement concern, if any]
- [import-surface concern, if any]

## Final word
GREEN to lock M-D11 phase 2 / PARTIAL with edits.
```

Be terse. Under 60 lines.
