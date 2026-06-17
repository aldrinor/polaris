#!/usr/bin/env bash
# GLM-5.2 vs DeepSeek-V4-Pro GENERATOR comparison arm (branch bot/glm52-vs-deepseek-compare).
#
# WHAT: re-run the SAME 5 questions on the SAME 5 corpus snapshots, with ONLY the generator swapped
#       to z-ai/glm-5.2 (the DeepSeek arm = outputs/beatboth_fixed on the original 5 boxes; this arm =
#       outputs/glm52_compare on 5 NEW boxes). Generator-only bake-off; everything else identical
#       (same I-arch-007-fixed pipeline: death-fix + breadth + hardening).
#
# VOTER SLATE (operator-chosen, anti-self-bias, all 4 distinct families):
#   generator = z-ai/glm-5.2        (family glm)   <- the upgrade under test
#   mirror    = deepseek/deepseek-v4-pro (deepseek) <- swapped off GLM-5.1 so GLM is not self-judged
#   sentinel  = minimax/minimax-m2  (minimax)      (unchanged)
#   judge     = qwen/qwen3.6-35b-a3b (qwen)        (unchanged)
#   -> generator(glm) + mirror(deepseek) = DIFFERENT families => family-segregation check passes; no override hack.
#
# PROVIDER: Friendli first (99.94% OpenRouter uptime, 1,048,576 max output, reasoning + structured)
#           -> "Highest Stability Server"; existing providers kept as fallback for the deepseek/minimax/qwen roles.
# REASONING: generator at MAX (xhigh); generous output cap (GLM-5.2 reasoning-first; tokens = a CAP not a target).
#
# PER-BOX LAUNCH (run from /root/polaris, after the corpus_snapshot is copied to
#                 outputs/glm52_compare/<domain>/<slug>/corpus_snapshot.json):
#
#   cd /root/polaris
#   export PYTHONPATH=/root/polaris:/root/polaris/src
#   # --- model slate (GLM-5.2 generator + DeepSeek mirror) ---
#   export PG_GENERATOR_MODEL=z-ai/glm-5.2
#   export PG_MIRROR_MODEL=deepseek/deepseek-v4-pro
#   export PG_SENTINEL_MODEL=minimax/minimax-m2
#   export PG_JUDGE_MODEL=qwen/qwen3.6-35b-a3b
#   # --- provider: Friendli first (highest stability) + fallbacks for the role models ---
#   export OPENROUTER_PROVIDER_ORDER=friendli,io-net,cloudflare,novita,baidu,siliconflow,deepseek,wandb
#   export OPENROUTER_ALLOW_FALLBACKS=true
#   # --- MAX reasoning + generous output cap for the GLM-5.2 generator ---
#   export PG_GENERATOR_REASONING_EFFORT=xhigh
#   export PG_REASONING_FIRST_MIN_MAX_TOKENS=65536
#   # --- carry env (same as the DeepSeek arm; slate force-sets breadth/wall/total-deadlines/caps) ---
#   export PG_ENTAILMENT_TOTAL_S=45 PG_ROLE_CALL_TIMEOUT_S=900 PG_ALWAYS_RELEASE=1 \
#          PG_REDACT_HELD_UNSUPPORTED=1 PG_FOUR_ROLE_REASONING_EFFORT=medium \
#          PG_AUTHORIZED_SWEEP_APPROVAL=1 PG_MAX_COST_PER_RUN=60 PG_RESUME_REUSE_POSTGEN=0
#   RD=outputs/glm52_compare/<domain>/<slug>
#   setsid nohup /opt/conda/bin/python -m scripts.dr_benchmark.run_gate_b \
#     --only <slug> --resume --out-root outputs/glm52_compare \
#     > "$RD/glm52_launch.log" 2>&1 &
#   echo $! > "$RD/glm52.pid"
#
# THE 5 (same slugs/domains as the DeepSeek arm; corpus copied from the matching beatboth_fixed box):
#   Q72 workforce/drb_72_ai_labor   Q76 clinical/drb_76_gut_microbiota_crc   Q75 clinical/drb_75_metal_ions_cvd
#   Q90 policy/drb_90_adas_liability Q78 clinical/drb_78_parkinsons_dbs
#
# VERIFY on launch: log shows OpenRouter client model=z-ai/glm-5.2 + BEHAVIORAL_CANARY_OK + no
#   family-segregation RuntimeError; the 4-role transport resolves mirror=deepseek-v4-pro.
# COMPARE on completion: §-1.1 line-by-line audit of glm52_compare/<q>/report vs beatboth_fixed/<q>/report
#   (same corpus) + vs gpt_5_5_pro/gemini_3_1_pro — faithfulness, breadth (cited sources), writing, structure.
