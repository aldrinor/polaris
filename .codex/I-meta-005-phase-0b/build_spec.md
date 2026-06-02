# Phase 0b BUILD SPEC — verification-mode router (gap-#18 fix). BINDING, near-mechanical.

Apply EXACTLY. All three deltas gate on a new env `PG_VERIFICATION_MODE` ∈ {off, shadow, enforce},
default `off`. **OFF = byte-identical to pre-0b behavior** (every new branch is gated; the only
structural change in off mode is one additive dataclass field, inert by default). shadow = DETECT +
log telemetry, output unchanged, NO extra judge calls (spend-neutral). enforce = deltas change
`is_verified` (rescue grounded prose / drop judge-error sentinel).

Target file: `src/polaris_graph/generator/provenance_generator.py` (+ one new smoke test file).
Use `Edit` with the exact `old`→`new` blocks below (context included for unique match).

---

## EDIT 1 — add `_verification_mode()` helper (after MIN_CONTENT_WORD_OVERLAP block, ~line 815)

old:
```
MIN_CONTENT_WORD_OVERLAP = int(
    os.getenv("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "2")
)
```
new:
```
MIN_CONTENT_WORD_OVERLAP = int(
    os.getenv("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "2")
)


def _verification_mode() -> str:
    """Phase 0b (I-meta-005, gap-#18): verification-mode router for the three
    grounded-prose deltas. Read at call time so tests can override.

      off (default) — byte-identical to pre-0b behavior; no delta fires.
      shadow        — deltas DETECT + log telemetry but do NOT change
                      is_verified, and make NO extra judge calls (spend-
                      neutral free Gate-A measurement).
      enforce       — deltas change is_verified (rescue grounded prose via a
                      BOUNDED local content window; drop the judge-error
                      fail-open sentinel).
    """
    v = os.getenv("PG_VERIFICATION_MODE", "off").strip().lower()
    return v if v in ("off", "shadow", "enforce") else "off"
```

---

## EDIT 2 — add `_find_local_content_window()` (immediately after `_find_local_support_window` returns, i.e. after the line `    return None` that closes that function, ~line 771, BEFORE the `# Codex round 1 B-1:` stopwords comment)

Insert this new function between `_find_local_support_window`'s final `return None` and the
`_STOPWORDS_FOR_GROUNDING` comment/definition:
```
def _find_local_content_window(
    needed_content_words: set[str],
    direct_quote: str,
    window: int = 400,
    min_content_overlap: int = 2,
) -> Optional[tuple[int, int]]:
    """Phase 0b Delta 1/2 (I-meta-005, gap-#18): content-word analog of
    _find_local_support_window. Find a BOUNDED contiguous window (<= `window`
    chars) inside `direct_quote` that contains at least `min_content_overlap`
    of the sentence's content words (word-boundary, token-exact). Returns
    (start, end) or None.

    Bounded + fail-closed BY CONSTRUCTION: never returns the whole document —
    only a <=window-char slice clustering the required content words. Same
    safety shape as the numeric I-gen-005 finder: a grounded sentence whose
    FULL cited row supports it is rescued, while a sentence whose content
    words are SCATTERED beyond `window` chars is NOT (true fabrication stays
    dropped). The window is anchored at each content-word match position and
    extended forward, so any cluster of >=min words spanning <=window chars is
    discovered when anchored at its leftmost member.
    """
    if not needed_content_words or not direct_quote:
        return None
    norm = direct_quote.lower()
    n = len(norm)
    positions: list[int] = []
    for w in needed_content_words:
        for m in re.finditer(r"\b" + re.escape(w) + r"\b", norm):
            positions.append(m.start())
    if len(positions) < min_content_overlap:
        return None
    positions.sort()
    for anchor in positions:
        ws = max(0, anchor)
        we = min(n, ws + window)
        window_text = norm[ws:we]
        hits = sum(
            1 for w in needed_content_words
            if re.search(r"\b" + re.escape(w) + r"\b", window_text)
        )
        if hits >= min_content_overlap:
            return (ws, we)
    return None
```

---

## EDIT 3 — Delta 1: bounded local-window rescue for the content-word floor (~line 1135-1144)

