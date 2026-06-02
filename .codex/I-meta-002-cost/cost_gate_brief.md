# Codex math gate — is POLARIS full-power cost-per-run SOLID, or guessing?

ADVERSARIAL §-1.1 cost auditor. The operator demands REAL, SOLID math — "if we don't have solid math, nothing
works." A workflow produced the cost table below (its sub-agents may have leaked a forbidden advisor tool — do
NOT trust their self-checks; re-verify against the repo + live prices yourself). Rule whether the per-run math
is SOLID. Verify the LOAD-BEARING numbers file:line and web-check the prices. Output YAML verdict FIRST. iter 1.

```yaml
verdict: SOLID | NEEDS_CORRECTION | NOT_SOLID_YET
wrong_or_unverifiable_numbers: [...]
internal_contradictions: [...]
arithmetic_errors: [...]
the_measured_anchor_is: "<$0.064 or $0.7477 — which is the real shallow-run cost, and is the ContextVar-undercount claim true?>"
gpu_topology_correct: <true|false>   # does command-a-plus actually need 9xH100+1xA100?
expected_cost_per_run: "<your own grounded number or band, both amortization models>"
is_it_solid_enough_to_act_on: <true|false>   # or must the operator buy ONE warm run first?
honest_one_line: "<for the operator>"
```

## The math to verify (full arithmetic in outputs/I-meta-002/cost_synthesis_full_power_per_run.md — READ IT)
MEASURED ANCHOR (the 12x correction): workflow claims the shallow tirzepatide run cost $0.7477 (re-summed
logs/pg_cost_ledger.jsonl, 138 entries = $0.7371 generate + $0.0106 entailment_judge), NOT the $0.064 in
manifest.json — claiming manifest cost_usd is a per-asyncio-task ContextVar UNDER-count. VERIFY: filter the
ledger to THIS run's entries and sum; read the cost-tracking code to confirm/refute the ContextVar-undercount
claim. This is the anchor everything scales from — it MUST be right.
INTERNAL CONTRADICTION to rule on: the file's read-aloud summary (§3) still says "six cents" while the footer
(§4) says $0.7477. Which is correct?
MODELS (config/architecture/polaris_runtime_lock.yaml): generator deepseek/deepseek-v4-pro (hosted);
verifiers self-hosted = mirror cohere/command-a-plus, sentinel ibm-granite/granite-guardian-4.1-8b, judge
qwen/qwen3.6-35b-a3b. VERIFY command-a-plus actual parameter count + bf16 VRAM (workflow says 218B MoE, ~438GB
load) and whether that truly needs 9xH100+1xA100. (NOTE: earlier I told the operator "Command A 111B -> 2x80GB"
— that was the WRONG older model; the lock pins command-a-PLUS. Confirm the corrected sizing.)
GPU PRICE: Vast H100 $2.28/hr x9 + A100 $1.07/hr x1 = cluster $21.59/hr. Verify the arithmetic (9*2.28=20.52
+1.07=21.59) AND web-check Vast H100/A100 current hourly.
PER-RUN BANDS: Model A warm steady-state = $21.59/hr x wall-clock 1.17-1.54hr + API $0.90-1.79 = ~$26-35/run.
Model B dedicated-over-golden-5 = cold-start (box held 7.93-12.80hr) /5 = ~$35-57/run; batch ~$185-295.
API/token subtotal $0.90 sticker / $1.79 billed (Serper $0.216 + DeepSeek gen $0.442+$0.189 + gap $0.046 +
deepener $0.006). DeepSeek V4 Pro price $0.435/M in, $0.87/M out (openrouter.ai/deepseek/deepseek-v4-pro) —
web-verify. Generation tokens scaled gen-cap 20->50 (2.5x) + length x2.0 from the measured ledger.
CLINICALTRIALS.GOV: workflow says it fail-closes 403, not wired (domain_backends.py:452-453) — verify (a
currently-dead channel changes the "free clinical channels" story).

## The decisive question
The workflow's OWN biggest-uncertainty flag: the 8-round iterative loop is a TARGET the shipped code does NOT
execute (shipped = ONE main pass + <=4-query R6 gap), so the 70-92min full-power wall-clock is UNMEASURED; and
GPU is >90% of cost, so a 2x wall-clock error swings per-run from ~$15 to ~$60. The 4-role gate also has ZERO
measured token data. RULE: is the ~$30 warm / ~$45 dedicated figure SOLID enough for the operator to act on, or
is the honest answer "you cannot have solid per-run math until you buy ONE warm full-power run to measure
wall-clock + 4-role tokens"? Give your own grounded band and say plainly which it is.
