# Deep-dive round 3 — Intake scope gate (BUG-B-100)

You are the independent reviewer for a focused deep-dive on the
scope-gate defect.

**Target**: `BUG-B-100 — Scope gate never actually rejects`
(full finding: `outputs/codex_findings/full_audit_pass_1/findings.md` §1).

## The defect, restated

`src/polaris_graph/nodes/scope_gate.py` sets `needs_user_review=True`
on problematic questions but has no rejection branch. The orchestrator
in `scripts/run_honest_sweep_r3.py:288-317` logs the flag then proceeds
to retrieval. The documented `abort_scope_rejected` status is
unreachable code.

Real-world evidence:
`outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/run_log.txt`
shows `[scope] ... needs_review=True` followed by retrieval +
generation + terminal `[status] ok_thin_corpus`. The flag was
surfaced then ignored.

## Your mandate (pass 1: scope + fix spec)

### 1. Map scope_gate's decision inputs

Read `src/polaris_graph/nodes/scope_gate.py`. What triggers
`needs_user_review=True`? What other flags / signals does it produce?
What is the semantic difference between:
- A question it should REJECT outright (e.g., off-topic, harmful,
  unanswerable)
- A question it should FLAG for human review but allow to proceed

Is there a signal in today's code that distinguishes these, or
does everything collapse into `needs_user_review`?

### 2. Map orchestrator's scope handling

Read `scripts/run_honest_sweep_r3.py:288-317` (the scope gate call
+ orchestrator's reaction).

- Does the orchestrator read any field besides `needs_user_review`?
- Is there ANY code path that currently emits
  `abort_scope_rejected`? (Answer is no, but confirm.)
- After the R1 fix (BUG-B-101 unified manifest), the
  `abort_scope_rejected` value is reserved in the taxonomy but no
  exit path emits it.

### 3. Choose a fix direction

Two candidate directions; pick one and justify:

**Direction A — Make the scope gate a real gate.**
Add a rejection branch. Define the criteria for hard rejection
(e.g., if scope_gate confidence is below X, or if the question is
classified as out-of-domain, or if required scope fields are
missing). Add an `if scope.rejected:` branch to `run_one_query`
that emits `abort_scope_rejected` before retrieval.

**Direction B — Retire the unreachable status.**
Remove `abort_scope_rejected` from the unified taxonomy. Document
scope review as advisory-only. Update docs to match.

### 4. Specify the implementation

For Direction A:
- Add what field(s) to `ScopeReport` / the protocol?
- Where in `scope_gate.py` gets the rejection logic?
- What criteria trigger rejection vs flag-only?
- How does the orchestrator integrate the rejection?

For Direction B:
- Remove `abort_scope_rejected` from `UNIFIED_STATUS_VALUES`
- Update `scripts/run_honest_sweep_r3.py::UNIFIED_STATUS_VALUES`
- Update all docs that mention `abort_scope_rejected`
- Update `test_manifest_contract_unified_taxonomy_defined`

### 5. Test specification

For Direction A: integration tests asserting a range of
reject/proceed/flag cases.

For Direction B: contract test asserting `abort_scope_rejected` is
NOT in the taxonomy + doc consistency check.

## Output

Write to `outputs/codex_findings/deep_dive_round_3/findings.md` with
this frontmatter:

```yaml
---
target_bug: B-100
scope: intake scope gate — unreachable abort_scope_rejected
verdict: scoped | needs_more_info
direction_chosen: A | B
invariants_affected: <list>
tests_required: <int>
rationale: |
  <2-4 sentences>
---
```

## Anti-circle-jerk rules

1. Read the actual `scope_gate.py` source, not summaries.
2. If the code has BOTH a rejection branch AND orchestrator-side
   handling that I missed, dispute the finding with evidence.
3. If direction B is chosen (retire the status), don't just
   rubber-stamp — confirm there's no future use case that needs
   the rejection semantics.

## What NOT to do

- Do NOT write the fix code. This pass produces the spec.
- Do NOT re-audit other parts of the pipeline; stay focused on B-100.

## Context

- `outputs/codex_findings/full_audit_pass_1/findings.md` — original B-100
- `src/polaris_graph/nodes/scope_gate.py` (~440 lines)
- `scripts/run_honest_sweep_r3.py` — esp. lines 280-330
- The R1 fix at commit `c764ddb` — manifest taxonomy includes
  `abort_scope_rejected` reserved value
- `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/run_log.txt`
  — real example of `needs_review=True` ignored

## Authentication

OAuth. No API-key burn.

## Expected duration

3-5 minutes. Smaller surface than R1/R2.

---

Start:

```
grep -n "needs_user_review\|needs_review\|rejected\|scope_rejected" \
  src/polaris_graph/nodes/scope_gate.py scripts/run_honest_sweep_r3.py
```

Then read the `ScopeReport` dataclass and the orchestrator's
handling.
