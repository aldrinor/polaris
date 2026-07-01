HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real gaps that would let a broken/vacuous run pass GO.
- Verdict APPROVE iff the preflight (base + v2 corrections) is COMPLETE + behavioral (no missed element, no config-check masquerading as a firing check, no GO path that skips a gate).

# Codex gate — I-deepfix-001 PREFLIGHT SPEC, ITER 2 (re-gate after your iter-1 REQUEST_CHANGES)

You reviewed `.codex/I-deepfix-001/PREFLIGHT_SPEC.md` at iter 1 and returned REQUEST_CHANGES with 4 novel P0 + many P1/P2. This iter reviews the FIX. Read BOTH `.codex/I-deepfix-001/PREFLIGHT_SPEC.md` (base) AND `.codex/I-deepfix-001/PREFLIGHT_SPEC_v2_corrections.md` (the corrections layer — where it and the base disagree, the corrections win). Cross-check against `.codex/I-deepfix-001/BEATBOTH_MASTER_PLAN.md` + `.codex/I-deepfix-001/RESMOKE_S11_FORENSIC_AUDIT.md`. Repo root C:/POLARIS, read-only.

## Verify each iter-1 finding is resolved in the v2 corrections
1. **P0-1 vacuous query** → Stage B now renders the EXACT drb_72 AI-labor query + aborts unless the defect preconditions (Eloundou figure, journal-only AI-labor class, DOI-only entity, >=1 contradiction) are PRESENT. Resolved?
2. **P0-2 GO skips Phase 4** → GO now requires ALL of 4.1-4.6 + WS-14 scorers (required, not optional). Resolved?
3. **P0-3 release_allowed** → 4.6 now requires release_allowed==True; disclosed-gap = NO-GO. Resolved?
4. **P0-4 degraded tiering** → 1.5 now requires retrieval_wall_hit==false AND tiering_mode!=rules_floor_degraded. Resolved?
5. **SSOT** → generator GLM-5.2 + kimi D8 judge + PERMIT=1 named as the DISCLOSED benchmark override of the sovereign lock; frozen-engine base pinned = 73f3bb13 (WS-1's judge_adapter/openrouter_role_transport edits are before that base + were gated). Is the family-distinct assertion (gen/mirror z-ai allowed collision; judge-collapse fail-closed) correct? Any residual SSOT ambiguity?
6. **Per-element P1s** → D6 weight-basis + tiering_mode, D2 non-chrome spans, WS-2/M6 output-fired (2 distinct tokens), WS-3 de-tautologized repair, WS-1 judge-stability firing-check, WS-12 quantified no-op, D4 specific breaching classes, D5 DOI/basket fixtures — all added. Any still missing or still config-only?
7. **Thresholds** → DeepTRACE=ESTIMATE, DRB-II TotalScore>=66 with sub-targets, token-budget = observed request bodies, breadth = surfaced keep-all (no forced target §-1.3), §-1.1 aborts on over-claim too. Correct?
8. **Honest scope** → the corrections state THIS run = Wave A+B+C (residuals + winners + faithfulness = contention/strong), and a clear #1-on-coverage needs WS-15 (TTD-DR) + WS-10/11 (Wave D/E, unbuilt). Is this honest scoping correct, or does it still over-claim?
9. **Anything STILL missed** — any element, any GO path that could pass with a real defect present, any §-1.3 forced-number, any faithfulness relaxation.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
all_iter1_p0_resolved: true | false
covers_all_6_residuals_behaviorally: true | false
covers_all_winners_firing: true | false
faithfulness_bar_airtight: true | false
s13_no_forced_number: true | false
honest_scope_correct: true | false
missed_elements: [ ... ]
novel_p0: [...]
p1: [...]
convergence_call: continue | accept_remaining
```
