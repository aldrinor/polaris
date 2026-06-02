
## AGENT SENTINEL (a4730390d3ce76d72)
### analysis fragments:
I'll start by orienting myself: reading the prior rationale docs, then live-verifying the OpenRouter catalog and leaderboards. Let me begin with the prior selection docs and the current architecture lock.
---
These prior docs are from 2026-05-27 and explicitly note that several scores were UNKNOWN/extrapolated, and the operator now demands LIVE-verified OpenRouter slugs + LIVE leaderboard numbers. The docs also predate the OpenRouter-availability hard gate. I need fresh live verification.

Let me load the web tools and the current architecture lock, then start live verification.
---
I have the full context. The current lock has 3 of 4 roles on `vast_self_host` (NOT OpenRouter), which directly conflicts with the operator's new hard gate ("not locked if no OpenRouter access"). Now I need LIVE verification. Let me start with the authoritative OpenRouter catalog via the API, plus the key leaderboards.
---
Critical finding from the live OpenRouter catalog: the current lock's `cohere/command-a-plus` and `ibm-granite/granite-guardian-4.1-8b` are NOT on OpenRouter. What IS on OpenRouter: `ibm-granite/granite-4.1-8b` (the BASE model, not the Guardian variant). This is the central tension the operator flagged.

Let me verify the leaderboards in depth. I'll pull the Granite Guardian README (RAGTruth/LLM-AggreFact numbers), the LLM-AggreFact leaderboard, and search for the key faithfulness specialists and general-LLM-as-judge scores in parallel.
---
Now I have a hard quantitative anchor: the LLM-AggreFact leaderboard with RAGTruth column. Key reads:
- Bespoke-MiniCheck-7B: RAGTruth 84.0, avg 77.4
- Granite Guardian 3.3 8B: RAGTruth 82.2, avg 76.5 (4.1 improves on RAGTruth per IBM)
- Mistral-Large 2 (123B): RAGTruth 85.9, avg 76.5 — a GENERAL LLM scoring high
- Qwen2.5-72B: RAGTruth 81.9, avg 75.6
- Llama-3.3-70B: RAGTruth 82.6, avg 74.5

This is the crux of the Sentinel decision: general large LLMs (Mistral-Large, Llama-3.3-70B, Qwen2.5-72B) are within a couple points of the specialists on RAGTruth. I need the clinical benchmarks (MedHallu, MedNLI, BioNLI) and the specialist license verifications. Let me run those plus confirm the Granite Guardian 4.1 exact RAGTruth number and Bespoke-MiniCheck license.
---
Important confirmations:
- **Bespoke-MiniCheck-7B = CC-BY-NC 4.0 → DISQUALIFIED** for production (matches the rule).
- **MedHallu**: best model F1 only 0.625 on "hard" hallucinations; general LLMs beat medically-fine-tuned LLMs; "not sure" category +38%. So clinical faithfulness is genuinely hard, and a general LLM-as-judge is competitive.

Now let me get the MedHallu per-model F1 table (which models scored what), confirm Granite Guardian 4.1's exact RAGTruth number from IBM's research blog, and check Patronus Lynx's current RAGTruth/HaluBench + license. Let me also verify the deepseek-v4-pro long-form / GDPval generator standing.
---
### fetched web data (11 snippets):
<system-reminder>[Truncated: PARTIAL view — showing lines 1-674 of 849 total (26746 tokens, cap 25000). Call Read with offset=675 limit=674 for the next page, or Grep to find a specific section. Do NOT answer from this page alone if the answer may be further in the file.]</system-reminder>

1	---
2	status: superseded
3	superseded_by: docs/polaris_step_b_full_set_audit_2026_05_27.md
4	superseded_on: 2026-05-28
5	superseded_reason: Step-B audit reached different conclusions on Mirror/Sentinel picks (Cohere Command A+ replaces Kimi K2.6 for Mirror; Granite Guardian 4.1 replaces 3.3 for Sentinel). Operator confirmed Step-B as final.
6	---
7	
8	# POLARIS Per-Role SOTA Open-Weight LLM Validation (2026-05-27)
9	
10	**Mission:** Replace single-composite-score selection (AA Intelligence Index) with
11	per-role validation using role-specific benchmarks. Operator pushback was correct:
12	each of the 4 POLARIS stack roles (generator / mirror / sentinel / judge) has a
13	distinct capability profile and the "highest average" model is not necessarily
14	the highest in any individual role.
15	
16	**Constraints (operator-locked, May 2026):**
17	- Open weights only (any license)
18	- Non-US runtime LLM (open weights on sovereign infra OK)
19	- No hardware ceiling, no time constraint
20	- Latest + strongest + most capable per role
21	- Multi-domain: clinical + legal + financial + regulatory + policy + scientific, EN baseline
22	- Multi-LLM stack OK if each layer earns its keep
23	
24	**Claude's
~~~
1	---
2	status: research_artifact
3	locked_decision: none (advisory research, no architecture lock here)
4	related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
5	---
6	
7	# Deepest research: Open-Source Non-US Clinical RAG Faithfulness, 2026 SOTA
8	
9	**Author:** Claude (Opus 4.7, 1M context) — research executor
10	**Date:** 2026-05-27
11	**Audience:** POLARIS operator + Codex (architectural reviewer)
12	**Constraints:** open-weight only at runtime, no US-vendor LLM at runtime (Anthropic Citations, Vertex Check Grounding, Azure Groundedness all DISQUALIFIED), no time pressure, no fake shit
13	**Supersedes:** `docs/clinical_rag_validation_sota_2026_05_26.md` — the prior report was constrained to a 9-day demo window and recommended Patronus Lynx 8B; **that recommendation is now invalidated** because Lynx v1.1 is CC-BY-NC (non-commercial). See §4.2 for the licence audit and §5 for the corrected recommendation.
14	
15	---
16	
17	## Executive answer
18	
19	**The actual SOTA architecture for sovereign clinical RAG faithfulness in 2026 is a four-layer pipeline that no single team has fully shipped, but each layer has at least one credibly-deployed open-weight non-US instantiation.** From outermost to innermost:
20	
21	1. **Generator: Qwen3-235B-A22B (Apache 2.0) or DeepSeek-V3.2-Exp (MIT)**, NOT DeepSeek V4 Pro. Both are open-weight, both have lower Vectara hallucination rates than V4 Pro (Qwen3 family clusters around 5%, V3.2-Exp at 5.3%, V4 Pro at 8.6%) [^vectara_lb]. Qw
~~~
1	# POLARIS Runtime Architecture Lock — v1
2	# I-meta-001 (#933) — Codex APPROVE_FOR_IMPLEMENTATION iter 2, operator D1 signed 2026-05-28T22:00 PDT
3	#
4	# This file is the SINGLE machine-readable source of truth for POLARIS's locked
5	# LLM stack. Code defaults, gate checks, tests, deployment surfaces, and PR
6	# attestations all derive their truth from this file.
7	#
8	# Mutation policy:
9	#   - Edits require Codex APPROVE on a brief that names the superseding lock doc
10	#   - Edits require operator commit signature (operator commits the change)
11	#   - Edits invalidate the propagation manifest (must be re-completed)
12	#   - canonical_pin.txt MUST track this file's SHA256
13	#
14	# Anti-drift gate: scripts/architecture/verify_lock.py asserts code defaults
15	# match this file at preflight; pathB_run_gate.py refuses to PASS unless
16	# every required_role is pinned AND observed in the captured LLM calls.
17	
18	version: 1
19	schema_version: 1.0
20	
21	# Provenance — the decision authority + Codex cross-validation
22	source_doc: docs/polaris_step_b_full_set_audit_2026_05_27.md
23	source_doc_sha256: TO_BE_COMPUTED_AT_COMMIT  # propagation manifest fills this after commit
24	codex_approval_artifact: .codex/I-meta-001/codex_brief_iter2_verdict.txt
25	codex_verdict: APPROVE_FOR_IMPLEMENTATION
26	codex_cross_validation_sources:
27	  - https://huggingface.co/CohereLabs/command-a-plus-05-2026-bf16
28	  - https://cohere.com/blog/command-a-plus
29	  - https://huggingface.co/ibm-gra
~~~
Web search results for query: "RAGTruth leaderboard balanced accuracy Granite Guardian 4.1 MiniCheck Lynx 2026"

