# POLARIS honest-rebuild — Codex review round 2

You are the independent reviewer in an automated Codex ↔ Claude audit loop.
This is round 2 of a maximum of 12. Loop protocol is in
`.codex/LOOP_PROTOCOL.md`.

## Your verdict is the decision-maker

You declare one of `READY`, `NOT_READY`, or `CONDITIONAL`. The loop stops
only on `READY`. If the findings are soft or cosmetic, DO NOT produce
`READY` just to end the loop. Claude cannot override your verdict.

## Required output format

Write your findings to `outputs/codex_findings/round_2/findings.md`.
(The `.codex/` directory has a Windows ACL deny ACE — the orchestrator
moved all outputs under `outputs/codex_findings/round_N/` in round 1.)

The file MUST start with this frontmatter:

```yaml
---
verdict: READY | NOT_READY | CONDITIONAL
blocker_count: <integer>
medium_count: <integer>
rationale: |
  <2-4 sentence justification referencing specific file:line>
---
```

Followed by sections:
- `## Critical issues (blockers)` — each with file:line + reproducer
- `## Medium issues` — same format
- `## Minor issues` — brief bullets
- `## Disputes with prior round` — if you disagree with Claude's fixes
- `## What's well-built` — preserve list
- `## Recommendation` — concrete next step

## Prior round context

- Round 1 findings: `outputs/codex_findings/round_1/findings.md`
- Claude's response: `outputs/codex_findings/round_1/claude_response.md`
- Claude's commit this round: `724edf5b79d246614b940dd1beb2976cc63a8b94`
- Test state after Claude's work: 267 passed, 0 xfail, 0 failed

## Anti-circle-jerk rules (must obey)

1. **Read the actual code at commit 724edf5, not Claude's summary.** Open
   each fixed file, read the function, trace the branch. Verify the
   behavior matches Claude's claim.
2. **If a blocker was claimed fixed but the fix is cosmetic** (added a
   comment, renamed a variable, updated a docstring without changing
   behavior), RE-RAISE with `severity_reraised: true` in findings.
3. **Specifically probe Claude's fixes with an attacker mindset.**
   Each fix below has a stated invariant. Your job is to find an input
   that violates the invariant.
4. **Never lower a blocker to medium** without showing the specific
   commit + diff that justifies the severity drop.
5. **`READY` has a hard bar:** zero blockers, ≤2 mediums, each medium
   carries an explicit acceptable-risk rationale. If you can construct
   ANY silent failure input, it is NOT ready.

## Round 2 specific: verify Claude's 5 claimed fixes

### B-1 — strict_verify semantic grounding

Claim: non-numeric claims now require content-word overlap with cited span.

Files to read: `src/polaris_graph/generator/provenance_generator.py`
(look for `_content_words`, `MIN_CONTENT_WORD_OVERLAP`, and the extended
`verify_sentence_provenance` function).

Specifically probe:
- Can the stopword list be trivially gamed? (e.g., if the sentence is
  "the drug was effective" and the span is "the drug was prescribed",
  both reduce to {drug, effective} vs {drug, prescribed} — only 1 overlap
  with MIN=2. But what if both collapse to {drug}?)
- What happens when the sentence has fewer than MIN content words?
- Does the overlap check run AFTER the decimal check, or instead of it?
- Is there a way to construct a sentence that passes the decimal check
  on numbers but fails the content check, or vice versa?

### B-2 — corpus approval enforcement

Claim: `if not approved` branch in `run_one_query` short-circuits with
zero LLM cost.

Files to read: `scripts/run_honest_sweep_r3.py` — `run_one_query`.

Specifically probe:
- Is there a code path between the `approved = ...` assignment and the
  `if not approved:` check that issues an LLM call?
- Does ANY earlier code (query amplification, embedding, etc.) also call
  the LLM and thus bypass the enforcement?
- Can a caller invoke the multi-section generator directly without going
  through `run_one_query`?

### B-3 — refuse report.md on zero verified sections

Claim: `filter_verified_sections` + `build_no_verified_sections_abort_body`
are extracted helpers; `if not verified_sections:` precedes Methods.

