# M-D5 phase 2 v1 — LLM-augmented ScopeEligibilityClassifier boundary

**Status:** v1 / 2026-04-29
**Module:** `src/polaris_graph/audit_ir/scope_classifier_llm.py`
**Tests:** `tests/polaris_graph/test_md5_phase2_llm_classifier.py` (34 passing)
**Pairs with:** M-D5 phase 1 (`scope_classifier.py`, v6 commit
460234a + post-460234a doc bump). Inherits prompt-injection
defense pattern from M-D2 phase b
(`auto_induction/llm_inductor.py`).
**Substrate:** stdlib + `scope_classifier` (phase 1 contracts).

---

## Scope

M-D5 phase 1 shipped the `ScopeEligibilityClassifier` Protocol +
`confidence_gated_match` orchestration. The Protocol slot was
empty — phase 1 was substrate-only.

Phase 2 v1 ships the **concrete LLM-augmented classifier** that
fills the Protocol slot:
  - `ScopeAffinityLLM` Protocol (LLM seam)
  - `LLMVerdict` dataclass (raw LLM output)
  - `MockScopeAffinityLLM` (deterministic, for tests)
  - `LLMScopeEligibilityClassifier` (Protocol implementation)
  - `LLMScopeEligibilityClassifierConfig` (supported_domains +
    min_confidence_floor)
  - `build_question_block` (per-call random delimiter)

**Unblocks M-D6** (cross-domain templates) — M-D6 needs a
working classifier to route queries to domain-specific
adapters. v1 gives M-D6 a Mock for testing + a clear
production-wiring path (just plug an OpenRouter-backed
`ScopeAffinityLLM` impl).

---

## v1 boundaries

### 1. Pure substrate — no LLM client coupling

`scope_classifier_llm.py` imports stdlib + `scope_classifier`
(phase 1 contracts) only. The `ScopeAffinityLLM` Protocol is
the seam: production wiring uses M-D2 phase b's existing
OpenRouterClient infrastructure (deferred to v2 of this
milestone).

This separation keeps the orchestration logic
(LLMScopeEligibilityClassifier) testable without API costs,
mirrors M-D2 phase b's pattern, and lets future LLM swaps
(Anthropic, OpenAI direct) drop in without touching the
classifier internals.

### 2. Closed verdict-string taxonomy

`LLMVerdict.verdict` MUST be one of `"in_scope"`,
`"out_of_scope"`, `"uncertain"` (case-insensitive at adapt
time — `"IN_SCOPE"` is accepted and normalized). Anything
else raises `LLMScopeClassifierError` at `classify()` time.

This protects against LLM misalignment (the LLM emits a
wrong-shape verdict) AND against silent taxonomy drift if
phase 1's `ScopeVerdict` enum grows new values without
updating phase 2.

**Mitigation**: `_VALID_VERDICT_STRINGS` frozenset is the
single source of truth. Tests pin every valid verdict +
several invalid cases.

### 3. Domain validation tied to supported_domains

`in_scope` verdicts MUST carry a `domain` value, and that
domain MUST be in `config.supported_domains`. Non-`in_scope`
verdicts (out_of_scope, uncertain) MUST carry `domain=None`.

Rationale:
  - An `in_scope` verdict naming a NON-supported domain
    would mislead M-6 routing (it'd send the question to a
    non-existent adapter).
  - An `out_of_scope` verdict with a domain set would also
    mislead — operators shouldn't see "out of scope, but
    here's a clinical tag" because the tag isn't actionable.

**Mitigation**: 3 tests pin
(`test_in_scope_without_domain_raises`,
`test_in_scope_with_unsupported_domain_raises`,
`test_non_in_scope_with_domain_raises`).

### 4. Confidence range enforced at adapter time

`LLMVerdict.confidence` MUST be numeric (int or float) and in
`[0.0, 1.0]`. Out-of-range or non-numeric values raise
`LLMScopeClassifierError`.

Phase 1's gate already validates classifier confidence at
gate-time too (per phase 1 boundary 2), but defense in depth
catches LLM-side bugs before they reach the gate.

### 5. min_confidence_floor demotes IN_SCOPE → UNCERTAIN

