# Codex logic gate — is the relevance-driven corpus math LOGICALLY SOUND + loophole closed?

ADVERSARIAL §-1.1 auditor. The operator caught a fatal loophole in a prior cost model: the pipeline discovers
~1,000 sources but truncates to a fixed top-K (evidence_rows[:PG_LIVE_MAX_EV_TO_GEN]) — dropping high-value sources
by POSITION, not quality. A workflow produced the redesign below (full doc: outputs/I-meta-002/corpus_relevance_
driven_logic.md — READ IT). Sub-agents may have leaked the forbidden advisor tool — re-verify yourself. Rule whether
the redesign is LOGICALLY SOUND and the loophole is genuinely closed, and whether the numbers hold. YAML verdict FIRST. iter 1.

```yaml
verdict: SOUND | NEEDS_CORRECTION | NOT_SOLID_YET
loophole_genuinely_closed: <true|false>   # does relevance-threshold + map-reduce remove ALL position-based silent truncation?
overfit_or_unsupported_models: [...]       # esp. claims(N)=24.7*N^0.489 (a 2-point fit) and wall=0.9+0.0145*N
wrong_or_unverifiable_numbers: [...]
four_role_not_wired_confirmed: <true|false>  # grep: are Mirror/Sentinel/Judge actually absent from the sweep path?
relevance_density_honest: "<is '~120-200 of ~1000 relevant, ~800 noise' + the TREC-2020 29% anchor defensible?>"
more_sources_hurts_claim_fair: <true|false>  # is the DeepTRACE/lost-in-the-middle 'covering set not biggest set' framing correct?
expected_cost_at_full_depth: "<your own grounded EU-sovereign $ for the all-relevant run>"
the_one_correction: "<single most important fix, or none>"
honest_one_line: "<for the operator>"
```

## The redesign to rule on (full arithmetic in the doc)
LOOPHOLE: 234 sub-queries x ~12 hits -> ~1,000 candidates, cut at FETCH_CAP=40 (run_honest_sweep_r3.py:1627) then
MAX_EV_TO_GEN=20 (:2266) = ~96% dropped by POSITION, silently (drops go to a best-effort Path-B trace, not a manifest
count). CONFIRMED by me via grep: the [:max_ev] slice + caps exist.
SOUND MODEL: keep every source clearing 3 bars — tier (T1-T4 admissible), relevance (_row_relevance >= adaptive tau,
evidence_selector.py:377), dedup-by-finding (collapse same-finding sources to 1 finding w/ N provenance ptrs). N =
survivors, NO fixed max. MAP-REDUCE: per-source digest call (MAP, parallel, ~2.5k in/0.5k out, never hits context
wall) -> hierarchical synthesis over ~500-tok digests (REDUCE) -> full-span re-read ONLY for cited claims.
HONEST SPLIT: of ~1,000, ~120-200 genuinely relevant kept, ~800 true noise dropped (off-topic/news/marketing/stub/
dup-finding). CLAIM: keeping ALL 1,000 would HURT quality (DeepTRACE / lost-in-the-middle — covering set, not biggest
set). The OLD cap dropped the WRONG ~960 (kept top-40 incl noise, killed relevant past rank 40).
COST f(N) [EU-sovereign 9xH100+1xA100 @ $33.86/hr; claims(N)=24.7*N^0.489 fit through measured (20,107) +
Codex-corrected (200,330); wall=0.9+0.0145*N hr]:
  N=200 -> 330 claims, 3.8hr, $129 EU
  N=500 -> 517 claims, 8.2hr, $277 EU
  N=1000 -> 725 claims, 15.4hr, $523 EU
  N=1500(all-relevant) -> 884 claims, 22.6hr, $770 EU
Generator tokens trivial (<$2.30 even at N=1500); driver = 4-role verifier GPU wall-clock.
CLOSURE BUILD: kill both count-caps -> relevance/tier floors + corpus_funnel manifest block (discovered/dropped-by-
reason/kept/tau); build per-source evidence_reducer (MAP); cluster into findings; re-point synthesis at findings;
WIRE the 4-role verifiers (CLAIM: Mirror/Sentinel/Judge are NOT in the sweep path today, grep=0 — only entailment_judge
+ one external_evaluation run); saturation stop-rule (stop when new-unique-finding rate < ~1/20 for 2 rounds).

## The real risks to rule on
1. Is claims(N)=24.7*N^0.489 a defensible model or an OVERFIT on 2 points? Sanity-check N=1000->725, N=1500->884.
2. Is wall=0.9+0.0145*N honest, or does it under/over-state the 4-role GPU time at high N?
3. Is the relevance-density (~120-200 of 1,000) defensible, or could the real relevant set be much larger (making
   the dump worse) — and does the model still hold if so? (The doc says it slides up the same f(N) curve.)
4. Verify grep: are Mirror/Sentinel/Judge genuinely ABSENT from run_honest_sweep_r3.py's path? (Load-bearing — it
   means the locked 4-role gate is not actually exercised by the shipping run.)
5. Is "keeping all 1,000 hurts" (DeepTRACE/lost-in-the-middle) FAIR, or a convenient excuse to cap? Cite if real.
6. Does the relevance-threshold + map-reduce design ACTUALLY remove all silent position-based truncation, or is
   there a residual hidden cap (context budget per section, dedup over-collapse, fetch concurrency)?

## Your ruling
Is the math LOGICALLY SOUND and the loophole CLOSED? Confirm/refute each load-bearing claim file:line or with a
cited source. Your own grounded full-depth EU cost. The single most important correction. Honest one-line for the operator.