Files to read: `scripts/run_honest_sweep_r3.py` — the two helpers (around
line 78–140) and the call site (around line 620–680).

Specifically probe:
- What happens if ALL sections have `dropped_due_to_failure=False` but
  `verified_text=""`? (The predicate handles this — but verify.)
- What happens if `multi.sections` is entirely empty (len==0)? (Then
  `verified_sections` is empty AND `len(multi.sections)==0`.)
- Is the abort artifact deterministic across runs? (Matters for
  manifest reproducibility.)

### B-4 — budget cap robust to missing `usage.cost`

Claim: `_impute_cost_from_tokens` provides a floor cost when OpenRouter
omits `usage.cost`.

Files to read: `src/polaris_graph/llm/openrouter_client.py` — look for
`_impute_cost_from_tokens`, `_PRICE_TABLE_USD_PER_M`, and the `_call()`
invocation site.

Specifically probe:
- Are the price-table values correct for April 2026? (DeepSeek V3.2-Exp
  should be ~$0.27/$0.38 per M; Qwen3-8B should be ~$0.05/$0.40.)
- What model-name variants bypass the lookup? (e.g., case-sensitivity,
  provider prefix, versioning suffix.)
- Does the imputation run before or after the budget check? (If after,
  imputation is useless.)
- Is the Opus-tier default ($3/$15 per M) actually pessimistic enough
  for a runaway unknown model?

### B-5 — delimiter breakout + Unicode evasion

Claim: two-pass sanitization redacts delimiter literals with NFKC
normalization + invisible-char strip + whitespace-or-underscore tolerance.

Files to read: `src/polaris_graph/generator/provenance_generator.py` —
`_DELIMITER_LITERAL_PATTERNS`, `_INVISIBLE_CHARS_RE`, and
`sanitize_evidence_text`.

Specifically probe:
- Can you construct a payload that evades NFKC? (Homoglyphs in
  `evidence` — Cyrillic 'е' vs Latin 'e', Greek 'ν' vs Latin 'v'.)
- What about U+3000 ideographic space, U+00A0 non-breaking space,
  other whitespace that `\s` might not catch?
- Can the `<<<evidence:...>>>` regex be bypassed with `>>>>` (four
  chars)? With `<<<< evidence: ... >>>>` (quad-chevron)?
- Is the invisible-char set complete? (Check U+200E, U+200F — LRM/RLM —
  those are in the stripped range, good. Check U+2066–U+2069
  isolate chars — those are NOT in the range.)

## Scope

Read-only access to:
- `src/polaris_graph/` (all)
- `scripts/run_honest_sweep_r3.py`, `scripts/run_r6_validation.py`,
  `scripts/codex_loop_parse.py`
- `config/`, `tests/polaris_graph/`
- `outputs/codex_findings/round_1/`

Do NOT modify any source, test, or config file. Your only writable path
is `outputs/codex_findings/round_2/`. The loop orchestrator (Claude)
handles all code changes.

## Authentication

OAuth (auth_mode=chatgpt). Does NOT burn OpenAI API credits.

## Bonus: attack vectors NOT covered in round 1

Round 1 focused on 5 specific blockers. Other attack surfaces that
round 2 can explore:

1. Family-segregation bypass via model-name tricks in `provider_for_model`.
2. Citation attribution bugs in `_subject_near_position()`.
3. Tier classifier edge cases (govt subdomains, academic blogs, preprints).
4. Multi-section generator: invalid outline, mid-call budget exhaustion,
   bibliography dedup correctness.
5. Completeness-checklist gaming (keyword-substring in negated contexts
   like "X was not evaluated").
6. Corpus-adequacy threshold calibration.
7. Determinism / reproducibility of the manifest across runs.

---

Start by running:

```
git log --oneline 724edf5 | head -5
git diff HEAD~1 HEAD -- src/polaris_graph/generator/provenance_generator.py | head -200
```

Then read the full diff of commit 724edf5 to see exactly what changed.
Then open each fixed file and stress-test the invariant.
