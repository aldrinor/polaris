# I-complete-003 (#1189) — PROVENANCE RE-ANCHOR (diff gate) — FAITHFULNESS-CRITICAL

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (return EXACTLY this, final line MUST be a `verdict:` line)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this change does (summary)

When a findings sentence FAILS `verify_sentence_provenance` on its CURRENTLY-cited span,
the new re-anchor (in `strict_verify`, BEFORE the existing drop) recovers citation-precision
+ uncited-grounded drops by RE-BINDING the sentence's `[#ev:...]` token ONLY to a span that
PASSES the full existing overlap + numeric + trial-name + NLI-entailment gate. It introduces
NO relaxed/alternate acceptance path. The acceptance test is the SAME single function
`verify_sentence_provenance` (reused, not re-implemented). If no candidate passes, the sentence
is still DROPPED (unchanged behaviour). The whole feature is env-gated by `PG_PROVENANCE_REANCHOR`
(default OFF -> byte-identical) AND additionally requires entailment `enforce` to accept.

Smoke (network-free, deterministic fake judge; 6/6 pass):
- pass=true; recover=true (wrong cited span -> re-anchored to the supporting span in the SAME row, kept);
- drops_when_no_support=true (number absent from every span -> still dropped, no fabrication);
- flagoff=true (PG_PROVENANCE_REANCHOR unset -> no re-anchor, no judge call, no counter mutation, sentence dropped exactly as before);
- laundering-guard=true (flag ON but entailment OFF + coincidental mechanical match -> STILL dropped, judge never called);
- nli-fail-open-guard=true (flag ON + enforce + a judge that returns the `judge_error:` fail-open sentinel on every call -> the L1865-1872 enforce fail-closed fires on each re-bound candidate, so NO candidate is recovered; the 40-window search does NOT amplify the fail-open; sentence stays dropped).

Existing regression: `test_m43_anchor_cap.py` + `test_b3_no_verified_sections.py` = 12 passed with the
flag BOTH unset AND =1 (no behavioral change off OR on for the existing anchor/no-verified-sections paths).

## CLAIMS LEDGER (drop site, verify fns, row model, insertion plan)

# I-complete-003 (#1189) — provenance re-anchor CLAIMS LEDGER

Source file: `src/polaris_graph/generator/provenance_generator.py` (1968 lines, read in full).

## (1) drop_site
- The per-sentence DROP happens in `strict_verify` at **L1841-1850** (findings loop): `verify_sentence_provenance(...)` returns `v`; `if v.is_verified: kept.append(v) else: dropped.append(v)` — L1847-1850. This is the OUTER drop.
- The DROP DECISION (is_verified True/False) is computed INSIDE `verify_sentence_provenance` at **L1647** `is_verified = len(failures) == 0`, returned L1648-1655.
- Real re-anchor insertion point is BEFORE that verdict crystallizes: the numeric/content/trial/entailment checks append to `failures` across **L1300-1616**. The cited-span failure modes a re-anchor must rescue are:
  - `number_not_in_any_cited_span` (L1334), `no_integer_overlap_any_cited_span` (L1350/1361)
  - `no_content_word_overlap_any_cited_span` (L1429)
  - `trial_name_mismatch` (L1453), `entailment_failed` (L1593/1613)
- Cleanest BEFORE-the-drop hook: after the full check block completes and `failures` is populated for a single cited token's span, BUT BEFORE L1647. Re-anchor enumerates alternative spans within the SAME cited row and re-runs `verify_sentence_provenance` per-candidate; first candidate yielding `is_verified=True` re-binds the token; else fall through to existing L1647 drop.

