# RESUME — where we are (2026-06-14, before operator computer restart)

## DONE
- **I-arch-003 (token/model governance):** complete, DUAL-READY (Claude + Codex both APPROVE, 0 P0/P1).
  Committed + pushed + deployed to VM. Branch `bot/I-arch-002-no-dumping`, HEAD ~`54947b91`
  (token fixes at 497fafea → fa80b556 → 70fdd33c → f1746920). 4-role + generator budgets set to
  min-of-chain max; 3 reasoning-ON starvation land mines fixed (branch-2 floor); model-lock conformant.
- **Smoke validation run (drb_72_ai_labor) on VM:** PROVED all token fixes work live (StormOutline
  floored 32768; 616 credibility calls no-freeze; 917 entailment 0-empty; weight-and-consolidate 656
  sources collapsed=0; real judge reasoning + honest NEUTRAL verdicts + Zyte firing). BUT it DIED at
  the finish: `status=error_unexpected`, cost $6.74 — a section hit the smoke-inherited 600s wall-clock
  twice + no gather exception isolation → whole run crashed, 3 hours discarded.
- **I-arch-004 (pipeline chokepoint forensic):** complete. Workflow wkrdog8e5, 12 agents, 74 findings
  (6 P0 / 21 P1 / 29 P2 / 18 P3). Full ledger: `.codex/I-arch-004/chokepoint_ledger.md` (committed).

## NEXT — the fixes (pending, all Codex-gated, all .env-ified, faithfulness gates NEVER relaxed)
Priority order from the ledger §6:
1. **P0 crash isolation:** add `return_exceptions=True` + map exceptions to a gap-stub SectionResult at
   `multi_section_generator.py:5509, 5550, 6432` (stub path ~321-347). One slow section = a GAP, not a
   whole-run kill. Keep the CredibilityPassError fail-loud carve-out (:5856).
2. **P0/P1 timeouts (recalc off the REAL 64000 budget, not stale 16384):** `PG_SECTION_WALLCLOCK_SECONDS`
   ~11000s (calc §2); `PG_GENERATOR_LLM_TIMEOUT_SECONDS` 1800→~6500; `run_gate_b` preflight must FAIL LOUD
   if any resolves below the calculated floor (stops smoke-value inheritance forever).
3. **Checkpoints (lost 3 hrs):** corpus_snapshot after retrieval (highest value) + per-section + composed
   snapshots at the 3 cancel-probe boundaries (run_honest_sweep_r3.py:2817,5909,7106) + checkpoint.json
   stage-pointer + resume flag. HARD INVARIANT: checkpoints carry DATA, never VERDICTS — always re-run
   strict_verify/NLI/4-role on reload (no faithfulness bypass).
4. **2 active outer-tighter-than-inner stranglers:** `PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS` 300→≥1800;
   semantic_conflict_detector `_JUDGE_TIMEOUT_S=30.0` hardcoded + fails-open → `PG_SEMANTIC_CONFLICT_JUDGE_TIMEOUT_S`=120.
5. **De-throttle + .env-ify:** retrieval breadth 12/12/40 → full-capability; .env-ify the call-site literals
   (outline_max_tokens=2500, section_temperature=0.3, resolver 3/15 heuristic, etc. — full list in ledger §4).
6. **Salvage run:** resume-from-middle pipeline using the drb_72 run's artifacts (corpus + 917 verified
   claims) so we don't re-run 3 hours.

## RUN ENV NOTES
- Branch: `bot/I-arch-002-no-dumping`. VM `polaris_run` @ f1746920 (RE-DEPLOY after fixes land).
- Run env MUST use `/home/ubuntu/polaris_run/.env` (has Zyte key). DO NOT use the smoke slate
  (`.smoke_env.sh`) for a real run — its 600s wall-clock + 300s LLM timeout are the killers.
- VM runner = `docker exec -d arch002_runner sh /app/<launch>.sh` (binds /home/ubuntu/polaris_run→/app;
  use `python` inside the container; do NOT `source .env` in sh — app loads it via dotenv).
