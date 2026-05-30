# D8 — Phase-0a Pilot Allocation (draft for Codex review)

**Deliverable**: Phase 0a.0 / D8 — the gold-set/pilot allocation design.
**Status**: LOCKED (Codex APPROVE 2026-05-27 after 2 rounds; pending operator sign-off).
**Parent**: contract v3.3 §3.2 (Gate A sizing) + §P4.2; depends on D1a, D2, D3, D4, D5, D6, D7', 0a.-1.A, 0a.-1.B, 0a.-1.C, 0a.-1.E.
**Plan**: `PHASE_0a_0_PLAN.md` (D8 blocked randomization + quotas/min-cost matching — Codex plan round-2 answer 6 / round-3).
**Codex review**: `.codex/I-safety-001b/codex_d8_review.txt`.
**Version**: 1 (draft)

**Why this exists**: the gold set must be allocated across the stratification cells so that (a) Gate A's per-stratum n_eff is met (§3.2: n_eff_S1≥539, n_eff_S2≥133, at the binding DEFF), (b) the observed pairwise-relation density P/N reflects the INTENDED construction (not an artifact of lazy batching — Codex plan P1-7 "design-contaminated P/N"), and (c) SMEs/templates are balanced. This deliverable locks the allocation design.

---

## §1. Stratification cells (locked)

The allocation stratifies by the locked axes:
- **domain** (D1a): 6
- **complexity_tier** (D2): C1/C2/C3
- **evidence_pool_bin** (D3): E1/E2/E3/E4
- **severity stratum** (0a.-1.B / 0a.-1.C): S0/S1/S2/SUPPORTED
- **fabrication_type** (0a.-1.B §2): 7 types (for fabricated claims; SUPPORTED has none)

The Gate A sizing (§3.2: n_eff_S1≥539, n_eff_S2≥133, S0 policy-sentinel ≥50 per 0a.-1.A/contract, SUPPORTED filler) sets the per-severity-stratum totals; the raw N inflates by DEFF_binding (§3.2 pairwise formula). The other axes (domain/complexity/evidence/fab-type) are SPREAD within each severity stratum per the quota design (§2), not independently sized.

## §2. Blocked randomization + quotas (Codex plan round-2 answer 6 — NOT full factorial, NOT BIBD)

Full factorial (6×3×4×4×7) is over-large; strict BIBD collapses at ~18 SMEs × many cells (Codex plan round-3). So:

- **Blocked randomization with quotas**: each severity stratum has a target N (from §3.2). Within a stratum, claims are allocated to (domain × complexity × evidence-bin × fab-type) cells by pre-registered QUOTAS, then RANDOMIZED within the quota using the pinned `D8-allocation` child seed (0a.-1.E §3).
- **Quota generator rules (Codex round-1 #2 — not "spreads coverage")**: the quota TABLE is pre-registered with: HARD marginals (per-domain, per-severity totals from §3.2 are hard) vs SOFT marginals (complexity/evidence-bin/fab-type spread is soft, balanced); a fixed rounding rule (largest-remainder to hit the hard total exactly); a minimum-coverage rule (every (domain × severity) cell ≥ a pre-registered floor); SUPPORTED cells are keyed WITHOUT a fab-type axis (SUPPORTED has no fabrication_type — its quota cells are domain × complexity × evidence-bin only); infeasible-cell handling (a cell with no constructible claim is logged + its quota redistributed to adjacent cells per a pre-registered rule); and how D6 template `fabrication_type_mix_target` / `severity_distribution_target` AGGREGATE up into the D8 quota (the D8 quota is the sum of the assigned templates' targets, reconciled to the hard marginals).
- **SME + template balancing (Codex round-1 #6)**: assignment is **hard constraints + soft balance penalties**. HARD (non-negotiable): 0a.-1.A role-disjointness (constructor ≠ adjudicator at blinding_unit level), COI (0a.-1.A §4 / D4 §5.5), the clinical MD/PharmD-in-path rule (0a.-1.A §3). SOFT (yields when needed): load + template balance. A **roster feasibility precheck** runs first: if no assignment satisfies the hard constraints (brittle at ~18 SMEs under COI/tiebreak/clinical constraints), it FAILS CLOSED (halt; the roster must expand or the quota relax) — it never silently violates a hard constraint to balance load.
- **Pinned seed**: all randomization draws from the `D8-allocation` named child stream (0a.-1.E §3 HMAC-derived). Reproducible.

## §3. Two-stage P/N validation + deterministic resample (Codex round-1 #1/#3/#4 — anti-design-contamination, build-order-correct)

**Build-order fix (Codex round-1 #1)**: the relation-builder needs real `construction_manifest` + `source_packet_manifest` fields (cited sources, packet_class, prompt families, microtopics, constructor, window) that DO NOT EXIST before structural construction. So the P/N check is TWO-STAGE custody (not "before construction begins"):

- **Stage 1 — plan (pre-construction)**: hash-pin the allocation PLAN (quota table + assignments + seed/draw index) before construction. No relation-builder run yet (the inputs don't exist).
- **Stage 2 — P/N validation (post-structural-construction, PRE-outcome)**: AFTER the structural manifests are populated + D6/admissibility/D4/D5 validators pass, but BEFORE any adjudicator/verifier OUTCOME exposure, RUN the APPROVE'd relation-builder (0a.-1.C) on the real construction + packet manifests to compute per-stratum P, N, DEFF, and hash-pin the result.

**Planned-intent stratum manifest (Codex round-1 #4)**: the stage-2 relation-builder needs a severity stratum, but the real `severity_stratum_manifest` is consensus-gold-derived (0a.-1.C §1.4b) and outcomes don't exist yet. So stage-2 uses a DISTINCT `allocation_stratum_manifest` with `stratum_source = planned_intent` (the construction-target severity per the template), custody-controlled + disjoint from adjudicators (per 0a.-1.E §4.1 — reading it bars adjudication). The FINAL pre-unblinding Gate A DEFF run (contract §3.2) uses the TRUE consensus-derived `severity_stratum_manifest`; `DEFF_binding = max(DEFF_Phase0a_pilot, DEFF_final_gold_set)` (§3.2) preserves conservatism if planned-intent and consensus strata diverge.

**Deterministic resample/expand rule (Codex round-1 #3)**:
```
target band: per-stratum DEFF <= the pre-registered UPPER bound the §3.2 raw-n was sized for
  (e.g. DEFF <= 2.0 at planning ICC=0.10). The UPPER bound is binding for SAFETY
  (too-high DEFF -> too-low n_eff). A lower bound is representativeness-only, NOT
  safety-binding (a lower DEFF only HELPS the bound).

procedure:
  attempt = 1
  accept the first seed draw whose every-stratum DEFF <= upper bound
  if out-of-band: resample (next sequential draw index) up to K=<pre-registered> attempts
  if still out-of-band after K: EXPAND raw N for the failing stratum to
    ceil(n_eff_required_S × observed_DEFF_S), a §P4 Category-3 (pre-outcome) amendment
```
Stage 2 is structural (0a.-1.E §6); the resample/expand happens PRE-outcome so it is not outcome-informed. This closes the "design-contaminated P/N" hole: P/N is validated against the intended design before outcomes, and the gold set is built to hit the target DEFF.

## §4. Allocation manifest (custody)

The `allocation_manifest` (custody artifact, explicitly under 0a.-1.E §1/§2/§3 — Codex round-1 #7) records: per-cell quotas (the quota table), the assigned constructor/template per scenario, the matched-control IDs (§5), the seed + draw index + infeasible/resample attempts, the solver/randomizer + relation-builder code pins, the objective weights + hard/soft constraint set, the input-manifest hashes (construction/source_packet/allocation_stratum), and the stage-2 P/N validation result (per-stratum P/N/DEFF/n_eff + relation-table hash + allocation_stratum_manifest hash + roster/template/prompt-inventory/ontology hashes). Stage-1 plan hash-pinned pre-construction; stage-2 P/N result hash-pinned post-structural-construction pre-outcome (§3).

## §5. Severity allocation note (S0 sentinel, SUPPORTED filler)

- **S1/S2**: sized for the Gate A n_eff (§3.2) × DEFF_binding.
- **S0**: policy sentinel (0a.-1.A / contract) — ≥50 stress-test items, NOT a UCB-sized stratum.
- **SUPPORTED**: the non-fab class. The matched-control ratio is PRE-REGISTERED here (Codex round-1 #5, per 0a.-1.B §3): each fabricated scenario is paired 1:1 with a matched SUPPORTED control built by the identical pipeline (D7' source_selection_manifest parity) on the same (domain × complexity × evidence-bin) cell; thus the matched-control ratio is 1:1 and `SUPPORTED ≥ fabricated_count`. SUPPORTED beyond the matched controls (for prevalence-plausibility) is allowed but the 1:1 matched pairing is the binding rule. The pairing/grouping (which SUPPORTED control matches which fab scenario) is recorded in the allocation_manifest.
- **S3**: NOT a gold-set stratum (D6 §2.2); observability-only.
- fabrication_type mix within S0/S1/S2: per the D6 template `fabrication_type_mix_target` (the 7 types spread per stratum).

## §6. Definition of done (D8)

Locked: stratification cells, blocked-randomization + quota-generator rules (hard/soft marginals, rounding, min-coverage, SUPPORTED no-fab-axis, infeasible redistribution, D6→D8 aggregation), hard-constraint + soft-penalty SME/template balancing with roster feasibility precheck (fail-closed), pinned D8-allocation child seed, TWO-STAGE P/N validation (stage-1 plan pre-construction; stage-2 relation-builder on real manifests post-construction pre-outcome, via allocation_stratum_manifest planned-intent; final Gate A uses consensus severity_stratum_manifest), deterministic resample/expand rule (upper-bound binding, K attempts, then §P4 Cat-3 expand), expanded allocation_manifest custody, severity allocation (S0 sentinel / 1:1 matched-control / S3 excluded). Codex §-1.1 APPROVE. Operator sign-off. NOTE: the allocation RUN is a Phase-0a step gated per §7; D8 locks the DESIGN.

## §7. Dependencies + forward notes

- Needs D1a/D2/D3/D4/D5/D6/D7'/0a.-1.A/0a.-1.B/0a.-1.C/0a.-1.E + §3.2 cluster-arithmetic — all LOCKED (D5 prompt-family + D7' packet_class are consumed by the stage-2 relation-builder run).
- Consumes the relation-builder (0a.-1.C code) for the stage-2 P/N validation.
- The allocation RUN is gated behind (Codex round-1 #8): D4-seed + D6-content + D5-inventory (the content the allocation assigns) + D7'/source_packet_manifest readiness + the post-0a.-1.E accepted relation-builder code + edge-fixture run + 0a.-1.A roster (the SMEs to balance, with the feasibility precheck).
- allocation_manifest + seed + two-stage P/N validation recorded in 0a.-1.E custody.
- Resample-then-expand that changes locked n = §P4 Category-3 (pre-outcome).