Links: [{"title":"granite-guardian/README.md at main · ibm-granite/granite-guardian","url":"https://github.com/ibm-granite/granite-guardian/blob/main/README.md"},{"title":"GitHub - ibm-granite/granite-guardian: The Granite Guardian models are designed to detect risks in prompts and responses. · GitHub","url":"https://github.com/ibm-granite/granite-guardian"},{"title":"RAG Benchmarks Leaderboard: Retrieval Rankings 2026 | Awesome Agents","url":"https://awesomeagents.ai/leaderboards/rag-benchmarks-leaderboard/"},{"title":"[Paper Note] HalluGuard: Evidence-Grounded Small Reasoning Models to Mitigate Hallucinations in Retrieval-Augmented Generation, Loris Bergeron+, arXiv'25, 2025.10 · Issue #3065 · AkihikoWatanabe/paper_notes","url":"https://github.com/AkihikoWatanabe/paper_notes/issues/3065"},{"title":"HalluGuard: Evidence-Grounded Small Reasoning Models to Mitigate Hallucinations in Retrieval-Augmented Generation","url":"https://arxiv.org/pdf/2510.00880"},{"title":"Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards","url":"https://arxiv.org/pdf/2505.04847"},{"title":"MiniCheck/README.md at main · Liyan06/MiniCheck","url":"https://github.com/Liyan06/MiniCheck/blob/main/README.md"},{"title":"GitHub - Liyan06/MiniCheck: MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents [EMNLP 2024] · GitHub","url":"https://github.com/Liyan06/MiniCheck"}]

B
~~~
# Models Matching Search Criteria

## DeepSeek
- **ID**: deepseek/deepseek-v4-pro
  - **Name**: DeepSeek: DeepSeek V4 Pro
  - **Context Length**: 1,048,576
  - **Prompt Price**: $0.000000435/token
  - **Completion Price**: $0.00000087/token

- **ID**: deepseek/deepseek-v4-flash
  - **Name**: DeepSeek: DeepSeek V4 Flash
  - **Context Length**: 1,048,576
  - **Prompt Price**: $0.0000000983/token
  - **Completion Price**: $0.0000001966/token

## Qwen
- **ID**: qwen/qwen3.7-max
  - **Name**: Qwen: Qwen3.7 Max
  - **Context Length**: 1,000,000
  - **Prompt Price**: $0.00000125/token
  - **Completion Price**: $0.00000375/token

- **ID**: qwen/qwen3.5-plus-20260420
  - **Name**: Qwen: Qwen3.5 Plus 2026-04-20
  - **Context Length**: 1,000,000
  - **Prompt Price**: $0.0000003/token
  - **Completion Price**: $0.0000018/token

- **ID**: qwen/qwen3.6-flash
  - **Name**: Qwen: Qwen3.6 Flash
  - **Context Length**: 1,000,000
  - **Prompt Price**: $0.0000001875/token
  - **Completion Price**: $0.000001125/token

- **ID**: qwen/qwen3.6-35b-a3b
  - **Name**: Qwen: Qwen3.6 35B A3B
  - **Context Length**: 262,144
  - **Prompt Price**: $0.00000014/token
  - **Completion Price**: $0.000001/token

- **ID**: qwen/qwen3.6-max-preview
  - **Name**: Qwen: Qwen3.6 Max Preview
  - **Context Length**: 262,144
  - **Prompt Price**: $0.00000104/token
  - **Completion Price**: $0.00000624/token

- **ID**: qwen/qwen3.6-27b
  - **Name**: Qwen: Qwen3.6 27B
  - **Context Length**: 262,144
  - **Prompt Price**: 
~~~
# Granite Guardian Benchmark Results

## RAG Hallucination Benchmarks (LM-AggreFact)

The document shows a chart comparing Granite Guardian 4.1 and 3.3, stating: "Granite Guardian 4.1 think matches 3.3 think on the aggregate average (0.76) and improves on RAGTruth, ClaimVerify, and Wice."

However, **specific balanced accuracy numbers for individual benchmarks are not provided in the text**—only a visual chart is referenced. The document confirms improvements on RAGTruth but gives no exact figures.

## License and Distribution

The models operate under the "Apache 2.0" license. The README provides links to Hugging Face model cards but **contains no information about OpenRouter availability**. Access appears limited to downloadable weights from Hugging Face.

## Comparison Models

The document does not include benchmark comparisons against MiniCheck, Bespoke-MiniCheck, or other specific competing models. Comparisons are limited to general statements about outperforming larger models on certain datasets (e.g., gpt-4o on REVEAL).

**Summary**: Exact numerical benchmarks for RAGTruth and component LLM-AggreFact datasets are not provided in this README, only aggregate performance claims and visual references.
~~~

## AGENT ?C (a639c059e3b0068cf)
### analysis fragments:
### fetched web data (0 snippets):

## AGENT MIRROR (a8a02cb17cd3f460c)
### analysis fragments:
I'll start by reading the prior rationale docs, then verify everything live. This is a MIRROR-role selection task, so my deliverable focuses on the MIRROR pick — but I need to ground it in the same benchmark framework used for all 4 roles.

Let me first load the web tools and read the prior docs.
---
Now let me read both prior rationale docs.
---
I have the full prior rationale. Key takeaway for MIRROR: the original pick was Kimi K2.6, but the lock (per the superseding doc) replaced it with Cohere Command A+ — which the operator now says is NOT on OpenRouter, so I must re-pick. Let me read the rest of the per-role doc (the cross-family check + final summary) and then go live.
---
I have the full prior rationale. Important context for my MIRROR-only task:

- Original Mirror pick was Kimi K2.6 (Moonshot). The lock then replaced it with Cohere Command A+. Operator says Command A+ is NOT on OpenRouter, so I must re-pick.
- The MIRROR function per the operator brief is broader than the prior doc's "second-opinion generator": it's **calibration auditor + citation/attribution grounding + entailment**. The relevant benchmarks are calibration (AA-Omniscience hallucination %, ECE), hallucination-rate (Vectara HHEM), LLM-AggreFact BAcc, and attribution (ALCE).

Now I go live. Let me verify the OpenRouter catalog + leaderboards. I'll run several searches in parallel to ground the candidate pool, then fetch specifics.
---
Critical finding already: **Cohere Command A IS on OpenRouter** at `cohere/command-a` ($2.50/$10 per M). The operator's premise that "Command A+ is not on OpenRouter" needs careful checking — there may be a distinction between "command-a" (111B, on OR) and "command-a-plus" (the locked pick). Let me verify the exact Cohere slugs and license, and confirm what the prior doc actually locked.

The OpenRouter `/api/v1/models` fetch was paginated/truncated — it did NOT show Cohere, Llama, or older Qwen big models. Let me directly verify the key candidates' OpenRouter pages and licenses, plus the Cohere license question (CC-BY-NC is the disqualifier risk for Cohere).
---
This is a pivotal finding and it resolves the operator's premise. Let me lay out what just emerged:

1. **There are TWO different Cohere models being conflated:**
   - `cohere/command-a` (= `c4ai-command-a-03-2025`, 111B, March 2025) — on OpenRouter at $2.50/$10, but **CC-BY-NC (non-commercial)** → DISQUALIFIED by HARD GATE 3.
   - **Command A+** — the prior doc's locked Mirror pick — released under **Apache 2.0** (first full Apache-2.0 Cohere model), with **native citations** and **lossless quantization**. AND it **leads the AA-Omniscience hallucination-rate leaderboard at 14.1%** — the single best calibration score in the public snapshot. This is exactly the MIRROR-relevant benchmark.

So the operator's claim ("Command A+ Apache 2.0 but NOT on OpenRouter") may be the real constraint. I need to verify: (a) is Command A+ actually on OpenRouter or not, and (b) confirm its Apache 2.0 license + the 14.1% AA-Omniscience hallucination number from primary sources.

Let me verify the Command A+ OpenRouter availability, the VentureBeat Apache-2.0 claim, and pull the AA-Omniscience full leaderboard for open-weight ranking.
---
The VentureBeat fetch hit 429 and AA-Omniscience didn't yield the table directly. Crucial: OpenRouter shows `cohere/command-a` and `cohere/command-a-03-2025` (both = the CC-BY-NC March 2025 model), but **NO `command-a-plus` slug**. This confirms the operator's premise: Command A+ (Apache 2.0, the locked pick) is NOT on OpenRouter. So the Mirror lock pick is indeed unavailable and I must re-pick from OpenRouter-available open-weight models.

Let me pause and consult the advisor before committing to the candidate framework and re-pick — wait, the advisor tool is explicitly FORBIDDEN per the brief ("Do NOT use the advisor tool") and per my memory (`feedback_no_opus_advisor_use_codex_cli`). I will NOT call it.

