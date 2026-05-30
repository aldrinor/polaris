# I-meta-002 — Wire Mirror + Sentinel + Judge to unfreeze the smoke pipeline (DESIGN BRIEF)

UNCAPPED iteration per planning-audit standing directive. This is design, not code-diff.

## Output schema

```yaml
verdict: APPROVE_DESIGN | REQUEST_DEEPER_DESIGN
confirmed_design_choices: [...]
novel_design_concerns_codex_found: [...]
disagreements: [...]
implementation_order: [...]              # dependency-ordered sequence of sub-PRs
operator_decisions_blocked_on: [...]
metrics_to_validate_at_each_step: [...]
convergence_call: continue | accept_remaining
```

## Context (already settled — do not relitigate)

- 4-role architecture locked at `config/architecture/polaris_runtime_lock.yaml` (I-meta-001 #933, PR #934). Operator D1 signed, Codex APPROVE_FOR_IMPLEMENTATION iter 2.
- Generator (deepseek/deepseek-v4-pro) is already wired. Smoke pipeline produces sections via `generate_multi_section_report` + per-sentence entailment via `entailment_judge`.
- Path-B gate's `_assert_architecture_coverage()` STRUCTURALLY FREEZES smokes while lock status = `codex_approved_pending_operator_signature`. To unfreeze: wire Mirror + Sentinel + Judge AND promote lock to `locked` via verify_lock.py.
- Carney deadline 2026-09-06 (~14 weeks). 5-cap binding on code-diff reviews; UNCAPPED on this design brief.

## The design question

How do 4 LLMs + 2 deterministic layers compose into a single production pipeline that:
1. Produces a clinical-grade research report
2. Captures every role's served identity via Path-B gate (`_PATHB_ROLE` ContextVar)
3. Honors §-1.1 line-by-line audit (claim-by-claim against fetched cited spans)
4. Passes the architecture-coverage check at preflight + post-run
5. Beats ChatGPT 5.5 Pro / Gemini 3.1 Pro DR on the 5 frozen DRB-EN questions

## Per-role responsibilities (from lock YAML)

- **Generator** (V4 Pro): recall-heavy synthesis. Produces sections + sentences + provenance tokens `[#ev:<id>:<start>-<end>]`. Existing: `src/polaris_graph/generator/multi_section.py`.
- **Mirror** (Cohere Command A+): calibration auditor. Best AA-Omniscience calibration in pool (14.1%), native citation grounding. Tests claims the Generator cannot self-verify. Input: Generator's claims + cited spans. Output: per-claim calibration verdict.
- **Sentinel** (IBM Granite Guardian 4.1 8B): purpose-built RAG hallucination detector. RAGTruth BAcc 0.841. Catches Mirror's misses. Input: Generator's claims + Mirror's verdicts. Output: hallucination flag + span attribution.
- **Judge** (Qwen 3.6-35B-A3B): terminal arbiter. Native structured-output discipline. Input: Generator's claims + Mirror's verdicts + Sentinel's flags. Output: stable parseable terminal verdict per claim (`{verdict: VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE, confidence: 0-1, reason: str}`).
- **Python validators** (existing strict_verify): citation existence, numeric/date checks, span-overlap.
- **Codex §-1.1 audit** (external): claim-by-claim manual + Codex-assisted PRISMA 2020 + AMSTAR-2 + GRADE per claim.

## Claude's working design (CHALLENGE THIS)

### Data flow (single claim path)

```
generator produces:
  claim_text + provenance_token [#ev:E12:230-410]
  ↓
strict_verify (python):
  pass/fail based on numeric/date/span-overlap → DROP if fail
  ↓
Mirror (Cohere) — calibration:
  prompt = "Given this claim and the cited span, rate calibration confidence."
  output = {calibration_score: 0-1, miscalibration_warning: str | null}
  ↓
Sentinel (Granite Guardian) — hallucination:
  prompt = "Given claim + cited span + Mirror's calibration, detect hallucination."
  output = {is_hallucination: bool, hallucination_type: enum, span_attribution: str}
  ↓
Judge (Qwen) — terminal verdict:
  prompt = "Given claim + cited span + Mirror calibration + Sentinel flag, emit terminal verdict."
  output = {verdict: VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE, confidence: 0-1, reason: str}
```

### Per-role module structure (proposed)

```
src/polaris_graph/
  mirror/
    __init__.py
    client.py            # MirrorCohereClient wrapping OpenRouterClient with role="mirror"
    prompt.py            # _MIRROR_PROMPT template
    schema.py            # MirrorVerdict dataclass + JSON Schema
    test_fixtures/...    # not src — tests go in tests/

  sentinel/
    __init__.py
    client.py            # SentinelGraniteClient
    prompt.py            # _SENTINEL_PROMPT (Granite Guardian's native prompt format)
    schema.py            # SentinelVerdict

  judge/
    __init__.py
    client.py            # JudgeQwenClient (Qwen 3.6-35B-A3B native structured output)
    prompt.py            # _JUDGE_PROMPT
    schema.py            # TerminalVerdict
```

Each client:
- Constructs OpenRouterClient with role parameter (extends current pattern in entailment_judge.py)
- Wraps the LLM call with `pathB_capture.llm_role(<role>)` context manager so Path-B gate captures it
- Returns the role-specific verdict object
- Handles its own retries / timeouts independent of other roles

### Orchestration in pathB_runner

`_role_pins()` currently returns 2 RolePins. Change to 4:

```python
def _role_pins() -> list[RolePin]:
    gen = os.getenv("PG_GENERATOR_MODEL") or _DEFAULT_GEN_SLUG
    mir = os.getenv("PG_MIRROR_MODEL") or "cohere/command-a-plus"
    sen = os.getenv("PG_SENTINEL_MODEL") or "ibm-granite/granite-guardian-4.1-8b"
    jud = os.getenv("PG_JUDGE_MODEL") or "qwen/qwen-3.6-35b-a3b"
    sf = ("provider_name", "model")
    return [
        RolePin("generator", gen, "", sf),
        RolePin("mirror",    mir, "", sf),
        RolePin("sentinel",  sen, "", sf),
        RolePin("judge",     jud, "", sf),
    ]
```

The pipeline ORDER per claim:
1. Generator emits the section (existing path)
2. strict_verify drops fabrications (existing path)
3. For each surviving sentence: Mirror → Sentinel → Judge → final verdict
4. Aggregate per-sentence verdicts into manifest

Per-claim mode is the natural §-1.1-aligned shape: each claim gets a single VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE verdict from Judge, with Mirror + Sentinel as upstream signals.

### Resource cost concerns

Currently smoke #13 (2-LLM) used 28 generator + 108 entailment calls = 136 calls / $0.40.

Projection for 4-LLM with the proposed flow:
- 28 generator calls (unchanged)
- ~108 strict_verify (free — Python only)
- ~108 Mirror calls
- ~108 Sentinel calls
- ~108 Judge calls
- Total: ~432 LLM calls per smoke (3.2× current)
- Per Codex's iter 1 brief (`feedback_no_cost_mentions` — don't cite $ in trade-off framing): we report calls + tokens, operator decides budget