`config.min_confidence_floor` (default 0.0 = disabled) lets
operators force low-confidence `in_scope` verdicts to
`uncertain`. The phase 1 gate's
`PG_SCOPE_GATE_CONFIDENCE_THRESHOLD` (default 0.70) gates
classifier-confidence at the gate level; this floor is a
classifier-internal pre-filter for operators who want
stricter abstention than the gate enforces.

Demotion preserves the original confidence value (caller can
still see "we got 0.5 from the LLM but treated as uncertain")
and prepends `"demoted to uncertain: ..."` to the rationale.

`out_of_scope` verdicts are NEVER demoted by the floor —
floor only protects against acting on weak `in_scope`
signals. Pinned by `test_floor_does_not_demote_out_of_scope`.

### 6. LLM-side exception handling: fail-loud-via-rationale

When the LLM call raises any non-`LLMScopeClassifierError`
exception (timeout, network error, JSON parse failure, etc.),
the classifier returns `ScopeClassification(verdict=UNCERTAIN,
confidence=0.0, domain=None, rationale="LLM call failed: ...")`
rather than re-raising.

Rationale: the gate handles UNCERTAIN by routing to operator
review. A raise here would crash the gate, taking down the
audit pipeline for transient LLM failures. Surface the
failure via rationale (operators see the actual error string)
without breaking the pipeline.

`LLMScopeClassifierError` (our own contract violations) DO
re-raise — those are programmer bugs, not transient failures.

**Mitigation**: `test_llm_exception_returns_uncertain_with_rationale` +
`test_llm_scope_classifier_error_propagates`.

### 7. Prompt-injection defense via per-call random delimiters

`build_question_block(question) -> (open_delim, close_delim,
escaped_question)` mirrors M-D2 phase b's
`_build_query_block`:
  - 16-hex-char random token from `secrets.token_hex(16)`
  - Open: `<<<question-{token}>>>`
  - Close: `<<<end-{token}>>>`
  - Defense in depth: any `<<<end-?[a-f0-9]*>>>` substring in
    the question body is replaced with `<<<escaped>>>`

This is identical to M-D2 phase b's defense, deliberately —
both subsystems face the same threat (untrusted user query
embedded in an LLM prompt) and should converge on the same
mitigation.

**Mitigation**: 3 tests pin (random-token-per-call,
static-close-delim-stripped, safe-text-byte-preserved).

---

## v1 NON-goals (defer to v2)

  - **No OpenRouter integration**: production wiring uses
    M-D2 phase b's existing `OpenRouterClient` machinery. v2
    will ship `OpenRouterScopeAffinityLLM` mirroring
    `OpenRouterTemplateAffinityClassifier`.
  - **No prompt template ship**: `build_question_block` is
    the prompt-injection-safe fence; the actual prompt body
    (system message, JSON schema instructions, few-shot
    examples) ships with v2 alongside the OpenRouter wiring.
  - **No cross-workspace cost accounting**: v2 inherits the
    M-D2 phase b cost-tracking ContextVar (`_RUN_COST_CTX`).
  - **No retry/backoff**: caller's `ScopeAffinityLLM` impl
    handles transient errors (or doesn't, and the
    classifier's exception handler routes to UNCERTAIN).
  - **No M-D6 domain-adapter selection**: classifier returns
    `domain` tag; M-D6 reads it and dispatches to the right
    adapter. The dispatch logic is M-D6 territory.

---

## Codex review trail

Round-1 brief incoming. Tool hints:
- `python -m pytest -q tests\polaris_graph\test_md5_phase2_llm_classifier.py`
- DO NOT run rg/find — read source/tests/threat-model directly
- DO NOT run Python verification scripts that print Unicode
- 34 tests pin all 7 boundaries

Targeted at 1-2 round convergence per the M-D7 phase 2 +
M-D11 phase 2 v2 patterns (substrate orchestration with
v1-shipped threat-model docs).

---

## Lock note

v1 GREEN-lock target after Codex round 1-2. v2 (OpenRouter
wiring + prompt template + cost tracking) and M-D6 unblock
tracked separately.
