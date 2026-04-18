# POLARIS honest-rebuild — Codex review round 5

Round 5 of max 12. Verdict: `READY | NOT_READY | CONDITIONAL`.

## Output

Write findings to `outputs/codex_findings/round_5/findings.md` with
frontmatter:

```yaml
---
verdict: READY | NOT_READY | CONDITIONAL
blocker_count: <int>
medium_count: <int>
rationale: |
  <2-4 sentence justification with file:line>
---
```

## Prior rounds

- All findings + responses: `outputs/codex_findings/round_{1,2,3,4}/`
- Loop state: `.codex/loop_state.json`
- Commits:
  - Round 1: `724edf5` — B-1..B-5 initial
  - Round 2: `9493326` — B-1 default=2, U+2066, initial homoglyph map
  - Round 3: `3a90b4f` — normalized view + index projection
  - Round 4: `c2570b2` — NFKC→NFKD + Mn/Mc strip (closes diacritic bypass)
- Test state: 303 passed, 0 xfail, 0 fail

## Round 5 verification targets

### 1. B-5 NFKD + Mn/Mc strip (round 4 fix)

Read `src/polaris_graph/generator/provenance_generator.py` around
`_build_normalized_view()` (line ~180-225):

- Confirm `unicodedata.normalize("NFKD", ch)` is used (not NFKC).
- Confirm `cat in ("Cf", "Mn", "Mc")` skips combining marks.
- Test round-4 reproducers:

```python
from src.polaris_graph.generator.provenance_generator import sanitize_evidence_text

# Must all redact
assert "REDACTED_DELIMITER" in sanitize_evidence_text("<<<\u0115nd_evidence>>>")[0]
assert "REDACTED_DELIMITER" in sanitize_evidence_text("<<<e\u0306nd_evidence>>>")[0]
```

Stress-test NFKD edge cases:

- Hangul syllables: `안녕` — NFKD decomposes to 3 Jamos each. Does the
  normalized view handle them correctly (they're not in any delimiter
  keyword but the expansion 1→3 matters for orig_idx correctness)?
- CJK compatibility ideographs (U+F900-U+FAFF) — do they decompose
  to canonical forms correctly?
- Stacked combining marks: 'e' + breve + grave + acute (4 codepoints
  that visually form one glyph). Does Mn-strip handle all three marks?
- Grapheme clusters that form emoji: 👨‍👩‍👧 (family emoji with ZWJ
  sequences) — byte-preserved in legit content?

### 2. Regression on round 1-3 invariants

After the NFKD change, verify nothing regressed:

- B-1: default `MIN_CONTENT_WORD_OVERLAP >= 2`.
- B-2: `if not approved:` branch in `run_one_query` aborts cleanly.
- B-3: `filter_verified_sections` + `build_no_verified_sections_abort_body`
  produce a valid pipeline-verdict artifact.
- B-4: `_impute_cost_from_tokens` closes the no-`usage.cost` bypass.
- B-5: normalized view still handles all prior attack vectors (tag
  chars, isolate controls, BOM, math alphanumerics, Cyrillic/Greek
  confusables, zero-width, full-width).

### 3. Attack surfaces NOT previously covered

Round 4's bonus list and more:

- **Verifier batch concurrency**: if `verify_sentence_provenance` is
  called on 1000+ sentences in a `concurrent.futures` pool, any
  shared mutable state? Any non-thread-safe module-level caches?
- **Tier classifier transitions**: a bioRxiv preprint (T4) that's
  later accepted to NEJM (T1) — does the classifier emit T1 or T4
  based on URL alone?
- **Budget negative tokens**: `_impute_cost_from_tokens(model, -100, 50, 0)`
  — does it handle negative token counts? Negative-cost is absurd
  but could happen if API returns corrupted data.
- **Citation numbering across sections**: if two sections cite ev_001,
  does `resolve_provenance_to_citations` issue [1] in both, or [1]
  and [2]? Sections are supposed to share a bibliography.
- **Determinism across runs**: run the abort-artifact writer twice
  with identical inputs in separate Python processes. Byte-identical?
- **Evaluator family-segregation edge case**: model name `"deepseek-ai/DeepSeek-V3.2-Exp"`
  (hyphenated org prefix) vs `"deepseek/deepseek-v3.2-exp"` — does
  `family_from_model()` treat both as same family?

### 4. Dead-code / unused-param audit

- `MIN_CONTENT_WORD_OVERLAP` is resolved at module load. Any code
  path that reads the env var at call time instead?
- `_CONFUSABLE_ASCII_MAP` — any entries never exercised by any test?
  If so, are they documentation-only or dead?
- `_INVISIBLE_CHARS_RE` — any range the tests don't exercise?

## Scope

Read-only: `src/polaris_graph/`, `scripts/run_honest_sweep_r3.py`,
`tests/polaris_graph/`, `outputs/codex_findings/round_*/`.

Writable: `outputs/codex_findings/round_5/` only.

## Anti-circle-jerk rules

1. Read code at `c2570b2`, not Claude's summary.
2. If a fix is cosmetic, re-raise with `severity_reraised: true`.
3. `READY` requires zero blockers + ≤2 mediums with acceptable-risk
   rationale. Silent failure mode = NOT_READY.

## Authentication

OAuth. No API-key burn.

---

Start:

```
git diff 3a90b4f c2570b2 -- src/polaris_graph/generator/provenance_generator.py
git log --oneline 724edf5..c2570b2
```

Then probe the NFKD architecture AND the bonus surfaces. If after
genuine probing you can't find a silent-failure input, grant `READY`.
