HARD ITERATION CAP: 5 per document. This is iter 1 of 5. APPROVE iff zero P0 and zero P1. Your shell is unavailable this session — this context is SELF-CONTAINED (diff + inlined surrounding code); verify from the inlined text, do NOT abstain on shell grounds.

# Wave-3a U5 — CLINICAL-SAFETY: numeric-comparator legacy arm-default hole (the comparator is now ACTIVATED, U4)

CONTEXT: POLARIS I-deepfix-001 (#1344). The numeric comparator (PG_NUMERIC_COMPARATOR) upgrades a NEUTRAL cross-source pair to a `comparison` connective only when the two findings share subject/unit/predicate/dose/arm/endpoint. It is now ON on the paid path (U4). This is clinical-safety-critical: a wrong same-arm comparison implies a wrong dose/effect ("it is lethal" is literal).

THE HOLE (found + fixed by this diff, Claude-authored, you gate): the numeric extractor defaults a missing arm to the non-blank string "treatment" (contradiction_detector.py:1601). The prior Wave-2a fix made the comparability guard reject only BLANK discriminators — "treatment" is non-blank, so two findings that each lack an arm cue both carry arm="treatment", pass the guard, and (if other discriminators match) get licensed as a SAME-arm comparison that was never established. arm is the ONLY legacy discriminator with a non-blank unknown default (dose/endpoint default to "" and are already caught). On today's exact paid config it is LATENT (PG_SWEEP_CREDIBILITY_REDESIGN forces the redesign key-builder, which singleton-forces a defaulted arm upstream via claim_graph._unknown_arm), but PG_NUMERIC_COMPARATOR and the redesign flag are independent env flags and the comparator is contracted to fail-closed on legacy keys too.

THE FIX: in numeric_comparator._numeric_comparability_key, after the blank-guard loop, treat a legacy 8-tuple arm slot == "treatment" as UNKNOWN → return None (not comparable). Mirrors claim_graph._unknown_arm. A SENTINEL that FAILS the comparability guard (stricter — fewer comparisons), NOT a different non-blank default. Legacy-8-tuple-only → strict no-op on redesign keys (len 6/14). Behind PG_NUMERIC_COMPARATOR (OFF byte-identical). Faithfulness engine untouched.

VERIFY:
1. STRICTER NOT LOOSER — the guard can only REDUCE the set of comparable pairs (a "treatment"/unknown arm → None → not comparable). It never licenses a NEW comparison. Confirm.
2. NO PAID-PATH REGRESSION — it fires ONLY on the legacy 8-tuple (len==8) arm slot; redesign keys (len 6/14) never carry "treatment" (singleton-forced upstream) so this is a no-op there. Confirm real comparisons (two findings with the SAME explicit arm + matching discriminators) still return a comparison.
3. CLINICAL-SAFETY CORRECT — two findings each with a MISSING arm (both defaulted "treatment") are now NOT comparable. Confirm the sentinel actually gates license_numeric_comparison (trace the None return through to "not a comparison").
4. OFF BYTE-IDENTICAL — the guard lives in the comparator module, dark unless PG_NUMERIC_COMPARATOR ON. Confirm no behavior change when OFF.
5. FAITHFULNESS untouched (no strict_verify / engine change). git diff -w == git diff (purely additive, +28/0). Confirm.
6. Any P0/P1.

## THE DIFF (numeric_comparator.py, +28/-0):
```diff
diff --git a/src/polaris_graph/generator/numeric_comparator.py b/src/polaris_graph/generator/numeric_comparator.py
index 456bea19..c7b39ddd 100644
--- a/src/polaris_graph/generator/numeric_comparator.py
+++ b/src/polaris_graph/generator/numeric_comparator.py
@@ -56,6 +56,23 @@ _NUMERIC_TAG = "numeric"
 _VALUE_SLOT_INDEX = 3
 _MIN_NUMERIC_KEY_LEN = 4  # tag, subject, predicate, value (nonclinical redesign is the shortest at 6)
 
+# Wave-3a (I-deepfix-001 #1344, clinical-safety): the LEGACY ``_normalized_key_numeric`` key is a fixed
+# 8-tuple ``("numeric", subject, predicate, value, unit, dose, arm, endpoint_phrase)`` and it carries a
+# NO-CUE arm as the non-blank DEFAULT ``"treatment"`` (contradiction_detector.py:1601, kept for OFF
+# byte-identity — Codex Slice-B P1). ``"treatment"`` is non-blank, so the blank guard in
+# ``_numeric_comparability_key`` does NOT catch it: two findings whose arm was NEVER positively extracted
+# (both defaulted to ``"treatment"``) would license a SAME-arm ``comparison`` that was never established —
+# the lethal over-relax. Mirror ``claim_graph._unknown_arm`` (which treats ``"treatment"`` AS UNKNOWN on
+# the redesign path): a legacy arm slot == ``"treatment"`` is UNKNOWN -> fail closed. The REDESIGN key
+# already singleton-forces a defaulted arm UPSTREAM (build_merge_key via _unknown_arm), so a redesign key
+# NEVER reaches the comparator carrying ``"treatment"`` -> this is a strict NO-OP on redesign keys and
+# closes the LEGACY path only. arm is the ONLY legacy discriminator with a non-blank unknown default
+# (dose / endpoint / etc. default to ``""`` — already caught by the blank guard; a defaulted "unknown"
+# subject is already sentinelled by ``_normalized_key_numeric`` itself).
+_LEGACY_NUMERIC_KEY_LEN = 8       # ("numeric", subject, predicate, value, unit, dose, arm, endpoint_phrase)
+_LEGACY_ARM_SLOT_INDEX = 6        # arm position in the full legacy 8-tuple
+_LEGACY_ARM_UNKNOWN_SENTINEL = "treatment"  # extractor no-cue arm default == UNKNOWN (claim_graph._unknown_arm)
+
 _ENV_NUMERIC_COMPARATOR = "PG_NUMERIC_COMPARATOR"
 
 
@@ -103,6 +120,17 @@ def _numeric_comparability_key(normalized_key: Any) -> Optional[tuple]:
     for slot in discriminators[1:]:
         if not str(slot).strip():
             return None
+    # Wave-3a (clinical-safety, mirrors claim_graph._unknown_arm): the LEGACY key carries a NO-CUE arm as
+    # the non-blank sentinel ``"treatment"`` (index 6 of the fixed 8-tuple), which the blank guard above
+    # does NOT catch. Two arm-unknown findings both default to ``"treatment"``; licensing a comparison
+    # implies a same-arm claim that was NEVER positively established (the lethal over-relax). Fail closed on
+    # it. LEGACY key ONLY (len == 8): the redesign key already singleton-forces a defaulted arm upstream, so
+    # it never reaches here carrying ``"treatment"`` -> strict NO-OP on redesign keys.
+    if (
+        len(normalized_key) == _LEGACY_NUMERIC_KEY_LEN
+        and str(normalized_key[_LEGACY_ARM_SLOT_INDEX]).strip().lower() == _LEGACY_ARM_UNKNOWN_SENTINEL
+    ):
+        return None
     return (discriminators, float(value))
 
 
```

## SURROUNDING CODE (inlined so you can verify without shell)
### numeric_comparator.py — _numeric_comparability_key (the guard's full function) + license_numeric_comparison (how the key gates the comparison):
```python
79:def numeric_comparator_enabled() -> bool:
88:def _numeric_comparability_key(normalized_key: Any) -> Optional[tuple]:
137:def license_numeric_comparison(key_a: Any, key_b: Any) -> Optional[str]:
# _numeric_comparability_key (blank guard + the NEW treatment sentinel):
80:     """``PG_NUMERIC_COMPARATOR`` gate (default OFF, LAW VI). OFF => the composer never consults the
81:     comparator and the cross-source relation set stays {conflict, agreement, extension, neutral}
82:     (byte-identical). ON => a NEUTRAL pair whose two baskets carry FULLY-comparable numeric claims is
83:     upgraded to the ``comparison`` connective. This is a WEIGHT/CONSOLIDATE surfacing lever, never a
84:     cap / target / thinner (§-1.3)."""
85:     return os.getenv(_ENV_NUMERIC_COMPARATOR, "0").strip().lower() not in ("", "0", "false", "off", "no")
86: 
87: 
88: def _numeric_comparability_key(normalized_key: Any) -> Optional[tuple]:
89:     """The comparability view of a numeric ``normalized_key``: ``(discriminators_tuple, value_float)``
90:     where ``discriminators_tuple`` is the merge key with the value slot removed (every discriminator, in
91:     order) and ``value_float`` is the EXACT verified value.
92: 
93:     Returns ``None`` (FAIL-CLOSED — treated as not-comparable) for anything that is not a
94:     FULLY-positively-known numeric merge key:
95:       * a non-tuple / too-short key;
96:       * a key whose tag (index 0) is not ``"numeric"`` — i.e. a qualitative key, the legacy
97:         ``__numeric_unknown__`` sentinel, or the redesign ``__unresolved__`` singleton;
98:       * a key whose value slot (index 3) is not a real number;
99:       * a key with ANY BLANK discriminator (empty / whitespace). The REDESIGN key never reaches here with
100:         a blank discriminator (``build_merge_key`` already singleton-forces on any unknown field), but the
101:         LEGACY ``_normalized_key_numeric`` sentinels ONLY on a blank SUBJECT — a blank predicate / unit /
102:         dose / arm / endpoint passes straight through as ``""``. Blank is UNKNOWN, not positively known, so
103:         this module ENFORCES the missing guard HERE (Fable P1, clinical-safety): any blank discriminator
104:         fails closed. This is a strict tightening (NO-OP on redesign keys) — never compare two numbers
105:         whose unit / entity / baseline was never established.
106:     Pure; never raises."""
107:     if not isinstance(normalized_key, tuple) or len(normalized_key) < _MIN_NUMERIC_KEY_LEN:
108:         return None
109:     if normalized_key[0] != _NUMERIC_TAG:
110:         return None
111:     value = normalized_key[_VALUE_SLOT_INDEX]
112:     # bool is an int subclass but is never a real measured value — reject it explicitly.
113:     if isinstance(value, bool) or not isinstance(value, (int, float)):
114:         return None
115:     discriminators = normalized_key[:_VALUE_SLOT_INDEX] + normalized_key[_VALUE_SLOT_INDEX + 1:]
116:     # Fable P1 (clinical-safety): EVERY discriminator field beyond the ``"numeric"`` tag must be POSITIVELY
117:     # KNOWN (non-blank). The legacy key does NOT self-fail-close on a blank non-subject field, and comparing
118:     # two values across an unknown unit / entity / baseline (%-points vs mmol/mol) is the lethal over-relax.
119:     # A single blank/empty/whitespace discriminator => fail closed. (``discriminators[0]`` is the tag.)
120:     for slot in discriminators[1:]:
121:         if not str(slot).strip():
122:             return None
123:     # Wave-3a (clinical-safety, mirrors claim_graph._unknown_arm): the LEGACY key carries a NO-CUE arm as
124:     # the non-blank sentinel ``"treatment"`` (index 6 of the fixed 8-tuple), which the blank guard above
125:     # does NOT catch. Two arm-unknown findings both default to ``"treatment"``; licensing a comparison
126:     # implies a same-arm claim that was NEVER positively established (the lethal over-relax). Fail closed on
127:     # it. LEGACY key ONLY (len == 8): the redesign key already singleton-forces a defaulted arm upstream, so
128:     # it never reaches here carrying ``"treatment"`` -> strict NO-OP on redesign keys.
129:     if (
130:         len(normalized_key) == _LEGACY_NUMERIC_KEY_LEN
131:         and str(normalized_key[_LEGACY_ARM_SLOT_INDEX]).strip().lower() == _LEGACY_ARM_UNKNOWN_SENTINEL
132:     ):
133:         return None
134:     return (discriminators, float(value))
135: 
136: 
137: def license_numeric_comparison(key_a: Any, key_b: Any) -> Optional[str]:
138:     """Decide whether a COMPARATIVE connective is licensed between two claim clusters, from their retained
139:     numeric ``normalized_key`` tuples.
140: 
# license_numeric_comparison (uses the key; None key => not comparable):
137: def license_numeric_comparison(key_a: Any, key_b: Any) -> Optional[str]:
138:     """Decide whether a COMPARATIVE connective is licensed between two claim clusters, from their retained
139:     numeric ``normalized_key`` tuples.
140: 
141:     Returns ``NUMERIC_COMPARISON_RELATION`` (``"comparison"``) IFF:
142:       * both keys reduce to a comparability view (both are positively-known numeric merge keys), AND
143:       * their discriminator tuples are EQUAL — every field (measure/entity/unit/denominator/baseline/
144:         time-window as carried by the merge-key spec) matches AND is positively known, AND
145:       * the two verified values DIFFER (equal values would already have shared a cluster — there is no
146:         "comparison" to draw between two identical numbers).
147:     Otherwise ``None`` (FAIL-CLOSED to the neutral connective): any missing / ambiguous / differing
148:     discriminator, a non-numeric key, or equal values. Pure; deterministic; arithmetic is ``==`` / ``!=``
149:     over already-verified floats. NEVER asserts a direction (larger/smaller) — the connective is
150:     non-directional and each clause keeps its own token."""
151:     ca = _numeric_comparability_key(key_a)
152:     cb = _numeric_comparability_key(key_b)
153:     if ca is None or cb is None:
154:         return None
155:     disc_a, val_a = ca
156:     disc_b, val_b = cb
157:     if disc_a != disc_b:
158:         return None  # different claim identity (measure/unit/entity/qualifier) => not comparable
159:     if val_a == val_b:
160:         return None  # identical values => same claim, no comparison to draw
```
### contradiction_detector.py:1601 — the arm="treatment" default (the source of the unknown sentinel):
```python
1596:         # forces a singleton; only the positively-extracted "comparator_adjacent"
1597:         # cue anchors a merge (design §4.3 — the arm lesson holds without None).
1598:         if _detect_placebo_arm(ctx_window):
1599:             arm = "comparator_adjacent"
1600:         else:
1601:             arm = "treatment"
1602:         endpoint_phrase = _extract_endpoint_phrase(ctx_window) or _extract_endpoint_phrase(quote)
1603: 
1604:         # Wave-3 positive-known discriminators (I-arch-002 [2]). Each reads the
```
### claim_graph._unknown_arm — the mirror the fix follows (treats "treatment" AS unknown on the redesign path):
```python
229:def _normalized_key_numeric(
351:def _unknown_arm(v: Any) -> bool:
359:    return s in ("", "treatment")
```

OUTPUT SCHEMA (return exactly):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
stricter_not_looser: true|false
no_paid_path_regression: true|false
clinical_safety_correct: true|false
off_byte_identical: true|false
faithfulness_untouched: true|false
convergence_call: continue | accept_remaining
notes: <short>
```
APPROVE iff stricter-not-looser, no paid-path regression, clinical-safety correct, OFF byte-identical, faithfulness untouched, zero P0/P1.
