# DeepSeek V4 Pro + strict_verify provenance — deep research

**Date:** 2026-05-25 (UTC night)
**Trigger:** Operator picked Option B ("make V4 Pro work properly") after I surfaced
what turned out to be a stale claim of a V3.2-Exp-vs-V4-Pro mismatch.
**Status of the mismatch:** RESOLVED 11 days before this research (I-gen-003 #495
shipped 2026-05-14). The mismatch I cited was stale `active_issue.json` data.

## TL;DR

- POLARIS already runs V4 Pro by default (`openrouter_client.py:408`).
- I-gen-003 #495 fixed the I-bug-091 CoT-leak failure mode 11 days ago via a HARD
  OUTPUT CONTRACT prompt + bounded multi-retry for reasoning-first models.
- I-gen-004 #496 added separate capture of the V4 Pro `reasoning_content` channel.
- This research surfaces ONE remaining concern: V4 Pro's multi-turn
  `reasoning_content` preservation requirement. POLARIS does single-turn-per-section
  today, so this doesn't bite — but it would if we ever add multi-turn refinement.

## 1. V4 Pro official API surface

Source: https://api-docs.deepseek.com/

- Base URL: `https://api.deepseek.com`. OpenAI-compatible ChatCompletions format.
- Model ID: `deepseek-v4-pro`.
- Response schema:
  - `choices[0].message.content` — final answer.
  - `choices[0].message.reasoning_content` — chain-of-thought reasoning (when
    thinking mode enabled), at the **same level** as `content`.
- Three reasoning modes via `reasoning_effort`: non-think / think-high / think-max.
- Think-max requires ≥384K context window (vs 1M available).
- Reasoning tokens generated **before** the final answer; counted toward
  completion tokens.

