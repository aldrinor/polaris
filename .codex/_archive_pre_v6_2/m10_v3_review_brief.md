M-10 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-10 v2 verdict: PARTIAL on umbrella drug-class bypass.
- "Phase 3 trial of biologic for psoriasis" → routed 0.72
- "Phase 3 trial of biosimilar for rheumatoid arthritis" → routed 0.70
- "Phase 3 trial of monoclonal antibody for eczema" → routed 0.87
- "Phase 3 trial of receptor agonist for dermatitis" → routed 0.70

Root cause: `biologic`, `biosimilar`, `monoclonal antibody`, and
`receptor agonist` were in the STRONG gate — too generic to anchor
ROUTED on their own.

## What changed in v3

`template_catalog.py`:
- Demoted ALL umbrella class terms (`biologic`, `biologics`,
  `biosimilar`, `biosimilars`, `monoclonal antibody`,
  `monoclonal antibodies`, `receptor agonist`, `receptor antagonist`)
  from `drug_keywords` to `medical_keywords`.
- `drug_keywords` (the STRONG gate) now contains ONLY:
  - 14 specific drug names (tirzepatide, semaglutide, liraglutide,
    dulaglutide, exenatide, metformin, empagliflozin, dapagliflozin,
    canagliflozin, sitagliptin, saxagliptin, atorvastatin,
    rosuvastatin, simvastatin)
  - 4 narrow class abbreviations (glp-1, sglt2, sglt-2, dpp-4 — each
    identifies a small known set of marketed drugs)
- Removed exemplar "Phase 3 trial of monoclonal antibody for
  hypertension" — generic class without a specific drug, the
  routing hazard. Replaced with "Dulaglutide phase 3 trial outcomes
  for type 2 diabetes" (specific drug + condition).

`tests/test_template_classifier.py`:
- Extended off-scope parametrized test with the 4 umbrella probes
  PLUS 2 additional ones:
    "Meta-analysis of biologics in inflammatory bowel disease"
    "Adverse events of monoclonal antibodies in oncology"

Tests: 56 / 56 in M-10 module. Phase B suite: 200 / 200 green.

Manual verification on your exact umbrella false positives:
  biologic + psoriasis              → operator_review (0.40)  drug=[]
  biosimilar + rheumatoid arthritis → operator_review (0.40)  drug=[]
  monoclonal antibody + eczema      → operator_review (0.40)  drug=[]
  receptor agonist + dermatitis     → operator_review (0.40)  drug=[]
True positives still route at confidence 1.00:
  tirzepatide + diabetes        → routed (1.00)
  metformin + diabetes          → routed (1.00)
  GLP-1 cardiovascular          → routed (1.00)
  empagliflozin meta-analysis   → routed (1.00)

## Your job

Final verdict on M-10. GREEN / PARTIAL / DISAGREE.

Please probe with:
- More umbrella terms / generic class names you can think of (drug
  family names, e.g. "statin", "ssri", "ace inhibitor")
- Any other route into Tier A you spot
- Sanity check: drug_keywords contains only specific drugs +
  narrow abbreviations now

If GREEN, M-10 is locked and Phase B can proceed to M-11 (bounded
upload + workspace data model).

## Output

Write to `outputs/codex_findings/m10_v3_review/findings.md`:

```markdown
# Codex final review of M-10 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## Umbrella-bypass fix
- [x/no] All 4 v2 umbrella false positives now ≤ OPERATOR_REVIEW
- [x/no] Cannot find a new exemplar-shape bypass via remaining
  drug_keywords

## Final word
GREEN to lock M-10 + proceed to M-11 / PARTIAL with edits.
```

Be terse. Under 60 lines.
