# M-D3 phase 1 — induction + scope-gate decision telemetry

**Status:** v2 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/decision_telemetry.py`
**Tests:** `tests/polaris_graph/test_md3_decision_telemetry.py` (42 passing)
**Pairs with:** M-D2 inductor (induction kind), M-D5 scope gate
(scope_gate kind via discriminator), M-23 review queue (closes
the loop on curator actions)
**Substrate:** stdlib + sqlite3, same per-call WAL connection
pattern as M-21 / M-D7 / M-D10

---

## Scope

M-D3 records every contract-induction decision and every scope-
gate decision the system makes, paired with what the human
curator did with that decision when it ships through M-23
review queue. The data substrate is the **calibration input**
for M-D4 (auto-trust gate), which is calendar-blocked on ≥6
months of M-D3 telemetry.

Phase 1 ships the **substrate only** — record + retrieve. Phase
2 (M-D4 territory) ships the trust-gate logic that consumes the
substrate.

Phase 1 ships:
- `DecisionKind` enum (induction / scope_gate)
- `CuratorAction` enum (pending / accepted_as_proposed / modified
  / overridden / rejected)
- `DecisionRecord` dataclass + JSON helper
- `DecisionRecordStore`: per-workspace SQLite store
  - `record_decision(...)` — fresh record in PENDING
  - `update_curator_action(...)` — transition to terminal action
  - `get(record_id)` / `list_for_workspace(...)` /
    `count_for_workspace(...)`
- SQL CHECK constraints at DB layer for closed-enum integrity
- 3 covering indexes (workspace+kind, workspace+action,
  workspace+created_at)

---

## Phase 1 v1 boundaries

### 1. Phase 1 = telemetry substrate only; M-D4 trust gate deferred

This module records data. It does NOT consume it for live
gating. M-D4 will read from `decision_records` to compute
calibration (acceptance rates per template-class, abstain
recall, etc.) and ship the auto-trust gate logic.

**Mitigation**: anyone tempted to use M-D3 telemetry to gate
live audits before M-D4 ships is misusing the substrate. The
acceptance-rate signal is statistically meaningless under ~6
months of cumulative records (per FINAL_PLAN M-D4 acceptance
criterion).

### 2. Recorded confidences are uncalibrated

`proposed_confidence` is whatever the inductor / classifier
self-reports. M-D2 phase b's LLM-augmented inductor and M-D5
phase 1's classifier protocol both ship UNCALIBRATED
confidence values — that's by design (M-D4 is what calibrates
them). Storing the raw self-reported value is correct because
M-D4 needs the raw stream as input.

**Mitigation**: do NOT compare confidence values across
inductor/classifier kinds. A `proposed_confidence=0.85` from
the keyword-only inductor (M-D2 phase a) means something
different from a `0.85` from the LLM-augmented inductor or
M-D5 phase 1's classifier. M-D4 will calibrate per-kind.

### 3. Generic decision_kind discriminator (advisor watch-out)

`decision_kind: DecisionKind = induction | scope_gate` lets a
single store record both M-D2 inductor decisions and M-D5
scope-gate decisions without forcing an M-D3 phase 2 to add
columns when M-D5 phase 2 ships a concrete classifier.

**Mitigation**: future decision sources (e.g. an M-D14
derivative-eligibility classifier, or an M-D2 phase c
ontology-grounded inductor) will need new enum values; the
DB-level CHECK constraint catches any unrecognized kind at
INSERT time. Adding a new kind is a forward-compatible schema
migration (new value in CHECK list — old data unaffected).

### 4. Per-workspace isolation (enforced at API boundary in v2)

`workspace_id` is the gating field on every read AND every
mutation. v1 relied on FS-level per-workspace DB isolation
(M-21 / M-D7 pattern); v2 (Codex round-1 MED fix) tightens
this further by requiring `workspace_id` on every public method
that touches a record:

- `get(record_id, *, workspace_id)` — query filters on both
  columns. A caller knowing only `record_id` (without
  workspace_id) cannot retrieve a record.
- `update_curator_action(record_id, *, workspace_id, ...)` —
  SELECT and UPDATE both filter on `(record_id, workspace_id)`.
  A workspace mismatch surfaces as "not found" — the row stays
  PENDING and untouched.
- `list_for_workspace` / `count_for_workspace` already required
  workspace_id in v1.

**Mitigation**: M-D4 will need a cross-workspace aggregation
layer, but that's a per-installation concern (ops-side, not
substrate-side). Phase 1 deliberately does not have a global
"telemetry" table — the substrate respects the same isolation
boundary as M-21. v2 adds defense-in-depth so even a caller
with multiple workspaces mounted on one process cannot
accidentally cross workspace boundaries through the public
API.

Tests pin this:
- `test_get_with_wrong_workspace_returns_none`
- `test_update_with_wrong_workspace_raises`
- `test_get_with_empty_workspace_raises`
- `test_update_with_empty_workspace_raises`

### 5. Cross-action invariants centralized in `_validate_terminal_args` (v2)

**Codex round-1 MED fix** (v2): all cross-action invariants on
`update_curator_action` are now enforced in a single private
helper `_validate_terminal_args`, called before any DB
mutation. v1 had the invariants inlined in
`update_curator_action`; v2 extracts them so the contract is
auditable in one place and exercised independently by tests.

Invariants enforced by the helper:

- `curator_action` MUST be a `CuratorAction` enum (not a string)
- `curator_action` MUST NOT be `PENDING` (the function transitions
  out of pending; it cannot transition into pending)
- `actor_user_id` MUST be non-empty for any terminal action
- `REJECTED`: `final_payload` + `diff_payload` MUST both be None
  (nothing shipped, no diff)
- `ACCEPTED_AS_PROPOSED`: `final_payload` required (the curator
  shipped exactly what was proposed); `diff_payload` MUST be None
- `MODIFIED` / `OVERRIDDEN`: `final_payload` required; `diff_payload`
  is optional but expected

`test_validate_terminal_args_helper_centralization` exercises
all 4 happy-path cases and 9 invariant-violation cases directly
through the helper, pinning that the helper IS the central
enforcement site for boundary 5.

### 6. Terminal states are terminal — no transitions

Once `update_curator_action` moves a record to a terminal
state (accepted_as_proposed / modified / overridden /
rejected), further transitions are forbidden. A "re-review"
is a NEW record at a fresh record_id, not a mutation of the
existing one.

**Why**: M-D4 calibration depends on a clean record-per-
decision count. Allowing re-edits would require a separate
audit trail of the edits to preserve calibration accuracy.
Phase 1 prefers the simpler invariant: terminal == terminal.

**Mitigation**: callers needing to record a follow-up review
(e.g. curator initially modified a contract, later realized
the modification was wrong and wants to mark it overridden)
should record a NEW DecisionRecord referencing the same
query, NOT transition the existing record. M-D4 will still
have full visibility — both records will surface.

### 7. JSON payload integrity (no schema validation in v1)

`proposed_payload`, `final_payload`, and `diff_payload` are
JSON-serializable dicts. Phase 1 does NOT validate their
internal structure — it stores whatever JSON-safe blob the
caller provides. The caller is responsible for the schema
contract.

**Why**: phase 1 ships before M-D2 phase a + b have stable
contract schemas (schemas are still evolving as inductor
calibration tightens). Imposing a schema in M-D3 phase 1
would force M-D2 schema work to ship before M-D3, blocking
the calendar.

**Mitigation**: callers MUST round-trip-test their payloads
(test_complex_payload_round_trips covers the JSON shape; per-
kind schema validation is the caller's responsibility). M-D4
may add per-kind schema validation if calibration uncovers
schema drift as a data-quality issue.

### 8. No notification callbacks

Phase 1 is record-only. There are no email / webhook /
in-product notifications when a record is created or
transitioned. M-23 ships its own review-queue notifications
(M-D3 doesn't duplicate them), and M-D10 ships freshness-alert
substrate (M-D3 doesn't duplicate that either).

**Mitigation**: callers needing notification callbacks should
hook into M-23's transition events directly. M-D3 substrate
listens to nobody; it just records.

---

## Empirical calibration contract

The **purpose** M-D3 must serve for M-D4 to ship is:

> Given ≥6 months of M-D3 telemetry for a workspace, the
> ratio `count(accepted_as_proposed) / count(non_pending)` per
> template-class converges within ±2% (statistical
> significance threshold) of the true acceptance rate.

This is the calibration input M-D4 will use. Phase 1 doesn't
prove this ratio; it just records the data with enough fidelity
that M-D4 *can* compute it. Specifically:
- Per-kind discrimination (induction vs scope_gate) so M-D4
  can calibrate inductor confidence and classifier confidence
  separately
- Per-curator-action discrimination so M-D4 can compute
  acceptance + modification + override + rejection rates
- Indexed `created_at` so M-D4 can window-slice (last-30d,
  last-6mo, etc.) without scanning the full table

`test_count_for_workspace` and the index design pin this. The
substrate is M-D4-ready by construction.

---

## Codex review trail

Round-1 brief incoming. v1's tight scope + threat-model-with-v1-
commit pattern (per M-D7/M-D10/M-D11 phase 2 precedent) targeted
at 2-3 round convergence.

Tool hints for Codex sandbox (per M-D5 lessons):
- Use `python -m pytest` not bare `pytest`
- Skip `outputs/codex_*` and `.codex_tmp/` dirs in `rg`
  invocations (they have permission-denied directory entries)

---

## Lock note

Phase 1 v1 GREEN-lock is the target after Codex round 1-2. v2
work (M-23 integration glue, per-kind schema validation if
needed, notification callbacks if needed) tracked separately
under M-D3 phase 2 / M-D4.
