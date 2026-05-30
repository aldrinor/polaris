# D1a — POLARIS Validation Domain Set (LOCKED)

**Deliverable**: Phase 0a.0 / D1a — the frozen validation-domain set.
**Status**: LOCKED (Codex §-1.1 review APPROVE 2026-05-27 "Lock D1a"; pending operator sign-off).
**Parent**: Statistical Safety Contract v3.3 (`state/polaris_statistical_contract/v3_3/contract.md`).
**Plan**: `state/polaris_statistical_contract/v3_4_phase_0a_0/PHASE_0a_0_PLAN.md`.
**Codex review**: `.codex/I-safety-001b/codex_D1a_review.txt` + `codex_D1a_confirm.txt` (5 fixes applied, all ✓ closed).
**Version**: 1
**Content hash**: see `D1a_validation_domain_set.sha256`

---

## §1. Validation-scope framing (binding)

These six domains define the **validation scope** of the POLARIS Statistical Safety Contract. They are the strata over which Gates A, B, D, E and prerequisites P1, P2 are constructed and measured.

**This is NOT**:
- a population claim about Prime Minister Carney's research interests,
- a claim about all POLARIS use,
- a claim that these are the only domains POLARIS supports.

Per contract §10.0, "all domains / all customers" is a forbidden overclaim. Gate pass-sentences are scoped to the applicable locked evaluation construction — including gold-set construction and/or canary eligibility as specified by each gate — within these six domains only.

## §2. The six validation domains (exact IDs)

| # | Domain ID | Scope template (exists) | Completeness checklist | Action |
|---|---|---|---|---|
| 1 | `clinical` | `config/scope_templates/clinical.yaml` | `config/completeness_checklists/clinical.yaml` (exists) | use as-is |
| 2 | `due_diligence` | `config/scope_templates/due_diligence.yaml` | `config/completeness_checklists/due_diligence.yaml` (exists) | use as-is |
| 3 | `policy` | `config/scope_templates/policy.yaml` | `config/completeness_checklists/policy.yaml` (exists) | use as-is |
| 4 | `tech` | `config/scope_templates/tech.yaml` | `config/completeness_checklists/tech.yaml` (exists) | use as-is |
| 5 | `ai_sovereignty` | `config/scope_templates/ai_sovereignty.yaml` | MISSING | D1 authors `ai_sovereignty.yaml` |
| 6 | `canada_us` | `config/scope_templates/canada_us.yaml` | MISSING | D1 authors `canada_us.yaml` |

The domain IDs are the canonical string identifiers used everywhere in the contract substrate (manifests, allocation, stratification). They MUST match the scope-template filename stems byte-for-byte (i.e., `config/scope_templates/{domain}.yaml`).

## §3. Explicit exclusions

| Excluded | Reason |
|---|---|
| `workforce` | Excluded from validation scope. Remains a valid POLARIS production domain and a member of the canonical-8 — the exclusion is validation-scope only. (Selection rationale is deferred to D1.) |
| `custom` | Not a stable substantive validation stratum (it is the fallback template shape). Remains a canonical-8 / supported production template; excluded from validation scope only. |

## §4. Canonical-8 non-interference note

The repo enforces a **canonical-8 template set** = {clinical, policy, tech, due_diligence, ai_sovereignty, canada_us, workforce, custom} in `tests/v6/test_template_canonical_set.py` and `src/polaris_graph/nodes/scope_gate.py`.

D1a does **NOT** modify the canonical-8. The validation domain set (six) is a SUBSET selected for contract validation. `workforce` and `custom` remain in the canonical-8 and in production; they are merely outside validation scope.

Completeness-checklist governance is **separate** from the canonical-8 and is currently permissive (a missing checklist returns `no_checklist_loaded`, not a canonical failure). D1 will add a validation-domain fail-closed guard (per Phase-0a.0 plan carry-forward redline 7) so the six validation domains require a present checklist. Authoring `ai_sovereignty.yaml` + `canada_us.yaml` in D1 does not change the canonical-8.

## §5. Freeze / change-control rule

This domain set is **frozen** on lock. Any change (add / remove / rename a validation domain) is a contract amendment governed by `state/polaris_statistical_contract/v3_3/contract.md` §P4:

- Before any Phase-0a structural exposure: §P4 Category-3 (pre-outcome design amendment) — versioned hash-pin, no fresh holdout.
- After structural exposure (pilot cluster structure observed): the domain set feeds stratification/allocation; a change is design-changing and requires §P4 Category-3 treatment with a re-run of affected allocation.
- After outcome exposure (any gate's miss counts seen): §P4 Category-4 — the affected gate's analysis becomes exploratory; the confirmatory gate requires one of the full Category-4 remedies (a fresh sealed holdout, a prospectively-defined alpha-spending plan covering both designs, or a clearly-labelled conservative bridging validation).

No silent reinterpretation of the set is permitted. The domain IDs in §2 are the sole authority.

## §6. Version + hash metadata

- **Version**: 1
- **Locked at**: 2026-05-27 (Codex APPROVE; operator sign-off pending)
- **Content hash**: SHA256 of this file, recorded in `D1a_validation_domain_set.sha256`
- **Supersedes**: none (first version)
- **Amendment log**: `state/data_lineage/amendments/` (per contract §P4.3)

---

## §7. Deferral note

The following are deferred to D1 (explicitly NOT part of this D1a lock): the domain-selection rationale, authoring the two missing completeness checklists (`ai_sovereignty.yaml`, `canada_us.yaml`), and the validation-domain fail-closed checklist guard.
