# Deep-dive R7 — Contradiction detector coverage (BUG-M-202)

**Target**: M-202. `contradiction_detector.py:77-92` hard-codes
obesity/cardiometabolic predicates ("weight loss", "hba1c reduction",
"ldl reduction", "incidence of nausea"). Other domains return zero
contradictions even when the corpus has them.

Real evidence: `clinical_afib_anticoagulation/run_log.txt` reports
`numeric_claims=0 contradictions=0` on a 20-source anticoagulation
guideline query (stroke/bleeding rates, HAS-BLED scores, etc. all
ignored).

## Mandate

1. Read `src/polaris_graph/retrieval/contradiction_detector.py`.
2. Identify hard-coded predicates + extraction rules + cardinality caps.
3. Choose: (a) per-domain predicate table (YAML-driven); or
   (b) generic LLM-extraction-based detection; or
   (c) hybrid — generic numeric-claim mining + domain-specific
   predicate hints.
4. Spec fix + 4-6 tests.

## Output

`outputs/codex_findings/deep_dive_round_7/findings.md` with standard frontmatter.

## Duration

5-10 minutes.

## Context

- Prior rounds R1-R6 committed.
- `outputs/codex_findings/full_audit_pass_1/findings.md` §3
- Config bundle: `docs/pipeline_audit_context/config_bundle/` — per-domain
  templates exist (clinical/tech/dd/policy); contradiction predicates
  could be added there.
