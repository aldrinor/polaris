# Codex BRIEF gate — I-perm-022 (#1214): verifier cited-span normalization

HARD ITERATION CAP: 5 per document. This is iter 4 of 5.

## ITER-4 CHANGES (your iter-3 P1 + P2)
- **iter-3 P1 (U+FB05 mis-mapped to "ft", should be "st" — "loﬅ"->"loft" not "lost") — FIXED at
  the ROOT.** The ligature map is no longer hand-typed; it is DERIVED from Unicode NFKD:
  `{chr(cp): unicodedata.normalize("NFKD", chr(cp)) for cp in range(0xFB00,0xFB07) if NFKD is
  ascii+alpha}`. This is authoritative (U+FB05 LONG-S-T -> "st") and removes the entire
  hand-typo class. New test `test_full_ligature_table_matches_unicode_nfkd` asserts the map ==
  NFKD for all 7 codepoints AND "lo<FB05>" -> "lost" (not "loft"), "be<FB06>" -> "best". A
  Python probe confirms map values = {ff, fi, fl, ffi, ffl, st}.
- **iter-3 P2 (run_gate_b.py comments still mention de-hyphen/NBSP/zero-width) — FIXED.** The
  slate (:566), force-on (:813), and preflight-required (:745) comments now all say
  LIGATURE-ONLY (no word-boundary change), matching the behavior.
- **Build:** 8 span tests + 8 existing FX-03 tests pass.

---

(iter-3 section below)

HARD ITERATION CAP (iter-3 header, superseded above): 5 per document. This is iter 3 of 5.

## ITER-3 CHANGE — narrowed to LIGATURE-ONLY (your iter-2 P1 accepted in full)
You showed the JOIN rules are not TP-only: de-hyphenation "re-\nsigned" -> "resigned"
(opposite meaning) and zero-width delete "not<ZWSP>able" -> "notable" / "in<ZWSP>active" ->
"inactive" can make an UNSUPPORTED claim appear present — a support-fabrication path. You are
right: ANY operation that joins or splits WORDS is §-1.1-unsafe for a verifier.

So `_normalize_span_text` is now LIGATURE-ONLY:
- It decomposes ONLY Latin presentation-form ligatures U+FB00..U+FB06 (ﬀﬁﬂﬃﬄﬅﬆ) to their
  fixed letters. A ligature is a SINGLE codepoint -> a fixed letter sequence with NO
  word-boundary change, so it can neither join nor split words and cannot fabricate support;
  it only renders the codepoint as the letters the LLM evaluator should have read. ZERO digit
  modification (ligature codepoints carry no digits).
- De-hyphenation AND all zero-width / NBSP handling are DROPPED. Zero-width / hyphen / NBSP
  chars are now left UNTOUCHED (the LLM renders zero-width as nothing anyway; leaving them
  avoids both the split and the wrong-join hazards).
Adversarial tests prove the unsafe transforms do NOT happen: `test_line_break_hyphen_is_NOT_joined`
("re-\nsigned" stays, no "resigned"), `test_zero_width_is_NOT_joined_negation_safe`
("not<ZWSP>able" unchanged, no "notable"; "in<ZWJ>effective" not split to "in effective").
`test_digits_and_nbsp_untouched` proves digits/ranges/negatives/NBSP byte-preserved.
7 span tests + 8 existing FX-03 cited-span tests pass.

Honest scope shrink: this delivers ONLY the genuine clean win the forensic identified
(ligature mis-reads); de-hyphenation/zero-width "recovery" was never §-1.1-safe and is
correctly out of scope (a verifier must never join/split words). Flag wiring (slate +
force-on + fail-closed preflight) is unchanged from iter-2.

Verdict request: APPROVE the narrowed, §-1.1-safe ligature-only design.

---

(iter-2 section below — the zero-width-delete approach it describes is SUPERSEDED by the
ligature-only narrowing above)

HARD ITERATION CAP (iter-2 header, superseded above): 5 per document. This is iter 2 of 5.

## ITER-2 CHANGES (addressing your iter-1 P1s + P2)

- **iter-1 P1 (zero-width → space could ADD support, §-1.1 LETHAL) — FIXED.** Zero-width
  FORMAT controls (ZWSP U+200B, ZWNJ U+200C, ZWJ U+200D, BOM/ZWNBSP U+FEFF) are now
  DELETED (joined), NEVER spaced. Spacing could split a negation ("in<ZWJ>effective" ->
  "in effective", "un<ZWSP>safe" -> "un safe") and fabricate apparent support; deleting can
  only make a span LESS matchable (a missed recovery), never ADD support. Only TRUE
  no-break spaces (NBSP U+00A0, figure space U+2007, narrow NBSP U+202F) become a space.
  New adversarial test `test_zero_width_is_DELETED_not_spaced_negation_safe` proves
  "in<ZWJ>effective" -> "ineffective" and "the drug was in<ZWSP>effective" yields
  "ineffective" (NOT "in effective"). Behavioral run confirms all 10 cases incl.
  negation-safety + zero-digit invariants.
