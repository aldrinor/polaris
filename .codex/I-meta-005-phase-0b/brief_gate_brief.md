HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding. Reserve P0/P1 for real execution risks; rest P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex BRIEF gate — Phase 0b (#984) RE-DIAGNOSIS of gap #18

Review `.codex/I-meta-005-phase-0b/brief.md` (READ IT). It is a RE-DIAGNOSIS that
replaces the prior union-rescue brief, which your earlier verdict
(`codex_brief_verdict.txt`) refuted. The new brief proves — by running the REAL
production verifier OFFLINE (stub judge, zero spend; harnesses
`rediagnose_drop_cause.py` + `rediagnose_drop_cause_2.py`) — exactly which regime
DROPS a grounded multi-source reasoning sentence today:

- CONFIRMS your P1 #1: the 2-span A+B union sentence WITH tokens ALREADY PASSES
  (`verify_sentence_provenance` judges `" ".join(aggregated_span_text)` at
  provenance_generator.py:1199). A duplicate union rescue is dead.
- CONFIRMS your P1 #2: `_get_judge()` defaults to `google/gemma-4-31b-it`
  (entailment_judge.py:79,132), NOT the locked qwen/granite. Brief §4 reconciles
  honestly (keep the seam model-agnostic in 0b; judge-model swap is a separate Issue).
- CONFIRMS your P1 #3: judge fails OPEN as `("ENTAILED","judge_error:…")`
  (entailment_judge.py:147,261) and rides through (:1204). Brief §5.3 mandates a
  hard return-shape DROP test.

The REAL gap-#18 delta (brief §3): Delta A = `no_provenance_token` auto-drop
(:957-964) on the token-less analyst-synthesis layer, which is ALSO structurally
non-repairable (sentence_repair.py `is_repairable` False + token-set-preservation
rejects added tokens). Delta C = non-numeric NEUTRAL has no local-window rescue
(:1244 decimal precondition). Delta B = content-overlap floor. Delta D = fail-open.

Question for you to rule on: is the §5.1 minimal-multi-span-attribution approach for
token-less reasoning the right industrial technique (ALCE leave-one-out citation
precision vs AIS/MiniCheck atomic attribution)? And: must 0b adopt the locked 4-role
Judge/Sentinel NOW, or is the model-agnostic seam (brief §4) acceptable for 0b scope?

Output the §8.3.9 YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