## (2) verify_fns — what "passes verify" is
Single entry point: **`verify_sentence_provenance(sentence, evidence_pool, *, require_number_match=True, quantified_models=None) -> SentenceVerification`** (L1164). is_verified == (failures empty). The acceptance test the re-anchor MUST REUSE = call this same function on the candidate-rebound sentence. Its internal gates:
- **Content-word overlap**: `_content_words(text)` (L883, alpha tokens >=3 chars minus `_STOPWORDS_FOR_GROUNDING`). Floor = `MIN_CONTENT_WORD_OVERLAP = int(os.getenv("PG_PROVENANCE_MIN_CONTENT_OVERLAP","2"))` (L900-902). Check at L1373-1432: `overlap = sentence_content & span_content; if len(overlap) < MIN_CONTENT_WORD_OVERLAP -> fail` (over aggregated cited-span text, L1374).
- **Numeric span-scoped match**: `_decimals_in(text)` (L688, regex `-?\d+\.\d+`), `_numbers_in(text)` (L683, `-?\d+(?:\.\d+)?` superset), `_INTEGER_PERCENT_RE` (L477). Span aggregate built from `direct_quote[tok.start:tok.end]` (L1271-1274, 1313-1319). Gate L1331-1364: every sentence decimal AND every %-expressed standalone integer (and, in the no-decimal branch, every standalone integer) must appear in a cited span. Helpers strip dose/placebo/threshold (`_strip_dose_patterns` L549, `_PLACEBO_COMPARATOR_RE` L492, `_THRESHOLD_RE` L504). NOTE: FIX-A3 REMOVED the old whole-direct_quote local-window numeric rescue (L1327-1330 comment) — a number must be IN the cited span.
- **NLI entailment gate** (6th check, L1471-1616), gated by `PG_STRICT_VERIFY_ENTAILMENT` via `_entailment_mode()` (`src/polaris_graph/clinical_generator/strict_verify.py:176`, values off/warn/enforce, default enforce). Judge: `_get_judge().judge(sentence_clean, combined_span) -> (verdict, reason)` from `src/polaris_graph/llm/entailment_judge.py:142,324`; verdict in {ENTAILED, NEUTRAL, CONTRADICTED}, fails OPEN as `("ENTAILED","judge_error: ...")`. On NEUTRAL/CONTRADICTED it re-judges against a BOUNDED local window (`_find_local_support_window` L693 / `_find_local_content_window` L816, window=400). enforce-mode appends `entailment_failed` (L1593/1613). judge_error sentinel → fail-closed at L1633-1645 keyed on entailment mode.
- **Trial-name gate** (M-25a, L1434-1457): `extract_trial_names` (L954), `_trial_names_for_cited_row` (L1007, title-authority then cited-span fallback under `PG_VERIFY_TRIAL_NAME_SPAN_FALLBACK` default ON).
- Also: `no_provenance_token` (L1231-1238), `evidence_not_in_pool` (L1257), `span_out_of_bounds` (L1260-1263), `span_invalid` (L1265-1268), `empty_or_contentless_sentence` (BUG-03 floor, L1284-1298).

## (3) row_model — row + full text + token→offset
- Token grammar: `[#ev:<evidence_id>:<start>-<end>]`, regex `_PROVENANCE_TOKEN_RE` (L343-345); parsed by `parse_provenance_tokens` (L444) into `ProvenanceToken(evidence_id, start, end, raw)` (L406-415).
- Row text resolution: `direct_quote = ev.get("direct_quote") or ev.get("statement") or ""` (L1259, also L1317). The span text = `direct_quote[tok.start:tok.end]` (L1271). So a candidate span for re-anchor = any `(s,e)` substring of the SAME row's `direct_quote`, and a re-bound token = `[#ev:<same evidence_id>:<s>-<e>]`.
- gap-#18 full-row rescue window: confirmed at **L1401-1428** (content-floor branch) and L1538-1568/L1581-1604 (entailment branch). It does NOT re-bind the token — it only proposes a bounded <=400-char window and defers to the entailment bind. It is gated by `_verification_mode()` == "enforce" AND `_entailment_mode()` == "enforce". So gap-#18 is a PASS/FAIL rescue, NOT a span re-anchor; I-complete-003 re-anchor is the missing complement (re-bind the token to a new in-row span).
- `PG_VERIFICATION_MODE`: `_verification_mode()` at **L905-918**, reads env, default "off", values off/shadow/enforce (off byte-identical pre-0b). Confirmed L917.

## (4) insertion_plan
When `verify_sentence_provenance` would DROP a sentence whose failures are span-localized (number_not_in_any_cited_span / no_content_word_overlap / trial_name_mismatch / entailment_failed) and the row IS in pool with valid bounds:
1. For each cited `ProvenanceToken`, take its `evidence_id`'s `direct_quote` (the SAME row, no cross-row, no whole-doc).
2. Generate a BOUNDED set of candidate spans within that row by tokenizing the row text into sentences/sliding windows (bounded count — e.g. window=400 sliding/sentence boundaries, cap N candidates to keep enumeration bounded, mirroring `_find_local_support_window` discipline).
3. For each candidate `(s,e)`: rebuild the sentence with the token rewritten to `[#ev:<evidence_id>:<s>-<e>]` and re-run the SAME acceptance test — `verify_sentence_provenance(rebound_sentence, evidence_pool, require_number_match=..., quantified_models=...)`. REUSE, do not reimplement the checks.
4. First candidate returning `is_verified=True` → re-bind the token (keep the new span), keep the sentence.
5. No candidate passes → fall through to the EXISTING drop (L1847-1850 / L1647). Faithfulness-only-tightening: a re-anchor can only ever move a token to a span that PASSES the full strict_verify, so it cannot launder an out-of-span/unsupported claim.

Default-OFF flag recommended (e.g. PG_PROVENANCE_REANCHOR) so off-mode is byte-identical, matching the gap-#18 / PG_VERIFICATION_MODE precedent.

## VERIFY (HARD) — answer each explicitly in your reasoning before the verdict

