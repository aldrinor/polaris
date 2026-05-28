# D1 — Validation-Domain Rationale + Checklist Authoring + Fail-Closed Guard

**Deliverable**: Phase 0a.0 / D1 — the domain-selection rationale (deferred from D1a), the two authored completeness checklists, and the validation-domain fail-closed guard.
**Status**: LOCKED (Codex §-1.1 APPROVE 2026-05-27 "Lock D1", no blocking findings; pending operator sign-off).
**Parent**: D1a (the 6-domain set is LOCKED); contract v3.3.
**Plan**: `PHASE_0a_0_PLAN.md` + carry-forward redline #7 (fail-closed checklist guard).
**Version**: 0 (draft)

**Scope**: D1a LOCKED the domain SET (and the validation-scope framing). D1 supplies what D1a explicitly deferred: (a) the selection rationale, (b) authoring the two missing checklists, (c) the fail-closed guard.

---

## §1. Domain-selection rationale

The six validation domains are `clinical`, `due_diligence`, `policy`, `tech`, `ai_sovereignty`, `canada_us` (locked in D1a §2). Rationale for this selection, from the canonical-8 template set:

- **Selected because they span the risk surface POLARIS must be safe across**: a clinical S0 (wrong dose) is a different harm shape than a `due_diligence` S0 (undisclosed liability), a `policy`/`canada_us` S0 (inverted binding obligation), a `tech` S0 (false safety/security property), or an `ai_sovereignty` S0 (false data-residency claim). Validating across all five harm shapes exercises the severity rubric (0a.-1.B) where it is hardest, not just where it is easiest.
- **`ai_sovereignty` kept** despite lacking a checklist (now authored, §2) because AI-sovereignty positioning is central to the Carney delivery; dropping it would leave the most strategically load-bearing domain unvalidated.
- **`canada_us` kept** for the same Carney relevance (cross-border trade/immigration/defense/energy) and because it exercises binding-obligation inversions distinct from generic `policy`.

### §1.1 Exclusions (consistent with D1a §3)

- **`workforce` excluded** from validation scope: it overlaps `policy`/`canada_us` on harm shape (labor/immigration policy), so it adds construction+SME cost without adding a distinct harm surface. It remains a canonical-8 production domain — the exclusion is validation-scope only.
- **`custom` excluded**: it is the fallback template shape, not a stable substantive stratum; using it would make the domain stratum ill-defined.

### §1.2 What this rationale does NOT claim (inherits D1a §1)

It does NOT claim these are the only domains POLARIS supports, nor a population claim about Carney's research interests. Per contract §10.0, "all domains" is a forbidden overclaim. The six are the VALIDATION SCOPE.

## §2. Authored completeness checklists

D1a noted `ai_sovereignty` and `canada_us` lacked completeness checklists (only `clinical`/`custom`/`due_diligence`/`policy`/`tech` had them). D1 authors the two, matching the locked checklist format (`config/completeness_checklists/policy.yaml` et al.):

- **`config/completeness_checklists/ai_sovereignty.yaml`** — 6 topics: regulatory_framework, data_residency, procurement_standards, model_provenance, security_controls, vendor_dependence.
- **`config/completeness_checklists/canada_us.yaml`** — 6 topics: binding_agreement, trade_tariff, immigration_status, defense_security, energy_interconnection, regulatory_alignment.

Each topic carries `id`, `label`, `keywords`, `expand_queries` per the loader (`src/polaris_graph/nodes/completeness_checker.py:load_checklist`). The canonical-8 template set (`tests/v6/test_template_canonical_set.py`) is unaffected — checklist governance is separate from the canonical-8 (verified in 0a.-1.D / D1a §4).

## §3. Validation-domain fail-closed guard

Per carry-forward redline #7: production completeness checking is PERMISSIVE (missing checklist → `no_checklist_loaded`, not failure — correct for arbitrary production domains). For the validation scope that permissiveness is unsafe: a gold set must not be built for a validation domain whose checklist is missing.

`src/polaris_safety/validation_domain_guard.py`:
- `VALIDATION_DOMAINS` — the locked six (single authority).
- `missing_validation_checklists()` — returns validation domains whose `load_checklist` yields zero topics.
- `assert_validation_checklists_present()` — RAISES `ValidationDomainChecklistError` if any validation domain lacks a present, non-empty checklist. A pre-construction gate, NOT a change to production completeness behaviour.

It REUSES the production `load_checklist` (single source of truth for "what counts as a present checklist") rather than re-implementing file discovery.

## §4. Verification (smoke-tested)

`tests/polaris_safety/test_validation_domain_guard.py` — 6 tests, all pass:
- all six validation domains have checklists (post-authoring)
- assert passes with all present
- VALIDATION_DOMAINS is exactly the locked six (workforce + custom excluded)
- fail-closed raises on a missing domain
- the missing-list names the offender
- each validation domain checklist loads ≥1 topic

`python -m pytest tests/polaris_safety/` → 55 passed (49 relation-builder + 6 guard).

## §5. Definition of done (D1)

Locked: domain-selection rationale, two authored checklists (ai_sovereignty + canada_us), fail-closed validation-domain guard + tests (smoke-passing). Codex §-1.1 APPROVE. Operator sign-off.

## §6. Dependencies + forward notes

- Needs D1a (6 domains) — DONE.
- The guard is a pre-construction gate: `assert_validation_checklists_present()` is called before gold-set construction (Phase 0b).
- Pre-existing unrelated failure flagged (NOT D1): `tests/v6/test_template_canonical_set.py::test_frontend_dashboard_fallback_is_canonical_8` fails because `web/app/dashboard/page.tsx` no longer contains the `FALLBACK_TEMPLATES` block (P2 UI rebuild drift). Out of D1 scope; should be a separate UI-drift issue.
