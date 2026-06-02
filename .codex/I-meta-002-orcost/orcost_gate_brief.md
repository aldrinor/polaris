# Codex math gate — OpenRouter full-unleashed per-run cost table: arithmetic + assumptions sound?

ADVERSARIAL §-1.1 cost auditor. A workflow computed the per-run cost of a full-unleashed POLARIS run on the
OpenRouter open-weight lineup (full table: outputs/I-meta-002/openrouter_full_run_cost.md — READ IT). Verify the
ARITHMETIC and the VOLUME ASSUMPTIONS. Prices were already Codex-verified 2026-05-31 (deepseek-v4-pro $0.435/$0.87,
glm-5.1 $0.98/$3.08, qwen3.6-35b-a3b $0.14/$1.00). Output YAML verdict FIRST. iter 1.

```yaml
verdict: SOLID | NEEDS_CORRECTION
arithmetic_errors: [...]
volume_assumption_concerns: [...]    # are 200 sources / 330 claims / token-per-call reasonable, or under/overstated?
dominant_line_correct: <true|false>  # Mirror GLM-5.1 2-pass = $1.48 = 56%?
total_per_run_honest: "<your own grounded EXPECTED $ + the LOW/HIGH band>"
the_one_correction: "<or none>"
honest_one_line: "<for the operator>"
```

## The table to verify (arithmetic = (in/1e6 * $in) + (out/1e6 * $out))
- Search/discovery: Serper ~$0.30 flat; S2/PubMed/EuropePMC free.
- MAP source-extraction: DeepSeek V4 Pro (per corpus_relevance_driven_logic.md:49), 200 calls, 500k in / 100k out →
  500000/1e6*0.435 + 100000/1e6*0.87 = 0.2175 + 0.087 = $0.3045.
- Generation: DeepSeek, 540k in / 63.6k out → 0.2349 + 0.0553 = $0.2902.
- Mirror verify (2-pass GLM-5.1): 660 calls, 990k in / 165k out → 990000/1e6*0.98 + 165000/1e6*3.08 = 0.9702 + 0.5082
  = $1.4784. DOMINANT (56%).
- Sentinel (self-host Granite Guardian 8B): 330 calls, GPU-amortized $0.50/hr, ~12.5min → $0.104 (band $0.05-0.21,
  whole-hour floor $0.50).
- Judge verify (Qwen): 330 calls, 495k in / 82.5k out → 0.0693 + 0.0825 = $0.1518.
- TOTAL EXPECTED ≈ $2.63. Band: LOW (100 src/180 claims) $1.61; HIGH (350 src/500 claims) $3.86.
- Mirror-output-cap lever: cap to ~100 out-tok → Mirror ~$1.17, total ~$2.32 (-11%).
- Contrast: sovereign GPU path was $129-770/run → OpenRouter ~49-290x cheaper.

## Verify
1. Recompute each line's arithmetic (flag any error). Sum to confirm ~$2.63.
2. Are the volume assumptions reasonable? Esp.: is 1,500 in / 250 out per verifier call right (the verifier sees the
   claim + cited span + instructions)? Is MAP 2,500-in/500-out per source right? Is 540k generation-input right for
   200 digests? If any is under/overstated, give the corrected number + corrected total.
3. Is Mirror really the dominant line at 56%, and is the 2-pass × $3.08-out the cause?
4. Is the Sentinel amortization honest (self-host wall-clock, not per-token), or should the whole-hour $0.50 floor be
   the headline (making total ~$3.01)?
5. Is the ~49-290x cheaper-than-sovereign contrast fair?

## Your ruling
SOLID or NEEDS_CORRECTION. Recompute the arithmetic. Your own grounded EXPECTED per-run $ + LOW/HIGH band. The single
most important correction. Honest one-liner for the operator.
