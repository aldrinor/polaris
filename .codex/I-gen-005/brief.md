# I-gen-005 — V4 Pro verifier bugs + atom-first architecture

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Issue summary

Original scope: V4 Pro verifier dropped 87% of sentences in baseline smoke. Investigation revealed VERIFIER bugs (not generator hallucinations).

Scope expanded per operator decision (after operator chose "atom-first per Codex's recommended_path"): architectural pivot from "fix verifier" to "atom-first generation contract." V4 Pro becomes a synthesis layer over a closed-world catalog of pre-extracted ClaimAtoms; refusal disclosure replaces silent drop for missing evidence.

## Acceptance criteria

1. Verifier bugs (Codex Step 1 5-iter review) fixed and APPROVE'd
2. Telemetry (final-state SectionResult drop categories) shipped per Codex smoke review
3. claim_atom_extractor module shipped per Codex APPROVE_DESIGN
4. atom_refusal_validator module shipped per Codex APPROVE_DESIGN
5. V4 Pro `_call_section` prompt-side atom catalog injection (Step 3a) — ADDITIVE to existing [ev_XXX] provenance contract
6. Full post-hoc validator wiring (Step 3b) — DEFERRED to separate PR per Codex iter-2 advice

## Per-component Codex review trail (all APPROVE)

| Component | Iters | Final verdict | Verdict file |
|---|---|---|---|
| Step 1 verifier fixes (provenance_generator.py) | 5 | APPROVE | .codex/I-gen-005/codex_step1_diff_verdict_iter5.txt |
| Step 1.5 telemetry (multi_section_generator.py) | 1 | APPROVE | (smoke review verdict) |
| Step 2 span window 500→800 | 0 | DECISION (no review needed) | (commit a7b40201) |
| claim_atom_extractor.py | 5 + post-cap | force-APPROVE §8.3.1 | .codex/I-gen-005-step15-atom/codex_diff_verdict_iter5.txt |
| atom_refusal_validator.py | 4 | APPROVE | .codex/I-gen-005-refusal/codex_diff_verdict_iter4.txt |
| Step 3a multi_section prompt injection | 2 | APPROVE | .codex/I-gen-005-refusal/codex_step3a_verdict_iter2.txt |

## Tests passing

109/109 in atom_extractor + atom_refusal_validator + i_gen_005_step15_telemetry suites.

## Step 3b deferral rationale (per Codex)

Step 3b touches SectionResult dataclass + multi_section_generator orchestrator + adds gaps.json sidecar artifact. Codex iter-2 verdict on Step 3a explicitly recommended SEPARATE_PR + logging-only mode behind flag + pass-through atom catalog + strip atom_NNN before strict_verify numeric matching. Per Codex, ship the prompt-side now; wire the post-hoc enforcement after real-run validates V4 Pro reliably emits atom_NNN.

## What this brief asks

Confirm: the aggregation of per-component APPROVE verdicts + the architectural pivot to atom-first + the additive-citation contract (atom_NNN PLUS existing [ev_XXX], not replacement) is sound for merge.

The canonical PR diff hash (computed AFTER excluding `.codex/I-gen-005/` and `outputs/audits/I-gen-005/` per CI workflow) is:
`7ec7f2a0f24f839635eddba8eb5bde22cc33c56734cdbcfb2b5ce25296e5af21`

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

per_component_approvals_complete: YES | NO
  if_no: |
    (which component lacks an APPROVE verdict)

architectural_pivot_sound: YES | NO
  if_no: |
    (concern)

additive_citation_contract_correct: YES | NO
  if_no: |
    (concern)

step_3b_deferral_acceptable: YES | NO
  if_no: |
    (why not separable)

novel_p0: [...]
novel_p1: [...]
p2: [...]

approval_to_merge: YES | NO
```

EMIT YAML ONLY. The component-level Codex verdicts (referenced by file above) are the source of truth for the actual code review. This brief asks only the aggregation question.
