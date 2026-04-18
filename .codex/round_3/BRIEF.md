# POLARIS honest-rebuild — Codex review round 3

You are the independent reviewer in an automated Codex ↔ Claude audit loop.
This is round 3 of a maximum of 12. Loop protocol: `.codex/LOOP_PROTOCOL.md`.

## Your verdict is the decision-maker

One of `READY`, `NOT_READY`, or `CONDITIONAL`. The loop stops only on
`READY`. Claude cannot override your verdict.

## Required output format

Write findings to `outputs/codex_findings/round_3/findings.md` (the
`.codex/` directory has a Windows ACL deny ACE — writable path is
`outputs/codex_findings/round_N/`).

Frontmatter:

```yaml
---
verdict: READY | NOT_READY | CONDITIONAL
blocker_count: <integer>
medium_count: <integer>
rationale: |
  <2-4 sentence justification referencing specific file:line>
---
```

Sections: Critical issues (blockers), Medium issues, Minor issues,
Disputes with prior round, What's well-built, Recommendation.

## Prior round context

- Round 2 findings: `outputs/codex_findings/round_2/findings.md`
- Claude's round 2 response: `outputs/codex_findings/round_2/claude_response.md`
- Claude's round 1 commit: `724edf5b79d246614b940dd1beb2976cc63a8b94`
- Claude's round 2 commit: `9493326447dd8ad228bdc88b87f4488bd03a49b5`
- Test state after round 2: 280 passed, 0 xfail, 0 failed

## Anti-circle-jerk rules

1. Read the code at commit 9493326, not Claude's summary.
2. If a fix is cosmetic, re-raise with `severity_reraised: true`.
3. Never lower severity without showing commit+diff.
4. `READY` requires zero blockers and ≤2 mediums with acceptable-risk
   rationale. Any silent failure mode disqualifies READY.

## Round 3 specific: verify round-2 fixes for B-1 and B-5

### B-1 round 2: default threshold raised to 2

Claim: default `MIN_CONTENT_WORD_OVERLAP` is now 2, which defeats
the single-token-overlap fabrication exploit you found.

File to read: `src/polaris_graph/generator/provenance_generator.py`
around line 369-380.

Specifically probe:
- Is the default actually 2, or is there a path where it stays 1?
- Can the stopword list still be gamed to reduce both sentence and
  span to a single overlapping content word even with threshold=2?
  (e.g., "The new aspirin was effective" vs "The new aspirin was
  prescribed" — overlap = {aspirin, new} could slip through if
  "new" is considered content.)
- Is `MIN_CONTENT_WORD_OVERLAP` imported at module load, or resolved
  per-call? If at load, stale env vars persist.
- Check the test `test_b1_default_threshold_is_at_least_two` — does
  it actually ASSERT the default or just accept any value?

### B-5 round 2a: isolate controls added to invisible-char set

Claim: `_INVISIBLE_CHARS_RE` now includes `\u2066-\u2069` plus the
round-1 set.

File to read: `src/polaris_graph/generator/provenance_generator.py`
around line 92-113.

Specifically probe:
- Is the range fully covered? (U+2066 LRI, U+2067 RLI, U+2068 FSI, U+2069 PDI)
- Are there OTHER invisible Unicode codepoints that an attacker
  could still use? E.g., Tag characters U+E0000-U+E007F (deprecated
  but still "invisible" in many terminals), variation selectors
  U+FE00-U+FE0F, U+E0100-U+E01EF, combining Grapheme Joiner U+034F,
  Mongolian Vowel Separator U+180E (deprecated, but some renderers
  still treat as invisible).
- Does the strip happen BEFORE or AFTER the NFKC pass? Does it
  matter for the attack surface?

### B-5 round 2b: homoglyph mapping (medium)

Claim: a narrow `_CONFUSABLE_ASCII_MAP` maps Cyrillic/Greek
confusables used in delimiter keywords back to Latin.

File to read: `src/polaris_graph/generator/provenance_generator.py`
around line 115-160.

Specifically probe:
- Coverage: are all letters in `evidence`, `end`, `pipeline`,
  `telemetry` covered? Build the full char set and check each
  against the map.
  - evidence: e, v, i, d, n, c
  - end: e, n, d
  - pipeline: p, i, l, n, e
  - telemetry: t, e, l, m, r, y
  - Full set: {a, c, d, e, i, l, m, n, p, r, t, v, y} plus caps.
- For each letter in that set, is there a Cyrillic or Greek
  confusable? Is it mapped? E.g., 'd' — Cyrillic has no direct
  visual confusable for lowercase d. But 'l' — Cyrillic 'ӏ' U+04CF?
  Not mapped. Greek iota capital 'Ι' → 'I' is mapped; what about
  lowercase iota 'ι' which looks like 'i' — is it mapped? (Yes, at
  line 148.) What about 'm' lowercase — Cyrillic 'м' U+043C looks
  like Latin 'm'? Not mapped.
- False positives: does the map corrupt legitimate non-ASCII content?
  The test `test_b5_legit_cyrillic_content_not_harmed` claims no, but
  verify by constructing a Russian sentence that happens to contain
  the exact sequence "end" (in Latin transliteration surrounded by
  Cyrillic) — does it over-redact?

### Bonus probes Codex round 2 did NOT cover

These vectors were raised in round 2's bonus section but not deeply
exercised:

1. **Family segregation bypass**: does `provider_for_model` prevent
   an attacker from registering a same-family generator+evaluator
   pair via model-name tricks (e.g., "deepseek/deepseek-v3.2-exp" vs
   "DeepSeek/DeepSeek-V3.2-Exp" — case normalization?).
2. **Citation attribution**: `_subject_near_position()` edge cases —
   what if the subject is split across a sentence boundary, or is a
   possessive ("the drug's efficacy"), or in passive voice ("was
   improved by drug X")?
3. **Tier classifier**: a preprint on bioRxiv — does it land in T1
   or T2? A .gov site that's just a press release — T3 or T5?
4. **Determinism**: does `build_no_verified_sections_abort_body()`
   produce byte-identical output for the same input across two
   invocations in separate processes? (Tests only verify deterministic
   WITHIN a process.)

## Scope

Read-only access to: `src/polaris_graph/`, `scripts/run_honest_sweep_r3.py`,
`scripts/codex_loop_parse.py`, `config/`, `tests/polaris_graph/`,
`outputs/codex_findings/round_1/`, `outputs/codex_findings/round_2/`.

Writable: `outputs/codex_findings/round_3/` only.

## Authentication

OAuth (auth_mode=chatgpt). Does NOT burn OpenAI API credits.

---

Start by diffing:

```
git diff 724edf5 9493326 -- src/polaris_graph/generator/provenance_generator.py
git diff 724edf5 9493326 -- tests/polaris_graph/
```

Then stress-test the round-2 invariants. Grant `READY` only if you
can't find a silent failure mode after genuine probing.