Per CLAUDE.md `feedback_no_cost_mentions`: not citing $ here. Operator authorizes spend.

### Path-B gate integration

Each module's client wraps every LLM call in:
```python
with pathB_capture.llm_role("mirror"):
    response = self._client.generate(...)
```

This makes role tagging automatic. The gate already supports per-role provider resolution via the contextvar substrate added in I-bug-946.

### Test strategy

Per module:
- Unit test: mock OpenRouterClient response → assert correct verdict shape
- Integration test: assert pathB_capture records the call under the expected role
- Cost test: assert no double-charging the budget cap when retries fire

Pipeline-level:
- 4-role smoke fixture (mock all LLMs) that exercises the full flow
- Assert manifest.architecture_coverage.status == "ok" + all 4 roles in served_identity_by_role

## OPEN DESIGN QUESTIONS for Codex

### Q1. Per-claim flow vs per-section batch?

Per-claim (my proposed): each claim → independent Mirror/Sentinel/Judge calls. Pro: claim-level granularity matches §-1.1. Con: high call count.

Per-section batch: Mirror sees the whole section + all claims at once, returns batch verdict. Pro: lower cost. Con: §-1.1 expects per-claim, so we'd need to disaggregate batched verdicts back to claims — error-prone.

Codex's read?

### Q2. Mirror prompt design — calibration vs disagreement?

