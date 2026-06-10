HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" -- if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" -- DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## ITER-2 -- what changed since your iter-1 review

Your iter-1 findings were addressed in this diff:

- **P1-1 (multi-occurrence leak):** the same non-VERIFIED stem can appear more than once (e.g. once cleanly + once inside a boundary-under-split merge). The prior single-pass logic stopped after the FIRST removal and left the second occurrence in the shipped body -- a leak. **FIX:** redaction now LOOPS per claim (`while _prose_present(working, stem_norm):` at report_redactor.py:230) running TIER 1 then TIER 2 each pass until the stem is ABSENT from the line-join-normalized whole body OR no tier makes progress (then fail-closed). The claim is appended to `result.redacted` exactly ONCE after the loop (report_redactor.py:265), never per-removal -- so a twice-occurring claim is not double-counted. New tests: `test_p1_1_multi_occurrence_both_removed_once_recorded`, `test_p1_1_multi_occurrence_both_clean_both_removed`.

- **P1-2 (fixture path):** the fixture moved from the gitignored/untracked `outputs/audits/I-redact-001/redaction_fixture.json` (which broke parametrize COLLECT on a clean CI checkout) to the TRACKED `tests/fixtures/redaction_fixture_redact001.json` (LAW VI: test fixtures live under tests/fixtures/). The test reads `Path(__file__).resolve().parents[1] / "fixtures" / "redaction_fixture_redact001.json"`. Confirmed `git ls-files` shows the fixture tracked; a copy stays under outputs/audits/ for the audit trail only.

- **P2 (ARM-3 mid-sentence inline-citation false-split):** ARM 3 of `_SENTENCE_BOUNDARY_RE` (marker-as-terminator with no preceding period) is now WORD-ANCHORED -- `(?<=\w)(?:\[\d+\])+\s+(?=[A-Z"'(#0-9])` -- so it fires ONLY on a word-attached marker like `risk[1]` / `recovery[17][22]`. A mid-sentence inline citation with WHITESPACE before the bracket (`...as shown [5] In vivo...`, `the [5] Group reported...`) is rejected by `(?<=\w)`, so the inline-cited sentence stays ONE span and is not over-split (which would drop it below the coverage floor and risk over-redaction of a VERIFIED sentence). New tests: `test_p2_inline_midsentence_citation_not_split`, `test_p2_inline_citation_verified_sentence_not_over_redacted`.

## Summary of the change under review

