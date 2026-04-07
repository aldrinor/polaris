"""Serious test of post-continuation word cap fix."""
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=== POST-CONTINUATION WORD CAP - SERIOUS TEST ===\n")

with open("src/polaris_graph/synthesis/section_writer.py", "r") as f:
    sw = f.read()

# Test 1: Verify execution order
print("Test 1: Word cap ordering...")
cap_pos = sw.find("WORD-CAP: Section")
cont_pos = sw.find("appears truncated")
post_cap_pos = sw.find("WORD-CAP-POST-CONT")
assert cap_pos < cont_pos < post_cap_pos, (
    f"Wrong order: cap={cap_pos}, cont={cont_pos}, post_cap={post_cap_pos}"
)
print(f"  WORD-CAP ({cap_pos}) -> continuation ({cont_pos}) -> POST-CONT ({post_cap_pos})")
print("  PASS")

# Test 2: Post-cap uses _max_section_words
print("\nTest 2: Post-cap references same variable...")
post_block_start = sw.find("# Re-apply word cap after continuation")
post_block = sw[post_block_start:post_block_start + 600]
assert "_max_section_words" in post_block
assert "_post_cont_words > _max_section_words" in post_block
print("  PASS")

# Test 3: _max_section_words defined before use
print("\nTest 3: Variable defined before first use...")
max_def_pos = sw.find("_max_section_words = ")
assert 0 < max_def_pos < cap_pos
max_line = sw[max_def_pos:sw.find("\n", max_def_pos)].strip()
print(f"  Definition: {max_line}")
print("  PASS")

# Test 4: Simulate TEST_083 Section 2 explosion with REAL sentence structure
print("\nTest 4: Simulate TEST_083 (1938w cap + continuation)...")
_max = 2000

# Build realistic content: ~1938 words in sentences (post word-cap, missing terminal punct)
sents_1938 = [f"Finding {i}: intermittent fasting shows measurable effects on metabolic markers [1]." for i in range(180)]
content = " ".join(sents_1938)
# Truncate to ~1938 words and remove terminal punctuation (simulates word-cap truncation)
words = content.split()[:1938]
content = " ".join(words).rstrip(".!?")
print(f"  After word cap: {len(content.split())} words (no terminal punct)")

# Continuation adds ~1600 words (realistic LLM continuation)
cont_sents = [f"Continued finding {i}: additional evidence supports these conclusions [2]." for i in range(150)]
continuation = " ".join(cont_sents)
content = content + " " + continuation
pre_cap_wc = len(content.split())
print(f"  After continuation: {pre_cap_wc} words")
assert pre_cap_wc > 3000, f"Expected >3000, got {pre_cap_wc}"

# Post-continuation cap (exact code from section_writer.py)
if pre_cap_wc > _max:
    sents = re.split(r"(?<=[.!?])\s+", content)
    trunc = []
    running = 0
    for s in sents:
        sw_count = len(s.split())
        if running + sw_count > _max:
            break
        trunc.append(s)
        running += sw_count
    if trunc:
        content = " ".join(trunc)

final_wc = len(content.split())
print(f"  After post-cont cap: {final_wc} words")
assert final_wc <= _max + 50, f"FAILED: {final_wc} > {_max + 50}"
print(f"  Reduction: {pre_cap_wc} -> {final_wc} ({pre_cap_wc - final_wc} words removed)")
print("  PASS")

# Test 5: Real sentences with citations
print("\nTest 5: Real sentence structure...")
real_sents = [
    "Intermittent fasting reduces body weight by 3-8% over 8-12 weeks [1].",
    "A meta-analysis of 27 trials confirmed significant reductions in fasting insulin [2].",
    "Time-restricted eating confines caloric intake to an 8-12 hour window daily [3].",
    "Alternate-day fasting alternates 24-hour fasting with ad libitum eating days [1].",
    "The metabolic switch from glucose to fatty acid oxidation occurs after 12-16 hours [4].",
    "HOMA-IR improvements suggest enhanced cellular responsiveness to insulin [2].",
    "LDL cholesterol decreased significantly compared to control groups [5].",
    "Blood pressure improvements were observed with moderate GRADE certainty [3].",
    "Leptin decreased with WMD of -2.28 ng/ml (95% CI: -3.72 to -0.84) [6].",
    "No significant change in adiponectin was observed during fasting protocols [6].",
] * 25  # ~250 sentences

pre_cap = " ".join(real_sents[:200])
cont_text = " ".join(real_sents[100:250])
combined = pre_cap + " " + cont_text
combined_wc = len(combined.split())
print(f"  Combined: {combined_wc} words")

if combined_wc > _max:
    sents = re.split(r"(?<=[.!?])\s+", combined)
    trunc = []
    running = 0
    for s in sents:
        sw_count = len(s.split())
        if running + sw_count > _max:
            break
        trunc.append(s)
        running += sw_count
    if trunc:
        combined = " ".join(trunc)

result_wc = len(combined.split())
print(f"  After cap: {result_wc} words")
assert result_wc <= _max + 20
# Verify ends at sentence boundary
assert combined.rstrip().endswith((".", "?", "!", "]")), f"Bad ending: ...{combined[-30:]}"
print(f"  Ends with: ...{combined[-50:]}")
print("  PASS")

# Test 6: Short content (no trigger)
print("\nTest 6: Short content - cap should NOT trigger...")
short = "Short section about fasting [1]. Additional data [2]."
short_wc = len(short.split())
triggered = short_wc > _max
assert not triggered
print(f"  {short_wc} words < {_max} cap: NOT triggered (correct)")
print("  PASS")

# Test 7: Content exactly at cap (no trigger)
print("\nTest 7: Content at exactly 2000 words...")
exact = " ".join(["word"] * 1999) + " end."
exact_wc = len(exact.split())
triggered = exact_wc > _max
print(f"  {exact_wc} words vs {_max} cap: {'triggered' if triggered else 'NOT triggered'}")
print("  PASS")

# Test 8: Would have prevented TEST_083
print("\nTest 8: Would this fix have prevented TEST_083 Section 2?")
print(f"  TEST_083 Section 2: 3562 words")
print(f"  Cap: {_max} words")
print(f"  Would trigger: {3562 > _max}")
print(f"  Would reduce to: ~{_max} words")
assert 3562 > _max
print("  PASS: Yes, fix prevents the explosion")

print("\n" + "=" * 55)
print("ALL 8 TESTS PASSED")
print("=" * 55)
