# Phase 0a.0 design plan — Codex-converged (3 rounds)

**Status**: Plan APPROVED by Codex round-3 ("Begin D1a"). Deliverables execute in locked order below.

**Plan trail**: `.codex/I-safety-001b/codex_phase_0a_0_design_plan_v{1,2,3}{,_review}.txt`

**Codex round-3 verdict**: "v3 closes the round-2 P0s enough to start D1a... Begin D1a (lock 6 domains)."

## Locked deliverable order

```
D1a   LOCK 6 validation domains (FIRST — minimal frozen artifact)
0a.-1.A  SME panel + role governance
0a.-1.B  severity + fabrication rubric
0a.-1.D  canonical source identity + admissibility
0a.-1.C  metadata schema (5 split manifests + facet) + relation-builder
            [SPLIT: C-schema/spec BEFORE E; C-fixture dry-run AFTER E]
0a.-1.E  execution protocol / chain of custody
0a.-1.C-fixtures  edge-fixture dry-run (post-E, hash-pinned)
D1    domain rationale + author ai_sovereignty.yaml + canada_us.yaml checklists + validation-domain fail-closed guard
D2    composite complexity rubric (dominant-trigger + additive)
D3    evidence-pool bins (E1:1-5, E2:6-20, E3:21-40, E4:41-80)
D7'   source-packet methodology
D4    microtopic ontology (hybrid controlled + governed append-only)
D6    SME template format (semantic IDs)
D5    runtime-reachable prompt-family inventory
D8    pilot allocation (blocked randomization + quotas/min-cost matching)
FINAL relation-builder full dry-run on planned allocation + hash-pin
```

## CARRY-FORWARD REDLINES (Codex round-3 — apply before C/D8 EXECUTION, not blockers for D1a)

1. **D1a content** (applied in D1a now): validation-scope framing statement, exact 6 IDs, explicit exclusions (custom, workforce), canonical-8 non-interference note, freeze/change-control rule, hash/version metadata. NO rationale essay, NO checklist work.

2. **facet_manifest label-safety** (apply at 0a.-1.C): facets produced NEUTRALLY from claim text — deterministic, uniform across ALL claims, no "this is the suspicious bit" structure. No constructor-hand-authored facets spotlighting the fabricated clause. Adjudicators label claim/facet views through the SAME blinded tool that never exposes constructor intent or consensus labels.

3. **0a.-1.E mechanical role-separation** (apply at 0a.-1.E): NOT policy prose — mechanical enforcement. Add `assignment_manifest` {constructor_sme_id, adjudicator_ids, tiebreaker_id} + validator rejecting constructor/adjudicator overlap for same claim. Adjudication UI/CLI refuses login/actions that violate it. Hash relation-builder/randomizer code (not just packet renderer). Record FULL rendered packet snapshots (canonical HTML/text), not only renderer hash. Exposure log covers READS as well as WRITES through controlled access channels.

4. **0a.-1.C split** (apply at 0a.-1.C): D → C-schema/spec → E → C-fixture dry-run. Accepted fixture dry-runs must be post-custody (after E) or rerun+hash-pinned after E. Don't use pre-custody artifacts as builder-works evidence.

5. **D2 solo C3 trigger** (apply at D2): "modality + interpretive burden" not modality alone. Prose extraction ≠ C3. Structured records usually ≠ C3. Tables/figures requiring cross-row interpretation / unit conversion / subgroup selection / statistical reading DO force C3. Named trigger `table/statistical extraction` is right shape.

6. **D8 design** (apply at D8): BIBD collapses at ~18 SMEs × 72 cells. Use blocked randomization with quotas/min-cost matching as PRIMARY. Latin-square only for clean 2-factor rotation (this is messier). BIBD optional only if params happen to fit.

7. **D1 validation-domain guard** (apply at D1): completeness checklists currently permissive (missing → `no_checklist_loaded`, not failure). Add a validation-domain guard so the 6 validation domains FAIL CLOSED if a checklist is missing. (Repo check confirmed: `tests/v6/test_template_canonical_set.py` enforces canonical-8; checklists are separately permissive.)

## Codex review cadence (per deliverable)

Each deliverable: Claude draft → Codex §-1.1 line-by-line audit (uncapped) → iterate to APPROVE → hash-pin → operator sign-off → next.
