M-D3 phase 1 v2 review (commit 212102d).

**Tool hints**: use `python -m pytest -q tests\polaris_graph\test_md3_decision_telemetry.py`.
Skip `outputs/codex_*` and `.codex_tmp/` in `rg`.

## Context

Round 1 (commit f0269a8): PARTIAL with 2 MED:
  1. Cross-action invariants documented/tested piecemeal rather
     than enforced centrally
  2. Workspace isolation appears to rely on caller/path discipline
     rather than a hard guard

v2 closes both.

## What changed in v2

`src/polaris_graph/audit_ir/decision_telemetry.py`:

1. New `_validate_terminal_args(curator_action, actor_user_id,
   final_payload, diff_payload)` private helper. Called from
   `update_curator_action` at the top before any DB mutation.
   All cross-action invariants live there in a single block.

2. `get(record_id, *, workspace_id)` — workspace_id required;
   query filters on `(record_id, workspace_id)`.

3. `update_curator_action(record_id, *, workspace_id, ...)` —
   workspace_id required; SELECT and UPDATE both filter on
   `(record_id, workspace_id)`. Wrong workspace surfaces as
   "not found" — original PENDING row stays untouched.

4. Matches M-D7 `RetrievalCacheStore.get(workspace_id, source_url)`
   pattern.

`tests/polaris_graph/test_md3_decision_telemetry.py` (42 tests, +5):
  - test_get_with_wrong_workspace_returns_none
  - test_get_with_empty_workspace_raises
  - test_update_with_wrong_workspace_raises (also checks original
    PENDING row stays untouched)
  - test_update_with_empty_workspace_raises
  - test_validate_terminal_args_helper_centralization (4 happy
    + 9 invariant-violation cases through the helper directly)

`docs/md3_phase1_threat_model.md`:
  - Boundary 4 expanded: API-level workspace_id enforcement
  - NEW boundary 5: cross-action invariant centralization
  - 8 boundaries total (was 7).

## Your job

GREEN-LOCK or PARTIAL.

1. **Round-1 fix integration**:
   - [ ] cross-action invariants centralized in
     `_validate_terminal_args`; called BEFORE DB mutation
   - [ ] get() filters on (record_id, workspace_id)
   - [ ] update_curator_action() SELECT and UPDATE both filter
     on (record_id, workspace_id); wrong-workspace = "not found"
   - [ ] threat-model boundaries 4 + 5 match code

2. **Stop criterion**: GREEN-lock if remaining findings are
   doc nits or follow-ups. PARTIAL only if you find:
     (a) The helper is bypassable (e.g. another method
         mutates terminal state without calling it)
     (b) Workspace isolation is still leaky somewhere
         (e.g. count_for_workspace, list_for_workspace)
     (c) New regression introduced

3. **Phase-2 readiness**: same as round 1.

## Output

`outputs/codex_findings/md3_v2_review/findings.md`:

```markdown
# Codex round 2 — M-D3 phase 1 v2 (commit 212102d)

## Verdict
GREEN / PARTIAL

## Round-1 fix integration
- [x/no] cross-action invariants centralized
- [x/no] get() filters on workspace_id
- [x/no] update_curator_action filters on workspace_id
- [x/no] threat-model boundaries 4 + 5 match code

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D3 phase 1.
```

Be terse. Under 30 lines.