1. The re-anchor can ONLY bind to a span that passes the SAME overlap + numeric + trial-name + NLI verify
   — there is NO relaxed/alternate acceptance path. Read `_try_reanchor`: every candidate is accepted ONLY
   if `verify_sentence_provenance(rebound, ...).is_verified` is True (the identical function strict_verify
   itself calls). Confirm the re-anchor therefore CANNOT introduce an unsupported / fabricated claim
   (faithfulness preserved). Also confirm the enforce-only accept gate (`_emode_reanchor() != "enforce" -> return None`)
   is correct: because the re-anchor ACTIVELY SEARCHES up to MAX_CANDIDATES windows for a coincidental
   mechanical match, accepting under entailment off/warn would launder a drop into a pass — is gating accept
   on enforce sufficient + correct?

2. When NO candidate passes, the sentence is still DROPPED (the existing `dropped.append(v)` path is reached
   unchanged; `_try_reanchor` returns None -> no `continue` -> falls to the drop). Confirm.

3. PG_PROVENANCE_REANCHOR OFF -> byte-identical. The env gate `if _provenance_reanchor_enabled():` early-outs
   so OFF-mode makes NO `_try_reanchor` call, NO judge call, NO counter mutation. Confirm there is no other
   code path the change touches when the flag is off (module-level additions are pure defs/constants).

4. Re-anchored sentences flow through the SAME downstream gates as normally-verified ones: the rescued
   `SentenceVerification` is appended to the SAME `kept[]` list (L2097) and is a normal `SentenceVerification`
   with `is_verified=True`. Confirm it is NOT special-cased downstream (section %-verified floor, zero-verified
   abort, report assembly all treat it identically).

5. Candidate search is BOUNDED (no compute blowup): `_reanchor_candidate_spans` caps total candidates at
   `PG_PROVENANCE_REANCHOR_MAX_CANDIDATES` (default 40) even on a huge row; Path-1 is single cited row only;
   Path-2 attempts only the FIRST verbatim-containing pool row then returns. Confirm. No magic numbers
   (every bound is an env-overridable module constant). Confirm.

6. NLI FAIL-OPEN MUST NOT BE AMPLIFIED (faithfulness-critical). The NLI judge fails OPEN to
   `("ENTAILED", "judge_error: ...")` on API/parse error. The pre-change pipeline calls
   `verify_sentence_provenance` ONCE per sentence; the re-anchor calls it up to MAX_CANDIDATES (40) times
   per FAILED sentence — so it could in principle multiply the fail-open exposure 40x. CONFIRM that this is
   NOT a leak: inside `verify_sentence_provenance`, the `judge_error_flag` sets a fail-CLOSED failure
   (`entailment_judge_error_fail_closed:...`) under entailment `enforce` (provenance_generator.py L1865-1872),
   so `is_verified=False` whenever the judge errors. Since the re-anchor accepts ONLY under enforce AND ONLY
   when `is_verified=True`, a degraded (errored) judge can NEVER recover a sentence across the 40-window
   search. Verify the enforce-only accept gate + the enforce-keyed judge_error fail-closed close this hole
   together. (Ground-truth confirmed by the new test case (f): with a judge that errors on every call, on a
   genuinely-supported sentence, the correct-span candidate verifies to is_verified=False with
   `entailment_judge_error_fail_closed`, reanchor_recovered==0, sentence DROPPED.)

Also apply your standard red-team checklist (silent fallback, assertion-relaxation, scope-creep,
new-code-has-tests, no mocking the verifier in a way that hides the real gate).

## THE DIFF UNDER REVIEW

