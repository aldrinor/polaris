# Codex M-62 audit

**Verdict**: CONDITIONAL-no-blockers

## Answers

1. Non-DOI / non-paper entity types: Yes, for rev #8's "arbitrary entity types" requirement. The contract uses four genuinely non-clinical types across five entities, none carry DOIs, and the tests prove the M-54/M-55/M-57/M-58/M-59/M-60/M-61 path accepts them without clinical vocab leakage (`config/scope_templates/policy.yaml:116-180`, `tests/polaris_graph/test_m62_non_clinical_regression.py:115-158`). The limit is identifier diversity: all five still reduce to `url_pattern` / `url:*`, so this is type-generalization proof, not mixed-identifier proof.
2. Architectural-not-clinical proof: Sufficient for the scoped M-54..M-61 architectural claim, not as a universal guard against future clinical-only code elsewhere. `TestArchitectureNotHardcoded` plus the other classes give a credible non-clinical end-to-end slice, but they do not cover a future M-63 or any higher-level scope-template discovery path because the fixture injects `policy.yaml` directly (`tests/polaris_graph/test_m62_non_clinical_regression.py:88-93`, `tests/polaris_graph/test_m62_non_clinical_regression.py:539-600`).
3. Policy contract realism: Good. IRA §11001, CMS guidance, Merck/NFIB litigation, and CBO scoring are real, active-domain anchors and span the policy reasoning stack cleanly (`config/scope_templates/policy.yaml:117-180`). They read as canonical policy artifacts, not synthetic fillers.
4. section_order non-alphabetic: Good test. `Economic_Analysis` being last makes alphabetical fallback observably wrong, so the outline assertion is a real guard that `section_order` is honored (`config/scope_templates/policy.yaml:110-114`, `tests/polaris_graph/test_m62_non_clinical_regression.py:207-224`).
5. Litigation ordering: Yes, sufficient for within-section positive ordering. Two `court_decision` slots share the same section with `ordering: 1` and `ordering: 2`, and the outline test asserts that exact order (`config/scope_templates/policy.yaml:193-201`, `tests/polaris_graph/test_m62_non_clinical_regression.py:226-245`). It does not test ties, which is acceptable for M-62.
6. url_pattern-primary identifier chain coverage: There is a gap, but not a blocker. The suite proves compiler-side `url:*` identifiers, yet it never invokes fetcher behavior; all downstream stages consume fabricated `FrameRow`s (`tests/polaris_graph/test_m62_non_clinical_regression.py:177-190`, `tests/polaris_graph/test_m62_non_clinical_regression.py:606-640`). One integration test should stub retrieval and assert url-pattern-primary entities stay `METADATA_ONLY` with zero network calls.
7. M-61 non-clinical integration: Partially sufficient. The statute path proves `doi=null` is accepted (`tests/polaris_graph/test_m62_non_clinical_regression.py:439-466`), but the file does not actually exercise a `court_decision` completion or the claimed case-citation `source_locator` path. Adding one court-decision completion test would close that gap.
8. Test coverage breadth: Right-sized for a preservation guard. Eighteen tests across eight classes is appropriate because the per-layer suites already own the edge-case matrices; M-62 should verify one realistic non-clinical slice end-to-end, not replicate all 276 earlier cases. The two additions worth making here are the gaps in answers 6 and 7. Local run passed with `python -m pytest tests/polaris_graph/test_m62_non_clinical_regression.py -q` (18/18).
9. Field threshold realism: Reasonable. `statute` at 4/6 (`config/scope_templates/policy.yaml:121-128`) forces more than a bare citation/date shell, which fits a high-value anchor. `court_decision` at 3/5 (`config/scope_templates/policy.yaml:148-167`) is appropriately tolerant because opinions reliably expose court/docket/disposition/date, while `constitutional_basis` or `plaintiff_standing` can be patchier.
10. Preservation guard staging: Moving this from the original V32 cycle into V30 makes sense. The question it answers is architectural, not post-ship calibration, so it belongs before V30 launch. A later V32 sweep can broaden corpus and identifier variety, but it should extend this guard, not replace it.

## Findings

- Medium: `tests/polaris_graph/test_m62_non_clinical_regression.py:17-32`, `tests/polaris_graph/test_m62_non_clinical_regression.py:144-158`, `tests/polaris_graph/test_m62_non_clinical_regression.py:545-580`
  The file presents itself as a near-full non-DOI chain proof, but it never exercises M-56 retrieval behavior. Every downstream stage consumes synthetic `_stub_row` objects, so a regression in url-pattern fetch handling could slip through while this suite still passes.
- Medium: `tests/polaris_graph/test_m62_non_clinical_regression.py:28-29`, `tests/polaris_graph/test_m62_non_clinical_regression.py:439-466`, `tests/polaris_graph/test_m62_non_clinical_regression.py:468-533`
  The M-61 coverage claim includes "court_decision case citation as source_locator", but the actual tests only parse a statute completion and generate a statute task. That leaves the court-decision / non-DOI legal-citation path unproven in this preservation guard.
- Nit: `config/scope_templates/policy.yaml:97-101`, `config/scope_templates/policy.yaml:144-180`
  The contract comment overstates identifier diversity: it says court decisions are "citation locator only" and CBO uses "DOI-like identifiers", but all five entities are configured only with `url_pattern`. The contract is still a valid non-clinical guard; the prose should match the implementation.

## Next

V30 Report Contract Architecture is complete. Claude moves to V30 full-scale sweep launch (task #28).
