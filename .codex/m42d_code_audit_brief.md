You are auditing M-42d — fourth of 4 items in the M-42 bundle.
Scope: Health Canada retrieval expansion + T3 selector HC quota
from 1 to 2 with FDA/EMA/NICE preservation guard.

## Plan reference

`outputs/audits/v25/fix_plan.md` M-42d, approved pass-1 with Codex
preservation guard requirement. Two coordinated changes:
1. Config: expand HC regulatory_anchors (DHPP/HPFB path)
2. Selector: HC quota 1→2 via PG_M41D_HC_QUOTA (default 2);
   preservation guard keeps FDA/EMA/NICE 1st-slot reservations
   untouched

## Diff

Commit `86c0ef4` (this HEAD). Three files:

1. `config/scope_templates/clinical.yaml`:
   - Added `hpfb-dgpsa.ca` to regulatory_anchors (DHPP root)
   - Existing HC anchors unchanged (hres.ca, pdf.hres.ca, canada.ca,
     recalls-rappels.canada.ca, health-products.canada.ca)

2. `src/polaris_graph/retrieval/evidence_selector.py`:
   - `import os` added
   - `hpfb-dgpsa.ca` added to `_M41D_JURISDICTION_HOSTS` HC tuple
   - New: `_M42D_HC_QUOTA_DEFAULT = 2`
   - New: `_M42D_HC_JURISDICTION_CODE = "HC"`
   - New: `_m42d_hc_quota()` reads `PG_M41D_HC_QUOTA` env (clamps
     below-1 to 1; invalid falls back to default)
   - T3 block additions (after existing 1-per-juris first pass):
     * HC expansion loop: up to `(hc_quota - 1)` extra HC rows
       reserved from remaining slots, iterating `juris_groups["HC"]`
       (already in by-score order).
     * Expansion ONLY fires if HC present AND slots_left > 0,
       guaranteeing FDA/EMA/NICE 1st slots are safe.
     * `m42d_hc_extras` counter tracks extras actually added.
     * Telemetry note `m42d_hc_quota_expand hc_pool=N reserved=M
       extras_added=K quota=Q` collected in `_m42d_pending_notes`,
       flushed after the tier loop.

3. `tests/polaris_graph/test_m42d_hc_quota_expansion.py`:
   16 tests — quota helper (4), HC host suffix match including
   hpfb-dgpsa.ca (3), expansion behavior (5: fires at >=2 HC,
   stays at pool when <2, guard protects FDA/EMA/NICE, expansion
   works when quota permits, env=1 disables), telemetry emitted /
   suppressed (2), YAML anchors preserved / new anchor loads (2).

## What to verify

1. **Preservation guard**: confirm that when quota is tight AND
   all 4 major juris present (FDA/EMA/NICE/HC) AND pool has HC
   >= 2, the HC 2nd slot does NOT displace any other juris's 1st
   slot. The implementation achieves this by running the HC
   expansion AFTER the 1-per-juris pass and only when slots_left
   > 0. Code review: is there any path where HC could take a slot
   before another juris's 1st? (I believe no — 1-per-juris runs
   first with slots_left decrement, then HC extras.)

2. **Env knob semantics**: `PG_M41D_HC_QUOTA=1` should behave
   exactly like pre-M-42d (no expansion, telemetry suppressed).
   Test `test_env_disables_expansion` verifies telemetry absence
   but the assertion on HC count is loose because fill-by-
   relevance can still pick up HC rows naturally. Is that
   acceptable?

3. **Non-HC jurisdictions**: M-42d only expands HC. Should TGA,
   PMDA, WHO, NMPA also get N-slot options? (The plan says no —
   HC is the specific V25 gap. Other juris keep 1 slot.) Is
   HC-only expansion the right scope for this fix, or should the
   knob be generalized? (Plan approved HC-only.)

4. **hpfb-dgpsa.ca host-suffix**: is the host tuple addition
   correct? Subdomain `dhpp.hpfb-dgpsa.ca` → `.hpfb-dgpsa.ca`
   suffix match via the existing `_row_jurisdiction()` logic.
   Pre-M-42d would have returned None for this host (not in the
   list). Backwards-compat: existing HC URLs (hres.ca, canada.ca,
   etc.) still match.

5. **Telemetry accuracy**: the `reserved` field in the telemetry
   note equals `min(hc_quota, len(hc_rows_in_juris_group))`. Is
   this the right meaning? Alternative: `reserved = 1 +
   extras_added` (actual slots taken). The plan says "track how
   many slots were reserved"; my interpretation is "how many HC
   rows the floor logic attempted to reserve, bounded by pool +
   quota". If the right semantic is "slots actually taken by the
   HC reservation", the computation should be `1 + extras_added`
   when HC was present in the first pass, or just `extras_added`
   if HC was absent there (impossible since `_M42D_HC_JURISDICTION_CODE
   in juris_groups` gate). So `1 + extras_added` is cleaner. Is
   my current `min(hc_quota, pool)` acceptable or should I
   switch?

6. **Edge case — small T3 quota**: if T3 quota is 3 and there
   are 4 jurisdictions present, the 1-per-juris pass only fills
   3 jurisdictions (1st come first serve). HC might not even get
   its 1st slot. In that scenario, the HC expansion is a no-op
   (slots_left=0). Correct behavior? (Yes — preservation is
   guaranteed because expansion only runs when slots_left > 0.)

7. **Pool edge case — 1 HC row only**: `hc_quota=2` but
   `hc_rows` has 1 entry. The expansion loop iterates once, sees
   the already-reserved 1 HC (id in reserved_ids), skips, exits
   with `extras_added=0`. Telemetry suppressed. Correct.

## What counts as a blocker vs medium

- **BLOCKER**: preservation guard has a hole (FDA/EMA/NICE 1st
  slot can be displaced); HC expansion over-allocates (extras >
  quota-1); env knob misparses; hpfb-dgpsa.ca breaks other
  jurisdictions' host matching; telemetry claim fabrication
  (reports extras_added > 0 when actually 0).
- **MEDIUM**: telemetry semantic (reserved field meaning),
  test coverage gaps, HC-only vs generalized knob.
- **LOW**: comments, naming.

## Deliverable

Write `outputs/codex_findings/m42d_code_audit/findings.md` with
final verdict (READY | BLOCKED | CONDITIONAL). Under 1000 words.
