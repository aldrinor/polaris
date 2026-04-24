M-62 code audit — xhigh reasoning.

**Skip git status.** Two files only.

## Scope

Commit `5efefca`. Files:

1. `config/scope_templates/policy.yaml` — new
   per_query_report_contract block for policy_medicare_drug_price
   (5 non-clinical entities + 5 rendering slots).
2. `tests/polaris_graph/test_m62_non_clinical_regression.py`
   — 18 tests in 8 classes exercising the full M-54→M-55→M-57→
   M-58→M-59→M-60→M-61 chain on the policy slug.

Codex at gpt-5.4 + xhigh (default).

## Your pass-1 plan verdict to verify

M-62 plan verdict was `preservation_guard_needs_revision`. Your
revision #8 required:
  "policy is the highest-value regression if the goal is
   architectural proof, because it stresses non-DOI / non-paper
   entity types and mixed source forms."

Verify the policy contract actually exercises non-DOI / non-paper
entity types — that it's not just a rehash of clinical.yaml
with renamed strings.

## Questions

1. **Non-DOI / non-paper entity types (rev #8)**: the 5 entities
   are statute, regulatory_ruling, court_decision (×2),
   cbo_report. None have DOIs; all use url_pattern. Does this
   sufficiently stress Codex rev #7/#8's "arbitrary entity
   types" requirement?
2. **Architectural-not-clinical proof**: TestArchitectureNotHardcoded
   runs the full chain on policy slug. Is that test class
   actually sufficient to catch a clinical regression, or could
   someone still slip in clinical-only behavior elsewhere (e.g.
   a new M-63 or scope_templates loader)?
3. **Policy contract realism**: the 5 entities (IRA §11001, CMS
   guidance, Merck/NFIB cases, CBO baseline) are real active-
   domain anchors. Good or does the choice feel synthetic in a
   way that weakens the regression proof?
4. **section_order non-alphabetic**: [Statute, Implementation,
   Litigation, Economic_Analysis] — Implementation < Litigation
   alphabetically, but the plan order matches the policy
   reasoning flow. Alphabetic would wrongly put Economic_Analysis
   first. Good test of section_order not being optional?
5. **Two court_decision entities in Litigation**: slot ordering
   (Merck=1, NFIB=2) proves within-section ordering works for
   a multi-entity section. Sufficient?
6. **url_pattern-primary identifier chain**: compiler produces
   primary_identifier="url:*" for all 5 entities. M-56
   frame_fetcher treats url_pattern-primary entities as METADATA_ONLY
   without network calls. The test chain doesn't actually call
   M-56 live (no network in tests). Is that a gap — should there
   be an integration-level test that stubs HTTP and verifies the
   url_pattern entity treatment?
7. **M-61 integration on non-clinical**: statute completion with
   doi=null tests this. Sufficient, or should M-61 also be
   exercised on a court_decision completion with non-DOI
   citation locator?
8. **Test coverage breadth**: 18 tests across 8 classes
   covering M-54 through M-61. Fewer than the individual per-
   layer suites (54/41/35/20/44/20/25/37 = 276). Is the
   coverage right-sized for a regression guard, or should
   M-62 also cover edge cases (gap slots, partial fills, etc.)
   per layer?
9. **Contract realism edge case**: did any policy entity
   require a field I should question? Specifically `enactment_year`
   on statute has min_fields=4 of 6; `date_decided` on
   court_decision has min_fields=3 of 5. Thresholds reasonable?
10. **Preservation guard classification**: this is Codex's
    original V32 cycle, moved forward into V30. Does that
    staging make sense, or would you still want a separate
    V32 calibration sweep after V30 ships?

## Output

Write to `outputs/codex_findings/m62_code_audit/findings.md`.

Format:
```markdown
# Codex M-62 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Non-DOI / non-paper entity types: ...
2. Architectural-not-clinical proof: ...
3. Policy contract realism: ...
4. section_order non-alphabetic: ...
5. Litigation ordering: ...
6. url_pattern chain coverage: ...
7. M-61 non-clinical integration: ...
8. Test coverage breadth: ...
9. Field threshold realism: ...
10. Preservation guard staging: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: V30 Report Contract
Architecture is complete. Claude moves to V30 full-scale sweep
launch (task #28).
```

Keep under 150 lines. Full xhigh reasoning budget. This is the
last layer — the bar for APPROVED is that V30 architecture is
CREDIBLY not tirzepatide-specific hardcoding.