### src/polaris_graph/generator/provenance_generator.py
```diff
diff --git a/src/polaris_graph/generator/provenance_generator.py b/src/polaris_graph/generator/provenance_generator.py
index 0b634538..00c480ee 100644
--- a/src/polaris_graph/generator/provenance_generator.py
+++ b/src/polaris_graph/generator/provenance_generator.py
@@ -901,6 +901,238 @@ MIN_CONTENT_WORD_OVERLAP = int(
     os.getenv("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "2")
 )
 
+# I-complete-003 (#1189) — PROVENANCE RE-ANCHOR.
+#
+# When a findings sentence FAILS verification on its CURRENTLY-cited span,
+# before the sentence is dropped the re-anchor enumerates a BOUNDED set of
+# candidate spans WITHIN the SAME cited evidence row (or, for an UNCITED but
+# verbatim-grounded sentence, the pool row that verbatim-contains it) and
+# re-runs the EXACT same `verify_sentence_provenance` acceptance gate against
+# each candidate. The FIRST candidate that passes the FULL gate (numeric +
+# >=MIN_CONTENT_WORD_OVERLAP content overlap + trial-name + NLI entailment)
+# re-binds the sentence's [#ev:...] token to that span and the sentence is
+# kept as RECOVERED. If NO candidate passes, the original drop stands — there
+# is NO new acceptance path, so the re-anchor can ONLY ever bind to a span
+# that already passes the full bar and therefore CANNOT introduce an
+# unsupported / fabricated claim.
+#
+# Default-OFF: when PG_PROVENANCE_REANCHOR is falsy the re-anchor is a no-op
+# and behaviour is BYTE-IDENTICAL to before (matches the gap-#18 /
+# PG_VERIFICATION_MODE precedent). It is ALSO gated on entailment ==
+# "enforce": under off/warn the reused verifier accepts on numeric +
+# content-overlap ALONE with NO enforced entailment bind, and because the
+# re-anchor ACTIVELY SEARCHES up to MAX_CANDIDATES windows for a coincidental
+# mechanical match, accepting under off/warn would launder a drop into a pass
+# (the §-1.1 lethal failure mode). So accept is permitted ONLY under enforce.
+
+PG_PROVENANCE_REANCHOR_MAX_CANDIDATES = int(
+    os.getenv("PG_PROVENANCE_REANCHOR_MAX_CANDIDATES", "40")
+)
+
+# Sliding-window size (chars) for enumerating candidate spans inside a row's
+# direct_quote. Mirrors the _find_local_support_window / _find_local_content_window
+# discipline (window=400) so a candidate is a bounded local slice, never the
+# whole row.
+PG_PROVENANCE_REANCHOR_WINDOW = int(
+    os.getenv("PG_PROVENANCE_REANCHOR_WINDOW", "400")
+)
+
+
+def _provenance_reanchor_enabled() -> bool:
+    """True iff PG_PROVENANCE_REANCHOR is set truthy. Read at call time so
+    tests can toggle without re-import. Falsy (unset/0/false/no/off) => the
+    re-anchor is a no-op and strict_verify is byte-identical to pre-#1189."""
+    v = os.getenv("PG_PROVENANCE_REANCHOR", "").strip().lower()
+    return v in ("1", "true", "yes", "on", "enabled")
+
+
+# I-complete-003 (#1189) — re-anchor telemetry. Module-level counters, read +
+# reset by the sweep. ONLY mutated inside the flag-on path, so OFF-mode never
+# touches them (byte-identity).
+_REANCHOR_TELEMETRY: dict[str, int] = {
+    "reanchor_attempts": 0,
+    "reanchor_recovered": 0,
+    "reanchor_uncited_bound": 0,
+}
+
+
+def get_reanchor_telemetry() -> dict[str, int]:
+    """Snapshot of the re-anchor counters (attempts / recovered / uncited-bound)."""
+    return dict(_REANCHOR_TELEMETRY)
+
+
+def reset_reanchor_telemetry() -> None:
+    """Zero the re-anchor counters (call between runs / tests)."""
+    for k in _REANCHOR_TELEMETRY:
+        _REANCHOR_TELEMETRY[k] = 0
+
+
+def _reanchor_candidate_spans(direct_quote: str) -> list[tuple[int, int]]:
+    """Enumerate a BOUNDED set of candidate (start, end) spans inside a row's
+    ``direct_quote``.
+
+    Candidates are produced by (a) sentence-segmenting the row text and (b) a
+    sliding window of PG_PROVENANCE_REANCHOR_WINDOW chars stepped by half the
+    window. Both are clamped to PG_PROVENANCE_REANCHOR_MAX_CANDIDATES total so
+    there is NO compute blow-up on a large row. Each span is a valid
+    ``0 <= start < end <= len(direct_quote)`` slice, so the reused verifier's
+    span-bounds checks pass naturally.
+    """
+    if not direct_quote:
+        return []
+    n = len(direct_quote)
+    cap = max(1, PG_PROVENANCE_REANCHOR_MAX_CANDIDATES)
+    seen: set[tuple[int, int]] = set()
+    candidates: list[tuple[int, int]] = []
+
+    def _add(start: int, end: int) -> None:
+        start = max(0, start)
+        end = min(n, end)
+        if start >= end:
+            return
+        key = (start, end)
+        if key in seen:
+            return
+        seen.add(key)
+        candidates.append(key)
+
+    # (a) Sentence-segment candidates: each sentence-like run of the row text.
+    for m in re.finditer(r"[^.!?]+[.!?]?", direct_quote):
+        if len(candidates) >= cap:
+            return candidates[:cap]
+        seg = m.group(0)
+        if seg.strip():
+            _add(m.start(), m.end())
+
+    # (b) Sliding-window candidates (half-window step) over the full row, to
+    # catch support that straddles sentence boundaries.
+    window = max(1, PG_PROVENANCE_REANCHOR_WINDOW)
+    step = max(1, window // 2)
+    pos = 0
+    while pos < n and len(candidates) < cap:
+        _add(pos, pos + window)
+        pos += step
+
+    return candidates[:cap]
+
+
+def _rebind_single_token(sentence: str, evidence_id: str, start: int, end: int) -> str:
+    """Rewrite the sentence's [#ev:...] provenance token(s) to a new
+    (evidence_id, start, end) span. SCOPE (v1, per ledger): single-token
+    re-anchor — every [#ev:...] occurrence is rewritten to the same rescued
+    span. Multi-token sentences with a UNION numeric failure
+    (which-token-to-move combinatorics) are explicitly OUT-OF-SCOPE for v1 and
+    are filtered out by the caller before this is reached."""
+    return _PROVENANCE_TOKEN_RE.sub(
+        f"[#ev:{evidence_id}:{start}-{end}]", sentence,
+    )
+
+
+def _try_reanchor(
+    sentence: str,
+    evidence_pool: dict[str, dict[str, Any]],
+    *,
+    require_number_match: bool,
+    quantified_models: dict[tuple[str, str], Any] | None,
+) -> Optional[SentenceVerification]:
+    """I-complete-003 (#1189) — attempt to RE-ANCHOR a sentence that just
+    FAILED ``verify_sentence_provenance`` on its currently-cited span.
+
+    Returns a RECOVERED ``SentenceVerification`` (token re-bound, is_verified=
+    True) when a candidate span in the relevant row passes the FULL reused
+    gate, else ``None`` (caller keeps the existing drop). NO recursion: this
+    is invoked from the ``strict_verify`` caller loop, and the reused
+    ``verify_sentence_provenance`` is the SAME single acceptance entry point —
+    not re-implemented and not called from inside itself.
+
+    HARD CONSTRAINTS:
+      * accept ONLY under entailment ``enforce`` (the search-for-a-match shape
+        would otherwise launder a drop into a pass under off/warn);
+      * candidates are bounded (<= MAX_CANDIDATES) per row;
+      * v1 scope = single-token (cited) OR uncited verbatim-lift; multi-token
+        union-numeric is out-of-scope (returns None).
+    """
+    # Enforce-only accept gate (faithfulness-critical, mirrors gap-#18 L1407).
+    from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: PLC0415
+        _entailment_mode as _emode_reanchor,
+    )
+    if _emode_reanchor() != "enforce":
+        return None
+
+    tokens = parse_provenance_tokens(sentence)
+
+    # ---- Path 1: CITED sentence — re-anchor within its cited row(s) ----
+    if tokens:
+        # v1 scope: single distinct cited evidence id. A multi-id sentence
+        # carries the which-token-to-move union combinatorics that v1 does
+        # NOT handle — leave the existing drop in place.
+        distinct_ids = {t.evidence_id for t in tokens}
+        if len(distinct_ids) != 1:
+            return None
+        evidence_id = next(iter(distinct_ids))
+        ev = evidence_pool.get(evidence_id)
+        if ev is None:
+            return None
+        direct_quote = ev.get("direct_quote") or ev.get("statement") or ""
+        if not direct_quote:
+            return None
+        _REANCHOR_TELEMETRY["reanchor_attempts"] += 1
+        for (cand_start, cand_end) in _reanchor_candidate_spans(direct_quote):
+            rebound = _rebind_single_token(
+                sentence, evidence_id, cand_start, cand_end,
+            )
+            v = verify_sentence_provenance(
+                rebound, evidence_pool,
+                require_number_match=require_number_match,
+                quantified_models=quantified_models,
+            )
+            if v.is_verified:
+                _REANCHOR_TELEMETRY["reanchor_recovered"] += 1
+                v.soft_warnings = list(v.soft_warnings) + [
+                    f"reanchored:{evidence_id}:{cand_start}-{cand_end}",
+                ]
+                return v
+        return None
+
+    # ---- Path 2: UNCITED sentence — find the pool row that verbatim-grounds it ----
+    # No [#ev] token: search the pool for the row whose direct_quote/text
+    # contains the verbatim (case-insensitive) sentence prose, then re-anchor
+    # within that row. Same full-gate bar applies.
+    bare = _verifier_cleaned_text(sentence).strip()
+    if not bare:
+        return None
+    bare_lower = bare.lower()
+    for evidence_id, ev in evidence_pool.items():
+        if not isinstance(ev, dict):
+            continue
+        direct_quote = ev.get("direct_quote") or ev.get("statement") or ""
+        if not direct_quote:
+            continue
+        if bare_lower not in direct_quote.lower():
+            continue
+        _REANCHOR_TELEMETRY["reanchor_attempts"] += 1
+        for (cand_start, cand_end) in _reanchor_candidate_spans(direct_quote):
+            # Append a fresh token (the sentence had none) and verify.
+            candidate_sentence = (
+                f"{sentence.rstrip()} [#ev:{evidence_id}:{cand_start}-{cand_end}]"
+            )
+            v = verify_sentence_provenance(
+                candidate_sentence, evidence_pool,
+                require_number_match=require_number_match,
+                quantified_models=quantified_models,
+            )
+            if v.is_verified:
+                _REANCHOR_TELEMETRY["reanchor_recovered"] += 1
+                _REANCHOR_TELEMETRY["reanchor_uncited_bound"] += 1
+                v.soft_warnings = list(v.soft_warnings) + [
+                    f"reanchored_uncited:{evidence_id}:{cand_start}-{cand_end}",
+                ]
+                return v
+        # Only the first verbatim-containing row is attempted (bounded).
+        return None
+
+    return None
+
 
 def _verification_mode() -> str:
     """Phase 0b (I-meta-005, gap-#18): verification-mode router for the three
@@ -1847,6 +2079,23 @@ def strict_verify(
         if v.is_verified:
             kept.append(v)
         else:
+            # I-complete-003 (#1189): before dropping, try to RE-ANCHOR the
+            # sentence to a different span in its cited row (or, if uncited
+            # but verbatim-grounded, to a pool row). The env gate early-outs
+            # so OFF-mode is BYTE-IDENTICAL (no _try_reanchor call, no judge
+            # call, no counter mutation). A rescued result has already passed
+            # the SAME full gate, so no fabrication path is introduced; it
+            # flows through the SAME downstream (kept[]) as a normally-verified
+            # sentence.
+            if _provenance_reanchor_enabled():
+                rescued = _try_reanchor(
+                    s, evidence_pool,
+                    require_number_match=require_number_match,
+                    quantified_models=quantified_models,
+                )
+                if rescued is not None:
+                    kept.append(rescued)
+                    continue
             dropped.append(v)
 
     # Limitations: telemetry-grounded verification if block supplied,
```

