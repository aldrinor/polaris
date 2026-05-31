# Codex gate — OpenRouter verifier availability + sovereignty: live-accurate?

ADVERSARIAL §-1.1 auditor. Operator asked "is there any verifier model I can get OpenRouter to access?" A workflow
checked the live OpenRouter catalog (sub-agents may have leaked the forbidden advisor tool — re-verify yourself via
WebFetch). Confirm/refute the availability, prices, and the sovereignty characterization. These drive a real spend/
architecture decision. Output YAML verdict FIRST. iter 1.

```yaml
verdict: ACCURATE | NEEDS_CORRECTION
availability_correct: "<are the 3 locked-model findings right?>"
price_errors: [...]
sovereignty_characterization_fair: <true|false>
the_one_correction: "<or none>"
honest_one_line: "<for the operator>"
```

## Claims to re-verify on the LIVE OpenRouter catalog (WebFetch the model pages)
1. Mirror cohere/command-a-plus: NOT on OpenRouter (exact slug absent); same-family cohere/command-a (111B) IS, at
   $2.50/M in, $10.00/M out.
2. Sentinel ibm-granite/granite-guardian-4.1-8b: NOT on OpenRouter; the ibm-granite namespace has only general
   granite-4.1-8b ($0.05/$0.10) + granite-4.0-h-micro — NO dedicated hallucination/RAG-grounding guardrail. CLAIM:
   no purpose-built grounding classifier (Granite Guardian / ShieldGemma / GuardReasoner / MiniCheck) is on
   OpenRouter; only meta-llama/llama-guard-4-12b ($0.18/$0.18) which is content-SAFETY not RAG-faithfulness.
3. Judge qwen/qwen3.6-35b-a3b: YES exact slug, $0.14/M in, $1.00/M out.
4. Alternatives claimed: mistralai/mistral-large-2512 ($0.50/$1.50), meta-llama/llama-3.3-70b-instruct ($0.10/$0.32).
5. COST: ~$2/run API verification (Mirror ~$1.90 dominates at command-a $2.50/$10) vs $130-770 self-hosted GPU →
   ~60-380x cheaper.
6. SOVEREIGNTY: default OpenRouter routes through (largely US) providers, no per-request country filter, doesn't
   disclose provider location by default → BREAKS the clinical "no US LLM vendor at runtime" rule. Provider-pinning
   (only:[...], data_collection:deny, zdr:true) is partial; the real lever is enterprise EU mode at eu.openrouter.ai
   = EU residency but still a US broker (OpenRouter Inc.) = NOT Canadian sovereignty. VERDICT: OK for non-sovereign
   proving runs, BREAKS the sovereign production gift.

## Your ruling
Re-verify the availability + prices on the live pages (flag any stale/wrong price). Is the Sentinel-gap claim (no
RAG-faithfulness guardrail on OpenRouter) correct? Is the sovereignty characterization FAIR (esp. eu.openrouter.ai
= EU-residency-via-US-broker ≠ Canadian sovereignty)? The single most important correction or 'none'. Honest one-liner.
