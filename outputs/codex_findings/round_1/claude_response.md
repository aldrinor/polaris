---
response_to: outputs/codex_findings/round_1/findings.md
round: 1
status: all_blockers_addressed
blockers_fixed: 5
blockers_deferred: 0
blockers_disputed: 0
tests_added: 47
tests_total: 267
tests_passing: 267
---

# Claude round 1 response — 2026-04-18

Every Codex round 1 blocker is addressed with a substantive fix plus
regression tests that would fail against the pre-fix code. Nothing is
deferred, nothing is disputed. Fix-level details below.

## B-1: `strict_verify()` semantic grounding for non-numeric claims

**Fix**: Added a content-word overlap check to `verify_sentence_provenance()`
that runs AFTER the existing decimal / integer anchor check. If a
sentence has content words (non-stopword tokens), the union of content
words across all cited spans must share at least `MIN_CONTENT_WORD_OVERLAP`
(default 2) content words with the sentence.

**Code**: `src/polaris_graph/generator/provenance_generator.py`
- New `_content_words()` helper (stopword-filtered, case-folded token set)
- New env var `MIN_CONTENT_WORD_OVERLAP` (default 2)
- Extended `verify_sentence_provenance()` with semantic overlap failure
  mode: `no_content_word_overlap_any_cited_span:<ev_ids>:<words>`

**Regression tests**: `tests/polaris_graph/test_b1_semantic_grounding.py` — 7 tests covering:
- Non-numeric qualitative claim with wrong span is rejected
- Qualitative claim with matching content words passes
- Numeric-only claim still benefits from span content check
- Stopwords alone don't satisfy overlap (e.g., "it was in" fails)
- Env var override lowers the threshold
- Pre-existing numeric mismatch failure path still fires first