Cohere Command A+ is best-in-class at AA-Omniscience calibration (14.1%). The natural Mirror task is: "score how confident the Generator should be in this claim given the cited span." Output: numeric score 0-1 + miscalibration warning.

Alternative: Mirror as DISAGREEMENT signal. "Read claim + cited span; would YOU make the same claim? If not, what would you say?" Output: agree/disagree + alternative formulation.

The locked decision doc emphasizes calibration. So lean is Q2-a (calibration). But the actual prompt matters — Codex's input?

### Q3. Sentinel's role overlap with strict_verify?

strict_verify catches obvious fabrications (numeric mismatch, span-overlap). Sentinel catches subtler hallucinations (unsupported entailment, plausible-but-wrong). The OVERLAP is "should Sentinel run on claims that strict_verify already dropped?" → no, run only on survivors. Codex confirm?

### Q4. Judge's output schema — match §-1.1 verdicts exactly?

§-1.1 audit uses {VERIFIED, PARTIAL, UNSUPPORTED, FABRICATED, UNREACHABLE}. Should Judge emit exactly this enum? Pro: per-claim ledger directly consumable by score_run.py. Con: Judge model might prefer different category names that map better to its training.

Lean: emit the §-1.1 enum verbatim; map Judge's native output if needed via post-processing.

### Q5. Failure modes — what if Judge disagrees with Mirror+Sentinel?

If Mirror says "calibrated" + Sentinel says "no hallucination" but Judge says FABRICATED, do we trust Judge as terminal? Or flag the disagreement for §-1.1 review?

Lean: Judge IS terminal; disagreements logged for offline analysis but don't change the verdict.

### Q6. Sub-PR ordering — is the proposed 6-PR sequence correct?

PR-1 (design doc) → PR-2 (Mirror) → PR-3 (Sentinel) → PR-4 (Judge) → PR-5 (orchestration) → PR-6 (lock promotion + smoke validation).

Alternative: parallel module development. Pro: faster. Con: orchestration depends on all 3, can't ship without all done. Lean: sequential, ~1 module/day with Codex review.

### Q7. What does PR-1 (design doc) actually deliver?

Lean: `docs/architecture/polaris_4role_data_flow_2026_05_28.md` with the claim-flow diagram + per-role I/O spec + orchestration sequence + Codex-APPROVED rationale. This becomes the spec the 4 implementation PRs reference.

## Required from Codex

A. Confirm or refute the per-claim flow design (Q1) and the per-role prompts/schemas (Q2-Q4).
B. Catch design risks Claude missed (especially failure modes Q5).
C. Lock the sub-PR ordering (Q6) and the design doc deliverable shape (Q7).
D. Surface any model-specific quirks Codex's web research can confirm:
   - Cohere Command A+ structured output format
   - IBM Granite Guardian's native prompt format + output schema
   - Qwen 3.6-35B-A3B function-call mode for terminal verdict emission
E. Estimate complexity per module (which is the longest pole).
F. Flag any §-1.1 alignment issues with the proposed flow.

When Codex hits `convergence_call: accept_remaining` AND Claude agrees the design is implementable, the next step is PR-1 (design doc) commit.