### tests/polaris_graph/test_provenance_reanchor.py (NEW FILE — untracked, full content)
```python
"""I-complete-003 (#1189) — PROVENANCE RE-ANCHOR at the strict_verify drop site.

When a findings sentence FAILS `verify_sentence_provenance` on its currently-
cited span, the re-anchor (env-gated PG_PROVENANCE_REANCHOR, accept ONLY under
entailment `enforce`) enumerates a BOUNDED set of candidate spans WITHIN the
SAME cited evidence row (or, for an uncited verbatim-grounded sentence, the
pool row containing it) and re-runs the EXACT same acceptance gate against each
candidate. The first candidate that passes the FULL gate re-binds the token and
the sentence is kept as RECOVERED. If none passes, the original drop stands.

These tests are network-free + deterministic: a fake entailment judge is
installed (the same convention as test_provenance_generator_entailment.py).
No relaxation of any verify check — the re-anchor reuses verify_sentence_provenance
unchanged, so it can only ever bind to a span that already passes the full bar.

Cases:
  (a) cited span WRONG, a DIFFERENT span in the SAME row supports it -> re-anchored + verified
  (b) no supporting span ANYWHERE -> still dropped (no fabrication)
  (c) uncited verbatim lift of a pool row -> bound
  (d) PG_PROVENANCE_REANCHOR unset -> byte-identical old behaviour (no re-anchor)
  (e) flag ON but entailment OFF + coincidental mechanical match -> STILL dropped (laundering guard)
"""

from __future__ import annotations

import pytest

from src.polaris_graph.clinical_generator import strict_verify as _gen2
from src.polaris_graph.generator import provenance_generator as _pg
from src.polaris_graph.generator.provenance_generator import (
    get_reanchor_telemetry,
    reset_reanchor_telemetry,
    strict_verify,
)


# ---------------------------------------------------------------------------
# Fake judge (mirrors test_provenance_generator_entailment.py)
# ---------------------------------------------------------------------------
class _FakeJudge:
    """Returns ENTAILED only when the judged span actually contains the
    sentence's anchor phrase; NEUTRAL otherwise. This lets the re-anchor
    search behave realistically — a candidate window that does NOT cover the
    support is rejected by the (faked) NLI just as a real judge would, while
    the correct window passes."""

    def __init__(self, anchor: str) -> None:
        self.anchor = anchor.lower()
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if self.anchor in (span or "").lower():
            return "ENTAILED", "fake-entailed"
        return "NEUTRAL", "fake-neutral"


def _install_judge(monkeypatch, fake: _FakeJudge) -> None:
    monkeypatch.setattr(_gen2, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _gen2.reset_judge_telemetry()
    reset_reanchor_telemetry()
    # Default each test to a clean slate; individual tests set the flags.
    monkeypatch.delenv("PG_PROVENANCE_REANCHOR", raising=False)
    monkeypatch.delenv("PG_STRICT_VERIFY_ENTAILMENT", raising=False)
    yield


# ---------------------------------------------------------------------------
# (a) cited span WRONG, a different span in the SAME row supports it
# ---------------------------------------------------------------------------
def test_reanchor_recovers_wrong_span_same_row(monkeypatch):
    """The token cites bytes 0-30 (a sentence about enrolment) but the actual
    support — "HbA1c reduction of 1.5 percent" — lives later in the SAME row.
    Re-anchor must find the supporting window, re-bind, and KEEP the sentence."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge("hba1c reduction of 1.5 percent"))

    # Row: a leading admin sentence, then the supporting clause.
    leading = "The trial enrolled adults at sites."          # bytes 0..len(leading)
    support = " Treatment produced an HbA1c reduction of 1.5 percent in adults."
    direct_quote = leading + support
    pool = {"ev_a": {"direct_quote": direct_quote}}

    # Cite the WRONG span (the admin leading clause) — number + content absent there.
    wrong_end = len(leading)
    draft = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_a:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 1, (
        f"expected re-anchor to recover the sentence, dropped="
        f"{[d.failure_reasons for d in report.dropped_sentences]}"
    )
    assert report.total_dropped == 0
    kept = report.kept_sentences[0]
    assert kept.is_verified is True
    assert any(w.startswith("reanchored:ev_a:") for w in kept.soft_warnings)
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 1
    assert tel["reanchor_recovered"] == 1


# ---------------------------------------------------------------------------
# (b) no supporting span ANYWHERE -> still dropped (no fabrication)
# ---------------------------------------------------------------------------
def test_reanchor_no_support_anywhere_still_dropped(monkeypatch):
    """The claimed number (9.9 percent) appears in NO span of ANY row. Even
    with the flag ON + enforce, every candidate fails the numeric gate, so the
    sentence is DROPPED — the re-anchor introduces no fabrication path."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge("never-matches-this-anchor"))

    direct_quote = "Treatment produced an HbA1c reduction of 1.5 percent in adults."
    pool = {"ev_b": {"direct_quote": direct_quote}}
    draft = (
        f"Treatment produced an HbA1c reduction of 9.9 percent in adults "
        f"[#ev:ev_b:0-{len(direct_quote)}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0
    assert report.total_dropped == 1
    assert any(
        "number_not_in_any_cited_span" in r
        for r in report.dropped_sentences[0].failure_reasons
    )
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 1
    assert tel["reanchor_recovered"] == 0


# ---------------------------------------------------------------------------
# (c) uncited verbatim lift of a pool row -> bound
# ---------------------------------------------------------------------------
def test_reanchor_binds_uncited_verbatim_lift(monkeypatch):
    """A sentence with NO [#ev] token that is a verbatim lift of a pool row
    must be located in the pool and BOUND (uncited-bound telemetry ticks)."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(
        monkeypatch, _FakeJudge("cardiovascular events in adults by 23.5 percent"),
    )

    direct_quote = (
        "Aspirin reduced cardiovascular events in adults by 23.5 percent."
    )
    pool = {"ev_c": {"direct_quote": direct_quote}}
    # Uncited sentence (no token) that verbatim-matches the row.
    draft = "Aspirin reduced cardiovascular events in adults by 23.5 percent."

    report = strict_verify(draft, pool)
    assert report.total_kept == 1, (
        f"expected uncited verbatim lift to be bound, dropped="
        f"{[d.failure_reasons for d in report.dropped_sentences]}"
    )
    kept = report.kept_sentences[0]
    assert kept.is_verified is True
    assert any(w.startswith("reanchored_uncited:ev_c:") for w in kept.soft_warnings)
    tel = get_reanchor_telemetry()
    assert tel["reanchor_uncited_bound"] == 1
    assert tel["reanchor_recovered"] == 1


# ---------------------------------------------------------------------------
# (d) flag unset -> byte-identical old behaviour (no re-anchor)
# ---------------------------------------------------------------------------
def test_reanchor_disabled_is_byte_identical(monkeypatch):
    """With PG_PROVENANCE_REANCHOR unset, the SAME wrong-span draft from case
    (a) is DROPPED exactly as before — no re-anchor, no judge call, no counter
    mutation."""
    # Flag intentionally NOT set (fixture deleted it). Entailment off so no
    # judge fires either — proves the early-out happens before any new logic.
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    fake = _FakeJudge("anything")
    _install_judge(monkeypatch, fake)

    leading = "The trial enrolled adults at sites."
    support = " Treatment produced an HbA1c reduction of 1.5 percent in adults."
    direct_quote = leading + support
    pool = {"ev_d": {"direct_quote": direct_quote}}
    wrong_end = len(leading)
    draft = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_d:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, "flag-off must NOT recover the sentence"
    assert report.total_dropped == 1
    # No re-anchor counters touched.
    tel = get_reanchor_telemetry()
    assert tel == {
        "reanchor_attempts": 0,
        "reanchor_recovered": 0,
        "reanchor_uncited_bound": 0,
    }
    # Helper must agree it is disabled.
    assert _pg._provenance_reanchor_enabled() is False


# ---------------------------------------------------------------------------
# (e) laundering guard — flag ON, entailment OFF, coincidental mechanical match
# ---------------------------------------------------------------------------
def test_reanchor_off_entailment_does_not_launder(monkeypatch):
    """ADVISOR-required laundering guard: with PG_PROVENANCE_REANCHOR=1 but
    PG_STRICT_VERIFY_ENTAILMENT=off, a row that contains a coincidental
    mechanically-matching window (number + 2 content words) must NOT rescue the
    sentence — the enforce-only accept gate keeps the drop. Otherwise the
    active span-search would launder a coincidental match into a pass (§-1.1
    lethal mode)."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    fake = _FakeJudge("anything")
    _install_judge(monkeypatch, fake)

    # A row where "reduction" + "adults" + "1.5" co-occur in a window — a
    # mechanically-passing coincidence that, under off-mode, would slip
    # through if accept were not gated on enforce.
    leading = "Enrolment of adults began early."
    support = " A separate reduction of 1.5 percent in adults was noted."
    direct_quote = leading + support
    pool = {"ev_e": {"direct_quote": direct_quote}}
    wrong_end = len(leading)
    draft = (
        f"Treatment produced a reduction of 1.5 percent in adults "
        f"[#ev:ev_e:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, (
        "off-mode re-anchor must NOT accept — that would launder a coincidental "
        "mechanical match into a pass"
    )
    assert report.total_dropped == 1
    # Enforce-only gate returns before any attempt, so no counters tick + no
    # judge call.
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 0
    assert tel["reanchor_recovered"] == 0
    assert fake.calls == [], "off-mode must not invoke the entailment judge"


# ---------------------------------------------------------------------------
# (f) NLI fail-open guard — judge_error sentinel must NOT recover across the
#     40-window search (the re-anchor must not amplify the fail-open path)
# ---------------------------------------------------------------------------
class _JudgeErrorJudge:
    """Simulates a DEGRADED NLI judge: every call fails OPEN, returning the
    `("ENTAILED", "judge_error: ...")` sentinel exactly as entailment_judge.py
    does on an API/parse error. The verifier's L1865-1872 fail-closed gate must
    turn this into is_verified=False under enforce, so NO candidate window can
    be 'recovered' by a degraded judge — the re-anchor's 40-window search must
    not multiply the fail-open into a pass."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return "ENTAILED", "judge_error: simulated transient API failure"


def test_reanchor_judge_error_does_not_amplify_fail_open(monkeypatch):
    """ADVISOR-required (point 6): in enforce mode, a candidate window where the
    NLI judge returns the judge_error fail-open sentinel must NOT yield
    is_verified=True inside the re-anchor loop. A genuinely supported sentence
    (number + content present in the cited span) is used so the ONLY thing that
    can flip is_verified is the judge — proving the L1865-1872 fail-closed fires
    on each re-bound candidate. The sentence stays DROPPED; the re-anchor cannot
    recover a sentence on the back of a degraded judge across the 40 windows."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _JudgeErrorJudge()
    _install_judge(monkeypatch, fake)

    # The support genuinely lives later in the SAME row, so numeric + content
    # gates would pass on the right window — ONLY the judge_error fail-closed
    # keeps it dropped. This isolates the fail-open-amplification risk.
    leading = "The trial enrolled adults at sites."
    support = " Treatment produced an HbA1c reduction of 1.5 percent in adults."
    direct_quote = leading + support
    pool = {"ev_f": {"direct_quote": direct_quote}}
    wrong_end = len(leading)
    draft = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_f:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, (
        "a judge_error fail-open must NOT let the re-anchor recover the sentence "
        "across the 40-window search — that would amplify the NLI fail-open"
    )
    assert report.total_dropped == 1
    # The re-anchor DID attempt (flag on, enforce on, row present) but recovered
    # nothing — the candidate window where numeric+content pass reaches the
    # entailment block, and the judge_error fail-closed (L1865-1872, enforce)
    # turns is_verified back to False, so NO candidate is accepted.
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 1
    assert tel["reanchor_recovered"] == 0
    # The judge WAS consulted on at least one candidate window (proving the
    # candidate reached the entailment gate, where the fail-open was caught).
    assert fake.calls, "judge should have been consulted on a candidate window"
    # Direct proof that the fail-closed fires on a candidate whose numeric +
    # content gates pass: the correct-span candidate verifies to is_verified
    # False with the judge_error fail-closed failure, NOT a pass.
    correct_span = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_f:{wrong_end}-{len(direct_quote)}]."
    )
    v_correct = _pg.verify_sentence_provenance(
        correct_span, pool, require_number_match=True,
    )
    assert v_correct.is_verified is False, (
        "under judge_error the candidate must fail-closed, not pass"
    )
    assert any(
        "entailment_judge_error_fail_closed" in r
        for r in v_correct.failure_reasons
    ), v_correct.failure_reasons
    assert v_correct.judge_error is True
```

## strict_verify drop-site (context, already in file pre-change at L2079-2099 after this diff applies)
The rescued result is appended to the SAME `kept[]` and `continue`s past the drop; flag-off early-outs.

END OF GATE INPUT. Return the YAML schema; the FINAL line MUST be a single `verdict:` line.