Let me get the AA-Omniscience leaderboard data from the secondary aggregators (BenchLM, Awesome Agents) and confirm the Command A+ Apache 2.0 + 14.1% number, plus pull LLM-AggreFact and the Vectara HHEM leaderboard for the OpenRouter-available candidates.
---
### fetched web data (12 snippets):
<system-reminder>[Truncated: PARTIAL view — showing lines 1-674 of 849 total (26746 tokens, cap 25000). Call Read with offset=675 limit=674 for the next page, or Grep to find a specific section. Do NOT answer from this page alone if the answer may be further in the file.]</system-reminder>

1	---
2	status: superseded
3	superseded_by: docs/polaris_step_b_full_set_audit_2026_05_27.md
4	superseded_on: 2026-05-28
5	superseded_reason: Step-B audit reached different conclusions on Mirror/Sentinel picks (Cohere Command A+ replaces Kimi K2.6 for Mirror; Granite Guardian 4.1 replaces 3.3 for Sentinel). Operator confirmed Step-B as final.
6	---
7	
8	# POLARIS Per-Role SOTA Open-Weight LLM Validation (2026-05-27)
9	
10	**Mission:** Replace single-composite-score selection (AA Intelligence Index) with
11	per-role validation using role-specific benchmarks. Operator pushback was correct:
12	each of the 4 POLARIS stack roles (generator / mirror / sentinel / judge) has a
13	distinct capability profile and the "highest average" model is not necessarily
14	the highest in any individual role.
15	
16	**Constraints (operator-locked, May 2026):**
17	- Open weights only (any license)
18	- Non-US runtime LLM (open weights on sovereign infra OK)
19	- No hardware ceiling, no time constraint
20	- Latest + strongest + most capable per role
21	- Multi-domain: clinical + legal + financial + regulatory + policy + scientific, EN baseline
22	- Multi-LLM stack OK if each layer earns its keep
23	
24	**Claude's
~~~
1	---
2	status: research_artifact
3	locked_decision: none (advisory research, no architecture lock here)
4	related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
5	---
6	
7	# Deepest research: Open-Source Non-US Clinical RAG Faithfulness, 2026 SOTA
8	
9	**Author:** Claude (Opus 4.7, 1M context) — research executor
10	**Date:** 2026-05-27
11	**Audience:** POLARIS operator + Codex (architectural reviewer)
12	**Constraints:** open-weight only at runtime, no US-vendor LLM at runtime (Anthropic Citations, Vertex Check Grounding, Azure Groundedness all DISQUALIFIED), no time pressure, no fake shit
13	**Supersedes:** `docs/clinical_rag_validation_sota_2026_05_26.md` — the prior report was constrained to a 9-day demo window and recommended Patronus Lynx 8B; **that recommendation is now invalidated** because Lynx v1.1 is CC-BY-NC (non-commercial). See §4.2 for the licence audit and §5 for the corrected recommendation.
14	
15	---
16	
17	## Executive answer
18	
19	**The actual SOTA architecture for sovereign clinical RAG faithfulness in 2026 is a four-layer pipeline that no single team has fully shipped, but each layer has at least one credibly-deployed open-weight non-US instantiation.** From outermost to innermost:
20	
21	1. **Generator: Qwen3-235B-A22B (Apache 2.0) or DeepSeek-V3.2-Exp (MIT)**, NOT DeepSeek V4 Pro. Both are open-weight, both have lower Vectara hallucination rates than V4 Pro (Qwen3 family clusters around 5%, V3.2-Exp at 5.3%, V4 Pro at 8.6%) [^vectara_lb]. Qw
~~~
675	- **MiniMax M2.7** — IFEval 69.3 disqualifies for any schema-disciplined role.
676	- **Qwen 3.5-397B Reasoning** — strongest pure reasoning + IFEval in pool,
677	  but at 397B MoE it is overkill for per-claim verdict and slower-thinking
678	  variants add latency. Reserve for offline appellate-review batch jobs.
679	- **Gemma 4 31B** — viable backup; AA-Omniscience Accuracy 19.9% suggests
680	  comparable to Qwen 3.6-27B; loses on documented structured-output
681	  discipline.
682	
683	### Does Claude's original pick survive?
684	
685	**NO.** Mistral Medium 3.5 is open-weight (initial assumption "API-only" was
686	wrong — modified MIT weights confirmed 2026-04-29) and a legitimate judge
687	candidate, but loses to **Qwen 3.6-35B-A3B** on (a) license cleanliness for
688	sovereign deployment (Apache 2.0 vs modified MIT with revenue-threshold),
689	(b) per-token cost at per-claim cardinality (35B/3B-active vs 128B dense),
690	and (c) Qwen-family's published structured-output discipline plus
691	multi-benchmark coverage. Operator's pushback validated again: the
692	single-composite Intelligence Index obscured the per-role differential —
693	Mistral Medium 3.5 wins on general-agentic intelligence; Qwen 3.6-35B-A3B
694	wins on the *specific* judge-role capability profile.
695	
696	---
697	
698	## Final cross-family integrity check + summary
699	
700	### Stack-shape clarification (operator-facing)
701	
702	Operator framed the task as a **4-LLM stack** (generator / mirror / senti
~~~
# Models from Requested Families

Based on the provided content, here are the models from the specified families with their pricing:

## Qwen Models
- **qwen/qwen3.7-max**: Prompt $0.00000125, Completion $0.00000375
- **qwen/qwen3.5-plus-20260420**: Prompt $0.0000003, Completion $0.0000018
- **qwen/qwen3.6-flash**: Prompt $0.0000001875, Completion $0.000001125
- **qwen/qwen3.6-35b-a3b**: Prompt $0.00000014, Completion $0.000001
- **qwen/qwen3.6-max-preview**: Prompt $0.00000104, Completion $0.00000624
- **qwen/qwen3.6-27b**: Prompt $0.00000029, Completion $0.0000032
- **qwen/qwen3.6-plus**: Prompt $0.000000325, Completion $0.00000195
- **qwen/qwen3.5-9b**: Prompt $0.00000004, Completion $0.00000015
- **qwen/qwen3.5-35b-a3b**: Prompt $0.00000014, Completion $0.000001

## NVIDIA Nemotron Models
- **nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free**: Free (prompt $0, completion $0)
- **nvidia/nemotron-3-super-120b-a12b:free**: Free (prompt $0, completion $0)
- **nvidia/nemotron-3-super-120b-a12b**: Prompt $0.00000009, Completion $0.00000045

## Google Gemma Models
- **google/gemma-4-26b-a4b-it:free**: Free (prompt $0, completion $0)
- **google/gemma-4-26b-a4b-it**: Prompt $0.00000006, Completion $0.00000033
- **google/gemma-4-31b-it:free**: Free (prompt $0, completion $0)
- **google/gemma-4-31b-it**: Prompt $0.00000012, Completion $0.00000037

## DeepSeek Models
- **deepseek/deepseek-v4-pro**: Prompt $0.000000435, Completion $0.00000087
- **deepseek/deepseek-v4-flash:free**: F
~~~
Web search results for query: "LLM-AggreFact leaderboard balanced accuracy 2025 2026 best open model"

Links: [{"title":"Open Source LLM Leaderboard 2026: Rankings, Benchmarks & the Best Models Right Now &#045; VERTU® Official Site","url":"https://vertu.com/lifestyle/open-source-llm-leaderboard-2026-rankings-benchmarks-the-best-models-right-now"},{"title":"LLM Leaderboard 2026: Compare 300+ Top AI Models by Intelligence, Speed & Price","url":"https://llm-stats.com/"},{"title":"LLM Leaderboard 2026: Best AI Models Benchmark & Ranking","url":"https://www.clickrank.ai/llm-leaderboard/"},{"title":"Open LLM Leaderboard 2026 - Compare Open Source LLM Rankings","url":"https://llm-stats.com/leaderboards/open-llm-leaderboard"},{"title":"Open Source LLM Leaderboard 2026 — Compare Open-Weight Models","url":"https://www.vellum.ai/open-llm-leaderboard"},{"title":"LLM Leaderboard - Comparison of over 100 AI models from OpenAI, Google, DeepSeek & others","url":"https://artificialanalysis.ai/leaderboards/models"},{"title":"Detecting Errors through Ensembling Prompts (DEEP): An End-to-End LLM   Framework for Detecting Factual Errors","url":"https://arxiv.org/pdf/2406.13009"},{"title":"LLM Leaderboard 2026 — Compare Top AI Models - Vellum","url":"https://www.vellum.ai/llm-leaderboard"}]

Based on my search results, I found information about LLM leaderboards and benchmarks for 2025-2026, though the results don't show a specific "LLM-AggreFact leaderboard" focused on balanced accuracy metrics th
~~~
Web search results for query: "OpenRouter Cohere Command A available model slug price 2026"

Links: [{"title":"Command A - API Pricing & Providers | OpenRouter","url":"https://openrouter.ai/cohere/command-a"},{"title":"OpenRouter Models Pricing Calculator | Compare Model Costs Instantly","url":"https://invertedstone.com/calculators/openrouter-pricing"},{"title":"Cohere API vs OpenRouter Pricing (2026)","url":"https://costbench.com/compare/cohere-api-vs-openrouter/"},{"title":"Command A compared to other AI models | OpenRouter","url":"https://openrouter.ai/compare/cohere/command-a"},{"title":"OpenRouter Pricing 2026: 300+ LLM Models — Passthrough Rates","url":"https://costbench.com/software/llm-api-providers/openrouter/"},{"title":"Pricing | OpenRouter","url":"https://openrouter.ai/pricing"},{"title":"OpenRouter Pricing Calculator & Cost Guide (May 2026)","url":"https://costgoat.com/pricing/openrouter"},{"title":"OpenRouter API Pricing 2026 — All Models Compared","url":"https://tokentab.dev/pricing/openrouter"},{"title":"Free Models Router - API Pricing & Providers | OpenRouter","url":"https://openrouter.ai/openrouter/free"},{"title":"OpenRouter Models - LLM Cost Calculator | Bifrost","url":"https://www.getmaxim.ai/bifrost/llm-cost-calculator/provider/openrouter"}]

Based on the search results, here's the information about Cohere Command A on OpenRouter:

**Model Details:**
Command A is an open-weights 111B parameter model with a 256k context window focused on delivering great
~~~

## AGENT JUDGE (a9e010362e7ce9bb7)
### analysis fragments:
I'll start by orienting myself — reading the prior rationale docs, then live-verifying the OpenRouter catalog and leaderboards for the JUDGE role specifically.
---
Let me read the prior rationale docs, focusing on the JUDGE role sections.
---
This is the key prior rationale for the Judge role. Let me read the rest of the Judge section and the conclusion.
---
I have the full prior rationale for the JUDGE role. The prior pick was Qwen 3.6-35B-A3B over Mistral Medium 3.5 (which was a closed-source error in the original). Now my task is to live-verify the OpenRouter catalog and BFCL/IFEval leaderboards. The decision context here is critical: a slug very close to the current locked pick is `qwen/qwen3.6-35b-a3b`. Let me start the live verification.

Key things I must establish for the JUDGE role:
1. OpenRouter live availability + slug + price for Qwen3.6 family and competitors (Llama 3.3 70B, Llama 4, Mistral Large 3, Gemma 3, Command-R/A).
2. BFCL (Berkeley Function-Calling Leaderboard) live numbers.
3. IFEval live numbers.
4. Structured-output/JSON-schema reliability.
5. Clinical judging (MedHallu detection F1) if available.

Let me fan out the live searches.
---
Important findings already: the OpenRouter catalog does NOT show `qwen/qwen3.6-35b-a3b` is the only candidate — but critically, my candidate competitors (Llama 3.3 70B, Llama 4, Mistral Large 3, Gemma 3/4, Command-R/A) did NOT appear in the OpenRouter results. That's a major availability signal that needs confirmation. The current pick `qwen/qwen3.6-35b-a3b` IS live at $0.14/$1.00 per M tokens, 262K context. Let me verify the missing families directly and pull the BFCL V4 numbers.
---
This is a major, decision-relevant finding. The WebFetch may be working off a truncated/partial view of the catalog (the API returns hundreds of models and the small model summarizing may not see all). I must NOT conclude "Llama/Cohere absent" from a possibly-truncated fetch — that would violate the verify-primary-sources rule. Let me query OpenRouter's catalog more precisely using their per-model API endpoints and search, and pull BFCL from the authoritative Berkeley source and llm-stats.
---
This corrects the earlier truncated read: BOTH `meta-llama/llama-3.3-70b-instruct` (131K ctx, ~$0.10/$0.32 per M cheapest) AND `cohere/command-a` (256K ctx, $2.50/$10 per M) ARE live on OpenRouter. The earlier WebFetch of the bulk catalog was truncated. The candidate pool is wider than the first fetch suggested. Now I need the actual BFCL numbers (the Berkeley HTML is JS-rendered, so I need llm-stats or BenchLM per-model pages) and IFEval. Let me also verify Llama 4, Mistral Large 3, Gemma current OpenRouter availability and pull the function-calling numbers from llm-stats.
---
Now I have solid OpenRouter availability. Confirmed live: `qwen/qwen3.6-35b-a3b`, `qwen/qwen3.6-27b`, `qwen/qwen3.6-plus`, `meta-llama/llama-3.3-70b-instruct`, `meta-llama/llama-4-maverick`, `meta-llama/llama-4-scout`, `mistralai/mistral-medium-3.5`, `cohere/command-a`. The BFCL-V4 leaderboard (BenchLM/llm-stats) only has Qwen3.5/3.7 family — sparse. The authoritative gorilla.cs.berkeley.edu is JS-rendered. I need the function-calling numbers for the non-Qwen families. Let me pull from BenchLM per-model BFCL pages and IFEval, and get Mistral Medium 3.5 / Command-A / Llama function-calling and structured-output numbers. Let me also confirm the Qwen3.6-35B-A3B license and the clinical MedHallu angle.
---
### fetched web data (14 snippets):
<system-reminder>[Truncated: PARTIAL view — showing lines 1-674 of 849 total (26746 tokens, cap 25000). Call Read with offset=675 limit=674 for the next page, or Grep to find a specific section. Do NOT answer from this page alone if the answer may be further in the file.]</system-reminder>

1	---
2	status: superseded
3	superseded_by: docs/polaris_step_b_full_set_audit_2026_05_27.md
4	superseded_on: 2026-05-28
5	superseded_reason: Step-B audit reached different conclusions on Mirror/Sentinel picks (Cohere Command A+ replaces Kimi K2.6 for Mirror; Granite Guardian 4.1 replaces 3.3 for Sentinel). Operator confirmed Step-B as final.
6	---
7	
8	# POLARIS Per-Role SOTA Open-Weight LLM Validation (2026-05-27)
9	
10	**Mission:** Replace single-composite-score selection (AA Intelligence Index) with
11	per-role validation using role-specific benchmarks. Operator pushback was correct:
12	each of the 4 POLARIS stack roles (generator / mirror / sentinel / judge) has a
13	distinct capability profile and the "highest average" model is not necessarily
14	the highest in any individual role.
15	
16	**Constraints (operator-locked, May 2026):**
17	- Open weights only (any license)
18	- Non-US runtime LLM (open weights on sovereign infra OK)
19	- No hardware ceiling, no time constraint
20	- Latest + strongest + most capable per role
21	- Multi-domain: clinical + legal + financial + regulatory + policy + scientific, EN baseline
22	- Multi-LLM stack OK if each layer earns its keep
23	
24	**Claude's
~~~
675	- **MiniMax M2.7** — IFEval 69.3 disqualifies for any schema-disciplined role.
676	- **Qwen 3.5-397B Reasoning** — strongest pure reasoning + IFEval in pool,
677	  but at 397B MoE it is overkill for per-claim verdict and slower-thinking
678	  variants add latency. Reserve for offline appellate-review batch jobs.
679	- **Gemma 4 31B** — viable backup; AA-Omniscience Accuracy 19.9% suggests
680	  comparable to Qwen 3.6-27B; loses on documented structured-output
681	  discipline.
682	
683	### Does Claude's original pick survive?
684	
685	**NO.** Mistral Medium 3.5 is open-weight (initial assumption "API-only" was
686	wrong — modified MIT weights confirmed 2026-04-29) and a legitimate judge
687	candidate, but loses to **Qwen 3.6-35B-A3B** on (a) license cleanliness for
688	sovereign deployment (Apache 2.0 vs modified MIT with revenue-threshold),
689	(b) per-token cost at per-claim cardinality (35B/3B-active vs 128B dense),
690	and (c) Qwen-family's published structured-output discipline plus
691	multi-benchmark coverage. Operator's pushback validated again: the
692	single-composite Intelligence Index obscured the per-role differential —
693	Mistral Medium 3.5 wins on general-agentic intelligence; Qwen 3.6-35B-A3B
694	wins on the *specific* judge-role capability profile.
695	
696	---
697	
698	## Final cross-family integrity check + summary
699	
700	### Stack-shape clarification (operator-facing)
701	
702	Operator framed the task as a **4-LLM stack** (generator / mirror / senti
~~~
# Models Matching Search Criteria

Based on the provided data, here are all models matching your filters:

| ID | Name | Context Length | Prompt Price | Completion Price |
|---|---|---|---|---|
| qwen/qwen3.7-max | Qwen: Qwen3.7 Max | 1,000,000 | $0.00000125 | $0.00000375 |
| qwen/qwen3.5-plus-20260420 | Qwen: Qwen3.5 Plus 2026-04-20 | 1,000,000 | $0.0000003 | $0.0000018 |
| qwen/qwen3.6-flash | Qwen: Qwen3.6 Flash | 1,000,000 | $0.0000001875 | $0.000001125 |
| qwen/qwen3.6-35b-a3b | Qwen: Qwen3.6 35B A3B | 262,144 | $0.00000014 | $0.000001 |
| qwen/qwen3.6-max-preview | Qwen: Qwen3.6 Max Preview | 262,144 | $0.00000104 | $0.00000624 |
| qwen/qwen3.6-27b | Qwen: Qwen3.6 27B | 262,144 | $0.00000029 | $0.0000032 |
| qwen/qwen3.6-plus | Qwen: Qwen3.6 Plus | 1,000,000 | $0.000000325 | $0.00000195 |
| qwen/qwen3.5-35b-a3b | Qwen: Qwen3.5-35B-A3B | 262,144 | $0.00000014 | $0.000001 |
| qwen/qwen3.5-9b | Qwen: Qwen3.5-9B | 262,144 | $0.00000004 | $0.00000015 |
| google/gemini-3.5-flash | Google: Gemini 3.5 Flash | 1,048,576 | $0.0000015 | $0.000009 |
| google/gemini-3.1-flash-lite | Google: Gemini 3.1 Flash Lite | 1,048,576 | $0.00000025 | $0.0000015 |
~~~
Web search results for query: "Berkeley Function-Calling Leaderboard BFCL V4 2026 Qwen3 Llama Mistral open weight ranking scores"

Links: [{"title":"BFCL v4 Benchmark 2026: 4 model averages | BenchLM.ai","url":"https://benchlm.ai/benchmarks/bfclV4"},{"title":"Berkeley Function Calling Leaderboard (BFCL) V4","url":"https://gorilla.cs.berkeley.edu/leaderboard.html"},{"title":"The Berkeley Function Calling Leaderboard (BFCL): From Tool Use to Agentic Evaluation of Large Language Models | OpenReview","url":"https://openreview.net/forum?id=2GmDdhBdDk"},{"title":"BFCL: Berkeley Function-Calling Leaderboard","url":"https://ukgovernmentbeis.github.io/inspect_evals/evals/assistants/bfcl/"},{"title":"BFCL Benchmark Leaderboard","url":"https://llm-stats.com/benchmarks/bfcl"},{"title":"Berkeley Function Calling Leaderboard (BFCL)","url":"https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard"},{"title":"BFCL-V4 Benchmark Leaderboard","url":"https://llm-stats.com/benchmarks/bfcl-v4"},{"title":"The Berkeley Function Calling Leaderboard (BFCL): From Tool Use to Agentic Evaluation of Large Language Models","url":"https://proceedings.mlr.press/v267/patil25a.html"},{"title":"Reasoning through Exploration: A Reinforcement Learning Framework for Robust Function Calling","url":"https://arxiv.org/pdf/2508.05118"}]

Based on the search results, here's information about the Berkeley Function-Calling Leaderboard V4 2026:

## BFCL V4 Overview

The Berkeley Function Callin
~~~
Based on the webpage content provided, I can only report the following BFCL v4 scores that are explicitly listed:

**Available Results:**
1. Qwen3.7 Max - 75.0%
2. ZAYA1-8B - 39.2%
3. MiniCPM5-1B - 25.1%
4. LFM2.5-VL-450M - 21.1%

**Important limitation:** The page states "4 models have been evaluated on BFCL v4." None of the open-weight models you requested (Qwen3.6, Qwen3.5, Llama 3.3 70B, Llama 4, Mistral Large 3, Mistral Medium, Gemma, Command-R, Command-A) appear in the current benchmark results shown.

The webpage only displays these four model results and does not contain scores for the other models you asked about.
~~~
# Model Search Results

Based on the provided data, here are the models matching your criteria:

## Mistral Models Found:

1. **mistralai/mistral-medium-3.5**
   - ID: `mistralai/mistral-medium-3.5`
   - Name: Mistral Medium 3.5
   - Context Length: 262,144
   - Prompt Price: $0.0000015
   - Completion Price: $0.0000075

2. **mistralai/mistral-small-2603**
   - ID: `mistralai/mistral-small-2603`
   - Name: Mistral Small 4
   - Context Length: 262,144
   - Prompt Price: $0.00000015
   - Completion Price: $0.0000006

## Meta-Llama Models:
**None found** in the provided dataset.

## Cohere Models:
**None found** in the provided dataset.

## Specific Models You Requested:
- `meta-llama/llama-3.3-70b-instruct` — **Not present**
- `meta-llama/llama-4` — **Not present**
- `mistralai/mistral-large` — **Not present**
- `mistralai/mistral-medium` — **Not present** (only Medium 3.5 available)
- `cohere/command-a` — **Not present**
- `cohere/command-r` — **Not present**
~~~

## AGENT ?A (ae74850c93517bd6b)
### analysis fragments:
I'll start by reading the prior rationale documents, then live-verify the OpenRouter catalog and leaderboards.
---
These two prior docs are from 2026-05-27, several days stale. The architecture has since been re-locked (per memory: V4 Pro + Cohere Command A + Granite Guardian 4.1 + Qwen3.6-35B-A3B). The operator is now reopening selection with a HARD new gate the prior docs never applied: must be live on OpenRouter NOW. Let me live-verify the OpenRouter catalog and the leaderboards before committing to any pick.

Let me load the web tools and start querying the live OpenRouter API.
---
Now let me query the live OpenRouter API for the actual catalog. This is the hard gate — I need to verify what's actually live right now.
---
Critical findings from the live OpenRouter catalog:

1. **Cohere is NOT on OpenRouter** — confirmed. The legacy Mirror pick (cohere/command-a-plus) must be re-picked. No `cohere/` slug exists in the live catalog.
2. **Granite Guardian is NOT on OpenRouter** — only `ibm-granite/granite-4.1-8b` (the base instruct model, NOT the Guardian safety/hallucination variant). The legacy Sentinel pick must be re-evaluated against the self-host exception.
3. **deepseek/deepseek-v4-pro IS live** at $0.435/$0.87 per M, 1M ctx. Writer pick confirmed available.
4. **qwen/qwen3.6-35b-a3b IS live** at $0.14/$1.00, 262K ctx. Judge pick available.

Let me now verify the leaderboard scores I need (RAGTruth/AggreFact for Sentinel, BFCL for Judge, plus license confirmations). Let me fetch the actual Vectara leaderboard README and pursue the RAGTruth/Granite Guardian data, plus confirm licenses.
---
Very important new data. The live Vectara HHEM-2.3 numbers differ materially from what the stale 2026-05-27 doc claimed:

- **DeepSeek V4-Pro: 8.6% hallucination, 97.2% answer rate** — confirmed worst-in-class among open frontier for grounded summarization. But note: 97.2% answer rate (it answers, doesn't abstain).
- **Qwen3-8b: 4.8%** — best small open. But the NEW Qwen3.5/3.6 line regressed badly (10.5%+).
- **Llama-3.3-70B: 4.1%** — best mid open-weight.
- **Mistral-large-2411: 4.5%**, but Mistral-3-large-2512: 14.5% (newest regressed).
- **Gemma-3-12b: 4.4%**, Gemma-4-26b-a4b: 5.2%.
- **GLM-5: 10.1%**, **Kimi-K2.6: 10.8%**.

Critical Sentinel finding: Granite Guardian 4.1-8b RAGTruth BAcc ~0.76-0.79 (thinking/non-thinking) — close to the legacy doc's 0.834/0.841 claim, but it is NOT on OpenRouter. Only `ibm-granite/granite-4.1-8b` (the base instruct, not Guardian) is live.

Let me now nail down the Judge benchmark (BFCL function-calling, IFEval), the Sentinel candidates that ARE on OpenRouter, and confirm licenses for the key picks. Let me also get the live OpenRouter model pages for the specific picks to confirm slugs.
---
Let me fetch the live BFCL V4 leaderboard directly to get the exact open-weight function-calling scores for the Judge role, and the live LLM-AggreFact leaderboard for the Sentinel role.
---
### fetched web data (8 snippets):
<system-reminder>[Truncated: PARTIAL view — showing lines 1-674 of 849 total (26746 tokens, cap 25000). Call Read with offset=675 limit=674 for the next page, or Grep to find a specific section. Do NOT answer from this page alone if the answer may be further in the file.]</system-reminder>

1	---
2	status: superseded
3	superseded_by: docs/polaris_step_b_full_set_audit_2026_05_27.md
4	superseded_on: 2026-05-28
5	superseded_reason: Step-B audit reached different conclusions on Mirror/Sentinel picks (Cohere Command A+ replaces Kimi K2.6 for Mirror; Granite Guardian 4.1 replaces 3.3 for Sentinel). Operator confirmed Step-B as final.
6	---
7	
8	# POLARIS Per-Role SOTA Open-Weight LLM Validation (2026-05-27)
9	
10	**Mission:** Replace single-composite-score selection (AA Intelligence Index) with
11	per-role validation using role-specific benchmarks. Operator pushback was correct:
12	each of the 4 POLARIS stack roles (generator / mirror / sentinel / judge) has a
13	distinct capability profile and the "highest average" model is not necessarily
14	the highest in any individual role.
15	
16	**Constraints (operator-locked, May 2026):**
17	- Open weights only (any license)
18	- Non-US runtime LLM (open weights on sovereign infra OK)
19	- No hardware ceiling, no time constraint
20	- Latest + strongest + most capable per role
21	- Multi-domain: clinical + legal + financial + regulatory + policy + scientific, EN baseline
22	- Multi-LLM stack OK if each layer earns its keep
23	
24	**Claude's
~~~
1	---
2	status: research_artifact
3	locked_decision: none (advisory research, no architecture lock here)
4	related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
5	---
6	
7	# Deepest research: Open-Source Non-US Clinical RAG Faithfulness, 2026 SOTA
8	
9	**Author:** Claude (Opus 4.7, 1M context) — research executor
10	**Date:** 2026-05-27
11	**Audience:** POLARIS operator + Codex (architectural reviewer)
12	**Constraints:** open-weight only at runtime, no US-vendor LLM at runtime (Anthropic Citations, Vertex Check Grounding, Azure Groundedness all DISQUALIFIED), no time pressure, no fake shit
13	**Supersedes:** `docs/clinical_rag_validation_sota_2026_05_26.md` — the prior report was constrained to a 9-day demo window and recommended Patronus Lynx 8B; **that recommendation is now invalidated** because Lynx v1.1 is CC-BY-NC (non-commercial). See §4.2 for the licence audit and §5 for the corrected recommendation.
14	
15	---
16	
17	## Executive answer
18	
19	**The actual SOTA architecture for sovereign clinical RAG faithfulness in 2026 is a four-layer pipeline that no single team has fully shipped, but each layer has at least one credibly-deployed open-weight non-US instantiation.** From outermost to innermost:
20	
21	1. **Generator: Qwen3-235B-A22B (Apache 2.0) or DeepSeek-V3.2-Exp (MIT)**, NOT DeepSeek V4 Pro. Both are open-weight, both have lower Vectara hallucination rates than V4 Pro (Qwen3 family clusters around 5%, V3.2-Exp at 5.3%, V4 Pro at 8.6%) [^vectara_lb]. Qw
~~~
# Model Listing by Provider

## DeepSeek
| ID | Context Length | Prompt ($/M tokens) | Completion ($/M tokens) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 1,048,576 | 0.435 | 0.87 |
| deepseek/deepseek-v4-flash:free | 1,048,576 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1,048,576 | 0.0983 | 0.1966 |

## Qwen
| ID | Context Length | Prompt ($/M tokens) | Completion ($/M tokens) |
|---|---|---|---|
| qwen/qwen3.7-max | 1,000,000 | 1.25 | 3.75 |
| qwen/qwen3.5-plus-20260420 | 1,000,000 | 0.3 | 1.8 |
| qwen/qwen3.6-flash | 1,000,000 | 0.1875 | 1.125 |
| qwen/qwen3.6-35b-a3b-20260415 | 262,144 | 0.14 | 1.0 |
| qwen/qwen3.6-max-preview-20260420 | 262,144 | 1.04 | 6.24 |
| qwen/qwen3.6-27b-20260422 | 262,144 | 0.29 | 3.2 |
| qwen/qwen3.6-plus-04-02 | 1,000,000 | 0.325 | 1.95 |
| qwen/qwen3.5-9b-20260310 | 262,144 | 0.04 | 0.15 |
| qwen/qwen3.5-35b-a3b-20260224 | 262,144 | 0.14 | 1.0 |

## Mistral
| ID | Context Length | Prompt ($/M tokens) | Completion ($/M tokens) |
|---|---|---|---|
| mistralai/mistral-medium-3.5 | 262,144 | 1.5 | 7.5 |
| mistralai/mistral-small-2603 | 262,144 | 0.15 | 0.6 |

## MoonshotAI
| ID | Context Length | Prompt ($/M tokens) | Completion ($/M tokens) |
|---|---|---|---|
| moonshotai/kimi-k2.6:free | 262,144 | 0 | 0 |
| moonshotai/kimi-k2.6 | 262,144 | 0.684 | 3.42 |

## Z.ai
| ID | Context Length | Prompt ($/M tokens) | Completion ($/M tokens) |
|---|---|---|---|
| z-ai/glm-5.1-20260406 | 202,752 | 0.98 | 3.08 |
| z-ai/glm-5v-turbo-20260401 | 202,752 | 
~~~
Web search results for query: "Vectara HHEM hallucination leaderboard 2026 DeepSeek Qwen latest scores"

Links: [{"title":"GitHub - vectara/hallucination-leaderboard: Leaderboard Comparing LLM Performance at Producing Hallucinations when Summarizing Short Documents · GitHub","url":"https://github.com/vectara/hallucination-leaderboard"},{"title":"Introducing the Next Generation of Vectara's Hallucination Leaderboard","url":"https://www.vectara.com/blog/introducing-the-next-generation-of-vectaras-hallucination-leaderboard"},{"title":"AI Hallucination Rates & Benchmarks in 2026","url":"https://suprmind.ai/hub/ai-hallucination-rates-and-benchmarks/"},{"title":"LLM Hallucination Leaderboard - a Hugging Face Space by vectara","url":"https://huggingface.co/spaces/vectara/leaderboard"},{"title":"Hallucination Evaluation Leaderboard - a Hugging Face Space by vectara","url":"https://huggingface.co/spaces/vectara/Hallucination-evaluation-leaderboard"},{"title":"LLM Benchmarks Explained: MMLU, Chatbot Arena & SWE-bench Leaderboard (2026) | mysummit.school - AI for Managers Blog","url":"https://mysummit.school/blog/en/how-llm-benchmarks-work-2026/"},{"title":"hallucination-leaderboard/README.md at main · vectara/hallucination-leaderboard","url":"https://github.com/vectara/hallucination-leaderboard/blob/main/README.md"},{"title":"Vectara's Hallucination Leaderboard","url":"https://www.emergentmind.com/topics/vectara-s-hallucination-leaderboard"},{"title":"AI Hallucination Statistics 2026: 
~~~
Web search results for query: "IBM Granite Guardian 4.1 RAGTruth benchmark score hallucination detection LLM-AggreFact 2026"

Links: [{"title":"RAGTruth: A Hallucination Corpus for Developing Trustworthy   Retrieval-Augmented Language Models","url":"https://arxiv.org/pdf/2401.00396"},{"title":"ibm-granite/granite-3.2-8b-lora-rag-hallucination-detection · Hugging Face","url":"https://huggingface.co/ibm-granite/granite-3.2-8b-lora-rag-hallucination-detection"},{"title":"ibm-granite/granite-guardian-4.1-8b · Hugging Face","url":"https://huggingface.co/ibm-granite/granite-guardian-4.1-8b"},{"title":"README.md · ibm-granite/granite-3.2-8b-lora-rag-hallucination-detection at main","url":"https://huggingface.co/ibm-granite/granite-3.2-8b-lora-rag-hallucination-detection/blob/main/README.md"},{"title":"Retromorphic Testing with Hierarchical Verification for Hallucination Detection in RAG","url":"https://arxiv.org/pdf/2603.27752"},{"title":"Granite Guardian 4.1 8B – 8K context, open source | LLM Reference","url":"https://www.llmreference.com/model/granite-guardian-4.1-8b"},{"title":"LettuceDetect: A Hallucination Detection Framework for RAG Applications","url":"https://arxiv.org/pdf/2502.17125"}]

Now let me search for information about LLM-AggreFact 2026:

Links: [{"title":"lytang/LLM-AggreFact · Datasets at Hugging Face","url":"https://huggingface.co/datasets/lytang/LLM-AggreFact"},{"title":"Statistics of AGGREFACT-CNN. Each dataset is stratified into three... | Download Scientific 
~~~
# Hallucination Leaderboard Results

Here are the requested models with their metrics:

**DeepSeek Models:**
- DeepSeek V4-Pro: 8.6% hallucination, 91.4% factual consistency, 97.2% answer rate
- DeepSeek V3.2: 6.3% hallucination, 93.7% factual consistency, 92.6% answer rate
- DeepSeek V3: 6.1% hallucination, 93.9% factual consistency, 97.5% answer rate

**Qwen Models:**
- Qwen3-4b: 5.7% hallucination, 94.3% factual consistency, 99.9% answer rate
- Qwen3-8b: 4.8% hallucination, 95.2% factual consistency, 99.9% answer rate
- Qwen3-14b: 5.4% hallucination, 94.6% factual consistency, 99.9% answer rate
- Qwen3-32b: 5.9% hallucination, 94.1% factual consistency, 99.9% answer rate
- Qwen3-235b-a22b: 9.3% hallucination, 90.7% factual consistency, 94.9% answer rate
- Qwen3.5-plus-2026-02-15: 10.7% hallucination, 89.3% factual consistency, 99.8% answer rate
- Qwen3.5-35b-a3b: 10.5% hallucination, 89.5% factual consistency, 99.8% answer rate
- Qwen3.5-flash-2026-02-23: 10.5% hallucination, 89.5% factual consistency, 99.8% answer rate
- Qwen3.5-122b-a10b: 11.2% hallucination, 88.8% factual consistency, 99.8% answer rate
- Qwen3.5-27b: 12.1% hallucination, 87.9% factual consistency, 99.8% answer rate

**Llama Models:**
- Llama-3.3-70B-Instruct-Turbo: 4.1% hallucination, 95.9% factual consistency, 99.5% answer rate
- Llama-4-Scout-17B-16E-Instruct: 7.7% hallucination, 92.3% factual consistency, 99.0% answer rate
- Llama-4-Maverick-17B-128E-Instruct-FP8: 8.2% hallucination, 91.8% factual co
~~~

## AGENT ?B (aee30833b02eb87ce)
### analysis fragments:
I'll build this evidence base systematically. Let me start by reading the prior rationale docs to understand what was claimed, then live-verify everything against current OpenRouter and leaderboard data.

First, let me load the web tools I'll need and read the prior docs.
---
Let me read both prior rationale docs in full.
---
I have strong context on the prior rationale. Key takeaways: the prior docs flagged that V4 Pro has a high hallucination rate (8.6% Vectara) and many "latest" models aren't on the leaderboards; the Sentinel role's real specialists (Lynx) are CC-BY-NC, and the Apache-2.0 picks (Granite Guardian, HHEM-2.1-Open) aren't on OpenRouter.

The critical gap for MY task: NONE of the prior docs verified OpenRouter availability. The operator's new hard gate is "not locked if no OpenRouter access." Let me read the rest of the per-role doc, then go live to OpenRouter and the leaderboards.
---
I now have the full prior rationale. The critical observation: the prior docs were written WITHOUT verifying OpenRouter availability — which is the operator's new binding gate. My job is to live-verify the OpenRouter catalog and pull current leaderboard numbers.

Let me hit the OpenRouter API directly (the JSON endpoint is the authoritative live catalog) plus the leaderboards in parallel.
---
This is decisive. Critical findings from the live OpenRouter catalog:

1. **The legacy Sentinel pick `ibm-granite/granite-guardian-4.1-8b` is NOT on OpenRouter.** OpenRouter only has `ibm-granite/granite-4.1-8b` (the base general model, NOT the Guardian RAG-faithfulness specialist). This is the operator's exact "not locked if no OpenRouter access" trigger.
2. **The legacy Mirror pick `cohere/command-a-plus` is NOT on OpenRouter** (confirmed: no Cohere at all). Already known to need re-pick.
3. **No Meta-Llama on OpenRouter** in this catalog — so Llama 3.3-70B (best HHEM open-weight at 4.1%) is NOT OpenRouter-available, surprising. Let me verify this isn't a WebFetch truncation.
4. Writer `deepseek-v4-pro` IS on OpenRouter (confirmed). Judge `qwen/qwen3.6-35b-a3b` IS on OpenRouter (confirmed, note legacy task says "qwen3.6-35b-a3b" — task header wrote "qwen3.6-35b" but the real slug is the a3b).
5. Vectara confirms V4 Pro at **8.6%** hallucination — worse than V3.2-Exp (5.3%), Qwen3-8B (4.8%), Finix S1 (1.8%). This is the Writer tension the prior doc flagged.

Let me verify the Llama/Cohere absence (critical — WebFetch may have truncated), and pull the RAGTruth/LLM-AggreFact/BFCL/IFEval/MedHallu leaderboards in parallel.
---
Confirmed: NO Llama, NO Cohere, NO Granite-Guardian, NO Phi, NO specialized verifiers (LettuceDetect/MiniCheck/Lynx) on OpenRouter. The legacy Sentinel and Mirror picks both fail the OpenRouter gate. NVIDIA Nemotron-3-Super-120B IS available — that's a new candidate not in the prior docs.

Let me record a checkpoint and call advisor before committing to the analysis structure — wait, advisor is FORBIDDEN per memory (`feedback_no_opus_advisor_use_codex_cli_2026_05_23`). I will NOT call advisor. I'll proceed with rigorous live verification.

Now let me get the precise leaderboard numbers: RAGTruth/RL4HS exact scores, BenchLM BFCL V4 + IFEval, and the clinical MedHallu/MedNLI data, plus LLM-AggreFact.
---
### fetched web data (8 snippets):
<system-reminder>[Truncated: PARTIAL view — showing lines 1-674 of 849 total (26746 tokens, cap 25000). Call Read with offset=675 limit=674 for the next page, or Grep to find a specific section. Do NOT answer from this page alone if the answer may be further in the file.]</system-reminder>

1	---
2	status: superseded
3	superseded_by: docs/polaris_step_b_full_set_audit_2026_05_27.md
4	superseded_on: 2026-05-28
5	superseded_reason: Step-B audit reached different conclusions on Mirror/Sentinel picks (Cohere Command A+ replaces Kimi K2.6 for Mirror; Granite Guardian 4.1 replaces 3.3 for Sentinel). Operator confirmed Step-B as final.
6	---
7	
8	# POLARIS Per-Role SOTA Open-Weight LLM Validation (2026-05-27)
9	
10	**Mission:** Replace single-composite-score selection (AA Intelligence Index) with
11	per-role validation using role-specific benchmarks. Operator pushback was correct:
12	each of the 4 POLARIS stack roles (generator / mirror / sentinel / judge) has a
13	distinct capability profile and the "highest average" model is not necessarily
14	the highest in any individual role.
15	
16	**Constraints (operator-locked, May 2026):**
17	- Open weights only (any license)
18	- Non-US runtime LLM (open weights on sovereign infra OK)
19	- No hardware ceiling, no time constraint
20	- Latest + strongest + most capable per role
21	- Multi-domain: clinical + legal + financial + regulatory + policy + scientific, EN baseline
22	- Multi-LLM stack OK if each layer earns its keep
23	
24	**Claude's
~~~
1	---
2	status: research_artifact
3	locked_decision: none (advisory research, no architecture lock here)
4	related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
5	---
6	
7	# Deepest research: Open-Source Non-US Clinical RAG Faithfulness, 2026 SOTA
8	
9	**Author:** Claude (Opus 4.7, 1M context) — research executor
10	**Date:** 2026-05-27
11	**Audience:** POLARIS operator + Codex (architectural reviewer)
12	**Constraints:** open-weight only at runtime, no US-vendor LLM at runtime (Anthropic Citations, Vertex Check Grounding, Azure Groundedness all DISQUALIFIED), no time pressure, no fake shit
13	**Supersedes:** `docs/clinical_rag_validation_sota_2026_05_26.md` — the prior report was constrained to a 9-day demo window and recommended Patronus Lynx 8B; **that recommendation is now invalidated** because Lynx v1.1 is CC-BY-NC (non-commercial). See §4.2 for the licence audit and §5 for the corrected recommendation.
14	
15	---
16	
17	## Executive answer
18	
19	**The actual SOTA architecture for sovereign clinical RAG faithfulness in 2026 is a four-layer pipeline that no single team has fully shipped, but each layer has at least one credibly-deployed open-weight non-US instantiation.** From outermost to innermost:
20	
21	1. **Generator: Qwen3-235B-A22B (Apache 2.0) or DeepSeek-V3.2-Exp (MIT)**, NOT DeepSeek V4 Pro. Both are open-weight, both have lower Vectara hallucination rates than V4 Pro (Qwen3 family clusters around 5%, V3.2-Exp at 5.3%, V4 Pro at 8.6%) [^vectara_lb]. Qw
~~~
675	- **MiniMax M2.7** — IFEval 69.3 disqualifies for any schema-disciplined role.
676	- **Qwen 3.5-397B Reasoning** — strongest pure reasoning + IFEval in pool,
677	  but at 397B MoE it is overkill for per-claim verdict and slower-thinking
678	  variants add latency. Reserve for offline appellate-review batch jobs.
679	- **Gemma 4 31B** — viable backup; AA-Omniscience Accuracy 19.9% suggests
680	  comparable to Qwen 3.6-27B; loses on documented structured-output
681	  discipline.
682	
683	### Does Claude's original pick survive?
684	
685	**NO.** Mistral Medium 3.5 is open-weight (initial assumption "API-only" was
686	wrong — modified MIT weights confirmed 2026-04-29) and a legitimate judge
687	candidate, but loses to **Qwen 3.6-35B-A3B** on (a) license cleanliness for
688	sovereign deployment (Apache 2.0 vs modified MIT with revenue-threshold),
689	(b) per-token cost at per-claim cardinality (35B/3B-active vs 128B dense),
690	and (c) Qwen-family's published structured-output discipline plus
691	multi-benchmark coverage. Operator's pushback validated again: the
692	single-composite Intelligence Index obscured the per-role differential —
693	Mistral Medium 3.5 wins on general-agentic intelligence; Qwen 3.6-35B-A3B
694	wins on the *specific* judge-role capability profile.
695	
696	---
697	
698	## Final cross-family integrity check + summary
699	
700	### Stack-shape clarification (operator-facing)
701	
702	Operator framed the task as a **4-LLM stack** (generator / mirror / senti
~~~
# AI Models by Family - Complete Listing

## DeepSeek
| ID | Name | Context Length | Prompt Price | Completion Price |
|---|---|---|---|---|
| deepseek/deepseek-v4-pro | DeepSeek V4 Pro | 1,048,576 | 0.000000435 | 0.00000087 |
| deepseek/deepseek-v4-flash | DeepSeek V4 Flash | 1,048,576 | 0.0000000983 | 0.0000001966 |
| deepseek/deepseek-v4-flash:free | DeepSeek V4 Flash (free) | 1,048,576 | 0 | 0 |

## Qwen
| ID | Name | Context Length | Prompt Price | Completion Price |
|---|---|---|---|---|
| qwen/qwen3.7-max | Qwen3.7 Max | 1,000,000 | 0.00000125 | 0.00000375 |
| qwen/qwen3.5-plus-20260420 | Qwen3.5 Plus 2026-04-20 | 1,000,000 | 0.0000003 | 0.0000018 |
| qwen/qwen3.6-flash | Qwen3.6 Flash | 1,000,000 | 0.0000001875 | 0.000001125 |
| qwen/qwen3.6-35b-a3b | Qwen3.6 35B A3B | 262,144 | 0.00000014 | 0.000001 |
| qwen/qwen3.6-max-preview | Qwen3.6 Max Preview | 262,144 | 0.00000104 | 0.00000624 |
| qwen/qwen3.6-27b | Qwen3.6 27B | 262,144 | 0.00000029 | 0.0000032 |
| qwen/qwen3.6-plus | Qwen3.6 Plus | 1,000,000 | 0.000000325 | 0.00000195 |
| qwen/qwen3.5-35b-a3b | Qwen3.5-35B-A3B | 262,144 | 0.00000014 | 0.000001 |
| qwen/qwen3.5-9b | Qwen3.5-9B | 262,144 | 0.00000004 | 0.00000015 |

## MoonshotAI (Kimi)
| ID | Name | Context Length | Prompt Price | Completion Price |
|---|---|---|---|---|
| moonshotai/kimi-k2.6 | Kimi K2.6 | 262,144 | 0.000000684 | 0.00000342 |
| moonshotai/kimi-k2.6:free | Kimi K2.6 (free) | 262,144 | 0 | 0 |
| ~moonshotai/kimi-latest | MoonshotAI Kimi Lates
~~~
# Open-Weight Models from Hallucination Leaderboard

Here are the top 30 lowest-hallucination open-weight models from the leaderboard (last updated May 11, 2026):

| Model | Hallucination Rate | Factual Consistency | Answer Rate |
|-------|-------------------|-------------------|-------------|
| antgroup/finix_s1_32b | 1.8% | 98.2% | 99.5% |
| meta-llama/Llama-3.3-70B-Instruct-Turbo | 4.1% | 95.9% | 99.5% |
| google/gemma-3-12b-it | 4.4% | 95.6% | 97.4% |
| qwen/qwen3-8b | 4.8% | 95.2% | 99.9% |
| qwen/qwen3-14b | 5.4% | 94.6% | 99.9% |
| qwen/qwen3-4b | 5.7% | 94.3% | 99.9% |
| qwen/qwen3-32b | 5.9% | 94.1% | 99.9% |
| google/gemma-3-4b-it | 6.4% | 93.6% | 67.3% |
| google/gemma-3-27b-it | 7.4% | 92.6% | 98.8% |
| google/gemma-4-31b-it | 7.4% | 92.6% | 100.0% |
| google/gemma-4-26b-a4b-it | 5.2% | 94.8% | 99.8% |
| deepseek-ai/DeepSeek-V3.2-Exp | 5.3% | 94.7% | 96.6% |
| deepseek-ai/DeepSeek-V3.1 | 5.5% | 94.5% | 94.5% |
| deepseek-ai/DeepSeek-V3 | 6.1% | 93.9% | 97.5% |
| deepseek-ai/DeepSeek-V3.2 | 6.3% | 93.7% | 92.6% |
| deepseek-ai/DeepSeek-R1 | 11.3% | 88.7% | 97.0% |
| deepseek-ai/DeepSeek-V4-Pro | 8.6% | 91.4% | 97.2% |
| mistralai/mistral-large-2411 | 4.5% | 95.5% | 99.9% |
| mistralai/mistral-small-2501 | 5.1% | 94.9% | 97.9% |
| mistralai/ministral-3b-2410 | 7.3% | 92.7% | 99.9% |
| mistralai/ministral-8b-2410 | 7.4% | 92.6% | 99.9% |
| zai-org/GLM-4.5-AIR-FP8 | 9.3% | 90.7% | 98.1% |
| zai-org/GLM-4.6 | 9.5% | 90.5% | 94.5% |
| zai-org/glm-4p7 | 11.7% | 88.3% | 9
~~~
# Model Search Results

**"llama"**: NONE

**"cohere"**: NONE

**"command"**: NONE

**"granite-guardian"**: NONE

**"guardian"**: NONE

**"nemotron"**: 
- ID: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Context: 256000 | Prompt: $0 | Completion: $0
- ID: `nvidia/nemotron-3-super-120b-a12b:free` | Context: 1000000 | Prompt: $0 | Completion: $0
- ID: `nvidia/nemotron-3-super-120b-a12b` | Context: 1000000 | Prompt: $0.00000009 | Completion: $0.00000045

**"phi"**: NONE

**"olmo"**: NONE

**"tulu"**: NONE

**"athene"**: NONE

**"bespoke"**: NONE

**"minicheck"**: NONE

**"lynx"**: NONE
~~~