**Issue I-redact-001 (#1181).** The F01 fix (#1174) made redaction severity-INDEPENDENT (every non-VERIFIED claim, including S3 observe-only, must be redacted). That exposed a pre-existing pinning regression: when the renderer under-split two real sentences into one over-long span (no terminal period before a `[N]` marker, or a next sentence starting with a digit), the rejected claim's stem covered `< _MIN_REDACTION_COVERAGE` of the merged span, so no single span matched, the stem was "present but unpinnable", and `reconcile_report_against_verdicts` RAISED `ReportRedactionError` -> `abort_report_redaction_failed` for the WHOLE run. **All 5 beat-both questions aborted with zero reports shipped.**

The fix makes a present-but-hard-to-pin UNSUPPORTED claim REDACT (via a multi-span / minimal-containing-unit fallback) instead of aborting the whole report; it fail-closed-ABORTS only when the prose is genuinely unbounded by any redactable unit. Three tiers (report_redactor.py docstring + `reconcile_report_against_verdicts` loop):

- **TIER 1** (precise, single span): prose pins to one discrete rendered span at the coverage floor -> redact exactly that span, leaving every VERIFIED neighbor and its `[N]` markers byte-for-byte. `_redact_sentence` / `_redact_line` / `_sentence_spans`.
- **TIER 2** (minimal containing unit): prose is unambiguously PRESENT but did not pin to one span (boundary under-split merged it with a VERIFIED neighbor, OR it straddles >=2 spans). `_redact_minimal_containing_unit` removes the SMALLEST set of consecutive spans (or, only if no within-line span set bounds it, the smallest run of consecutive redactable body lines) whose concatenation contains the stem -- over-redact SAFELY rather than abort.
- **TIER 3** (genuinely absent): prose absent from the rendered report -> `already_absent`, ship nothing extra (SAFE state).

**Boundary hardening:** `_SENTENCE_BOUNDARY_RE` now has 3 alternation arms (ARM 1 terminator->sentence-start char; ARM 2 terminator+marker->digit-start; ARM 3 word-attached marker-as-terminator, no period) so the common under-split shapes resolve at TIER 1. Decimals/abbreviations (`0.90`, `U.S.`, `No. 157`) still never split (ARM 1/2 require inter-sentence whitespace; ARM 2 requires an intervening `[N]` marker).

**Invariants the fix must hold:** (a) NO faithfulness leak -- every non-VERIFIED claim is still removed (now including every occurrence); (b) VERIFIED neighbors keep their `[N]` markers byte-for-byte; (c) minimal over-redaction -- a whole verified section is not nuked for one bad sentence; (d) fail-closed still fires when the prose is genuinely present-but-unbounded.

**Smoke:** the targeted suite passes -- `pytest tests/roles/test_report_redactor_redact001.py tests/polaris_graph/roles/` = 27 passed (18 new redact001 tests + 9 adjacent). Broader run reported tests=488, passed=true.

## VERIFY (your line-by-line checklist -- this is clinical-safety-critical faithfulness)

1. **NO faithfulness leak.** Confirm every non-VERIFIED claim's prose is removed -- TIER 1 clears clean occurrences, TIER 2 clears under-split/straddle occurrences, and the multi-occurrence loop guarantees a SECOND occurrence of the same stem cannot survive (`while _prose_present(...)` re-checks the line-join-normalized whole body after every removal). Check that `_prose_present` is high-recall (it joins redactable body lines so a line-straddling claim is never falsely `already_absent`). Look for any path where a non-VERIFIED claim is recorded as redacted/already_absent while its normalized prose still appears in `result.report_text`.

2. **VERIFIED neighbor `[N]` citations survive byte-for-byte.** TIER 1 `_redact_line` preserves every non-matching span and all inter-sentence whitespace verbatim. TIER 2 `_minimal_consecutive_span_set` chooses the SMALLEST consecutive-span window containing the stem; verify the slice boundaries (`spans[lo][0]` .. `spans[hi][1]`) cannot clip a neighbor's marker, and that the cross-line branch only blanks lines whose join contains the stem. Confirm ARM 3 word-anchoring (`(?<=\w)`) cannot strip a marker off a VERIFIED neighbor.

3. **Fail-closed still fires when prose is genuinely present-but-unbounded.** Confirm the `raise ReportRedactionError` inside the loop fires when `_prose_present` is True but NEITHER tier makes progress (e.g. prose only inside a heading/`[`-prefixed bib line the redactor must not touch -- `_is_redactable_body_line`). Confirm this cannot infinite-loop: each successful removal substitutes `_GAP_REPLACEMENT` (which cannot re-match the stem), so progress is monotonic; no-progress + still-present == immediate abort. Confirm `test_d_genuinely_absent_claim_still_raises` exercises the heading-only present-but-unbounded path and `test_d2_truly_absent_prose_is_already_absent_not_error` exercises the TIER-3 safe path.

4. **Over-redaction minimized.** Confirm a whole VERIFIED section is NOT nuked for one bad sentence: TIER 1 redacts one span; TIER 2 grows the unit by length (smallest first) so the FIRST containing window wins; the cross-line branch is reached ONLY when no within-line span set bounds the stem. Check `_minimal_consecutive_span_set` returns the minimal window and that the coverage floor (`_MIN_REDACTION_COVERAGE = 0.6`) still guards TIER 1 against a short stem redacting a longer VERIFIED sentence (`test_boundary_does_not_split_decimal_or_abbreviation`, `test_p2_inline_citation_verified_sentence_not_over_redacted`).

Additionally scan for: regex catastrophic-backtracking risk in the 3-arm `_SENTENCE_BOUNDARY_RE`; the O(spans^2) / O(lines^2) window walks being unbounded on a large report; any divergence between `_is_redactable_body_line` and the skip set in `_redact_sentence` (must be identical no-touch set); and whether recording-once logic (`redacted_any_for_claim`) is correct when a claim has zero occurrences from the start (TIER-3 already_absent).

## Output schema (REQUIRED -- final line MUST be a `verdict:` line)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

## DIFF -- tracked files (`git --no-pager diff -- src/polaris_graph/roles/report_redactor.py tests/roles/`)

```diff
diff --git a/src/polaris_graph/roles/report_redactor.py b/src/polaris_graph/roles/report_redactor.py
index bc9599df..a27f9c12 100644
--- a/src/polaris_graph/roles/report_redactor.py
+++ b/src/polaris_graph/roles/report_redactor.py
@@ -30,14 +30,34 @@ redaction IS the "one rewrite/refuse-in-place attempt" the D8 policy docstring d
 but the runner never wired.
 
 The mapping is NOT 1:1 with strict_verify-kept (run_honest_sweep_r3.py:5660-5669 in-tree
-caveat: downstream dedup/repair passes mutate the body). Two cases:
-  * The claim's prose IS in the rendered report -> redact it (the leak).
-  * The claim's prose is genuinely ABSENT from the rendered report -> already not
-    shipped; record ``already_absent`` and ship nothing extra (the SAFE state).
-FAIL-CLOSED contract: if a material non-VERIFIED claim's normalized prose IS present in
-the normalized full report but the helper cannot pin a discrete rendered sentence to
-replace, it RAISES ``ReportRedactionError`` so the caller can take the terminal
-``abort_report_redaction_failed`` status rather than ship an unredacted leak.
+caveat: downstream dedup/repair passes mutate the body). THREE TIERS of locating the prose
+(I-redact-001 #1181 — high-recall detection, high-precision action):
+  * TIER 1 (precise, single span): the claim's prose IS one discrete rendered sentence
+    span (coverage >= ``_MIN_REDACTION_COVERAGE``) -> redact exactly that span, leaving
+    every VERIFIED neighbor sentence and its [N] markers byte-for-byte (the leak fix).
+  * TIER 2 (minimal containing unit): the claim's normalized prose is unambiguously
+    PRESENT but it does not cover one span at the coverage floor — because a boundary
+    under-split merged it with a VERIFIED neighbor, OR it straddles >=2 rendered spans.
+    Redact the SMALLEST set of consecutive spans (or, only if no span set bounds it, the
+    body line) whose concatenation contains the stem — over-redact SAFELY rather than
+    abort (issue acceptance 1+2). The cross-line projection makes table/line-join
+    rendering visible so this is never a silent ``already_absent``.
+  * TIER 3 (genuinely absent): the claim's prose is genuinely ABSENT from the rendered
+    report (downstream dedup/repair removed it) -> already not shipped; record
+    ``already_absent`` and ship nothing extra (the SAFE state).
+FAIL-CLOSED contract (I-redact-001 #1181): the helper RAISES ``ReportRedactionError`` ONLY
+when a material non-VERIFIED claim's normalized prose is genuinely ABSENT from the normalized
+report yet a real inconsistency demands a fail-closed abort — i.e. neither TIER-1 nor TIER-2
+can bound the prose AND the prose is not cleanly absent. A merely hard-to-pin-to-one-sentence
+claim is redacted via TIER 2, NOT aborted. The boundary hardening (``_SENTENCE_BOUNDARY_RE``,
+I-redact-001) splits ``...risk[1] Cereal...`` / ``...adherence.[16] 87.3%...`` so the common
+case resolves at TIER 1; TIER 2 is the defense-in-depth for any future under-split shape.
+
+MULTI-OCCURRENCE (I-redact-001 #1181, Codex iter-1 P1-1): the same non-VERIFIED stem can appear
+more than once (e.g. once cleanly + once in an under-split merge). The tiered redaction LOOPS
+per claim until the stem is absent from the line-join-normalized whole body (no occurrence left)
+or no tier makes further progress (fail-closed) — so a second occurrence can never leak. The
+claim is recorded in ``redacted`` exactly ONCE regardless of how many physical spans were removed.
 
 Pure function (string ops only; no network, no I/O). The CALLER reads/writes report.md.
 """
@@ -197,8 +217,52 @@ def reconcile_report_against_verdicts(
                 "cannot reconcile (fail-closed)."
             )
 
-        removed, working = _redact_sentence(working, stem_norm)
-        if removed:
+        # MULTI-OCCURRENCE LOOP (I-redact-001 #1181, Codex iter-1 P1-1): a non-VERIFIED stem can
+        # appear MORE THAN ONCE in the body — e.g. once cleanly (TIER 1 catches it) and once in a
+        # boundary-under-split span (only TIER 2 catches it). The prior single-pass logic marked
+        # the claim handled after the FIRST successful removal and `continue`d, leaving the second
+        # occurrence in result.report_text — a leak. We now loop the tiered redaction until the
+        # stem is ABSENT from the line-join-normalized whole-body projection (no occurrence left)
+        # OR no tier can make further progress (-> fail-closed). The loop terminates because each
+        # successful removal replaces the matched prose with ``_GAP_REPLACEMENT`` (which cannot
+        # re-match the stem), so occurrences are consumed monotonically.
+        redacted_any_for_claim = False
+        while _prose_present(working, stem_norm):
+            # TIER 1 — precise single-span redaction (coverage floor protects VERIFIED neighbors).
+            # One pass clears EVERY clean (pin-at-floor) occurrence across all lines at once.
+            removed, working = _redact_sentence(working, stem_norm)
+            if removed:
+                redacted_any_for_claim = True
+                continue
+
+            # TIER 1 made no progress this pass, but the prose IS still present (line-join
+            # projection): it did not pin to one span at the coverage floor (a boundary
+            # under-split merged it with a VERIFIED neighbor, OR it straddles spans). TIER 2 —
+            # redact the minimal CONTAINING unit, over-redacting SAFELY rather than aborting a
+            # present-but-hard-to-pin claim (#1181). TIER 2 removes ONE under-split unit per pass;
+            # the loop re-checks presence and keeps going for any further occurrence.
+            removed, working = _redact_minimal_containing_unit(working, stem_norm)
+            if removed:
+                redacted_any_for_claim = True
+                continue
+
+            # FAIL-CLOSED: the prose registers as present in the line-join projection (e.g. it
+            # spans a heading/bibliography line the redactor must not touch, or its alignment is
+            # unbounded across non-adjacent units) but NEITHER tier could bound it to a redactable
+            # unit without nuking a forbidden line. A real inconsistency — refuse to ship a partial
+            # report (#1174). Raising here (not after the loop) means we never spin: no progress +
+            # still present == abort.
+            raise ReportRedactionError(
+                f"claim {claim_id} ({verdict}/{severity}) prose is present in report.md "
+                "but could not be bounded to any redactable unit (span set or body line); "
+                "refusing to ship a partially-reconciled report (fail-closed). "
+                f"prose_stem={stem_norm[:120]!r}"
+            )
+
+        # Record the claim ONCE after the loop (Codex iter-1 P1-1: appending per removal would
+        # double-count a claim that occurred twice and inflate redacted_count). If the loop body
+        # never ran, the prose was genuinely ABSENT from the start — the SAFE state (TIER 3).
+        if redacted_any_for_claim:
             result.redacted.append(
                 RedactedClaim(
                     claim_id=claim_id,
@@ -207,17 +271,8 @@ def reconcile_report_against_verdicts(
                     claim_text=sentence,
                 )
             )
-            continue
-
-        # Not redacted: either genuinely absent (SAFE) or present-but-unlocatable (FAIL).
-        if stem_norm in _normalize(working):
-            raise ReportRedactionError(
-                f"claim {claim_id} ({verdict}/{severity}) prose is present in report.md "
-                "but could not be pinned to a discrete rendered sentence for redaction; "
-                "refusing to ship a partially-reconciled report (fail-closed). "
-                f"prose_stem={stem_norm[:120]!r}"
-            )
-        result.already_absent.append(claim_id)
+        else:
+            result.already_absent.append(claim_id)  # TIER 3 — genuinely absent, ship nothing
 
     result.report_text = working
     return result
@@ -261,9 +316,38 @@ def _redact_sentence(report_text: str, stem_norm: str) -> tuple[bool, str]:
 # "...crashes.[8]" immediately before the UNSUPPORTED 05-001 sentence — the [8] belongs to
 # 05-000 and must survive redaction of 05-001.
 #
-# A decimal like "0.457" or "No. 157" is never a boundary: the lookahead demands whitespace +
-# a sentence-start char (uppercase/quote/open-paren/hash), never a digit.
-_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?:\s*\[\d+\])*\s+(?=[A-Z\"'(#])")
+# I-redact-001 #1181 — three ALTERNATION ARMS so a real boundary is not under-split (the
+# under-split merged a non-VERIFIED sentence with a VERIFIED neighbor into one over-long span,
+# dropping coverage below the floor and forcing a whole-report abort). Each arm still demands
+# inter-sentence whitespace + a sentence-start, so decimals/abbreviations never become a split:
+#   ARM 1 (terminator, sentence-start char): "...crashes.[8] The..." — the original behavior.
+#   ARM 2 (terminator + >=1 marker, digit-start next): "...adherence.[16] 87.3% of..." — the
+#          next sentence begins with a digit (defeating ARM 1's [A-Z"'(#] lookahead). REQUIRES
+#          at least one [N] marker between the period and the digit, so a bare decimal
+#          "0.90 (0.83 to 0.97) was found." (period, space, digit, NO marker) never matches.
+#   ARM 3 (>=1 marker as terminator, NO preceding period): "...risk[1] Cereal...",
+#          "...recovery[17][22] Legal..." — the renderer emitted the citation marker(s) with no
+#          terminal period before them; the marker(s) ARE the boundary. The marker stays with
+#          the LEFT (cited) sentence (it is m.start()-anchored, then rstrip-included in the span),
+#          so a VERIFIED neighbor keeps its [N] byte-for-byte (the Codex iter-1 P1 invariant).
+#          Codex iter-1 P2: ARM 3 is WORD-ANCHORED — the marker run must immediately follow a
+#          word character ``(?<=\w)`` (NO whitespace between the sentence-final word and its
+#          marker), so it fires only on a plausible sentence end where the renderer dropped the
+#          terminal period ("risk[1]", "recovery[17][22]"). A MID-sentence inline citation —
+#          "...as shown [5] In vivo..." or "the [5] Group reported..." — has WHITESPACE before
+#          the bracket, so ``(?<=\w)`` rejects it and the inline-cited sentence stays intact (no
+#          false split -> no over-redaction of a VERIFIED sentence). This only ever causes an
+#          UNDER-split, which TIER 2 then bounds safely; it can never over-split a survivor.
+# A decimal like "0.457" or "No. 157" or "U.S." is never a boundary: ARM 1/2 require whitespace
+# before the next char and ARM 2 requires an intervening [N] marker; "U.S. products" splits only
+# if "products" were uppercase (it is not), and "No. 157" has no marker so ARM 2 cannot fire.
+_SENTENCE_BOUNDARY_RE = re.compile(
+    r"(?:"
+    r"[.!?](?:\s*\[\d+\])*\s+(?=[A-Z\"'(#])"   # ARM 1: terminator -> sentence-start char
+    r"|[.!?](?:\s*\[\d+\])+\s+(?=\d)"           # ARM 2: terminator + marker -> digit-start
+    r"|(?<=\w)(?:\[\d+\])+\s+(?=[A-Z\"'(#0-9])"  # ARM 3: WORD-ATTACHED marker-as-terminator, no period
+    r")"
+)
 
 # The claim stem must cover at least this fraction of a rendered sentence to redact it. Guards
 # against a short non-VERIFIED claim whose normalized prose is a substring of a LONGER VERIFIED
@@ -323,3 +407,104 @@ def _redact_line(line: str, stem_norm: str) -> tuple[str, bool]:
         cursor = end
     out.append(line[cursor:])
     return "".join(out), hit
+
+
+def _is_redactable_body_line(line: str) -> bool:
+    """A body line the redactor is allowed to rewrite: NOT a heading (#…), a bibliography /
+    already-gap row ([…), or blank. Mirrors the skip in ``_redact_sentence`` so TIER-2 honors
+    the exact same no-touch set (a claim that exists ONLY inside a heading stays a fail-closed
+    inconsistency, not a TIER-2 redaction — preserving the present-but-unlocatable contract).
+    """
+    stripped = line.lstrip()
+    return bool(stripped) and not stripped.startswith("#") and not stripped.startswith("[")
+
+
+def _prose_present(report_text: str, stem_norm: str) -> bool:
+    """High-RECALL presence detector over a LINE-JOIN-NORMALIZED projection of the whole body
+    (research practice: cross-line / table rendering is a blind spot — never silently treat a
+    line-straddling claim as already-absent). Returns True iff the claim stem is normalized-
+    present either within one body line OR across the join of consecutive redactable body lines.
+
+    Recall here only guards against a FALSE ``already_absent`` (a leak); the high-PRECISION
+    decision of WHICH unit to remove stays in ``_redact_minimal_containing_unit`` (exact
+    normalized containment + the coverage floor), so this projection never itself redacts.
+    """
+    if stem_norm in _normalize(report_text):
+        return True
+    # Cross-line projection: join only the redactable body lines (skip headings / bib / blanks),
+    # normalized, and look for the stem straddling a soft line break.
+    body = " ".join(
+        line for line in report_text.split("\n") if _is_redactable_body_line(line)
+    )
+    return stem_norm in _normalize(body)
+
+
+def _redact_minimal_containing_unit(report_text: str, stem_norm: str) -> tuple[bool, str]:
+    """TIER-2 fallback (#1181): the stem is present but did NOT pin to one span at the coverage
+    floor. Remove the SMALLEST containing unit, over-redacting SAFELY rather than aborting:
+
+      1. Within a single redactable body line, find the smallest set of CONSECUTIVE spans whose
+         concatenation (normalized) contains the stem, and replace exactly that span set with one
+         gap sentence — preserving every OTHER span (and its [N] markers) and all inter-span
+         whitespace byte-for-byte. This handles both the boundary-under-split residue and a TRUE
+         multi-span straddle (issue acceptance 1+2) with the same walk.
+      2. If no within-line consecutive-span set bounds the stem (it straddles a soft line break),
+         replace the smallest run of consecutive redactable body lines whose join contains the
+         stem with one gap line — the coarsest safe unit.
+
+    Returns (redacted_any, new_text). Returns (False, unchanged) iff the stem cannot be bounded
+    by any redactable unit (the caller then fails closed). NEVER touches a heading/bib line.
+    """
+    lines = report_text.split("\n")
+
+    # ---- 1) within-line minimal consecutive-span set -------------------------------------
+    for idx, line in enumerate(lines):
+        if not _is_redactable_body_line(line):
+            continue
+        if stem_norm not in _normalize(line):
+            continue
+        spans = _sentence_spans(line)
+        span_set = _minimal_consecutive_span_set(line, spans, stem_norm)
+        if span_set is not None:
+            lo, hi = span_set  # inclusive span indices
+            start = spans[lo][0]
+            end = spans[hi][1]
+            new_line = line[:start] + _GAP_REPLACEMENT + line[end:]
+            lines[idx] = new_line
+            return True, "\n".join(lines)
+
+    # ---- 2) cross-line: smallest consecutive redactable-body-line run --------------------
+    redactable_idx = [i for i, ln in enumerate(lines) if _is_redactable_body_line(lines[i])]
+    for span_len in range(1, len(redactable_idx) + 1):
+        for offset in range(0, len(redactable_idx) - span_len + 1):
+            window = redactable_idx[offset : offset + span_len]
+            # The window must be CONTIGUOUS in the body-line sequence to be one rendered unit.
+            if window[-1] - window[0] != span_len - 1:
+                continue
+            joined = " ".join(lines[i] for i in window)
+            if stem_norm in _normalize(joined):
+                first = window[0]
+                # Replace the first line of the run with the gap; blank the remaining lines so the
+                # leak prose is fully removed while preserving the line count (no structural churn).
+                lines[first] = _GAP_REPLACEMENT
+                for i in window[1:]:
+                    lines[i] = ""
+                return True, "\n".join(lines)
+
+    return False, report_text
+
+
+def _minimal_consecutive_span_set(
+    line: str, spans: list[tuple[int, int]], stem_norm: str
+) -> tuple[int, int] | None:
+    """Smallest (lo, hi) inclusive index window over ``spans`` whose concatenated source text is
+    normalized-containing ``stem_norm``. Grows the window by length so the FIRST hit is minimal;
+    prefers the smallest unit (precision: do not nuke a section when a span-pair suffices)."""
+    n = len(spans)
+    for window in range(1, n + 1):
+        for lo in range(0, n - window + 1):
+            hi = lo + window - 1
+            seg = line[spans[lo][0] : spans[hi][1]]
+            if stem_norm in _normalize(seg):
+                return (lo, hi)
+    return None
```

## DIFF -- new untracked test + package-init files (`git --no-pager diff --no-index /dev/null <file>`)

```diff
warning: in the working copy of 'tests/roles/test_report_redactor_redact001.py', LF will be replaced by CRLF the next time Git touches it
diff --git a/tests/roles/test_report_redactor_redact001.py b/tests/roles/test_report_redactor_redact001.py
new file mode 100644
index 00000000..4229e889
--- /dev/null
+++ b/tests/roles/test_report_redactor_redact001.py
@@ -0,0 +1,381 @@
+"""I-redact-001 (#1181) — report_redactor must REDACT a present-but-hard-to-pin
+UNSUPPORTED claim, not abort the whole report.
+
+Regression context
+------------------
+F01 (#1174) made redaction severity-INDEPENDENT (every non-VERIFIED claim, incl. S3
+observe-only, must be redacted). That exposed a pre-existing weakness: when the renderer
+under-split two real sentences into one over-long span (no terminal period before a [N]
+marker, or a next sentence beginning with a digit), the rejected claim's stem covered
+< ``_MIN_REDACTION_COVERAGE`` of that merged span, so no single span matched, the stem was
+"present but unpinnable", and ``reconcile_report_against_verdicts`` raised
+``ReportRedactionError`` -> ``abort_report_redaction_failed`` for the WHOLE run. All 5
+beat-both questions aborted with zero reports shipped.
+
+This module loads the 3 REAL failing cases (drb_76 / drb_78 / drb_90) from
+``outputs/audits/I-redact-001/redaction_fixture.json`` and asserts each now redacts +
+SHIPS (no ``ReportRedactionError``) while the unsupported prose is gone and the VERIFIED
+neighbor sentence keeps its [N] markers byte-for-byte. It then pins the issue acceptance
+matrix with SYNTHETIC invariant tests:
+  (a) sub-clause-in-longer-sentence redacts;
+  (b) a claim spanning 2 rendered sentences redacts both;
+  (c) a VERIFIED neighbor keeps its [N] citation byte-for-byte;
+  (d) a genuinely-ABSENT claim STILL raises ``ReportRedactionError`` (the real-inconsistency
+      fail-closed path is preserved).
+"""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+import pytest
+
+from src.polaris_graph.roles.report_redactor import (
+    ReportRedactionError,
+    reconcile_report_against_verdicts,
+)
+from src.polaris_graph.roles import report_redactor as _redactor
+
+# The 3 REAL failing cases captured offline from the beat-both re-run @454b7652 on the VM.
+# Codex iter-1 P1-2: the fixture lives under tests/fixtures/ (LAW VI: test fixtures live in
+# tests/fixtures/) so a clean CI checkout always has it — the prior outputs/audits/ path is
+# gitignored and untracked, so parametrize collection (which reads the fixture at COLLECT time)
+# failed on CI and took down the whole module. parents[1] of tests/roles/<file> == tests/.
+# A copy is retained under outputs/audits/I-redact-001/ for the audit trail; the TEST reads
+# tests/fixtures/.
+_FIXTURE = (
+    Path(__file__).resolve().parents[1]
+    / "fixtures"
+    / "redaction_fixture_redact001.json"
+)
+
+
+def _load_cases() -> list[dict]:
+    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
+    cases = data["cases"]
+    assert len(cases) == 3, "fixture must carry exactly the 3 real failing cases"
+    return cases
+
+
+def _normalized(text: str) -> str:
+    """Test-side normalize matching the module's matching projection (citation/whitespace-
+    insensitive, trailing-period-stripped) so 'prose gone' is asserted in the same space the
+    redactor matches in."""
+    return _redactor._normalize(text)
+
+
+# ─────────────────────────────────────────────────────────────────
+# RED -> GREEN on the 3 REAL cases: each must now redact + ship (no abort).
+# ─────────────────────────────────────────────────────────────────
+
+@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["case_id"])
+def test_real_case_redacts_and_ships(case: dict):
+    """The real failing claim is redacted, its prose is gone from the shipped report, and
+    reconcile does NOT raise (status != abort_report_redaction_failed)."""
+    res = reconcile_report_against_verdicts(
+        case["report_text"], case["final_verdicts"], case["audit_map"]
+    )
+    target_id = case["target_claim_id"]
+    redacted_ids = {rc.claim_id for rc in res.redacted}
+    assert target_id in redacted_ids, f"{case['case_id']}: target {target_id} not redacted"
+    # The rejected prose must be GONE from the shipped body (no leak).
+    assert case["target_stem_normalized"] not in _normalized(res.report_text), (
+        f"{case['case_id']}: UNSUPPORTED stem still present after redaction (leak)"
+    )
+    # The gap language was inserted (refuse-in-place, not a silent drop).
+    assert _redactor._GAP_REPLACEMENT in res.report_text
+
+
+@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["case_id"])
+def test_real_case_verified_neighbor_survives_byte_for_byte(case: dict):
+    """The VERIFIED neighbor merged into the same under-split span keeps its rendered prose
+    AND its [N] citation markers byte-for-byte (Codex iter-1 P1: never strip a survivor's
+    citation). The neighbor lead text is asserted present unchanged."""
+    res = reconcile_report_against_verdicts(
+        case["report_text"], case["final_verdicts"], case["audit_map"]
+    )
+    # The neighbor's first words (a distinctive, citation-free lead) must survive verbatim.
+    neighbor_lead = " ".join(case["neighbor_sentence"].split()[:8])
+    assert neighbor_lead in res.report_text, (
+        f"{case['case_id']}: VERIFIED neighbor lead {neighbor_lead!r} was over-redacted"
+    )
+    # The neighbor is still a VERIFIED verdict in the fixture (sanity on the fixture itself).
+    assert case["final_verdicts"][case["neighbor_claim_id"]] == "VERIFIED"
+
+
+def test_real_cases_preserve_neighbor_citation_markers():
+    """Per-case byte-for-byte [N] survival of the VERIFIED neighbor's own citation markers."""
+    # The neighbor's trailing rendered marker(s) per real case (the [N] that cite the survivor).
+    neighbor_markers = {
+        "drb_76": ["risk[1]"],            # 04-003 survivor ends "...risk[1]"
+        "drb_78": ["days.[10]"],          # 05-007 survivor ends "...4.3 days.[10]"
+        "drb_90": ["recovery[17][22]"],   # 07-001 survivor ends "...recovery[17][22]"
+    }
+    for case in _load_cases():
+        res = reconcile_report_against_verdicts(
+            case["report_text"], case["final_verdicts"], case["audit_map"]
+        )
+        for marker in neighbor_markers[case["case_id"]]:
+            assert marker in case["report_text"], (
+                f"fixture sanity: {marker!r} should be in the pre-redaction {case['case_id']}"
+            )
+            assert marker in res.report_text, (
+                f"{case['case_id']}: VERIFIED neighbor marker {marker!r} dropped on redaction"
+            )
+
+
+# ─────────────────────────────────────────────────────────────────
+# SYNTHETIC invariant tests (issue acceptance a-d).
+# ─────────────────────────────────────────────────────────────────
+
+def test_a_subclause_in_longer_sentence_redacts():
+    """(a) A non-VERIFIED claim whose stored sentence is a SUB-CLAUSE of a longer rendered
+    sentence (boundary under-split: no terminal period before the [N] marker) is redacted —
+    not aborted — and the VERIFIED neighbor clause keeps its [N]."""
+    # The renderer merged a VERIFIED neighbor and the UNSUPPORTED claim into one span because
+    # the first sentence ended "...risk[1]" with no period before the marker (subtype A).
+    report = (
+        "A meta-analysis examined fiber and colorectal cancer risk[1] "
+        "Cereal fiber yielded an RR of 0.90 based on eight studies.[1]\n"
+    )
+    audit = {
+        "claim-bad": {
+            "sentence": "Cereal fiber yielded an RR of 0.90 based on eight studies [#ev:e:0-9].",
+            "severity": "S1",
+        },
+        "claim-good": {
+            "sentence": "A meta-analysis examined fiber and colorectal cancer risk [#ev:e:0-9].",
+            "severity": "S1",
+        },
+    }
+    fv = {"claim-bad": "UNSUPPORTED", "claim-good": "VERIFIED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    assert "Cereal fiber yielded an RR of 0.90" not in res.report_text  # claim gone
+    assert "A meta-analysis examined fiber and colorectal cancer risk[1]" in res.report_text
+    assert "claim-bad" in {rc.claim_id for rc in res.redacted}
+
+
+def test_b_claim_spanning_two_rendered_sentences_redacts_both():
+    """(b) A claim whose stored sentence straddles TWO rendered sentence spans (the renderer
+    split one stored claim across a '.' boundary) redacts BOTH spans (the minimal consecutive-
+    span set), while a VERIFIED sentence on the same line is preserved with its marker."""
+    # Stored claim text spans two rendered sentences: "...first half. And the second half...".
+    report = (
+        "Verified opening fact about the dataset.[9] "
+        "The intervention reduced events by forty percent. And it did so without "
+        "any increase in adverse outcomes.[3]\n"
+    )
+    audit = {
+        "straddle": {
+            "sentence": (
+                "The intervention reduced events by forty percent. And it did so without "
+                "any increase in adverse outcomes [#ev:e:0-9]."
+            ),
+            "severity": "S1",
+        },
+        "kept": {
+            "sentence": "Verified opening fact about the dataset [#ev:e:0-9].",
+            "severity": "S1",
+        },
+    }
+    fv = {"straddle": "UNSUPPORTED", "kept": "VERIFIED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    # BOTH halves of the straddling claim are gone.
+    assert "reduced events by forty percent" not in res.report_text
+    assert "without any increase in adverse outcomes" not in res.report_text
+    # The VERIFIED neighbor and its [9] marker survive byte-for-byte.
+    assert "Verified opening fact about the dataset.[9]" in res.report_text
+    assert "straddle" in {rc.claim_id for rc in res.redacted}
+
+
+def test_c_verified_neighbor_keeps_its_citation():
+    """(c) Redacting an UNSUPPORTED middle sentence consumes only ITS OWN marker; the [8] and
+    [7] of the VERIFIED sentences on either side survive byte-for-byte."""
+    report = "Alpha verified one.[8] Bravo bad claim sentence here.[4] Charlie verified two.[7]\n"
+    audit = {"bravo": {"sentence": "Bravo bad claim sentence here [#ev:e:0-9].", "severity": "S1"}}
+    fv = {"bravo": "UNSUPPORTED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    assert "Alpha verified one.[8]" in res.report_text
+    assert "Charlie verified two.[7]" in res.report_text
+    assert "Bravo bad claim sentence here" not in res.report_text
+    assert "[4]" not in res.report_text  # the redacted claim's own marker leaves with it
+    assert "bravo" in {rc.claim_id for rc in res.redacted}
+
+
+def test_d_genuinely_absent_claim_still_raises():
+    """(d) FAIL-CLOSED preserved: when a non-VERIFIED claim's prose is GENUINELY present only
+    inside a heading the redactor must not touch (so it cannot be bounded to any redactable
+    unit), reconcile STILL raises ReportRedactionError — a real inconsistency, not a hard-to-pin
+    one — so the caller takes abort_report_redaction_failed rather than ship an unredacted leak.
+    """
+    report = "# Heading mentioning the secret penalty figure inline\n\nBody line unrelated.\n"
+    audit = {
+        "absent-in-body": {
+            "sentence": "the secret penalty figure [#ev:x:0-10].",
+            "severity": "S2",
+        }
+    }
+    fv = {"absent-in-body": "UNSUPPORTED"}
+    with pytest.raises(ReportRedactionError):
+        reconcile_report_against_verdicts(report, fv, audit)
+
+
+def test_d2_truly_absent_prose_is_already_absent_not_error():
+    """(d, SAFE side) When the prose is GENUINELY absent from the rendered body (downstream
+    dedup removed it), it is recorded as already_absent and does NOT raise — only a prose that
+    is PRESENT-but-unbounded raises."""
+    report = "An entirely unrelated verified body sentence about something else.[2]\n"
+    audit = {"gone": {"sentence": "A claim about a topic not in the report [#ev:e:0-9].", "severity": "S2"}}
+    fv = {"gone": "UNSUPPORTED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    assert "gone" in res.already_absent
+    assert res.redacted == []
+    assert res.report_text == report  # byte-identical: nothing redacted
+
+
+# ─────────────────────────────────────────────────────────────────
+# BOUNDARY-REGEX safety: the hardened _SENTENCE_BOUNDARY_RE must NOT introduce false splits
+# on decimals / abbreviations (decimal/multilingual-safe invariant).
+# ─────────────────────────────────────────────────────────────────
+
+def test_boundary_does_not_split_decimal_or_abbreviation():
+    """A short UNSUPPORTED claim sharing words with a LONGER VERIFIED sentence that contains
+    decimals ('0.90'), an abbreviation ('U.S.', 'No. 157') must not over-redact the survivor —
+    the hardened boundary still treats those as intra-sentence, so the coverage floor protects
+    the longer VERIFIED sentence."""
+    report = (
+        "Recall is high.[1] "
+        "Under U.S. rule No. 157 the model achieves recall of 0.90 across every benchmark.[2]\n"
+    )
+    audit = {"short": {"sentence": "Recall is high [#ev:e:0-9].", "severity": "S2"}}
+    fv = {"short": "UNSUPPORTED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    assert "Recall is high.[1]" not in res.report_text  # own sentence redacted
+    # The longer VERIFIED sentence with decimal + abbreviations survives untouched, with [2].
+    assert "Under U.S. rule No. 157 the model achieves recall of 0.90 across every benchmark.[2]" in res.report_text
+
+
+def test_digit_start_boundary_splits_for_redaction():
+    """Subtype B (drb_78 shape): a real boundary '...adherence.[16] 87.3% of...' where the next
+    sentence starts with a digit is now split, so the UNSUPPORTED first sentence redacts alone
+    and the VERIFIED digit-led neighbor keeps its marker."""
+    report = (
+        "However the wearable evidence shows poor long-term adherence.[16] "
+        "87.3% of patients used rechargeable devices over the study.[10]\n"
+    )
+    audit = {
+        "bad": {
+            "sentence": "However the wearable evidence shows poor long-term adherence [#ev:e:0-9].",
+            "severity": "S3",
+        },
+        "good": {
+            "sentence": "87.3% of patients used rechargeable devices over the study [#ev:e:0-9].",
+            "severity": "S3",
+        },
+    }
+    fv = {"bad": "UNSUPPORTED", "good": "VERIFIED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    assert "However the wearable evidence shows poor long-term adherence" not in res.report_text
+    assert "87.3% of patients used rechargeable devices over the study.[10]" in res.report_text
+    assert "bad" in {rc.claim_id for rc in res.redacted}
+
+
+# ─────────────────────────────────────────────────────────────────
+# Codex iter-1 P1-1 — MULTI-OCCURRENCE LEAK: a non-VERIFIED stem appearing twice (once clean,
+# once under-split) must have BOTH occurrences removed, recorded ONCE in result.redacted.
+# ─────────────────────────────────────────────────────────────────
+
+def test_p1_1_multi_occurrence_both_removed_once_recorded():
+    """The same UNSUPPORTED stem appears TWICE: once as a clean discrete sentence (TIER 1) and
+    once inside a boundary-under-split merge with a VERIFIED neighbor (TIER 2 — no terminal
+    period before the marker). The prior single-pass logic stopped after the first removal and
+    left the second occurrence in the body (a leak). Both must now be gone, the claim recorded
+    exactly once, and the VERIFIED neighbor's [N] preserved byte-for-byte."""
+    stem_prose = "The device cut events by exactly forty two percent"
+    # Occurrence 1 (line 1): a clean discrete rendered sentence — pins at TIER 1 (coverage >= floor).
+    # Occurrence 2 (line 2): UNDER-SPLIT — the VERIFIED neighbor ends "...registry[7]" with NO
+    # period before the marker. ARM 3 splits there, but the RIGHT span is long (the claim plus a
+    # trailing verified-looking clause), so the stem covers < _MIN_REDACTION_COVERAGE of it and
+    # TIER 1 misses it; only TIER 2 (minimal containing unit) catches this occurrence. This is
+    # exactly the clean+under-split pair the P1-1 loop must clear (the prior single-pass logic
+    # stopped after the line-1 removal and left line 2 in the body — a leak).
+    report = (
+        f"{stem_prose}.[3] An unrelated verified closing sentence here.[5]\n"
+        f"The data came from a national registry[7] {stem_prose} and did so without raising "
+        f"any adverse outcome at all over the multi year follow up window.[3]\n"
+    )
+    audit = {
+        "dup": {"sentence": f"{stem_prose} [#ev:e:0-9].", "severity": "S1"},
+        "reg": {"sentence": "The data came from a national registry [#ev:e:0-9].", "severity": "S1"},
+    }
+    fv = {"dup": "UNSUPPORTED", "reg": "VERIFIED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    # BOTH occurrences of the rejected prose are gone (no leak).
+    assert stem_prose not in res.report_text
+    assert _normalized(stem_prose) not in _normalized(res.report_text)
+    # The claim is recorded exactly ONCE despite two physical removals (no double-count).
+    assert [rc.claim_id for rc in res.redacted].count("dup") == 1
+    # The VERIFIED neighbor on line 2 keeps its prose and its [7] marker byte-for-byte.
+    assert "The data came from a national registry[7]" in res.report_text
+    # The VERIFIED closing sentence on line 1 survives with its [5] marker byte-for-byte.
+    assert "An unrelated verified closing sentence here.[5]" in res.report_text
+
+
+def test_p1_1_multi_occurrence_both_clean_both_removed():
+    """Two CLEAN occurrences of the same UNSUPPORTED stem on different lines are BOTH removed in
+    one TIER-1 pass and the claim is recorded once."""
+    stem_prose = "Mortality fell by thirteen percent under the protocol"
+    report = (
+        f"{stem_prose}.[2] Verified tail one.[9]\n"
+        f"Verified head two.[4] {stem_prose}.[2]\n"
+    )
+    audit = {"m": {"sentence": f"{stem_prose} [#ev:e:0-9].", "severity": "S2"}}
+    fv = {"m": "UNSUPPORTED"}
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    assert stem_prose not in res.report_text
+    assert [rc.claim_id for rc in res.redacted].count("m") == 1
+    assert "Verified tail one.[9]" in res.report_text
+    assert "Verified head two.[4]" in res.report_text
+
+
+# ─────────────────────────────────────────────────────────────────
+# Codex iter-1 P2 — ARM-3 OVER-SPLIT: a MID-sentence inline citation (whitespace before the
+# bracket) must NOT be treated as a sentence boundary, so the verified sentence stays intact and
+# the coverage floor protects it from over-redaction.
+# ─────────────────────────────────────────────────────────────────
+
+def test_p2_inline_midsentence_citation_not_split():
+    """Unit pin on `_sentence_spans`: an inline mid-sentence citation '...as shown [5] In vivo...'
+    (WHITESPACE before the bracket) is NOT a boundary — the word-anchored ARM 3 ``(?<=\\w)`` only
+    fires on a word-attached marker like 'risk[1]'. The sentence stays ONE span; a real
+    word-attached marker-as-terminator still splits."""
+    # Inline citation mid-sentence: must remain ONE span (no false split).
+    one = "The effect was robust as shown [5] In vivo assays confirmed the same trend.[2]"
+    assert len(_redactor._sentence_spans(one)) == 1
+    # Word-attached marker-as-terminator (real boundary, no preceding period): still TWO spans.
+    two = "linked to higher colorectal cancer risk[1] Cereal fiber yielded an RR of 0.90.[1]"
+    assert len(_redactor._sentence_spans(two)) == 2
+
+
+def test_p2_inline_citation_verified_sentence_not_over_redacted():
+    """End-to-end: a VERIFIED sentence with an INLINE mid-sentence citation followed by an
+    UPPERCASE continuation ('as shown [5] Across …') is the exact shape that the un-hardened
+    ARM 3 would FALSE-split (marker-run + whitespace + uppercase). Splitting it into two short
+    spans drops each below the coverage floor and risks over-redaction. With the word-anchored
+    ARM 3 the sentence stays ONE span and survives byte-for-byte (inline [5] + trailing [2]),
+    while a co-located UNSUPPORTED short claim still redacts cleanly."""
+    report = (
+        "Recall was strong.[1] "
+        "The effect was robust as shown [5] Across every clinical subgroup the model held.[2]\n"
+    )
+    audit = {"short": {"sentence": "Recall was strong [#ev:e:0-9].", "severity": "S2"}}
+    fv = {"short": "UNSUPPORTED"}
+    # Sanity: the verified sentence is a SINGLE span (no false split on the inline citation).
+    verified = "The effect was robust as shown [5] Across every clinical subgroup the model held.[2]"
+    assert len(_redactor._sentence_spans(verified)) == 1
+    res = reconcile_report_against_verdicts(report, fv, audit)
+    # The UNSUPPORTED short sentence (and only it) is redacted.
+    assert "Recall was strong.[1]" not in res.report_text
+    # The longer VERIFIED sentence with the inline citation survives untouched, markers intact.
+    assert verified in res.report_text
diff --git a/tests/polaris_graph/roles/__init__.py b/tests/polaris_graph/roles/__init__.py
new file mode 100644
index 00000000..e69de29b
```