old:
```
        sentence_content = _content_words(sentence_stripped)
        span_content = _content_words(" ".join(aggregated_span_text))
        if sentence_content:
            overlap = sentence_content & span_content
            if len(overlap) < MIN_CONTENT_WORD_OVERLAP:
                ev_ids = ",".join(sorted({t.evidence_id for t in tokens}))
                failures.append(
                    f"no_content_word_overlap_any_cited_span:{ev_ids}:"
                    f"sentence_words={sorted(sentence_content)[:5]}"
                )
```
new:
```
        sentence_content = _content_words(sentence_stripped)
        span_content = _content_words(" ".join(aggregated_span_text))
        if sentence_content:
            overlap = sentence_content & span_content
            if len(overlap) < MIN_CONTENT_WORD_OVERLAP:
                ev_ids = ",".join(sorted({t.evidence_id for t in tokens}))
                # Phase 0b Delta 1 — CORRECTED per architect P1 (entailment-
                # gated PROPOSE; downstream Delta 2 BINDS): floor-clear only
                # proposes a bounded <=400-char window; the entailment bind
                # happens downstream. GATED on _entailment_mode() in
                # (warn,enforce) so an entailment-off config can NEVER let a
                # content-words-only clear be the sole gate (brief §3.3 + R1 +
                # HARD CONSTRAINT #5). off = no rescue. shadow = log, still
                # fail (output + spend neutral, no judge call). enforce +
                # entailment-active + window = clear (defer to the bind).
                _vmode_c = _verification_mode()
                _rescued_c = False
                if _vmode_c in ("shadow", "enforce"):
                    from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: PLC0415
                        _entailment_mode as _emode_c,
                    )
                    if _emode_c() == "enforce":  # enforce-only (Codex diff-gate P1: warn never drops)
                        for tok in tokens:
                            ev = evidence_pool.get(tok.evidence_id)
                            if ev is None:
                                continue
                            dq_c = ev.get("direct_quote") or ev.get("statement") or ""
                            if _find_local_content_window(
                                sentence_content, dq_c, window=400,
                                min_content_overlap=MIN_CONTENT_WORD_OVERLAP,
                            ):
                                _rescued_c = True
                                logger.warning(
                                    "[provenance] %s content_floor_full_row "
                                    "ev=%s — narrow span missed content words; "
                                    "bounded full-row window exists, deferring "
                                    "to the downstream entailment bind",
                                    "ENFORCE_propose" if _vmode_c == "enforce"
                                    else "SHADOW_would_propose",
                                    tok.evidence_id,
                                )
                                break
                if not (_vmode_c == "enforce" and _rescued_c):
                    failures.append(
                        f"no_content_word_overlap_any_cited_span:{ev_ids}:"
                        f"sentence_words={sorted(sentence_content)[:5]}"
                    )
```

**ARCHITECT P1+P2 CORRECTION (2026-05-31):** EDIT 3 above is the CORRECTED Delta 1 — the entailment
bind is gated on `_entailment_mode()` so `PG_VERIFICATION_MODE=enforce` + `PG_STRICT_VERIFY_ENTAILMENT=off`
can no longer launder a content-floor drop (the judge would otherwise never be consulted). Smoke adds
**S0b-8** (entailment-off no-launder: judge never called, sentence drops) and **S0b-9** (window-not-
entailed: Delta 1 proposes, Delta 2 binds NEUTRAL → fail-closed → drop), and **S0b-2** now uses a
discriminating judge (NEUTRAL narrow / ENTAILED window) so the bind is actually exercised. 20/20 green.

---

## EDIT 4 — init the judge-error flag (immediately before `if not failures:` at the entailment block, ~line 1183)

old:
```
        if not failures:
            from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: PLC0415
                _entailment_mode,
                _get_judge,
                _record_judge_outcome,
            )
```
new:
```
        # Phase 0b Delta 3 (I-meta-005, gap-#18): tracks whether the entailment
        # judge failed OPEN ((ENTAILED,"judge_error: ...")). Set in either judge
        # call below; consumed by the ON-mode fail-closed gate near the return.
        judge_error_flag = False
        if not failures:
            from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: PLC0415
                _entailment_mode,
                _get_judge,
                _record_judge_outcome,
            )
```

---

## EDIT 5 — Delta 3 (first judge call) detect the sentinel (~line 1200-1204)

