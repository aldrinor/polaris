M-42d pass-2 audit — closes Codex pass-1 CONDITIONAL findings.

## Pass-1 (commit 86c0ef4) verdict

CONDITIONAL. No blocker. 1 MEDIUM + 1 LOW:
- MEDIUM: telemetry `reserved=` can overstate actual HC reservation
  when `PG_M41D_HC_QUOTA` raised above available T3 slots. Recommended:
  `reserved = 1 + m42d_hc_extras`.
- LOW: `test_hc_expands_to_2_when_pool_has_3_hc` used max_rows=7 with
  7-row pool — selector takes pool_size<=max_rows short-circuit before
  T3 block executes.

## Pass-2 changes (commit 98cf5ce)

1. `src/polaris_graph/retrieval/evidence_selector.py`: M-42d telemetry
   block now computes `m42d_hc_reserved = 1 + m42d_hc_extras` (actual
   slots taken) instead of `min(hc_quota, pool_size)` (desired target
   bounded by pool). Telemetry note semantic: "reserved" = slots the
   M-42d floor logic took, including the 1-per-juris first pass's HC
   slot and every confirmed extra.

2. `tests/polaris_graph/test_m42d_hc_quota_expansion.py`:
   - `test_hc_expands_to_2_when_pool_has_3_hc`: max_rows reduced from
     7 to 5 so the T3 block executes. Pool=7, quota=5 forces drops.
     Reservations: 1 HC + 1 FDA + 1 EMA + 1 HC expansion + 1 fill
     = 5. HC reaches 2 through the floor, not through short-circuit.
   - `test_telemetry_emitted_when_expansion_fires`: adds
     `assert "reserved=2" in note` to validate the new semantic.

## What to verify

1. Is the `1 + m42d_hc_extras` semantic the cleanest expression of
   "slots actually reserved by the M-42d floor"? It assumes the HC
   entry was in the 1-per-juris first pass (gated by
   `_M42D_HC_JURISDICTION_CODE in juris_groups`). If HC weren't
   present in the first pass — impossible under this gate — the
   telemetry would undercount by 1. Is the gate sufficient?

2. Does `test_hc_expands_to_2_when_pool_has_3_hc` now exercise the
   T3 block? max_rows=5 < pool=7 means short-circuit doesn't fire.
   Trace: reservations run → HC=1 reserved + FDA=1 + EMA=1 + HC
   expansion=1 extra (HC reaches 2) + fill=1 (takes next top-scored)
   = 5. HC ends at 2.

3. All 16 M-42d tests pass. All 121 M-41/M-42 tests pass. All 8
   V26-gated preservation tests correctly skip.

## Deliverable

Write `outputs/codex_findings/m42d_code_audit_pass2/findings.md`
with verdict (READY | CONDITIONAL | BLOCKED). Under 500 words.