Quote (https://api-docs.deepseek.com/guides/thinking_mode):

> "The chain-of-thought content is returned via the `reasoning_content` parameter,
> at the same level as `content`."

## 2. V4 Pro vs V3.2-Exp — breaking changes in output format

Source: https://www.siliconflow.com/models/compare/deepseek-v3-2-exp-vs-deepseek-v4-pro
and https://api-docs.deepseek.com/news/news260424 (V4 release notes 2026-04-24).

| Aspect | V3.2-Exp | V4 Pro | Impact on POLARIS |
|---|---|---|---|
| Thinking mode | Single path | 3 modes (non-think / think-high / think-max) | Output structure differs |
| Tokenizer | Original | **New** | Cached prefix indices invalidated |
| Multi-turn `reasoning_content` | Optional in follow-ups | **REQUIRED** if tool calls present | 400 error if not preserved |
| Attention | Sparse uniform | Hybrid CSA + HCA | Speed only; not visible |
| CoT planning leakage to `content` | Rare | Common in think-max | Caught by I-bug-091, fixed by I-gen-003 |

Quote (https://www.digitalapplied.com/blog/deepseek-v3-2-to-v4-migration-playbook-open-weight-stack-2026):

> "V4 ships a new tokenizer. Any prompt-prefix cache, KV-cache prefix index, or
> evaluation suite built against V3.2 token IDs is invalidated on the first V4
> request."

## 3. What I-bug-091 (2026-05-09) actually saw

Quoting the commit body (4446a2df):

> "Live BEAT-BOTH on V4 Pro + Gemma 4 31B post I-bug-088/089/090 stack demonstrated
> V4 Pro's CoT-style output is structurally incompatible with
> multi_section_generator's strict_verify [#ev:] provenance-token requirement:
>   Run 1 (PR#339): no recovery, content empty
>   Run 2 (PR#340): fail-loud Section 1
>   Run 3 (PR#341+6000): fail-loud Section 2 (43K input, 19,843 chars of CoT
>     planning, no provenance markers)"

V4 Pro emitted **chain-of-thought planning instead of the cited paragraph**, and
the planning text had no `[ev_XXX]` markers. `strict_verify` dropped the whole
draft. The token budget was exhausted by planning before the actual answer began.

## 4. What I-gen-003 (2026-05-14) shipped

Quoting the commit body (0c55a4bc):

> "multi_section_generator._call_section — on the tighter_retry path, for
> reasoning-first models (model in _REASONING_FIRST_MODELS), append a HARD
> OUTPUT CONTRACT: explicit anti-CoT instruction forbidding 'Let me…', 'First,
> I will…', step lists, meta-commentary; demand ONLY the finished paragraph
> body, every sentence ending in [ev_XXX]."

Three changes:

1. **HARD OUTPUT CONTRACT prompt** appended on retry for reasoning-first models.
2. **Bounded multi-retry up to 3** for reasoning-first models (was 1).
3. **Retry gate fix** — fires even when `total_in == 0` (V4 Pro CoT planning has
   no parseable sentence structure).

I-gen-003 was Codex-APPROVE iter 2; smoke #4 passed.

## 5. What I-gen-004 (#496) added

Captures V4 Pro `reasoning_content` channel separately from `content`. Stored
alongside the report for audit/transparency. This addresses the architectural
half of the V4 Pro adoption — the operator now has visibility into what V4 Pro
was THINKING vs what it RETURNED.

## 6. Known V4 Pro bugs in the broader ecosystem (still open)

From GitHub issues:

- **BerriAI/litellm #26395** — `reasoning_content` stripped from assistant messages
  during multi-turn. V4 Pro returns 400 on turn 2 if not preserved.
- **anomalyco/opencode #24442** — interleaved transform processes requests twice;
  second pass overwrites stored `reasoning_content` with empty string.
- **anomalyco/opencode #24190** — `reasoning_content` not round-tripped through
  conversation history; 400 error on tool calls.
- **NousResearch/hermes-agent #16677** — OpenRouter V4 Pro gateway crash loop
  April 26-27 2026.
- **cline/cline #10551** — 1M context capped at 128K via OpenRouter; tool parsing
  mistakes; context overflow.

**POLARIS exposure assessment:** `multi_section_generator._call_section` does
**single-turn-per-section** requests (each retry is a fresh call, not a
continuation of conversation history). So the multi-turn `reasoning_content`
bug class does NOT apply to POLARIS today. **It would bite hard if we ever add
multi-turn refinement** (e.g., "verify these citations" follow-up turn). Flag
for future work.

## 7. Best-practice patterns for per-sentence citation discipline

From the literature (CiteFix arxiv 2504.15629, VeriCite arxiv 2510.11394,
SemanticCite arxiv 2511.16198):

1. **Two-pass citation verification.** Generate answer + draft citations in
   single turn; then run a separate verification pass that validates each
   `[#ev:X:Y-Z]` span against the actual evidence source. POLARIS's existing
   `strict_verify` is exactly this pattern.
2. **JSON-schema-bound output for citations.** Conflicts with inline citation
   tokens at the API level — DeepSeek's `response_format: json_object` mode
   does NOT enforce `[#ev:X:Y-Z]` token discipline.
3. **Reasoning/output channel separation.** Use the `<think>...</think>` /
   `reasoning_content` field for planning, force the answer-only `content` to
   carry citations. This is what I-gen-004's separation enables.
4. **HARD OUTPUT CONTRACT prompt.** Explicit anti-CoT instruction for
   reasoning-first models. This is what I-gen-003 shipped.

POLARIS's combination of I-gen-003 (anti-CoT prompt) + I-gen-004 (channel
separation) + `strict_verify` (per-sentence span validation) matches the
literature's recommended architecture.

## 8. What's NOT verified

- Whether V4 Pro's current behavior on real clinical questions hits acceptable
  HHEM Vectara faithfulness scores under I-gen-003's HARD OUTPUT CONTRACT. The
  most recent `outputs/honest_sweep_r3/.../manifest.json` shows
  `status: partial_qwen_advisory` — but that data may be stale (modified at
  session start; predates current code state).
- Whether the bounded 3-retry is enough or whether V4 Pro still occasionally
  emits CoT after 3 retries. Smoke test needed.
- Whether the OpenRouter 128K context cap (cline #10551) bites POLARIS's
  long-context corpus loading.

## 9. Recommended next step

**Single smoke test:** run one `scripts/run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm`
end-to-end on V4 Pro. Inspect:

- `manifest.json` `status` field (should be `success`, not `abort_*`).
- `report.md` non-empty with `[ev_XXX]` markers on every sentence.
- `verification_details.json` strict_verify pass rate ≥ 40% per section.
- HHEM Vectara faithfulness on the report.

If the smoke passes → V4 Pro work is DONE. No new issue needed.
If it fails → file an issue with the specific failure mode + counts; iterate.

## 10. Sources (42, complete)

Pulled into one bibliography for audit:

### Official DeepSeek

- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/guides/thinking_mode
- https://api-docs.deepseek.com/guides/json_mode
- https://api-docs.deepseek.com/news/news260424

### Migration / comparison

- https://www.siliconflow.com/models/compare/deepseek-v3-2-exp-vs-deepseek-v4-pro
- https://artificialanalysis.ai/models/comparisons/deepseek-v4-pro-high-vs-deepseek-v3-2-reasoning-0925
- https://www.digitalapplied.com/blog/deepseek-v3-2-to-v4-migration-playbook-open-weight-stack-2026
- https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-pro
- https://openrouter.ai/deepseek/deepseek-v4-pro
- https://openrouter.ai/deepseek/deepseek-v4-pro/api

### V4 Pro bug reports

- https://github.com/BerriAI/litellm/issues/26395
- https://github.com/anomalyco/opencode/issues/24442
- https://github.com/anomalyco/opencode/issues/24190
- https://github.com/anomalyco/opencode/issues/24114
- https://github.com/NousResearch/hermes-agent/issues/16677
- https://github.com/cline/cline/issues/10551
- https://github.com/musistudio/claude-code-router/issues/1378

### Citation verification literature

- https://arxiv.org/pdf/2510.11394 (VeriCite)
- https://arxiv.org/pdf/2504.15629 (CiteFix)
- https://arxiv.org/pdf/2511.16198 (SemanticCite)
- https://arxiv.org/html/2506.06605v1 (MedCite)
- https://arxiv.org/pdf/2509.21557 (Generation-time vs post-hoc citation)
- https://arxiv.org/pdf/2511.06738 (Rethinking RAG for medicine)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC12540348/ (MEGA-RAG)
- https://ailva.ai/blog/why-clinical-ai-tools-hallucinate-citations
- https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2026.1737532/full

### Constrained generation

- https://fireworks.ai/blog/constrained-generation-with-reasoning
- https://python.useinstructor.com/integrations/deepseek/
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://arxiv.org/pdf/2408.11061 (StructuredRAG)
- https://arxiv.org/pdf/2501.10868 (JSONSchemaBench)
- https://arxiv.org/pdf/2502.14905 (Think Inside the JSON)

### Reasoning model architecture

- https://arxiv.org/abs/2501.12948 (DeepSeek-R1)
- https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B
- https://bagerbach.com/blog/understanding-deepseek-r1/
- https://arxiv.org/pdf/2503.01923 (Output length effect on R1 safety)
- https://arxiv.org/html/2512.12117v1 (Citation-grounded code comprehension)
- https://arxiv.org/pdf/2305.14627 (Enabling LLMs to generate text with citations)

### LLM citation behavior

- https://derivatex.agency/blog/how-llms-decide-what-to-cite/
- https://discoveredlabs.com/blog/content-clarity-and-verifiability-the-technical-patterns-that-drive-llm-citations/
- https://dev.to/tensorlake/make-rag-provable-page-bbox-citations-for-all-extracted-data-4ipc
- https://www.getpliant.com/en/blog/production-ready-ai