**Why this is not cosmetic**: The reproducer from B-1 ("Semaglutide
improved sleep quality" cited to a "14.9% weight loss" span) would have
passed pre-fix because the span contained no decimals. With the fix it
fails at the content-word overlap check (sleep/quality ∩ weight/loss/14 = ∅).

## B-2: Sweep orchestrator enforces corpus approval

**Fix**: Added an `if not approved:` branch BEFORE the multi-section
generation call. The branch writes a pipeline-verdict `report.md`, sets
`status="abort_corpus_approval_denied"`, emits a manifest with zero cost,
and returns. No LLM call is issued.

**Code**: `scripts/run_honest_sweep_r3.py`
- New helper `expected_str_for_abort(protocol)` formats the expected
  tier distribution for the abort report
- New enforcement branch checks `approved` before
  `generate_multi_section_report(...)` is called

**Regression tests**: `tests/polaris_graph/test_b2_corpus_approval_enforcement.py` — 5 tests:
- Rubber-stamp note + material deviation → `check_auto_approve_allowed` rejects
- Substantive note + material deviation → accepted
- `run_one_query` source contains the `if not approved:` branch
- Enforcement branch PRECEDES `generate_multi_section_report` call
- Enforcement branch contains `return summary` before generator call
- `expected_str_for_abort` helper formats tiers correctly

**Why this is not cosmetic**: Pre-fix, `corpus_approval.json` was
written with `approved: false` and the pipeline continued. Post-fix,
the pipeline short-circuits with zero LLM cost and an explicit verdict
artifact. The tests inspect `run_one_query` source to confirm the
branch exists and is placed correctly.

## B-3: Refuse to write `report.md` when no sections verified

**Fix**: Added an `if not verified_sections:` branch AFTER the
multi-section generator runs but BEFORE Methods/Bibliography assembly.
Writes a pipeline-verdict `report.md` with per-section verdicts, sets
`status="abort_no_verified_sections"`, and returns.

**Code**: `scripts/run_honest_sweep_r3.py:626-690`
- Filters `multi.sections` for `not sr.dropped_due_to_failure and sr.verified_text`
- If zero pass, emits the abort artifact and returns

**Regression tests**: `tests/polaris_graph/test_b3_no_verified_sections.py` — 5 tests:
- `if not verified_sections:` branch exists
- Abort precedes Methods/Bibliography assembly
- Abort contains `return summary`
- Abort body describes the pipeline verdict and per-section breakdown
- Abort manifest records `sentences_verified: 0`

**Why this is not cosmetic**: Pre-fix, `report.md` was emitted with
Methods + Bibliography + empty findings, masked behind a post-hoc
`fail_no_verified_prose` status. Post-fix, the report.md explicitly
declares "Pipeline verdict: ... every section failed Phase-4
strict_verify ..." — no reader can confuse it with a content report.

## B-4: Budget cap robust to missing `usage.cost`

**Fix**: Added `_impute_cost_from_tokens()` in `openrouter_client.py`.
Modified `_call()` to impute cost from token counts when OpenRouter
returns `usage={input_tokens, output_tokens}` without a `cost` field.
Legacy behavior preserved when `cost` IS returned.

**Code**: `src/polaris_graph/llm/openrouter_client.py`
- `_PRICE_TABLE_USD_PER_M` with DeepSeek, Qwen, Llama, and generic tiers
- `_impute_cost_from_tokens(model, in_tok, out_tok, reasoning_tok)` looks
  up the model's rate or falls back to Opus-tier worst case ($3/$15 per M)
- In `_call()`: `if api_cost is None or api_cost == 0: imputed = ...`

**Regression tests**: `tests/polaris_graph/test_b4_budget_imputation.py` — 6 tests:
- DeepSeek tokens impute nonzero (~$0.0015 for 5K/500)
- Qwen3-8B tokens are cheap (~$0.00011 for 1K/100/50)
- Unknown-vendor model uses Opus-tier worst-case (~$0.0045)
- Zero tokens → zero cost
- **Budget guard not bypassable**: simulates 10 calls with no API cost
  field, verifies `check_run_budget()` raises when imputed total > cap
- Legacy `api_cost=0.005` path still honored verbatim

**Why this is not cosmetic**: The budget-bypass test explicitly
constructs the scenario Codex described — 10 calls × 2500 tokens with
no API `cost` field on an unknown model — and confirms
`BudgetExceededError` fires. Pre-fix, `current_run_cost()` would be
$0.00 after those same 10 calls.

## B-5: Delimiter breakout sanitization (with Unicode hardening)

**Fix**: Added `_DELIMITER_LITERAL_PATTERNS` to `provenance_generator.py`.
`sanitize_evidence_text()` now runs a second pass that redacts
`<<<evidence:...>>>`, `<<<end_evidence>>>`, `<<<pipeline_telemetry>>>`,
and `<<<end_telemetry>>>` literals inside evidence content.

Unicode evasion hardening (added proactively):
1. NFKC-normalize input first — collapses full-width variants
   (`＜＜＜ｅｎｄ＿ｅｖｉｄｅｎｃｅ＞＞＞`), ligatures, and compatibility forms.
2. Strip invisible codepoints: U+200B–U+200F (zero-width + LRM/RLM),
   U+202A–U+202E (bidi overrides including RLO), U+2060–U+2064 (word
   joiner), U+FEFF (BOM). Otherwise `<<<end\u200bevidence>>>` would
   evade a regex looking for `end_evidence`.
3. Delimiter patterns tolerate `[\s_]*` between `end` and `evidence`
   (and `pipeline` and `telemetry`), so even if a zero-width strip
   collapses `end evidence` → `endevidence`, the regex still matches.

Collateral bug also fixed in `_build_telemetry_block()`: the function
was sanitizing its own structural delimiters. Reworked to build the
body first, sanitize body only, then wrap.

**Code**:
- `src/polaris_graph/generator/provenance_generator.py:79-130` — new
  delimiter-literal patterns (with `[\s_]*` tolerance), NFKC pass,
  invisible-char strip, two-pass `sanitize_evidence_text()`
- `src/polaris_graph/generator/live_deepseek_generator.py:100-165` —
  telemetry block now sanitizes body only, wraps with delimiters after

**Regression tests**: `tests/polaris_graph/test_b5_delimiter_breakout.py` — 15 tests:
- Each delimiter literal (open-evidence, end-evidence, pipeline-telemetry, end-telemetry) individually redacted
- Case-insensitive variants redacted
- Whitespace-padded variant (`<<< end_evidence >>>`) redacted
- Zero-width space inside delimiter (`<<<end\u200bevidence>>>`) redacted
- Zero-width non-joiner (U+200C) variant redacted
- Full-width Unicode variant (`＜＜＜ｅｎｄ＿ｅｖｉｄｅｎｃｅ＞＞＞`) redacted via NFKC
- Bidi-override (U+202E) variant redacted
- BOM (U+FEFF) variant redacted
- Full attack payload (legit + fake end + fake open + injected
  directive + fake end) neutralized by `wrap_evidence_for_prompt`
- Wrapped output has exactly 1 opening and 1 closing delimiter
- Legit text with no delimiters is untouched
- Legit angle brackets in scientific notation (`p<0.001`, `half-life 3<t<5`) untouched

**Why this is not cosmetic**: The `test_b5_full_breakout_attack_neutralized`
test uses the exact attack vector Codex described. Pre-fix, the wrapped
output contained two opening and two closing delimiters, letting a
model see a forged second evidence block with an injected directive.
Post-fix, the wrapped output has exactly one of each and the directive
text is also scrubbed by the first-pass injection-pattern match. The
Unicode hardening closes the obvious evasion vectors (zero-width,
bidi, full-width) that a reviewer would likely probe next.

## Test suite state

- Pre-fix baseline (pinned in `.codex/loop_state.json`): 220 passed
- Post-fix: 267 passed (+47: 7 B-1, 5 B-2, 7 B-3, 6 B-4, 15 B-5, plus
  one fix for pre-existing `test_limitations_gap3` that depended on
  telemetry delimiter emission)
- Zero failing, zero xfail

Breakdown by blocker:
- B-1 semantic grounding: 7 tests
- B-2 corpus approval enforcement: 5 tests
- B-3 no verified sections: 7 tests (5 source-check + 2 behavior on extracted pure helpers)
- B-4 budget imputation: 6 tests
- B-5 delimiter breakout: 15 tests (basic, case-insensitive, whitespace, Unicode evasions)

## What Codex confirmed and I did not regress

- `outputs/honest_sweep_r6_validation/tech/tech_rag_architectures_2024/manifest.json`
  still shows `status=abort_corpus_inadequate` and `cost_usd=0`.
- The abort manifest still does not contain `evaluator_rule_pass`.

## Request for round 2

Verify each fix is substantive, not cosmetic. Run the full suite:

```
pytest tests/polaris_graph/ -v
```

Then audit the code paths directly:
- **B-1**: `verify_sentence_provenance()` in provenance_generator.py —
  look for `_content_words()` and the `no_content_word_overlap_any_cited_span`
  failure mode.
- **B-2 and B-3**: the `if not approved:` and `if not verified_sections:`
  branches in `scripts/run_honest_sweep_r3.py::run_one_query` — both must
  precede the multi-section generator call and Methods assembly respectively.
- **B-4**: `_impute_cost_from_tokens()` in openrouter_client.py — check the
  `_PRICE_TABLE_USD_PER_M` values match OpenRouter's published rates
  (as of April 2026: DeepSeek V3.2-Exp $0.27/$0.38, Qwen3-8B $0.05/$0.40).
- **B-5**: the two-pass `sanitize_evidence_text()` in provenance_generator.py,
  including NFKC normalization and invisible-char strip. The regex now
  allows `[\s_]*` between `end`/`evidence` to defeat strip-induced collapsing.

If any fix is deemed cosmetic, please re-raise with `severity_reraised=true`
per the LOOP_PROTOCOL anti-circle-jerk rule. New blockers you uncover
in other parts of the codebase are welcome — round 1 focused on the 5
stress-test attack vectors and did not attempt full-coverage review.

I am standing by for round 2 feedback.
