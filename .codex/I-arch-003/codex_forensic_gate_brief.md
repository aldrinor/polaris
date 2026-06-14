# I-arch-003 (#1253) — Codex independent forensic gate: LLM model + token/reasoning-cap audit

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (REQUIRED — loose prose is rejected)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Mission (operator directive 2026-06-14, verbatim intent)
"Claude and codex run parallel forensic audit on the model setting and OpenRouter credit left and
reasoning token and output token. Model must be right. Credit must be sufficient. Token setting go to
max. Remove all of the wrong LLM and wrong token cap. Only when both Claude and Codex agree that all land
mines are cleared do we move forward. If you don't know the allowed max token for a model, read its
OpenRouter API doc — don't guess."

This is **clinical-safety-critical** (CLAUDE.md §-1.1): audit line-by-line, no metadata/pattern shortcuts.
You are the INDEPENDENT second auditor. A Claude forensic ledger is attached (Appendix C); **do not merely
agree with it — independently verify it and find anything it missed.**

## What you are auditing
The committed I-arch-003 change set (this branch, `bot/I-arch-002-no-dumping`):
- commit range `98e07d33~1..HEAD` (run `git log --oneline 98e07d33~1..HEAD`):
  - 98e07d33 governance lock (CLAUDE.md §9.1.8 + AGENTS.md)
  - a4498223 / (earlier #1251 #1252) retire stale **gemma** code-defaults on credibility / entailment /
    semantic-conflict judges -> z-ai/glm-5.1
  - 6a2d3fb3 retire 5 closed-source obsolete scripts (-> scripts/_retired_2026_06_14/) + fix 2 live gemma
    script-defaults (pathB_run_gate.py, run_rehearsal.py)
  - 2848fbdc un-starve live reasoning-first calls (clinical_generator/real_completion.py,
    api/disambiguation_route.py, tools/react_agent.py InterpretationCritique)
  - 38667753 generator -> fp8 full-cap providers + PG_REASONING_FIRST_HARD_CAP 16384->384000
  - 7af2a109 generator chain by measured reliability (WandB first, drop flaky Parasail)
  - 497fafea 4-role + generator token budgets to min-of-chain max (live OpenRouter caps)
- Read `git diff 98e07d33~1..HEAD -- src/ config/ scripts/` for the full diff.

## Appendix A — the locked architecture (config/architecture/polaris_runtime_lock.yaml, operator-signed)
- generator = `deepseek/deepseek-v4-pro`
- mirror    = `z-ai/glm-5.1`
- sentinel  = `minimax/minimax-m2`
- judge     = `qwen/qwen3.6-35b-a3b`
RUNTIME RULE: NO `gemma`, NO closed-source vendor models (`openai/* gpt*`, `anthropic/* claude*`,
`google/gemini*|gemma*`) on the live inference path (sovereignty). Verify NONE remain on the live path.

## Appendix B — the token-clamp mechanism + live OpenRouter caps (verified 2026-06-14)
- `src/polaris_graph/llm/openrouter_client.py` floors+caps max_tokens to [32768, 384000] ONLY when the
  model is in `_REASONING_FIRST_MODELS` = { z-ai/glm-5, glm-5-turbo, glm-4.7, glm-5.1,
  deepseek/deepseek-v4-pro, deepseek/deepseek-v4-flash } (openrouter_client.py ~1656/1667/1703/1734).
  -> a tiny max_tokens on one of those 6 models is AUTO-FLOORED to 32768 (NOT a land mine).
  -> a tiny max_tokens on ANY OTHER reasoning model passes RAW = starvation (the #1251/#1252 class).
- The 4-role transport `src/polaris_graph/roles/openrouter_role_transport.py` sets its OWN budgets and
  does NOT use that clamp. Under `allow_fallbacks:false` the binding cap = MIN max_completion_tokens
  across the role's provider chain. Live per-provider caps (GET /api/v1/models/<m>/endpoints, 2026-06-14):
  - deepseek-v4-pro: WandB/Parasail=1,048,576 (=CONTEXT, not usable output), Baidu/NextBit/SiliconFlow/
    Novita/Alibaba/AtlasCloud=393,216, DeepSeek/StreamLake=384,000, DeepInfra=16,384(fp4), Wafer=65,536.
    Generator chain min-of-chain = 384,000. Hard cap set to 384,000. OK.
  - glm-5.1 (mirror): AtlasCloud=202,752, Z.AI/Baidu/Novita/SiliconFlow/Ambient/Parasail=131,072,
    DeepInfra=32,768(fp4). Re-pinned chain [atlas-cloud,z-ai,baidu,novita,gmicloud]; min-of-chain=131,072.
    Transport max_tokens=131,072, reasoning.max_tokens=100,000. Bake-off proved 3/3 blank-clean on all 5.
  - minimax-m2 (sentinel): Google/AtlasCloud=196,608, Novita/Minimax=131,072. Chain
    [google-vertex,novita,atlas-cloud,minimax]; min-of-chain=131,072. Transport decomp max_tokens=131,072. OK.
  - qwen3.6-35b-a3b (judge): WandB=262,144, Io-Net=262,140, AtlasCloud=65,536(DROPPED). Chain [wandb,io-net];
    min-of-chain=262,140. Transport max_tokens=262,140. OK.
- OpenRouter credit balance 2026-06-14: $167.48 remaining of $650. (Flag if you judge this insufficient for
  the planned smoke + bounded run; the operator can top up.)

## Specific things to verify (independently — read the code, do not assume)
1. **Model conformance:** grep the live path for any remaining `gemma` / closed-source default. The Claude
   pass claims all are retired — verify, including yaml configs and PG_*_MODEL env defaults.
2. **No provider-cap 400s:** for every transport/generator budget, confirm it does NOT exceed the MIN
   max_completion_tokens of its provider chain under allow_fallbacks:false (the failure is a hard 400
   "requested N > max M", exactly like the deepseek 1,048,576 case). This is the highest-risk class.
3. **No residual starvation:** any reasoning model NOT in _REASONING_FIRST_MODELS with max_tokens < ~2000
   on the live path. EXCLUDE deliberate liveness probes (validate_reasoning "2+2") and short-label
   classifiers on non-reasoning models.
4. **Mirror blank-safety:** confirm raising reasoning.max_tokens 4000->100000 does NOT re-introduce the
   GLM empty-200 blank (the invariant is reasoning_cap << total max_tokens; bake-off evidence in Appendix C).
5. **No faithfulness gate relaxed:** confirm none of the strict_verify / NLI / 4-role / span-grounding
   gates were weakened — these are usage-billed ceiling changes only.
6. **Self-host (GPU/vLLM) route — lower priority, flag only:** the imminent beat-both run is CPU-only via
   OpenRouter (openrouter_role_transport), NOT the self-host adapters. But for governance completeness:
   `src/polaris_graph/roles/judge_adapter.py:35 _DEFAULT_MAX_TOKENS = 16` — assess whether that is safe
   (choice-constrained enum decoding with server-side reasoning separation) or a latent starvation on the
   GPU route. Sentinel self-host floor is 3000 (openai_compatible_transport.py:70). These are NOT blockers
   for the OpenRouter run; classify P2/P3 unless you find the GPU route is actually wired into the
   imminent run path.

## Appendix C — Claude forensic ledger + the fixes you are verifying

The full Claude parallel-forensic ledger is committed at `.codex/I-arch-003/forensic_ledger.md`
(read it). Bottom line from that pass:

- **3 real land mines found, all the SAME un-floored reasoning-first mechanism** (branch 2 of the
  openrouter_client._call elif chain, `elif reasoning_enabled:`, had no 32768 floor; branch 3 does):
  - P0 `evidence_deepener.py:294` `_extract_named_studies` — `reason(effort=high, max_tokens=2000)`
  - P0 `evidence_deepener.py:815` `_mechanism_search` — `reason(effort=high, max_tokens=500)`
  - P1 `storm_interviews.py:1108` outline — `generate_structured(reasoning_enabled=True, 4096)`
  Two were freshly re-starved THIS session (effort raised to high, max_tokens left tiny). All three
  are force-on in the benchmark (`run_gate_b.py:454,810` deepener; `:453` STORM) and fail SILENTLY
  into deterministic fallbacks (so "gates green" would not catch them — only the line-by-line read did).
- **Model-lock: CONFORMANT.** All 4 locked roles resolve correctly; no gemma/closed-source on any live
  default (only inert pricing keys + the family-segregation guardrail detectors + an off-path legacy
  `config/settings/models.yaml` gemini config that the sweep does not import).
- **Provider-caps: no overruns.** 4-role budgets = min-of-chain; generator hard cap 384000 matches the
  fp8 chain.

**These 3 land mines are now FIXED** in commit `fa80b556` (HEAD) — so the audit range is
`98e07d33~1..fa80b556`. The fix is:
1. ROOT CAUSE — `openrouter_client.py` branch 2 now mirrors branch 3's floor (32768) + cap (384000)
   for `_REASONING_FIRST_MODELS` ONLY (GLM stays on its branch-1 4096 floor; non-reasoning-first models
   keep their small budgets — narrow by design).
2. TACTICAL — deepener extract/mechanism default 32768 (env `PG_DEEPENER_EXTRACT_MAX_TOKENS` /
   `PG_DEEPENER_MECHANISM_MAX_TOKENS`); STORM outline default 4096->32768.
3. TEST — `tests/polaris_graph/test_reasoning_first_branch2_floor_iarch003.py` (5 tests, no network):
   deepseek reason() 500/2000/4096 -> floored 32768; 900000 -> capped 384000; qwen non-reasoning-first
   keeps 500. 17 pre-existing reasoning-first tests still green.

**Your job:** (a) VERIFY the fa80b556 fix is correct — the branch-2 floor is narrow, does not change
GLM/non-reasoning-first behavior, cannot 400 on the generator chain, and does not touch any faithfulness
gate; (b) INDEPENDENTLY re-audit the live run path for ANY model-lock violation, token starvation, or
provider-cap mismatch the Claude ledger missed; (c) return the schema verdict. APPROVE iff zero P0/P1
remain after fa80b556.
