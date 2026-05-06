M-D5 phase 1 v1 review (commit a29a77f).

**Skip git status.** Codex at gpt-5.4 + xhigh.

**Important**: in this PowerShell sandbox `pytest` isn't on the
PATH directly — invoke via `python -m pytest -q tests\polaris_graph\test_md5_scope_classifier.py`
(or just trust the test count from the brief and review code +
threat-model only).

## Context

Phase D M-D5: confidence-gated template matching. Sits above
M-20 router. Pluggable scope-eligibility classifier protocol
(in_scope/out_of_scope/uncertain + confidence) wraps M-20.

6 phase D milestones already GREEN-LOCKED (M-D2 phase a/b,
M-D7 phase 1, M-D9 phase 1, M-D10 phase 1, M-D11 phase 1+2).
Convergence pattern: foundational milestones 5+ rounds; subsequent
ones with v1-shipped threat-model docs converge in 2-3.

## What v1 ships

`src/polaris_graph/audit_ir/scope_classifier.py`:
  - `ScopeVerdict` enum: in_scope | out_of_scope | uncertain
  - `ScopeClassification` dataclass: verdict + confidence in
    [0,1] + domain (metadata) + rationale
  - `ScopeEligibilityClassifier` Protocol — phase 1 ships
    contract only; concrete impls deferred to phase 2 alongside
    M-D6 cross-domain adapters
  - `GatedAction`: route | operator_review | reject
  - `GatedMatchResult`: action + template_id + router_result +
    classification + threshold + rationale
  - `confidence_gated_match(question, *, classifier, threshold,
    router_config)`: 4-branch gate per advisor:
      classifier.confidence < threshold       → operator_review
      classifier.OUT_OF_SCOPE                 → reject
      classifier.UNCERTAIN                    → operator_review
      classifier.IN_SCOPE + router.ROUTED     → route
      classifier.IN_SCOPE + router.OP_REVIEW  → operator_review
      classifier.IN_SCOPE + router.UNSUPP     → operator_review

  - Threshold gates the CLASSIFIER's confidence, not M-20's score
    (M-20 has its own gate). Default 0.70 via env, clamps [0,1].
  - REJECT is soft — verdict only, not hard block. Operators
    can force-enqueue via M-23 review queue (preserves M-20
    fail-closed-with-escape pattern).

`tests/polaris_graph/test_md5_scope_classifier.py` — 24 tests:
  - 6 gating-branch tests (4 main branches per advisor's matrix
    + boundary values + low-confidence regardless of verdict)
  - 6 threshold semantics tests (env override, clamp above 1,
    clamp below 0, invalid → default, kwarg clamps, default
    when arg=None)
  - 4 protocol-violation guards (wrong type, wrong verdict
    enum, out-of-range confidence positive + negative)
  - 3 boundary-value tests (exactly-at threshold inclusive,
    confidence-zero with zero-threshold, router_config passes
    through and changes verdict)
  - 1 empty query (does not auto-route even with confident
    classifier)
  - 4 validation-set contract tests against M-D1 (43 cases):
      - zero-route-on-non-in-scope across full set
      - in-scope: gate matches router (ROUTED→ROUTE,
        else→OPERATOR_REVIEW)
      - out-of-scope: every case rejects at threshold 0.70
      - ambiguous: every case operator_review (uncertain branch)

`docs/md5_phase1_threat_model.md` — 6 boundaries:
  1. Phase 1 = gating logic + protocol; classifier impl deferred
  2. Classifier confidence is uncalibrated until phase 2
  3. REJECT is soft — operator override path preserved
  4. Threshold gates classifier, not router (deliberate
     separation; not duplicating M-20)
  5. No telemetry table (gate_decisions deferred to phase 2 +
     M-D3 telemetry)
  6. No LLM client imports (substrate-only, like M-D11 ph 1+2)

## Your job

GREEN-LOCK or PARTIAL.

1. **Gate logic**:
   - [ ] 4-branch logic correct per advisor's spec
   - [ ] Threshold inclusivity at boundary (0.70 == 0.70 is
     not "below")
   - [ ] Empty query handling (router returns UNSUPPORTED →
     gate doesn't auto-route even with confident classifier)
   - [ ] Protocol violations fail loudly (LAW II)

2. **Validation-set abstain contract** (the spec):
   - [ ] Zero `route` for non-in-scope cases pinned
   - [ ] OOS rejects at threshold 0.70 + oracle 0.95
   - [ ] Ambiguous → OPERATOR_REVIEW

3. **Threat model**:
   - [ ] 6 boundaries match the code
   - [ ] Soft-reject contract documented & enforced
   - [ ] Phase 2 deferral list realistic

4. **Stop criterion**: GREEN-lock if remaining findings are
   minor (doc nits, additional contract tightening). PARTIAL only
   if you find:
     (a) Gate logic violates the advisor's matrix in some path
     (b) Threshold semantics mis-implemented (boundary off-by-one,
         clamping wrong direction)
     (c) Protocol violation can pass through silently
     (d) Validation-set contract has a hole (some category routes
         when it shouldn't)
     (e) Threat-model boundary contradicted by the code

5. **Phase-2 readiness**: with v1 substrate (gate + protocol +
   abstain spec), can phase 2 layer cleanly? (Concrete classifier
   impl + M-D6 domain pairing + calibration sweep on M-D1.)

## Output

`outputs/codex_findings/md5_review/findings.md`:

```markdown
# Codex round 1 — M-D5 phase 1 v1 (commit a29a77f)

## Verdict
GREEN / PARTIAL / DISAGREE

## Coverage
- [x/no] 4-branch gate matches advisor's spec
- [x/no] threshold env + clamp + boundary inclusivity
- [x/no] protocol violations fail loudly
- [x/no] M-D1 abstain contract pinned (zero route on non-in-scope)
- [x/no] threat-model 6 boundaries match code

## New findings (if any)
- [HIGH/MED/LOW] [...]

## Final word
GREEN to lock M-D5 phase 1 / PARTIAL with edits.
```

Be terse. Under 50 lines.
