"""I-gen-005 iter 2 adversarial test suite.

Tests the 3 P1 fixes from Codex iter 1 review:
  P1 #1 — Token-exact matching ('50' must NOT match '150'/'21.50')
  P1 #2 — Range-dash safety ('8.12–8.21' must NOT become '-8.21')
  P1 #3 — Localized entailment fallback (no whole-doc judge)

Each test asserts the EXACT behavior the operator + Codex demanded.
Run: python scripts/test_i_gen_005_iter2_adversarial.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    _NUMBER_RE,
    _decimals_in,
    _find_local_support_window,
    _normalize_unicode_minus,
    _numbers_in,
)


def banner(name: str) -> None:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")


failures: list[str] = []


def check(name: str, ok: bool, details: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}")
    if details:
        print(f"         {details}")
    if not ok:
        failures.append(name)


# ------------------------------------------------------------------------
# TEST 1: Token-exact matching — '50' must NOT match '150' / '21.50'
# ------------------------------------------------------------------------
banner("TEST 1 — Token-exact matching (Codex P1 #1)")

# Sentence claims "50% of patients responded"
# Evidence contains '150', '21.50', '503' but NOT bare '50'
evidence_no_bare_50 = (
    "Among the 150 patients enrolled, mean baseline HbA1c was 21.50%. "
    "The trial randomized 503 participants across 4 arms. "
    "Adverse events were reported in 47.5% of the active arm."
)

# The sentence has '50' as its needed token (no decimal, integer-only path)
needed = {"50"}
needed_content = {"patients", "responded", "cancer"}
win = _find_local_support_window(
    needed, needed_content, evidence_no_bare_50,
    window=400, min_content_overlap=1, token_regex=_NUMBER_RE,
)
check(
    "'50' does NOT match inside '150', '21.50', '503'",
    win is None,
    f"window={win} (None expected — no bare 50 in evidence)",
)

# Confirm '503' WOULD match if it were the needed token
needed_503 = {"503"}
win_503 = _find_local_support_window(
    needed_503, {"patients", "trial"}, evidence_no_bare_50,
    window=400, min_content_overlap=1, token_regex=_NUMBER_RE,
)
check(
    "'503' DOES match (token-exact positive control)",
    win_503 is not None,
    f"window={win_503}",
)

# Decimal path: '0.56' (positive) does NOT match '-0.56' (negative)
evidence_negative = "The HbA1c reduction was -0.56% vs placebo at week 26."
win_pos = _find_local_support_window(
    {"0.56"}, {"hba1c", "reduction", "week"}, evidence_negative,
    window=400, min_content_overlap=1,
)
check(
    "Positive '0.56' does NOT match negative '-0.56' in evidence",
    win_pos is None,
    f"window={win_pos} (None expected — only '-0.56' exists, not bare '0.56')",
)

# And vice versa: '-0.56' DOES match when present
win_neg = _find_local_support_window(
    {"-0.56"}, {"hba1c", "reduction", "week"}, evidence_negative,
    window=400, min_content_overlap=1,
)
check(
    "'-0.56' DOES match when actually present (negative control passes)",
    win_neg is not None,
    f"window={win_neg}",
)


# ------------------------------------------------------------------------
# TEST 2: Range-dash safety — '8.12–8.21' must NOT extract as '-8.21'
# ------------------------------------------------------------------------
banner("TEST 2 — Range-dash safety (Codex P1 #2)")

# Range using U+2013 EN DASH between positive numbers
range_text = "The 95% CI was 8.12–8.21 mmol/L at week 12."
normalized = _normalize_unicode_minus(range_text)
check(
    "U+2013 between digits → space (not minus)",
    "8.12 8.21" in normalized and "-8.21" not in normalized,
    f"normalized={normalized!r}",
)

decs = _decimals_in(range_text)
check(
    "'8.12–8.21' extracts as {'8.12', '8.21'} (both positive)",
    decs == {"8.12", "8.21"},
    f"extracted={sorted(decs)}",
)

# Real negative (U+2212 MINUS SIGN) MUST be preserved
real_neg = "HbA1c change was −1.44% (95% CI −1.59 to −1.29)"
normalized_neg = _normalize_unicode_minus(real_neg)
check(
    "U+2212 MINUS SIGN → ASCII '-' (preserves negative)",
    "-1.44" in normalized_neg and "-1.59" in normalized_neg,
    f"normalized={normalized_neg!r}",
)

decs_neg = _decimals_in(real_neg)
check(
    "'−1.44%' extracts as '-1.44' (real negative)",
    "-1.44" in decs_neg,
    f"extracted={sorted(decs_neg)}",
)

# Mixed range of negatives (U+2013 between digit and minus sign)
# "−1.59 to −1.29" — `to` separator, both should extract as negative
mixed_range = "Body weight change ranged from −7.5 to −12.9 kg over 72 weeks."
normalized_mixed = _normalize_unicode_minus(mixed_range)
check(
    "Mixed range with 'to' separator preserves both negatives",
    "-7.5" in normalized_mixed and "-12.9" in normalized_mixed,
    f"normalized={normalized_mixed!r}",
)

decs_mixed = _decimals_in(mixed_range)
check(
    "'−7.5 to −12.9' extracts as {'-7.5', '-12.9'}",
    decs_mixed == {"-7.5", "-12.9"},
    f"extracted={sorted(decs_mixed)}",
)

# ITER 3 — Codex iter-2 continuing P1 #2 fix: whitespace variants
# Codex caught these by actually running verify_sentence_provenance:
#   `'HbA1c 95% CI was 8.12 -8.21 percent at week 12 in patients.'`
#   was producing decimals `['-8.21', '8.12']` → fake negative.

# Leading whitespace before dash, no whitespace after
left_ws_only = "HbA1c 95% CI was 8.12 –8.21 percent at week 12."
norm_left = _normalize_unicode_minus(left_ws_only)
check(
    "ITER 3 — '8.12 –8.21' (left-ws only) does NOT yield '-8.21'",
    "-8.21" not in norm_left,
    f"normalized={norm_left!r}",
)
decs_left = _decimals_in(left_ws_only)
check(
    "ITER 3 — '8.12 –8.21' extracts as {'8.12', '8.21'}",
    decs_left == {"8.12", "8.21"},
    f"extracted={sorted(decs_left)}",
)

# Both whitespace (space dash space)
both_ws = "HbA1c 95% CI was 8.12 — 8.21 percent."
norm_both = _normalize_unicode_minus(both_ws)
check(
    "ITER 3 — '8.12 — 8.21' (both-ws em-dash) does NOT yield '-8.21'",
    "-8.21" not in norm_both,
    f"normalized={norm_both!r}",
)
decs_both = _decimals_in(both_ws)
check(
    "ITER 3 — '8.12 — 8.21' extracts as {'8.12', '8.21'}",
    decs_both == {"8.12", "8.21"},
    f"extracted={sorted(decs_both)}",
)

# Trailing whitespace before digit (right-ws only)
right_ws = "HbA1c 95% CI was 8.12– 8.21 percent."
norm_right = _normalize_unicode_minus(right_ws)
check(
    "ITER 3 — '8.12– 8.21' (right-ws only) does NOT yield '-8.21'",
    "-8.21" not in norm_right,
    f"normalized={norm_right!r}",
)
decs_right = _decimals_in(right_ws)
check(
    "ITER 3 — '8.12– 8.21' extracts as {'8.12', '8.21'}",
    decs_right == {"8.12", "8.21"},
    f"extracted={sorted(decs_right)}",
)

# Range of negatives — dash between digit and U+2212 minus sign
neg_range = "Body weight change −7.5–−12.9 kg over 72 weeks."
norm_neg = _normalize_unicode_minus(neg_range)
check(
    "ITER 3 — '−7.5–−12.9' (range of negatives) preserves both negatives",
    "-7.5" in norm_neg and "-12.9" in norm_neg,
    f"normalized={norm_neg!r}",
)
decs_neg_range = _decimals_in(neg_range)
check(
    "ITER 3 — '−7.5–−12.9' extracts as {'-7.5', '-12.9'}",
    decs_neg_range == {"-7.5", "-12.9"},
    f"extracted={sorted(decs_neg_range)}",
)

# Codex's exact failing test (verbatim from iter 2 verdict)
codex_test = "HbA1c 95% CI was 8.12 –8.21 percent at week 12 in patients."
codex_decs = _decimals_in(codex_test)
check(
    "ITER 3 — Codex's exact failing string: '8.12 –8.21' yields {'8.12', '8.21'}",
    codex_decs == {"8.12", "8.21"},
    f"extracted={sorted(codex_decs)}",
)

# Narrative em-dash near digits but NOT range (must keep as ASCII '-')
narrative = "—Tirzepatide 15 mg—the highest dose tested."
norm_narr = _normalize_unicode_minus(narrative)
# Leading em-dash has no digit before it (start of string), so should
# fall through to step-3 ASCII conversion: "-Tirzepatide 15 mg-the..."
check(
    "ITER 3 — Narrative em-dash NOT between digits: still becomes ASCII '-'",
    "-Tirzepatide" in norm_narr and "mg-the" in norm_narr,
    f"normalized={norm_narr!r}",
)

# ------------------------------------------------------------------------
# ITER 4 — Codex iter-3 continuing P1 #2 fix: \s* was too broad
# Codex ran live tests showing two new failure cases:
#  (a) `\s*` crosses newlines — `"week 12\n–8.21"` corrupts real negative
#  (b) `\s` does NOT match zero-width chars — `"8.12​–8.21"` bypassed
# ------------------------------------------------------------------------

# Codex's exact newline reproducer (verbatim)
newline_neg = "HbA1c at week 12\n–8.21 percent in patients."
norm_newline = _normalize_unicode_minus(newline_neg)
check(
    "ITER 4 — Newline between digit and dash: real negative PRESERVED",
    "-8.21" in norm_newline,
    f"normalized={norm_newline!r}",
)
decs_newline = _decimals_in(newline_neg)
check(
    "ITER 4 — 'week 12\\n–8.21' extracts -8.21 (NOT corrupted to positive)",
    "-8.21" in decs_newline,
    f"extracted={sorted(decs_newline)}",
)

# Codex's exact ZWSP reproducer
zwsp_range = "HbA1c 8.12​–8.21 percent."
norm_zwsp = _normalize_unicode_minus(zwsp_range)
check(
    "ITER 4 — ZWSP (U+200B) between digit and dash: range separator wins",
    "-8.21" not in norm_zwsp,
    f"normalized={norm_zwsp!r}",
)
decs_zwsp = _decimals_in(zwsp_range)
check(
    "ITER 4 — '8.12\\u200b–8.21' extracts as {'8.12', '8.21'}",
    decs_zwsp == {"8.12", "8.21"},
    f"extracted={sorted(decs_zwsp)}",
)

# Paragraph separator (U+2029) must also NOT bridge digit-to-negative
para_sep = "HbA1c 8.12 \u2029\u20138.21 percent."
decs_para = _decimals_in(para_sep)
check(
    "ITER 4 - U+2029 PARA SEP does NOT bridge digit-to-negative",
    "-8.21" in decs_para,
    f"extracted={sorted(decs_para)}",
)

# Line separator (U+2028) likewise
line_sep = "HbA1c 8.12 \u2028\u20138.21 percent."
decs_line = _decimals_in(line_sep)
check(
    "ITER 4 - U+2028 LINE SEP does NOT bridge digit-to-negative",
    "-8.21" in decs_line,
    f"extracted={sorted(decs_line)}",
)


# Vertical tab + form feed
for cp, name in (("\v", "VT"), ("\f", "FF")):
    txt = f"HbA1c 8.12{cp}–8.21 percent."
    d = _decimals_in(txt)
    check(
        f"ITER 4 — {name} ({cp!r}) does NOT bridge digit→negative",
        "-8.21" in d,
        f"extracted={sorted(d)}",
    )

# NBSP (U+00A0) IS inline → must bridge as range separator
nbsp_only = "HbA1c 8.12 –8.21 percent."
decs_nbsp = _decimals_in(nbsp_only)
check(
    "ITER 4 — NBSP (U+00A0) is inline → range separator wins",
    decs_nbsp == {"8.12", "8.21"},
    f"extracted={sorted(decs_nbsp)}",
)


# ------------------------------------------------------------------------
# TEST 3: Cancer-50% adversarial via FULL verifier path
# ------------------------------------------------------------------------
# Note: _find_local_support_window is a NUMERIC anchor only. The full
# verifier has THREE additional defense layers downstream:
#   (a) content_word_overlap on aggregated_span_text (narrow span only) —
#       at line 977. If V4 Pro cites a narrow byte range that lacks the
#       sentence's content words, drop with no_content_word_overlap.
#   (b) trial_name match.
#   (c) entailment judge → if NEUTRAL/CONTRADICTED, retry on LOCAL WINDOW
#       (NOT whole doc per Codex P1 #3 fix).
#
# This test exercises the full verify_sentence_provenance for the
# cancer-50% adversarial to confirm it drops via downstream gates.
banner("TEST 3 — Cancer-50% adversarial via FULL verifier path (must drop)")

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)

ev_with_unrelated_50 = (
    "A total of 1,879 participants with type 2 diabetes were enrolled "
    "in SURPASS-2. Baseline HbA1c averaged 8.28%. After 40 weeks, "
    "tirzepatide 15 mg reduced HbA1c by 2.46% from baseline. "
    "Demographics: 53.4% female, mean age 56.6 years, mean BMI 34.2. "
    "Approximately 50% of patients had no documented family history "
    "of cancer at screening."
)

# V4 Pro cites byte range 0-100 (just the intro: "A total of 1,879
# participants with type 2 diabetes were enrolled in SURPASS-2.")
# The narrow span has NO content words from the fabricated sentence.
fab_sentence = (
    "Tirzepatide reduces cancer by 50% in patients with metabolic "
    "syndrome [#ev:ev_fab:0-100]."
)
evidence_pool = {
    "ev_fab": {
        "evidence_id": "ev_fab",
        "direct_quote": ev_with_unrelated_50,
        "statement": "SURPASS-2 demographics",
    }
}

# Disable LLM judge for this test (would require API) — drop should
# still occur via numeric or content_word_overlap gates.
import os  # noqa: E402

prev_entailment = os.environ.get("PG_ENTAILMENT_MODE")
os.environ["PG_ENTAILMENT_MODE"] = "off"
try:
    sv = verify_sentence_provenance(
        fab_sentence, evidence_pool, require_number_match=True,
    )
finally:
    if prev_entailment is None:
        os.environ.pop("PG_ENTAILMENT_MODE", None)
    else:
        os.environ["PG_ENTAILMENT_MODE"] = prev_entailment

check(
    "Cancer-50% fabrication is DROPPED via full verifier "
    "(content_word_overlap on narrow span fails)",
    not sv.is_verified,
    f"is_verified={sv.is_verified} failure_reasons={sv.failure_reasons}",
)


# ------------------------------------------------------------------------
# TEST 4: SURPASS-grounded sentence MUST still pass (no regression)
# ------------------------------------------------------------------------
banner("TEST 4 — SURPASS grounded sentence (must pass)")

# Real evidence text (compressed from ev_017 / ev_001 patterns):
# narrow citation 0-500, but the numbers are at offset 500+
ev_surpass = (
    "ABSTRACT: SURPASS-3 was a phase 3 randomized open-label trial "
    "comparing tirzepatide to titrated insulin degludec in 1,444 "
    "adults with type 2 diabetes inadequately controlled on metformin "
    "with or without SGLT2 inhibitors. The primary endpoint was the "
    "mean change from baseline in HbA1c at week 52. " + "X" * 50 +
    " RESULTS: At week 52, mean change in HbA1c from baseline was "
    "−1.93% with tirzepatide 5 mg, −2.20% with 10 mg, and −2.37% "
    "with 15 mg, versus −1.34% with insulin degludec (estimated "
    "treatment difference −0.59% to −1.04%, all p<0.001)."
)

# V4 Pro writes "tirzepatide 15 mg reduced HbA1c by 2.37% vs 1.34%
# for insulin degludec" with citation byte range [0:500] (abstract only)
needed_decs = {"2.37", "1.34"}  # both present in evidence (with U+2212 minus)
needed_words = {"tirzepatide", "hba1c", "insulin"}

# The decimals will normalize: −2.37 → -2.37, but the sentence-side
# decimals are positive "2.37"/"1.34". Test that positive-claim form
# still matches via the missing-in-span fallback (Codex iter-2 expects
# this — the sentence-side may write "tirzepatide reduced HbA1c by
# 2.37%" without a minus sign because the sentence already says
# "reduced", so the decimal token is positive).
#
# IMPORTANT: per Codex P1 #1, positive '2.37' MUST NOT match '-2.37'
# token-exactly. So a positive-claim sentence citing a negative
# evidence number will (correctly) NOT find a local window.
# This is the CORRECT behavior — the verifier should drop a sentence
# that writes "+2.37%" against evidence that says "-2.37%".

# To test the positive-passes-case, we need a sentence whose decimals
# match the evidence sign. Construct: "estimated treatment difference
# 0.59 to 1.04" (the absolute value range cited in the evidence).
# Evidence has both "−0.59%" and "−1.04%" — token-exact will see those
# as "-0.59"/"-1.04".
needed_signed = {"-0.59", "-1.04"}
needed_diff_words = {"tirzepatide", "treatment", "difference"}
win_pass = _find_local_support_window(
    needed_signed, needed_diff_words, ev_surpass,
    window=400, min_content_overlap=2,
)
check(
    "Signed decimals '-0.59' + '-1.04' DO find a local window (grounded sentence passes)",
    win_pass is not None,
    f"window={win_pass}",
)

# And confirm: if sentence and evidence agree on sign and on at least
# 2 content words, the window IS found
needed_2_37 = {"-2.37", "-1.34"}
needed_surpass_words = {"hba1c", "insulin", "tirzepatide"}
win_surpass = _find_local_support_window(
    needed_2_37, needed_surpass_words, ev_surpass,
    window=400, min_content_overlap=2,
)
check(
    "SURPASS-3 numbers '-2.37' + '-1.34' find local window (no regression)",
    win_surpass is not None,
    f"window={win_surpass}",
)


# ------------------------------------------------------------------------
# TEST 5: Cluster placement — non-rarest tokens must be inside window
# ------------------------------------------------------------------------
banner("TEST 5 — Cluster window placement (Codex P2)")

# Tokens '1.5' (rare) and '2.0' (common 5x in evidence). The rarest is '1.5'.
# The cluster must find the nearest occurrence of '2.0' to '1.5' that
# fits within 400 chars.
ev_multi = (
    "Pre-randomization: HbA1c was 8.2%. " + "Z" * 200 +
    " 2.0 mmol/L glucose. " + "Y" * 300 +
    " HbA1c reduction was 1.5% with active and 2.0% with placebo. " +
    "X" * 200 + " 2.0%. " + "W" * 200 + " 2.0%. " + "V" * 200 + " 2.0%."
)
needed_multi = {"1.5", "2.0"}
content_multi = {"hba1c", "reduction", "active"}
win_multi = _find_local_support_window(
    needed_multi, content_multi, ev_multi,
    window=400, min_content_overlap=2,
)
check(
    "Multi-token cluster: nearest '2.0' to '1.5' is found within 400 chars",
    win_multi is not None,
    f"window={win_multi}",
)



# ------------------------------------------------------------------------
# ITER 5 - Codex iter-4 continuing P1 #2 fixes
# ------------------------------------------------------------------------
banner("ITER 5 - Codex iter-4 continuing P1 #2 fixes")

# Codex iter-4 P1 (a): "week 12 -8.21" bare-integer label + left-gap-only
# corrupted real negative -8.21. Fixed by Pattern A (no-left-gap OR
# both-gap) + Pattern B (decimal-left+left-gap-only).
src_iter5_a = "HbA1c at week 12 \u20138.21 percent in patients."
check(
    "ITER 5 (a) week 12 -8.21 bare integer preserves negative",
    "-8.21" in _decimals_in(src_iter5_a),
    f"extracted={sorted(_decimals_in(src_iter5_a))}",
)

src_iter5_a_tab = "HbA1c at week 12	\u20138.21 percent."
check(
    "ITER 5 (a) week 12 + TAB + dash: preserves negative",
    "-8.21" in _decimals_in(src_iter5_a_tab),
    f"extracted={sorted(_decimals_in(src_iter5_a_tab))}",
)

src_iter5_a_nbsp = "HbA1c at week 12\u00a0\u20138.21 percent."
check(
    "ITER 5 (a) week 12 + NBSP + dash: preserves negative",
    "-8.21" in _decimals_in(src_iter5_a_nbsp),
    f"extracted={sorted(_decimals_in(src_iter5_a_nbsp))}",
)

src_iter5_a_zwsp = "HbA1c at week 12\u200b\u20138.21 percent."
check(
    "ITER 5 (a) week 12 + ZWSP + dash: preserves negative",
    "-8.21" in _decimals_in(src_iter5_a_zwsp),
    f"extracted={sorted(_decimals_in(src_iter5_a_zwsp))}",
)

# Codex iter-4 P1 (b): U+00AD SOFT HYPHEN missing from gap class.
src_iter5_b = "HbA1c 8.12\u00ad\u20138.21 percent."
check(
    "ITER 5 (b) U+00AD SOFT HYPHEN between digit and dash: positive range",
    _decimals_in(src_iter5_b) == {"8.12", "8.21"},
    f"extracted={sorted(_decimals_in(src_iter5_b))}",
)

src_iter5_b_bidi = "HbA1c 8.12\u202a\u20138.21 percent."
check(
    "ITER 5 (b) U+202A LRE bidi: positive range",
    _decimals_in(src_iter5_b_bidi) == {"8.12", "8.21"},
    f"extracted={sorted(_decimals_in(src_iter5_b_bidi))}",
)

src_iter5_b_rlo = "HbA1c 8.12\u202e\u20138.21 percent."
check(
    "ITER 5 (b) U+202E RLO bidi: positive range",
    _decimals_in(src_iter5_b_rlo) == {"8.12", "8.21"},
    f"extracted={sorted(_decimals_in(src_iter5_b_rlo))}",
)

src_iter5_b_iat = "HbA1c 8.12\ufff9\u20138.21 percent."
check(
    "ITER 5 (b) U+FFF9 interlinear: positive range",
    _decimals_in(src_iter5_b_iat) == {"8.12", "8.21"},
    f"extracted={sorted(_decimals_in(src_iter5_b_iat))}",
)

# Regression: decimal-left with left-gap STILL is range
src_iter5_reg = "HbA1c 95% CI was 8.12 \u20138.21 percent."
check(
    "ITER 5 regression: decimal-left + left-gap + dash: still a range",
    _decimals_in(src_iter5_reg) == {"8.12", "8.21"},
    f"extracted={sorted(_decimals_in(src_iter5_reg))}",
)

# Regression: both-gap with bare integer left STILL treated as range
src_iter5_intboth = "week 12 \u2013 8.21"
check(
    "ITER 5 regression: integer + both-gap: still treated as range",
    _decimals_in(src_iter5_intboth) == {"8.21"},
    f"extracted={sorted(_decimals_in(src_iter5_intboth))}",
)


# ------------------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------------------
print(f"\n{'=' * 70}")
print(f"SUMMARY: {len(failures)} failures")
print(f"{'=' * 70}")
if failures:
    for f in failures:
        print(f"  FAIL: {f}")
    sys.exit(1)
else:
    print("  ALL ADVERSARIAL TESTS PASSED")
    sys.exit(0)