old:
```
                verdict, reason = _get_judge().judge(
                    sentence_clean, combined_span,
                )
                _record_judge_outcome(verdict, reason)
                if verdict in ("NEUTRAL", "CONTRADICTED"):
```
new:
```
                verdict, reason = _get_judge().judge(
                    sentence_clean, combined_span,
                )
                _record_judge_outcome(verdict, reason)
                # Phase 0b Delta 3: the judge fails OPEN (entailment_judge.py:147)
                # returning ("ENTAILED","judge_error: ..."). Flag it; ON mode
                # fails-closed near the return. OFF leaves is_verified unchanged
                # (pre-0b fail-open preserved — filed as a separate gated issue).
                if verdict == "ENTAILED" and reason.startswith("judge_error:"):
                    judge_error_flag = True
                if verdict in ("NEUTRAL", "CONTRADICTED"):
```

---

## EDIT 6 — Delta 2: non-numeric local-window rescue (~line 1244, `if not sentence_dec_local: continue`)

old:
```
                        if not sentence_dec_local:
                            continue
                        win = _find_local_support_window(
                            sentence_dec_local,
                            sentence_content_local,
                            direct_quote,
                            window=400,
                            min_content_overlap=2,
                        )
```
new:
```
                        if not sentence_dec_local:
                            # Phase 0b Delta 2 (I-meta-005, gap-#18): non-numeric
                            # NEUTRAL had NO local-window second chance (the
                            # second-chance was decimal-gated). off = unchanged
                            # (continue -> fail-closed). enforce = recover a
                            # BOUNDED content-word window from this cited row and
                            # re-judge against it. shadow = log would-attempt, no
                            # extra judge call (spend-neutral), output unchanged.
                            _vmode_n = _verification_mode()
                            if _vmode_n in ("shadow", "enforce") and sentence_content_local:
                                cwin = _find_local_content_window(
                                    sentence_content_local,
                                    direct_quote,
                                    window=400,
                                    min_content_overlap=2,
                                )
                                if cwin:
                                    if _vmode_n == "enforce":
                                        local_window_text = direct_quote[cwin[0]:cwin[1]]
                                        local_ev_id = tok.evidence_id
                                        break
                                    logger.warning(
                                        "[provenance] SHADOW "
                                        "would_attempt_nonnumeric_window_rescue "
                                        "ev=%s", tok.evidence_id,
                                    )
                            continue
                        win = _find_local_support_window(
                            sentence_dec_local,
                            sentence_content_local,
                            direct_quote,
                            window=400,
                            min_content_overlap=2,
                        )
```

---

## EDIT 7 — Delta 3 (second/local-window judge call) detect the sentinel (~line 1259-1262)

old:
```
                    if local_window_text:
                        verdict2, reason2 = _get_judge().judge(
                            sentence_clean, local_window_text,
                        )
                        _record_judge_outcome(verdict2, reason2)
                        if verdict2 in ("NEUTRAL", "CONTRADICTED"):
```
new:
```
                    if local_window_text:
                        verdict2, reason2 = _get_judge().judge(
                            sentence_clean, local_window_text,
                        )
                        _record_judge_outcome(verdict2, reason2)
                        if verdict2 == "ENTAILED" and reason2.startswith("judge_error:"):
                            judge_error_flag = True
                        if verdict2 in ("NEUTRAL", "CONTRADICTED"):
```

---

## EDIT 8 — Delta 3 ON-mode fail-closed gate + additive return field (the function's final return, ~line 1301-1308)

old:
```
    is_verified = len(failures) == 0
    return SentenceVerification(
        sentence=sentence,
        tokens=tokens,
        is_verified=is_verified,
        failure_reasons=failures,
        soft_warnings=soft_warnings,
    )
```
new:
```
    # Phase 0b Delta 3 (I-meta-005, gap-#18): ON-mode fail-closed on the
    # judge-error sentinel. off = flag set but is_verified UNCHANGED (pre-0b
    # fail-open preserved, byte-identical). shadow = log only. enforce = DROP.
    if judge_error_flag:
        _vmode_j = _verification_mode()
        if _vmode_j == "enforce":
            ev_ids = ",".join(sorted({t.evidence_id for t in tokens})) if tokens else ""
            failures.append(f"entailment_judge_error_fail_closed:{ev_ids}")
        elif _vmode_j == "shadow":
            logger.warning(
                "[provenance] SHADOW would_fail_closed_on_judge_error "
                "(enforce-mode would drop this sentence)",
            )

    is_verified = len(failures) == 0
    return SentenceVerification(
        sentence=sentence,
        tokens=tokens,
        is_verified=is_verified,
        failure_reasons=failures,
        soft_warnings=soft_warnings,
        judge_error=judge_error_flag,
    )
```

