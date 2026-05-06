M-D3 phase 1 v1 review (commit f0269a8).

**Skip git status.** Codex at gpt-5.4 + xhigh.

**Tool hints (per M-D5 lessons)**: Use `python -m pytest -q
tests\polaris_graph\test_md3_decision_telemetry.py`. If `rg`
hits permission errors on `outputs/codex_*` or `.codex_tmp/`,
skip those dirs — they have stale-fixture entries.

## Context

M-D3: induction + scope-gate decision telemetry substrate. Phase
1 records data only; M-D4 (calendar-blocked ≥6mo) consumes it
for the auto-trust gate.

7 phase D milestones already GREEN-LOCKED (M-D2 phase a/b, M-D5
phase 1, M-D7 phase 1, M-D9 phase 1, M-D10 phase 1, M-D11 phase
1+2). Convergence pattern: 2-3 rounds when threat-model ships
with v1.

## What v1 ships

`src/polaris_graph/audit_ir/decision_telemetry.py`:
  - DecisionKind enum (induction | scope_gate) — generic
    discriminator per advisor watch-out, lets M-D5 scope-gate
    decisions land in the same store when M-D5 phase 2 ships
  - CuratorAction enum: pending → {accepted_as_proposed |
    modified | overridden | rejected}
  - DecisionRecord dataclass + JSON helper
  - DecisionRecordStore: per-workspace SQLite (per-call WAL
    connections, same M-21 pattern as M-D7 / M-D10)
  - record_decision() — fresh record in PENDING
  - update_curator_action() — single transition to terminal;
    terminal states are terminal (no re-edits)
  - get / list_for_workspace / count_for_workspace
  - SQL CHECK constraints (decision_kind, curator_action,
    proposed_confidence ∈ [0, 1])
  - 3 covering indexes for M-D4 calibration queries

Cross-action invariants:
  - rejected: final + diff must be None (nothing shipped)
  - accepted_as_proposed: final required (= proposed),
    diff must be None
  - modified / overridden: final required, diff expected

`tests/polaris_graph/test_md3_decision_telemetry.py` — 37 tests:
  - record_decision invariants (8: workspace, query, kind,
    confidence ∈ [0,1] both sides, unserializable payload)
  - transition matrix (12: 4 terminal × {happy path,
    invariant violation × 2}, plus pending-as-target,
    no-actor)
  - terminal immutability (3: 2× double-transition, 1×
    nonexistent record)
  - generic discriminator (1: induction + scope_gate coexist)
  - list/count filters (5: kind, action, workspace iso,
    limit, ordering, count)
  - DB-layer CHECK constraints (3: invalid kind/action/
    confidence trip IntegrityError on raw INSERT)
  - coexistence (2: M-21, M-D7 share same DB file)
  - JSON round-trip (2: simple dict, complex nested)

`docs/md3_phase1_threat_model.md` — 7 boundaries:
  1. Phase 1 = telemetry only; M-D4 trust gate deferred
  2. Confidences uncalibrated by design
  3. Generic decision_kind discriminator (future-proofing)
  4. Per-workspace isolation; cross-workspace agg = M-D4
  5. Terminal states are terminal — re-review = new record
  6. JSON schema validation deferred (caller owns schema)
  7. No notification callbacks (M-23/M-D10 cover those)

M-D suite: 328/328 (was 291; +37).

## Your job

GREEN-LOCK or PARTIAL.

1. **Substrate correctness**:
   - [ ] DecisionKind discriminator preserves backward compat
     when adding new kinds (CHECK constraint listing)
   - [ ] terminal-state invariant holds under concurrent
     update_curator_action (BEGIN IMMEDIATE atomicity)
   - [ ] cross-action invariants on final/diff payloads
     enforced at module level (not just at DB layer)
   - [ ] workspace isolation (no cross-workspace leak)

2. **Calibration readiness**:
   - [ ] M-D4 calibration queries (count by kind+action+
     workspace+window) hit indexes
   - [ ] uncalibrated-confidence boundary explicitly documented
     so consumers can't accidentally compare across kinds

3. **Threat-model coherence**:
   - [ ] 7 boundaries match code (no v2-style drift)
   - [ ] tool-hint preamble preempts the M-D5 sandbox cycles

4. **Stop criterion**: GREEN-lock if remaining findings are
   minor (doc nits, additional contract tightening). PARTIAL
   only if you find:
     (a) An invariant that's documentation-only but not
         enforced (matches M-D5 round-2 pattern)
     (b) A schema/data-quality issue that'd corrupt M-D4
     (c) A cross-action invariant that's missing or wrong
     (d) Workspace-isolation hole

5. **Phase-2 readiness**: with v1 substrate, can M-D4 layer
   cleanly? (Calibration computation + auto-trust gate logic.)

## Output

`outputs/codex_findings/md3_review/findings.md`:

```markdown
# Codex round 1 — M-D3 phase 1 v1 (commit f0269a8)

## Verdict
GREEN / PARTIAL / DISAGREE

## Coverage
- [x/no] DecisionKind discriminator forward-compatible
- [x/no] terminal-state invariant atomic
- [x/no] cross-action invariants enforced module-level
- [x/no] workspace isolation
- [x/no] M-D4-readiness (calibration query support)
- [x/no] threat-model 7 boundaries match code

## New findings (if any)
- [HIGH/MED/LOW] [...]

## Final word
GREEN to lock M-D3 phase 1 / PARTIAL with edits.
```

Be terse. Under 50 lines.