- **iter-1 P1 (flag inert on the paid path) — FIXED.** `PG_GATE_B_SPAN_NORMALIZE` is now in
  `_FULL_CAPABILITY_BENCHMARK_SLATE` (="1"), `_BENCHMARK_FORCE_ON_FLAGS` (force-set, no
  setdefault drift), AND `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (fail-closed if not active on
  a paid run) — same triple as the FX-03 cited-span precedent.
- **iter-1 P2 (literal invisible chars in the regex vs \u escapes) — disclosed.** The
  `_LIGATURE_MAP` / `_ZERO_WIDTH_RE` / `_NBSP_SPACE_RE` character classes currently hold the
  literal codepoints (behaviorally verified correct by the test suite + an ascii-safe
  codepoint probe). Editor tooling kept mangling typed `\u` escapes; the classes are
  correct and tested. Flag if you want this blocked on a \u-escape rewrite (cosmetic
  maintainability, not behavior).
- **Build:** 8 span-normalize tests + 8 existing FX-03 cited-span tests pass (flag-off
  byte-identical integration confirmed).

---

(original iter-1 brief follows)

HARD ITERATION CAP (iter-1 header, superseded above): 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
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

## Issue (#1214, I-perm-022)
Un-normalized PDF-extraction artifacts (ligatures, line-break hyphenation, NBSP/zero-width)
in the cited SPAN reach the four-role second evaluators (Sentinel decomposition + Judge)
verbatim and can flip a genuinely-supported atom to "unsupported" → surfaced as
[confidence:low]. Normalize the cited span BEFORE the 2nd evaluator; recover TRUE positives
only; gate NEVER loosened. DoD: default-OFF flag, byte-identical when off; faithfulness gates
NEVER relaxed; unit tests; Codex diff-gate APPROVE; paid §-1.1 smoke; wired into Gate-B slate.

The full grounded forensic is at `.codex/I-perm-022/forensic.md` (read it).

## Design (as built)
NORMALIZE THE SPAN ONLY (artifacts are source-side); grade the CLAIM as-authored.
- `_normalize_span_text(text)` in `src/polaris_graph/roles/native_gate_b_inputs.py`, gated by
  default-OFF `PG_GATE_B_SPAN_NORMALIZE` (OFF → returns input unchanged → byte-identical):
  1. Ligatures U+FB00..U+FB06 → ASCII (the unambiguous, high-value repair).
  2. Line-break (soft) hyphenation, ALPHABETIC neighbours ONLY: `([A-Za-z])-[ \t]*\n[ \t]*([A-Za-z])`.
  3. Invisible/zero-width/NBSP → space; collapse space/tab runs.
  - ZERO digit modification — every rule matches ALPHABETIC context only, so numbers, ranges
    ("20-\n30"), and negatives ("-1.07") are byte-preserved (the I-gen-005 lesson).
- Wired at `_resolve_evidence` (the EvidenceDocument the evaluator reads):
  `text=_normalize_span_text(_cited_window_text(text, token))`. Records keep FULL un-normalized
  text. Slate force-on `PG_GATE_B_SPAN_NORMALIZE=1`.

## Faithfulness analysis (the crux you must verify)
1. **Repair, not rewrite — recovers TPs only.** The normalizer maps a garbled token to its
   true form and ADDS NO content. If the span genuinely does not state a claim's atom, the
   repaired span STILL does not → the atom stays unsupported → the claim stays non-VERIFIED. A
   genuine negative cannot flip, because no new support is introduced.
2. **Zero digit modification (testable invariant).** Every regex matches alphabetic context
   only; ligature codepoints carry no digits; de-hyphenation is `[A-Za-z]-...-[A-Za-z]`.
   `test_numeric_difference_does_NOT_collapse` proves `2%`/`20%` stay distinct and a digit
   line-break hyphen is preserved.
3. **Gate untouched.** strict_verify, D8, `_compose_final_verdict` fail-closed, Mirror doc_id
   binding, Sentinel UNGROUNDED override, the VERIFIED coverage credit are all unchanged. The
   only change is the TEXT the evaluator reads, made faithfully comparable to its own source.
4. **No recovery target.** The fix accepts whatever recovers (possibly far fewer than the
   drb_76 "12"); it is NOT tuned to a count (that would force-pass genuine negatives).

## Honesty caveats (from the forensic — weigh these)
- The drb_76 "12 false negatives" is NOT confirmed artifact-driven: in the captured run the one
  artifact-bearing row (ev_206) feeds no Sentinel-unsupported claim, and MOST of the 8 are
  GENUINE semantic negatives that MUST stay negative. The fix is defensible prophylaxis + one
  demonstrated truncation case (05-007 "natural kill[er] cell"), proven per-claim only by the
  paid §-1.1 smoke.
- De-hyphenation is irreducibly imperfect at the seam ("oxaliplatin-\ninduced" residual);
  ligatures are the clean win, hyphenation is best-effort/alphabetic-only/documented. A wrong
  join only FAILS to match (a missed recovery), never ADDS support.
- Truncation artifacts ("natural kill" vs "killer") are NOT fixed here (need fuzzy/edit-distance
  = different + riskier; out of scope). Persistent cross-run verdict cache deferred (the in-run
  `_dedup_key` already inherits the normalized identity for free since we normalize upstream).

## Tests (`tests/polaris_graph/test_span_normalize_iperm022.py`, 7) + FX-03 regression
flag-off byte-identical; ligatures repaired; alphabetic hyphen joined (+ documented residual);
**numeric difference does NOT collapse**; NBSP/ZWSP/BOM → space + run collapse; genuine negative
gains no content; empty-safe. 7 new pass; 8 existing FX-03 cited-span tests pass (flag-off
integration → byte-identical EvidenceDocument.text).

## Questions
1. Is "normalize span / grade claim as-authored, recovers-TP-only, zero-digit-mod" sufficient to
   keep this faithfulness-NEUTRAL? Any path where a repaired span ADDS support to a genuine
   negative?
2. Is deferring the persistent cross-run verdict cache (keeping only the free in-run dedup
   identity) acceptable to stay under the 200-LOC cap?
3. Is folding the per-claim causal proof into the paid §-1.1 smoke (vs claiming it offline)
   the honest call, given the "12 FN" is not artifact-confirmed?