NOTE: `judge_error_flag` is initialized in EDIT 4 INSIDE the `for sentence ...`-style body block
right before `if not failures:`. Confirm it is in the SAME scope as the final return (same function
body indentation) — if the `if not failures:` is nested inside a loop/with, hoist the
`judge_error_flag = False` init to the top of the function body (right after `failures: list[...] = []`
is created) so it is always defined at the return. **The build agent MUST verify this scope** and
adjust the init placement if needed (defensive: a `NameError` at return would be a hard bug).

---

## EDIT 9 — additive dataclass field (SentenceVerification, ~line 398-407)

old:
```
    soft_warnings: list[str] = field(default_factory=list)


def parse_provenance_tokens(sentence: str) -> list[ProvenanceToken]:
```
new:
```
    soft_warnings: list[str] = field(default_factory=list)
    # Phase 0b Delta 3 (I-meta-005, gap-#18): True when the entailment judge
    # failed OPEN ((ENTAILED,"judge_error: ...")). Additive, default False —
    # inert in off mode (is_verified unchanged). ON mode (enforce) reads this
    # to fail-closed. OFF byte-identity is defined over behavioral/output
    # fields + rendered artifacts, NOT raw dataclass asdict (Codex iter-3 P2).
    judge_error: bool = False


def parse_provenance_tokens(sentence: str) -> list[ProvenanceToken]:
```

---

## SMOKE TESTS — new file `tests/polaris_graph/generator/test_verification_mode_phase0b.py`

HEAVY coverage. A fake judge is injected by monkeypatching
`src.polaris_graph.clinical_generator.strict_verify._get_judge` to return an object with a
`.judge(sentence, span) -> (verdict, reason)` method. Also set `PG_STRICT_VERIFY_ENTAILMENT=enforce`
so the judge branch runs where a delta needs it. Build the evidence_pool + provenance-tokened
sentences with the module's real helpers (no mocking of evidence DB). Required cases:

- **S0b-1 OFF byte-identity:** with `PG_VERIFICATION_MODE` unset (off), run a representative battery
  (a grounded sentence that passes; a content-floor-miss sentence that fails
  `no_content_word_overlap_any_cited_span`; a numeric-miss; a trial-name-miss). Assert `is_verified`
  and `failure_reasons` EXACTLY match the pre-0b expected values. (This is the regression wall.)
- **S0b-2 Delta 1 rescue:** sentence whose NARROW cited byte-range misses content words but the FULL
  cited row (direct_quote) contains >=2. off → dropped (`no_content_word_overlap...`); enforce →
  is_verified True (rescued, no that failure); shadow → dropped (output == off) + a `SHADOW_would_rescue`
  log emitted (assert via caplog).
- **S0b-3 Delta 2 rescue:** NON-NUMERIC sentence; fake judge returns NEUTRAL on the narrow combined_span
  but ENTAILED on the bounded local content window. off → dropped (`entailment_failed`); enforce →
  is_verified True (rescued via content-window re-judge); shadow → dropped (output == off, no extra
  judge call — assert the fake judge call-count for shadow == off).
- **S0b-4 Delta 3 judge-error:** fake judge returns `("ENTAILED","judge_error: ConnectError")`.
  off → is_verified True AND `judge_error is True` (byte-identical pass, flag inert); shadow →
  is_verified True + judge_error True + `SHADOW would_fail_closed_on_judge_error` log; enforce →
  is_verified False with `entailment_judge_error_fail_closed:` in failure_reasons.
- **S0b-5 ANTI-LAUNDERING (LETHAL):** a TRUE fabrication whose content words are SCATTERED across the
  cited row beyond a 400-char window (place them >400 chars apart). enforce → STILL dropped (the
  bounded window must NOT rescue a scattered/fabricated claim). This is the clinical-safety gate: a
  rescue that passes this case is a regression and MUST fail the build.
- **S0b-6 bounded-window unit:** `_find_local_content_window` returns None when <min words present;
  returns a window with `end - start <= 400`; returns None when the only matches are >400 chars apart.
- **S0b-7 reproduction:** invoke `scripts/rediagnose_gap18.py` (with repo root on PYTHONPATH) or import
  its harness; assert the gap-#18 sentence that dropped under off now passes under
  `PG_VERIFICATION_MODE=enforce`, and that a genuinely-unsupported sentence still drops.

Run serialized (no parallel pytest, §8.4). All 7 must pass. The S0b-1 byte-identity wall and the
S0b-5 anti-laundering gate are the two that MUST NOT be relaxed to make the build green.
