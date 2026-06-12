# Codex DIFF gate — I-perm-022 (#1214): verifier cited-span LIGATURE normalization

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Reserve P0/P1 for real execution risks; cosmetic = P3/P2.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## The diff
`.codex/I-perm-022/codex_diff.patch` (staged). 3 files, +~90. Read these EXACT files
(do NOT scan the whole repo — codex_* temp dirs crash exec):
- EDIT `src/polaris_graph/roles/native_gate_b_inputs.py` — `_normalize_span_text`
  (LIGATURE-ONLY) + wired at `_resolve_evidence`
  (`text=_normalize_span_text(_cited_window_text(...))`).
- EDIT `scripts/dr_benchmark/run_gate_b.py` — `PG_GATE_B_SPAN_NORMALIZE` in slate +
  `_BENCHMARK_FORCE_ON_FLAGS` + `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS`.
- NEW `tests/polaris_graph/test_span_normalize_iperm022.py` — 7 tests.

The brief was APPROVED at `.codex/I-perm-022/codex_brief_verdict_iter3.txt` — the design was
NARROWED across 3 brief-gate iters to LIGATURE-ONLY because de-hyphenation and zero-width
handling are §-1.1-unsafe (any word JOIN/SPLIT can fabricate support). Read it.

## What it does (LIGATURE-ONLY — the only §-1.1-safe span repair)
`_normalize_span_text` decomposes ONLY Latin presentation-form ligatures U+FB00..U+FB06
(ﬀﬁﬂﬃﬄﬅﬆ) to their fixed letters, BEFORE the four-role evaluator reads the cited span,
default-OFF `PG_GATE_B_SPAN_NORMALIZE`. The CLAIM is graded as-authored. Nothing else is
touched — no de-hyphenation, no zero-width/NBSP handling, no whitespace collapse.

## Red-team this — focus
1. **§-1.1 no word-boundary change (the whole safety argument):** a ligature is a SINGLE
   codepoint -> a FIXED letter sequence. Decomposing it cannot JOIN two words and cannot
   SPLIT a word, so it cannot turn a genuine negative into apparent support. Confirm there is
   NO ligature whose decomposition crosses a word boundary or alters meaning. (The 7 keys are
   all intra-word letter clusters: ff/fi/fl/ffi/ffl/ft/st.)
2. **De-hyphen / zero-width are NOT done (the iter-2 P1 you raised):** confirm the diff
   removed ALL join/split logic. Tests `test_line_break_hyphen_is_NOT_joined`
   ("re-\nsigned" stays, no "resigned"), `test_zero_width_is_NOT_joined_negation_safe`
   ("not<ZWSP>able" unchanged, no "notable"; "in<ZWJ>effective" not split).
3. **Zero digit modification:** ligature codepoints carry no digits;
   `test_digits_and_nbsp_untouched` proves "20-\n30", "2 percent", "-1.07", NBSP all
   byte-preserved.
4. **Flag wiring fail-closed:** `PG_GATE_B_SPAN_NORMALIZE` in slate (="1") + force-on (no
   setdefault drift) + preflight-required (a paid run fails closed if off) — same triple as
   FX-03 `PG_GATE_B_CITED_SPAN`.
5. **Byte-identical when off:** flag default "0" -> identity -> identical EvidenceDocument.text
   -> identical verdicts. Proven by 8 existing FX-03 tests passing with the wrapped call site.

## Honest scope note
This delivers ONLY the genuine clean win the forensic identified (LLM evaluators mis-read the
ligature codepoint). The broader scope (de-hyphenation, zero-width "recovery") was never
§-1.1-safe and is correctly OUT OF SCOPE — a verifier must never join/split words. Truncation
artifacts + a persistent cross-run verdict cache remain out of scope. Tests: 7 new + 8 FX-03
pass. Per-claim live proof is the operator-gated paid §-1.1 smoke.
