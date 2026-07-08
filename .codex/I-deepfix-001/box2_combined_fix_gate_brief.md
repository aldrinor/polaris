# DUAL-GATE BRIEF — box2 credibility-pass fix (freeze + corroboration, ONE shared root cause)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1 findings.
- If you detect "I'm holding back a P1 to surface next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## WHAT THIS FIX IS
A paid deep-research run (`run_gate_b.py --only drb_72_ai_labor`) had TWO symptoms that are ONE root cause:
1. box2 FROZE at generation (looked like a deadlock).
2. box1 rendered but FAILED the breadth-enrichment canary (rc=1) — the "Corroborated Weighted Findings"
   section was absent.

ROOT CAUSE (proven): the generation-stage **credibility pass** must LLM-judge ~999 basket members. The
Gate-B slate FORCE-PINNED `PG_CREDIBILITY_PASS_WALL_S=3000`; on the fetch-yield-fixed RICH corpus (~1061
sources / ~999 members) the pass overran 3000s; the caller `multi_section_generator.py` wrapped it in
`asyncio.wait_for(...)` which, on TimeoutError, set `credibility_analysis = None` and **discarded the WHOLE
analysis** (all-or-nothing). None → `weighted_enrichment.diagnose_unbound_supports_selection` returns
`[]` (reason=credibility_analysis_none) → no baskets → no corroboration section → canary rc=1. The "freeze"
was the same pass grinding ~999 judge POSTs through a 2-slot semaphore for hours (not a true deadlock).
PROOF it is the discard, not a render filter: the box2 RESUME run (credibility present) rendered 3 corroboration
sections, canary=present. b2dc6c0d (box2, the deliverable) has the IDENTICAL bug (git-verified: no bank).

## THE FIX (two composing halves, both in the diff)
HALF A — SPEED (make the pass finish, don't worsen the already-heavy OpenRouter 429 rate):
- `credibility_skill.py`: tier-band HYBRID — LLM-judge only ambiguous tiers (PG_CREDIBILITY_JUDGE_HYBRID_TIERS),
  clear-cut T1/T7 use their deterministic authority prior (every source STILL weighted). ~46% fewer judge calls.
- `credibility_judge_caller.py`: fast small OPEN judge model (PG_CREDIBILITY_JUDGE_MODEL, e.g. z-ai/glm-4.5-air)
  + optional dedicated endpoint/key + no-retry on slot timeout.
- `judge_concurrency.py`: phase-scoped side-judge concurrency override (PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY)
  for the pass duration only (composition-time cap unchanged) + BOUNDED `acquire_judge_slot(timeout=)` (JudgeSlotTimeout)
  so a wedged slot degrades ONE row to a disclosed prior instead of freezing + a progress log.
- `multi_section_generator.py`: wraps the credibility `to_thread` in `credibility_pass_concurrency(...)`.

HALF B — BANK-BEFORE-WALL (never discard computed corroboration):
- `credibility_pass.py`: `deadline_monotonic` threaded through run_credibility_analysis → _run_chain →
  _assemble_baskets → _run_member_verifies. At the SOFT deadline, the verified prefix is BANKED verbatim and
  the rest filled with `_DEADLINE_SKIP_VERDICT = (UNSUPPORTED, UNVERIFIED, judge_unavailable=True)` — disclosed,
  UNDERCOUNT-only. Plus a defense-in-depth phase-A/B budget split (PG_CREDIBILITY_PASS_PHASE_A_FRAC) so phase A
  can't starve phase B's banking.
- `multi_section_generator.py`: computes `deadline = monotonic() + wall × PG_CREDIBILITY_PASS_BANK_FRAC` (0.85)
  and passes it; the `asyncio.wait_for` wall stays ONLY as the hang backstop.
- `run_gate_b.py`: slate `PG_CREDIBILITY_PASS_WALL_S` 3000 → 6000 (sized for ~999 members; still ≪ run-wall 14400).

## FAITHFULNESS (the ONLY hard gate — verify this HARD)
The credibility pass is ADVISORY. Claim of neutrality to VERIFY:
- Banked members carry GENUINE ENFORCE-entailment verdicts from the FROZEN engine (verify_fn injected, called-not-edited).
- A skipped/deadline member is UNSUPPORTED + disclosed → it can only UNDERCOUNT corroboration, never SURFACE an
  ungrounded claim. Every surfaced enrichment sentence still re-passes the UNCHANGED strict_verify in _run_section.
- ZERO edits to strict_verify / NLI entailment / 4-role D8 / span-grounding. Selection/breadth rank on
  authority_score (weight_mass.py §148), NOT the LLM credibility — so the hybrid/skip does NOT move selection.
- CONFIRM no critical function is ZEROED: every source stays weighted (LLM or prior); the entailment leg is NOT
  reduced; W8 retrieval tiering untouched.

## TESTS
- `tests/polaris_graph/test_credibility_pass_bank_before_wall.py`: 10/10 pass (legacy no-deadline byte-identical;
  serial+parallel banking KEEP-ALL bounded zero-post-expiry-calls; banked SUPPORTS member flows through REAL
  selection → the "Corroborated Weighted Findings" SectionPlan is built; the REAL canary returns "present" on that
  shape and still fails-closed on the box1 shape; phase-A budget cap honored).
- Existing credibility + judge-concurrency tests: green. 49 neighboring tests pass (3 area failures are PRE-EXISTING —
  reproduce with the changes stashed).

## PROVENANCE NOTE (full honesty)
credibility_pass.py was briefly reverted by a parallel session then re-applied — the tree you review is the final
COMBINED state. The phase-A/B split is defense-in-depth (a0cf verdict: NOT load-bearing; the base bank + the pin below
already guarantee surfacing). It is kept because it is tested (10/10) and harmless. If you judge it should be removed
for minimality, say so (P3).

## EXACT box2 RELAUNCH FLAGS (verify these make surfacing UNCONDITIONAL)
```
PG_CREDIBILITY_PASS_WALL_S=6000
PG_CREDIBILITY_PASS_BANK_FRAC=0.85
PG_CREDIBILITY_JUDGE_POOL_WALL_S=2400   # THE PIN: phase-A self-bound << bank_deadline(5100) so phase B ALWAYS banks
PG_CREDIBILITY_PASS_MAX_INFLIGHT=20
PG_BREADTH_ENRICHMENT_ENABLED=1
PG_CREDIBILITY_JUDGE_MODEL=z-ai/glm-4.5-air
PG_CREDIBILITY_JUDGE_HYBRID_TIERS=T1,T2,T6,T7
PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY=10
PG_CREDIBILITY_JUDGE_SLOT_WAIT_S=180
```
Invariant to check: `PG_CREDIBILITY_JUDGE_POOL_WALL_S (2400) < PG_CREDIBILITY_PASS_WALL_S × PG_CREDIBILITY_PASS_BANK_FRAC (5100)`.

## ASK / OUTPUT SCHEMA
Review the diff at `.codex/I-deepfix-001/box2_credibility_combined_fix.diff` (appended below for Codex).
Verify: (1) the two halves COMPOSE coherently (no conflict at the shared files); (2) faithfulness-neutral / NO
critical function zeroed; (3) the corroboration layer WILL surface on the rich corpus with these flags; (4) the pin
invariant holds; (5) any real execution risk. Return:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
