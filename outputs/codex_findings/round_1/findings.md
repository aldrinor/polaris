---
verdict: NOT_READY
blocker_count: 5
medium_count: 0
rationale: |
  Codex round 1 surfaced 5 critical blockers: strict_verify skips
  semantic checks on non-numeric claims; the sweep orchestrator writes
  corpus_approval.json but never enforces the approved flag; report.md
  can still be written when all sections drop; the budget cap is
  bypassable if OpenRouter omits usage.cost; prompt-injection sanitizer
  doesn't redact literal delimiter strings inside evidence. All 5
  include file:line refs. The aborted-path behavior (tech_rag) was
  confirmed correct.
---

# Codex round 1 findings — 2026-04-18

_Auto-captured from Codex stdout (writing to `.codex/` was blocked by
Windows ACL deny ACE on that directory; review ran to completion and
the content below is Codex's verbatim output)._

## Critical issues (blockers)

### B-1: `strict_verify()` skips semantic checks on non-numeric claims

- **File:line**: `src/polaris_graph/generator/provenance_generator.py:277-375`
  and `src/polaris_graph/generator/live_deepseek_generator.py:269-274`
- **Reproducer**: A sentence like `Semaglutide improved sleep quality
  [#ev:ev1:0-20].` is kept even if the cited span only says
  `14.9% weight loss`. The non-numeric content ("improved sleep quality")
  receives no semantic grounding check.
- **Impact**: A generator can fabricate qualitative claims (populations,
  contraindications, comparative superiority, indication scope) and
  the verifier will pass them as long as at least one integer / decimal
  in the sentence lines up.

### B-2: Sweep orchestrator does not enforce corpus approval

- **File:line**: `scripts/run_honest_sweep_r3.py:475-490` (writes
  `corpus_approval.json`) and `:505-631` (continues regardless of `approved`).
- **Reproducer**: Trigger a material deviation + supply a trivial
  approval note. `check_auto_approve_allowed()` returns False, the
  decision is saved with `approved=False`, but the orchestrator still
  runs contradiction detection, multi-section generation, and evaluator
  calls. There is no branch that aborts on rejected corpus approval.
- **Impact**: The corpus-approval gate is cosmetic. A corpus with
  material deviation + rubber-stamp note is still synthesized.

### B-3: `report.md` written even when all sections fail verification

- **File:line**: `src/polaris_graph/generator/multi_section_generator.py:343-352`
  and `:397-413` and `:624-634`; `scripts/run_honest_sweep_r3.py:545-631`.
- **Reproducer**: Set up a scenario where every section's
  `dropped_due_to_failure=True` (e.g., all sections' outlines reference
  evidence whose direct_quote doesn't contain any cited-sentence decimals).
  The assembled `sections_concat` becomes an empty string, but
  `report.md` is still written (with only Methods + Bibliography +
  empty body), and only then does the post-hoc status check mark the
  run `fail_no_verified_prose`.
- **Impact**: Downstream consumers of `report.md` may process a
  technically-written file that has no verified findings. The status
  marker is the only signal, and it's post-hoc.

### B-4: Budget cap bypassable when OpenRouter omits `usage.cost`

- **File:line**: `src/polaris_graph/llm/openrouter_client.py:1235-1273`
- **Reproducer**: OpenRouter's API response for some models does not
  include `usage.cost`. The code extracts `api_cost = usage_data.get("cost", 0.0)`
  and then `_add_run_cost(api_cost)` only adds the non-zero cost.
  A model returning `usage={input_tokens, output_tokens}` without a cost
  field contributes `$0.00` to `_RUN_COST_USD`. `check_run_budget()`
  happily keeps running past the intended cap.
- **Impact**: `PG_MAX_COST_PER_RUN` is not a reliable hard cap. A runaway
  loop with a model that doesn't report cost can burn indefinite budget.

### B-5: Prompt-injection delimiter breakout via `<<<end_evidence>>>` literal

- **File:line**: `src/polaris_graph/generator/provenance_generator.py:62-130`
- **Reproducer**: A malicious evidence source contains the literal
  string `<<<end_evidence>>>` followed by injected instructions
  followed by `<<<evidence:ev_001>>>`. The sanitizer redacts a fixed
  list of phrases ("ignore previous instructions", "system:", etc.)
  but does NOT redact or escape the delimiter strings themselves. The
  model sees what looks like the end of one evidence block and the
  start of a new one — bypassing the "DATA, not INSTRUCTIONS" framing.
- **Impact**: Prompt-injection defense claim in Methods section is
  overstated. The delimiter is the root of the trust boundary and it's
  bypassable by literal string insertion.

## Minor issues (Codex did not surface any this round)

## Disputes with prior round

N/A (round 1).

## What's well-built (don't regress)

- `outputs/honest_sweep_r6_validation/tech/tech_rag_architectures_2024/manifest.json`
  has `status=abort_corpus_inadequate` and `cost_usd=0`. Confirmed no
  LLM call was made. The abort path is genuinely correct.
- The abort manifest does NOT contain `evaluator_rule_pass`, so the
  flow short-circuits before Phase 5 evaluation — matches the protocol
  spec.

## Recommendation

Not ready for full-scale production. Fix all 5 blockers before round 2.
Each has a concrete code-level reproducer. Expected effort: 2-4 hours
per blocker = 10-20 hours total, well inside the 24-hour window.

## Operational note (ACL)

`C:\POLARIS\.codex` has a Deny ACE for the Codex sandbox user SID that
overrides the `CodexSandboxUsers Modify` allow. Future rounds should
write findings to `outputs/codex_findings/round_N/findings.md` which
is writable from the sandbox.
