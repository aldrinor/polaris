# Codex BRIEF gate — I-run11-004 — certified MiniMax-M2 decomposition Sentinel + GLM-5.1 Mirror

HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## HARD CONSTRAINTS (operator-locked, NOT Codex-consultable)

These are operator directives, not design options. Do not pushback-relax them:
1. **The 3 voters + the generator must be OPEN-WEIGHT only.** No gpt/claude/gemini — even at the OpenRouter benchmark stage. (operator, 2026-06-03)
2. **The voters must be the strongest LATEST frontier open-weight LLMs.** NO small/old/specialized encoder models (LettuceDetect/FactCG-class explicitly rejected: "old and weak... perform very bad... to harm the output"). (operator, 2026-06-03)
3. **4 distinct lineages** (family_policy all_distinct), per the runtime lock + CI architecture-conformance gate.

## Problem (what failed)

Run-12 (drb_72_ai_labor, VM) reached the four-role evaluation and **held release**
(`manifest.status=abort_four_role_release_held`, coverage 0.286, only $1.15 spent, V30
retrieval coverage pass=7). Root cause: the benchmark-stage Sentinel was IBM Granite-Guardian,
whose groundedness head **over-rejected verbatim-grounded clinical claims** → too few VERIFIED
claims survived the fail-closed composition → release held. The generator + retrieval were fine.

## Approach (acceptance criteria)

Replace the broken Granite-Guardian benchmark Sentinel with a CERTIFIED frontier open-weight LLM
running a **claim-decomposition + span-coverage** faithfulness check, and re-pick the Mirror
(Cohere Command A+ is NOT on OpenRouter) to a frontier open-weight LLM.

1. **Sentinel = `minimax/minimax-m2`** (MiniMax-M2, ~229B MoE, license `modified-mit` = MIT + a
   large-product UI-attribution condition per HF; permissive open-weight, non-binding for our
   hosted-inference use; family `minimax`). New
   `decomposition` groundedness mode: the model atomizes the claim into mechanism/attribution/
   relation atoms and checks each against the CITED SPAN ONLY, returning strict JSON
   `{verdict, unsupported_atoms, atoms}`. Catches scope-inflation + wrong-attribution that a
   single yes/no groundedness head misses.
2. **Mirror = `z-ai/glm-5.1`** (GLM-5.1, MIT, family `glm`).
3. **Judge = `qwen/qwen3.6-35b-a3b`** (unchanged, Apache-2, family `qwen`).
   **Generator = `deepseek/deepseek-v4-pro`** (unchanged, family `deepseek`). 4 distinct families.
4. **Parser fail-CLOSED** (`parse_sentinel_decomposition`): ANY non-string / unparseable /
   missing-verdict / off-enum input → UNGROUNDED parsed_ok=False. A "supported" verdict that
   ALSO reports any unsupported atom (count != clean-zero, OR an atom whose status is
   "unsupported") VETOES to UNGROUNDED — the internally-contradictory case is the §-1.1 lethal
   fail-open and must hold, never release. **CONTRACT GATE (Codex brief-gate iter-1 P1, fixed):** a
   "supported" verdict that OMITS the decomposition (no non-empty `atoms` list with ≥1 atom object,
   or no `unsupported_atoms` field) FAILS CLOSED to UNGROUNDED — a bare/truncated/non-atomized
   "supported" did no per-atom span-coverage work and must not release. Validated against the cert
   cache: all 25 real "supported" outputs carry both → ZERO false-drops.
5. **Timeout sizing** (operator directive — "calculate the timeout for full performance"): the
   SEAM was the truncator at 2400s (only 50/87 claims checked) → default raised to 7200s; per-call
   `PG_VERIFIER_LLM_TIMEOUT_SECONDS` 900s; decomposition Sentinel reasoning ON + max_tokens floored
   ≥3000 so the atomization isn't truncated.
6. **Certification (the empirical bake-off, NOT a guess)**: deterministic-corruption test set
   `outputs/audits/I-run11-004/faithfulness_testset.json` (28 grounded + 28 fabricated, 5 error
   types). MiniMax-M2 decomposition = **0 false-accepts on all 28 fabrications**, over-flag 0.107.
7. **Lock + pin**: `config/architecture/polaris_runtime_lock.yaml` mirror→glm-5.1, sentinel→
   minimax-m2 (GLM MIT, MiniMax modified-mit); `docs/canonical_pin.txt` lock-SHA reconciled to LF blob.
   verify_lock.py: roles + code-defaults + canonical-pin-includes checkpoints OK.

## GREEN criteria

- `tests/roles tests/architecture tests/dr_benchmark` all green (661 passed).
- Sentinel certification: 0 false-accepts on the 28 deterministic fabrications.
- 4 distinct open-weight families; all permissive (deepseek/glm MIT, minimax modified-mit, qwen
  Apache-2); no closed-source.
- Parser fail-closed properties hold (no malformed input yields GROUNDED).

## Files I have ALSO checked and they're clean

- `src/polaris_graph/roles/role_pipeline.py` — `_compose_final_verdict` fail-closed UNCHANGED:
  Sentinel UNGROUNDED OR parsed_ok=False downgrades Judge VERIFIED/PARTIAL → UNSUPPORTED;
  worse Judge verdicts (FABRICATED/UNREACHABLE) preserved, never upgraded.
- `src/polaris_graph/roles/sweep_integration.py` — `build_evaluator_agrees_map` unchanged
  (evaluator_agrees = kept AND final_verdict==VERIFIED).
- Sovereign self-host inverted Guardian path (`guardian` mode, `<score>yes|no</score>`) byte-unchanged.
- `config/serving/verifier_roles.yaml` sentinel GPU sized for ~229B MoE (8×H100 fp8 TP8), marked
  PENDING sovereign GPU procurement (#90); benchmark stage routes via OpenRouter.

## Ask

APPROVE the acceptance-criteria correctness: does this brief correctly capture a clinical-safe,
operator-constraint-compliant fix for the run-12 four-role-held failure? (The CODE diff was
reviewed separately across 6 diff-gate iters → APPROVE, lethal fail-open closed; see
codex_diff_audit.txt.)

## Output schema (required)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
