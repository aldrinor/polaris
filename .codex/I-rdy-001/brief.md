# Codex review — I-rdy-001 (#497): docs/polaris_locked_scope.md

**Type:** REVIEW of a documentation deliverable. Highest-quality standard.

## §0. Cap directive
HARD ITERATION CAP: 5. This is iter 1 of 5. Front-load ALL findings now — no
drip-feeding. Same quality bar regardless of iteration. "Don't pick bone from
egg" — reserve P0/P1 for real defects; classify nits as P2/P3. Verdict APPROVE
iff zero P0 and zero P1.

## §1. Context
I-rdy-001 (#497) is Phase 0A of the Carney demo execution plan
(`state/carney_demo_execution_plan_2026_05_15.md`, Codex-approved). Deliverable:
`docs/polaris_locked_scope.md` — the single anti-drift source of truth that
freezes the LLM, architecture, and feature scope for the Carney demo.

Background docs in the repo: `state/carney_readiness_gaps_2026_05_15.md` (the
gap register the feature statuses are drawn from), `state/canada_gpu_research_2026_05_15.md`,
`docs/carney_delivery_plan_v6_2.md` (the mission).

## §2. Acceptance criteria for I-rdy-001
1. Captures the 5 operator-locked constraints: V4 Pro + Gemma 4 31B + 1 concurrent; Canadian sovereign GPU only; v6 architecture no-rewrites; BPEI banned; single-venue June demo.
2. Lists the canonical 8 templates, naming `config/scope_templates/` as the single source of truth.
3. Lists the 15 features + cross-cutting capabilities with status.
4. Constraints (§1) marked LOCKED; feature statuses (§3) marked PROVISIONAL pending Phase 1.
5. States the binding rule: harness/fixture evidence does not count as feature-complete.
6. Has a change protocol making §1 operator-owned.

## §3. What to verify (review `docs/polaris_locked_scope.md`)
- Completeness vs the 6 acceptance criteria above.
- Accuracy: do the 8 templates match `config/scope_templates/`? Do the feature statuses match `state/carney_readiness_gaps_2026_05_15.md`? Is the V4 Pro spec (1.6T, FP4/FP8, ~880GB) correct?
- Internal consistency: any contradiction within the doc, or with the execution plan / gap register.
- Is anything material MISSING that a scope-lock doc must have.
- Is any claim an over-claim or factually wrong.

## §4. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
p3: [...]
completeness_check: <text — all 6 acceptance criteria met?>
accuracy_errors: [...]
verdict_reasoning: <text>
```
Do not propose reopening the locked constraints themselves — verify the doc
correctly CAPTURES them.
