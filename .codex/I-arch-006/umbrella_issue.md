## I-arch-006 — Beat-both readiness: 19-fix forensic campaign + bounded parallelism + 5-VM scale-out run

**Context.** Five forensic investigations (live monitoring of 5 runs, drb_75 + drb_78 hang forensics, the drb_72/76/90 deep-read, and the Marlin/AB-MCTS + SOTA + Codex-gated plan) consolidated into one bug list: `outputs/audits/marlin_v2/MASTER_FIX_LIST.md` + `state/forensic_bug_list.md`. 4 of 5 beat-both runs died or hung. This issue executes the fixes and re-runs.

**Non-negotiables.** Faithfulness NEVER relaxed (the only hard gate stays the verify engine). Open-weight models only (deepseek-v4-pro / glm-5.1 / minimax-m2 / qwen3.6 — no gemma, no closed). §-1.3 DNA: weight-don't-filter, consolidate-don't-drop, basket faithfulness, no caps/targets/thinners.

### The 19 fixes
**Run reliability (must finish at all):**
1. Unified TIGHT TOTAL DEADLINE on every LLM call — F33 (generator stream read-timeout) + HANG-J1 (unbounded entailment judge) + HANG-J2 (CLOSE_WAIT socket leak) + BUG-22 (18–32 min generator distill_map/generate calls). One `httpx.Timeout` + per-call `asyncio.wait_for` total deadline (gen ~600–900s, judge bounded) + retry on fresh socket + null-content retry before json.loads.
2. BUG-21 — always write a terminal manifest (`status=error_*`) on ANY exit (try/finally around verify/finalize) + serialize/cap runs (superseded at run-time by the 5-VM scale-out).

**Source quality / completeness (the lever vs ChatGPT):**
3. BUG-15 — Zyte actually fires on the paywalled-anchor path; on fire-and-fail, fall through to other paid modes, don't gap-disclose.
4. BUG-14 — stub/empty/DOI-mismatch fetch → mark `fetch_failed` + re-fetch (Zyte), NEVER silently relevance-drop; T1 flows at weight.
5. BUG-1 — carry source titles onto the evidence row + outline digest (stop blank-title guessing).
6. BUG-20 — surface credibility weight to the generator so it prefers T1 spans (weight, not drop).

**Gate integrity (protects the edge vs Gemini):**
7. BUG-19 (now HIGH/structural) — input hygiene: strip crawl chrome + drop non-assertional/table/DOI fragments BEFORE finding-extraction AND before the entailment gate (a 404 page must never be "verified"). NOT a gate relaxation.
8. BUG-7 — completeness/contraindication applicability from a real drug/intervention detector, not the routing label; fail-closed/disclose on ambiguity (clinical-safety: regression on drug + non-drug Qs).
9. BUG-17 — contradiction grouping only on same true-subject; unknown-subject → disclosure not blanket-skip; don't apply the clinical drug-trial schema to non-clinical claims.
10. BUG-18 — remove the hardcoded section-count breadth targets ("EXACTLY 5", "never only 3 if ≥100 rows", "target 12–20", retry hard-requires 5–6); sections follow evidence + disclose when thin. (§-1.3 ban.)

**Coverage / retrieval:**
11. BUG-8 — weight off-topic down (not drop) + budget disclosure; harvester carries a snippet so the topical screen can work.
12. BUG-4 — surface the hidden fetch/search caps (disclose, env-overridable), don't silently throttle breadth.

**Observability / robustness:**
13. BUG-3 — heartbeat the REAL sub-phase (entailment N/total) + true cost, not frozen at generation_started.
14. BUG-23 — downgrade `check_fa2_competitor_outputs_present` from a hard GateError to a non-fatal warning.
15. BUG-2 — reasoning effort + max_tokens always MAX on the generation call.
16. BUG-9 — disclosed STORM time reserve for the outline (not a coverage target).
17. BUG-5 — clean stale `gate_b_query_crash.json` on a fresh attempt.
18. BUG-13 — normalize `AgenticRoundAnalysis.convergence_assessment` schema (dict-vs-string).
(verify-deployed) BUG-12 — confirm `ddgs` installed in the run venv.

**Speed (fix #19, folded in):**
19. Bounded INTERNAL parallelism — parallel entailment verifier (~8–16 concurrent) + parallel section generator (~5–7), questions SERIAL per box. The consolidation/basket dedup stays a deterministic post-step; each section still independently verified. Faithfulness-neutral (verdicts are independent; concurrency changes timing, not verdicts).

### Process
1. Claude builds all fixes — parallel agents where files don't collide; Claude edits the HOT files directly (openrouter_client.py, entailment_judge.py, multi_section_generator.py, run_honest_sweep_r3.py, live_retriever.py).
2. Claude self-tests each — unit test + offline smoke.
3. ONE consolidated Codex diff review of the whole batch (faithfulness checklist: no gate relaxed, no new silent-drop). 1–2 iters. The ~6 faithfulness/clinical-touching fixes get the careful read.
4. Behavioral preflight — 1-query canary that exercises the fixed paths (deadline, Zyte firing, boilerplate strip), per "config-flag preflights lie."
5. Re-run the 5 golden questions — **one question per VM across 5 independent VMs in parallel** (scale-out; cost authorized for speed). Then §-1.1 line-by-line audit vs gpt_5_5_pro + gemini_3_1_pro.

### Acceptance criteria
- All 19 fixes present + unit-tested; ONE Codex diff review APPROVE (0 faithfulness relaxation, 0 new silent-drop).
- Behavioral preflight green on a clinical + a non-clinical canary.
- 5/5 questions produce a complete report.md + manifest (no hang, no silent death).
- §-1.1 line-by-line audit completed vs both competitors; beat-both assessed honestly (hypothesis → evidence).
- Faithfulness gates byte-equivalent in strictness; only input hygiene + timing changed.
