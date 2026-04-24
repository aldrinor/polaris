You are auditing M-42e — T1 named-trial-primary selector floor.
First of 4 M-42 bundle sub-fixes; narrow scope.

## Context

M-42 plan Codex-approved pass-3 at
`outputs/audits/v25/codex_plan_review_pass3.md`. M-42e is the
first item in the Codex-recommended implementation order.

**V25 gap addressed**: SURPASS-2 NEJM was the only named-trial
primary cited in V25 biblio; SURPASS-1 Rosenstock, SURPASS-3
Ludvik, SURMOUNT-1 Jastreboff were in the corpus (M-35 anchors
surfaced them) but lost within-T1 competition on relevance.

## Diff

Commit at HEAD. Three files:

- `src/polaris_graph/retrieval/evidence_selector.py`:
  - `_m42e_detect_primary_for_anchor(row, anchor)` — returns True
    iff anchor appears in title AND url matches a primary-pub
    DOI prefix OR primary-pub host.
  - `select_evidence_for_generation` accepts new kwarg
    `primary_trial_anchors: list[str] | None = None`.
  - T1 tier pick loop: if anchors provided, reserves up to 6
    T1 slots for anchor-matched primaries before filling by
    relevance. Cap enforced via `_M42E_PRIMARY_FLOOR_CAP = 6`.

- `src/polaris_graph/retrieval/primary_trial_expander.py`:
  - New public `get_primary_trial_anchors_for_slug(template, slug)`
    returning raw anchor list (thin wrapper over existing
    private `_extract_anchors`).

- `scripts/run_honest_sweep_r3.py`:
  - Import + call `get_primary_trial_anchors_for_slug` after
    template load, pass `primary_trial_anchors=_primary_anchors`
    into the selector.

- `tests/polaris_graph/test_m42e_primary_trial_floor.py`: 12 tests.

## What to verify

1. **Primary detection precision**: does the DOI-prefix + host
   pair reliably identify named-trial primaries? Known good:
   NEJM `10.1056/NEJMoa*`, Lancet `10.1016/S0140-6736`, JAMA
   `10.1001/jama`. Known risk: a post-hoc published in NEJM
   (rare) would match; the test
   `test_post_hoc_on_primary_host_does_not_match_primary` asserts
   this does NOT happen when the host is not a primary-pub host
   (springer.com case).

2. **Cap enforcement**: `_M42E_PRIMARY_FLOOR_CAP = 6` protects
   T2 quota. When 8 primaries exist in the pool, at most 6 are
   reserved via the floor. Remaining 2 may still be selected on
   relevance (within the rest of T1 quota). Is this the right
   trade-off?

3. **T1-quota interaction**: the floor operates WITHIN T1 quota.
   If T1 quota is 5 and 6 primaries exist, reservations cap at 5
   (the T1 quota) — all 5 go to primaries; no leftover T1 slots
   for reviews. Is this acceptable or does it over-displace T1
   review content?

4. **Zero-anchor backwards compatibility**:
   `primary_trial_anchors=None` or `[]` → selector behavior
   identical to pre-M-42e. Test asserts.

5. **Order-sensitivity**: `for anchor in primary_trial_anchors`
   iterates in list order. If the YAML anchor list is
   [SURPASS-1, SURPASS-2, ..., SURMOUNT-4] (11 entries) and
   only 6 primaries match, the first 6 by list order win the
   reservations, not the first 6 by relevance. Is this the
   desired behavior? (I think yes — YAML order is the operator's
   explicit priority declaration; relevance-within-anchor picks
   the top-scoring match for each anchor.)

6. **Sweep wiring**: the sweep script is wired unconditionally
   even when anchors are empty (backwards-compat case). Any
   overhead?

## What counts as a blocker vs medium

- **BLOCKER**: any path where the floor displaces T2 meta-analysis
  below V25 baseline; any path where a non-primary is wrongly
  classified as primary (e.g., a post-hoc on NEJM host); broken
  sweep-script wiring.
- **MEDIUM**: tightening DOI-prefix list, adding more primary-
  pub hosts, adding telemetry to `EvidenceSelection.notes` when
  the floor fires.
- **LOW**: naming / comments.

## Deliverable

Write `outputs/codex_findings/m42e_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums

Keep under 1000 words.
