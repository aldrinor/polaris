# Implementation Brief — I-meta-005 Phase 0b (GH #984, gap #18): the REAL drop-regime fix

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

---

## 0. HARD CONSTRAINTS (operator-locked — NOT Codex-consultable; do not offer the relaxed option)

1. **The faithfulness wedge is preserved, never weakened.** Every existing FAIL in `verify_sentence_provenance` stays a FAIL. The 0b change only RESCUES sentences that are dropped TODAY for a *byte-range-precision* reason while their support genuinely exists in the cited rows; it may never convert a today-DROP-for-fabrication into a PASS.
2. **`no_provenance_token` stays an ABSOLUTE drop.** A sentence with zero `[#ev:...]` tokens is dropped, unchanged (`provenance_generator.py:957-964`). 0b does NOT invent attribution for token-less prose (see §1.3 — that is a separate, deferred phase). This is the safest cut and the one Codex's proof leaves open.
3. **Kill-switch default OFF / shadow.** `PG_VERIFY_REASONING_MODE` defaults OFF. OFF ⇒ byte-identical pass-through to today's `strict_verify`/`verify_sentence_provenance`. No live spend in this PR.
4. **Open-weight, judge-agnostic.** The rescue runs whatever `_get_judge()` resolves to (TODAY that is `google/gemma-4-31b-it` via `PG_ENTAILMENT_MODEL` — see §4, reconciled honestly). 0b adds NO new served model and does NOT re-point the judge to the locked Qwen/Granite. Two-family segregation (§9.1.1) is already enforced at judge construction (`entailment_judge.py:134-140`).
5. **Fail-CLOSED everywhere.** Every new branch defaults to DROP. A rescue is granted only on an explicit ENTAILED verdict whose reason is NOT a `judge_error:` sentinel. An unsupported inference stays dropped.
6. **§-1.1 line-by-line, clinical-safety-critical.** No metadata/count/string-presence reasoning. Every claim below is verified claim-by-claim against the real `provenance_generator.py` lines and a reproducible offline verifier run (§6).

---

## 1. WHAT THIS PHASE FIXES — the REAL gap #18 (re-diagnosed; the prior premise is dead)

### 1.1 The prior brief premise was REFUTED by Codex's proof — and I reproduced the refutation on the real verifier

The prior 0b brief framed the fix as "verify analytical sentences against the UNION of their cited spans." Codex's brief-gate verdict (`.codex/I-meta-005-phase-0b/codex_brief_verdict.txt`, iter 1, `verdict: REQUEST_CHANGES`) ran a fake-judge proof and refuted that premise. **I re-ran the REAL production verifier OFFLINE** (deterministic fake judge, zero spend) and confirmed it:

> **Union entailment ALREADY EXISTS.** `verify_sentence_provenance` collects every cited byte-range into `aggregated_span_text` (`provenance_generator.py:1009-1012`) and judges entailment against `combined_span = " ".join(aggregated_span_text)` (`:1199-1202`). A 2-span A∧B number-free reasoning sentence **PASSES today** (harness CASE 1, CASE 4, CASE 8 → `is_verified=True`; the judge demonstrably received `span A + span B` concatenated, printed as `first_judged_span`).

A duplicate union-rescue would fix nothing. **The 0b fix targets a different, real drop regime.**

### 1.2 The REAL drop causes of grounded reasoning — PROVEN per-case on the running verifier (§6 harness)

Verifier under test = `provenance_generator.verify_sentence_provenance` / `strict_verify` — the function the production sweep actually calls (`scripts/run_honest_sweep_r3.py:58` imports `strict_verify` from `provenance_generator`; `multi_section_generator.py:1471` calls it). The separate `clinical_generator/strict_verify.py` path (which DOES have an `is_synthesis_claim=True` token-less escape at `:208,224,236-239`) is **not** the production path and is out of scope.

| Harness case | Sentence shape | Result | Regime that fires (`provenance_generator.py`) |
|---|---|---|---|
| CASE 1 / 4 / 8 | A∧B reasoning, **with** `[#ev:a][#ev:b]`, judge ENTAILED on union | **PASS** | none — union already built + judged (`:1199`) |
| CASE 2 | same reasoning, **NO** `[#ev:...]` token | **DROP** | `no_provenance_token` `:957-964` (0 judge calls) — STAYS (Constraint #2) |
| **CASE 3b** | **narrow cited byte-range** of a row whose FULL text shares the vocabulary | **DROP** | `no_content_word_overlap_any_cited_span` `:1135-1144` — floor computed against the **cited byte-range only** (`:1136`); judge never runs |
| CASE 7 | number-free, overlap≥2, judge NEUTRAL even on the union | **DROP** | `entailment_failed` fail-closed `:1204` → `:1284-1291`; the NEUTRAL→local-window rescue (`:1244 if not sentence_dec_local: continue`) NEVER fires for non-numeric prose |
| CASE 9 | A∧B reasoning, judge **fails OPEN** `("ENTAILED","judge_error: ConnectError")` | **PASS (wrongly)** | none — sentinel treated as real ENTAILED (`:1200-1204` never inspects `reason`) |
| CASE 5 / 6 | reasoning sentence carrying a NUMBER absent from every span | **DROP (correct)** | `no_integer_overlap_any_cited_span` — these are FACTUAL, not analytical; STAYS |

Verbatim from the run (`outputs/rediagnose_gap18_output.txt`):
- CASE 3b: `no_content_word_overlap_any_cited_span:a,b:sentence_words=['change','decarbonization','industry','reflects','regional']`; printed evidence: `narrow-union overlap: []` vs `FULL-row overlap: ['change','decarbonization','industry','regional','structural']` (5 shared content words in the cited rows, 0 in the cited byte-range).
- CASE 7: `entailment_failed:a,b:verdict=NEUTRAL:reason=premise not present in this span`.
- CASE 9: `is_verified: True` — the leak.

### 1.3 THE 0b SCOPE — three deltas, each with an accepted precedent or a hard test. NOT a union rescue.

**Delta 1 (PRIMARY) — content-floor narrow-span wrongful drop (CASE 3b).** When the writer cites a *narrow* byte-range of a cited row whose **full text** shares the synthesis vocabulary, the content-word floor (`:1139`, computed against the cited byte-range at `:1136`) drops the sentence **before the judge ever runs**. This is the **exact same shape** as the already-ACCEPTED I-gen-005 numeric fix `_find_local_support_window` (`:651-771`, "the numbers ARE in the cited evidence — just not in the cited byte range") — but for the *content-word* lane instead of the *decimal* lane. The fix widens the floor's candidate to the **full cited rows**, then BINDS entailment on the bounded union, fail-closed. **This is the dominant fixable delta** and the spine of 0b.

**Delta 2 — non-numeric NEUTRAL has no local-window rescue (CASE 7).** The NEUTRAL→local-window second-chance (`:1229-1291`) is gated on `sentence_dec_local` (decimals): `:1244 if not sentence_dec_local: continue` → `local_window_text` stays `None` → fail-closed at `:1284`. A genuinely-grounded number-free reasoning sentence judged NEUTRAL on the narrow span gets **zero** rescue. Delta 2 extends the same bounded-window discipline to non-numeric prose: propose a content-words-only window in the cited rows, re-judge, accept iff ENTAILED, else fail-closed.

**Delta 3 — judge-error fail-OPEN leak (CASE 9, Codex P1 #3).** `_EntailmentJudge.judge()` returns `("ENTAILED", "judge_error: …")` on API/parse failure (`entailment_judge.py:147-148` docstring, `:261` return). The verifier only branches on `verdict in ("NEUTRAL","CONTRADICTED")` (`:1204`) and never inspects `reason`, so a `judge_error:` ENTAILED rides through. The reasoning lane MUST DROP any ENTAILED whose `reason.startswith("judge_error:")`. The test must feed the **return-shape sentinel**, not a *raising* fake judge (a raise is a different code path).

**Explicitly DEFERRED out of 0b (so Codex can rule):** token-less reasoning attribution (CASE 2 / `no_provenance_token`). Earning span attribution for prose the generator emitted with NO token is an *attribution-generation* problem (how does a grounded reasoning sentence EARN a `[#ev:...]` anchor it never carried?), and it is **structurally non-repairable today**: `no_provenance_token` is NOT in `sentence_repair.REPAIRABLE_REASON_PREFIXES` (`:64-71`), `is_repairable()` returns False (`:94-108`), and the token-set-preservation invariant (`:20-24, _extract_token_signature`) rejects any repair that ADDS a token. Folding that into 0b would (a) blow the 200-LOC cap, (b) open a model-chosen-attribution leak surface that violates Constraint #5's fail-closed posture. **0b keeps `no_provenance_token` an absolute drop** and files token-less attribution as a separate phase. *(Codex scope question §9: if you judge token-less attribution must be in 0b, say so and I re-scope.)*

---

## 2. FILE LAYOUT (careful; snake_case; one canonical brief path)

| Path | New/edit | Purpose |
|---|---|---|
| `.codex/I-meta-005-phase-0b/brief.md` | this file (canonical, overwrite) | the build contract |
| `src/polaris_graph/generator/verification_mode_router.py` | NEW | `verify_sentence_with_mode()` + `_reasoning_mode_enabled()` + the reasoning lane (`_classify_reasoning_sentence()`, `_rescue_content_floor_on_full_rows()`, `_rescue_neutral_nonnumeric()`, `_drop_on_judge_error()`) |
| `src/polaris_graph/generator/provenance_generator.py` | EDIT (1 call-site) | route the single findings-loop call through `verify_sentence_with_mode` (§3) |
| `tests/polaris_graph/test_verification_mode_router.py` | NEW | the §6 heavy offline smoke (10 groups) |
| `scripts/rediagnose_gap18.py` + `outputs/rediagnose_gap18_output.txt` | EXISTS (diagnosis artifact) | reproducible proof of the drop regimes; referenced, not shipped as product |

The router lives in a NEW module (not inline) because `verify_sentence_provenance` is ~380 lines of locked wedge logic with a 2026-05-30 composition-fix lock; **wrapping** it (never editing its body) is the only way to guarantee byte-identity when OFF. The router IMPORTS `verify_sentence_provenance` and the helper predicates; it does not fork them.

---

## 3. THE DROP-IN, PRECISELY (file:line; OFF byte-identical)

### 3.1 Public entry + kill-switch (byte-identical when OFF)

New `verification_mode_router.py`:

```
def verify_sentence_with_mode(
    sentence: str,
    evidence_pool: dict[str, dict[str, Any]],
    *,
    require_number_match: bool = True,
) -> SentenceVerification:
    base = verify_sentence_provenance(
        sentence, evidence_pool, require_number_match=require_number_match
    )
    if not _reasoning_mode_enabled():        # default OFF — read at call time via os.getenv
        return base                          # byte-identical: same object, same failure_reasons
    if base.is_verified:
        return base                          # never weaken a PASS
    return _maybe_rescue_reasoning(sentence, evidence_pool, base)
```

- `_reasoning_mode_enabled()` reads `PG_VERIFY_REASONING_MODE` via `os.getenv` at call time (mirrors `_trial_name_span_fallback_enabled()` at `:896-901`) so tests flip it per-case.
- OFF ⇒ returns `verify_sentence_provenance(...)` verbatim. This is the byte-identity Codex must confirm.
- ON ⇒ rescue is attempted ONLY for an already-FAILED sentence (`base.is_verified is False`), and ONLY for the three deltas in §3.3. Every other failure reason passes through unchanged (still dropped).

### 3.2 The single seam edit in `provenance_generator.py`

`strict_verify` (the production drop-loop, def `:1467`) calls `v = verify_sentence_provenance(...)` per sentence at `:1494`. Change THAT ONE call to `verify_sentence_with_mode(...)` (lazy import to avoid a circular import: the router imports `provenance_generator`). No other call site changes; `multi_section_generator.py:1471,1568` keep calling `strict_verify`; `sentence_repair.py:360` re-verifies via `verify_sentence_provenance` directly and is intentionally left unchanged (repair operates on its own pre-token-set-preservation contract). Diff blast radius: 1 import + 1 call.

### 3.3 The reasoning lane (`_maybe_rescue_reasoning`) — fail-CLOSED, judge-bound

Reached only when `base.is_verified is False` AND mode ON. **Gate first:** the sentence is eligible for the reasoning lane ONLY if it is genuinely analytical — `_classify_reasoning_sentence()` returns ANALYTICAL iff the sentence is free of every hard-claim signal (any decimal via `_decimals_in` `:646-648`; any standalone number via `_numbers_in` `:641-643` after dose/placebo/threshold strips; any named trial via `extract_trial_names` `:851-869`; any dose/unit/`%`/currency via `_DOSE_PATTERN_RE` `:441-444`; any qualitative-negation cue). FACTUAL is the fail-safe default; over-routing to FACTUAL costs recall, never faithfulness (Codex confirmed this cut is safe). A sentence whose ONLY failure reasons are FACTUAL regimes (`no_integer_overlap_any_cited_span`, `number_not_in_any_cited_span`, `trial_name_mismatch`) is NOT eligible — those stay dropped (CASE 5/6).

Then, by failure reason:

- **Delta 1 — `no_content_word_overlap_any_cited_span` (CASE 3b):** rebuild the candidate text as the **full cited rows** (`direct_quote` per cited evidence_id, the rows the tokens already point at — NOT whole-corpus, NOT uncited rows). Recompute the `_content_words` overlap (`:774+`, `MIN_CONTENT_WORD_OVERLAP=2`, `:813`) against the full cited rows. If still `< 2` → stays dropped. If `≥ 2`, propose a **bounded** ≤400-char window inside the cited rows that contains those overlapping content words (reuse the `_find_local_support_window` discipline, `:651-771`, content-words path), then BIND entailment: `_get_judge().judge(sentence_clean, window_text)`; accept iff ENTAILED-and-not-judge-error (Delta 3); else fail-closed. **Whole-row proposes, bounded window binds** — preserves the 2026-05-30 composition lock (never bind on a whole-document blob).
- **Delta 2 — `entailment_failed` on a NON-NUMERIC sentence (CASE 7):** the existing code already fails-closed here because `:1244` skips the window search when there are no decimals. The lane re-attempts the same bounded content-words-only window inside the cited rows, re-judges, accepts iff ENTAILED-and-not-judge-error; else fail-closed on the original NEUTRAL.
- **Delta 3 — judge-error sentinel (CASE 9):** ANY judge call inside the lane that returns `("ENTAILED", reason)` with `reason.startswith("judge_error:")` is treated as **NOT a pass** → the sentence stays dropped with a new reason `analytical_judge_unusable:<ev_ids>:reason=<reason[:60]>`. The rescue is granted **iff** `verdict == "ENTAILED" AND NOT reason.startswith("judge_error:")`.

A rescued sentence returns a `SentenceVerification` (`:398-407`) with `is_verified=True`, the SAME tokens, and a `soft_warnings` entry `analytical_rescue:content_floor_full_row` / `analytical_rescue:neutral_window` so the manifest can count rescues (observability; non-blocking).

---

## 4. THE MODEL PATH, RECONCILED HONESTLY (Codex P1 #2)

**Truth, against running code:** `_get_judge()` (`entailment_judge.py:301-306`) builds `_EntailmentJudge` whose model is `os.environ.get("PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL)` with `_DEFAULT_ENTAILMENT_MODEL = "google/gemma-4-31b-it"` (`:79,131-133`). This is the **legacy 2-family Gemma evaluator**, NOT the locked 4-role Judge `qwen/qwen3.6-35b-a3b` (`polaris_runtime_lock.yaml:80`) or Sentinel `ibm-granite/granite-guardian-4.1-8b` (`:70`). The lock's role env vars exist but `entailment_judge.py` does not read them. The prior brief's claim that `_get_judge()` *is* the locked Sentinel/Judge was FALSE.

**Recommendation for 0b: KEEP the legacy `_get_judge()` path unchanged.** Re-routing the entailment seam to the locked Qwen/Granite is a model-stack migration governed by the lock mutation policy (`polaris_runtime_lock.yaml:11-15` — separate Codex APPROVE + operator signature) and would blow the 200-LOC cap. 0b's rescue logic is judge-agnostic (proven offline with a fake judge); at enforce-time it uses whatever `_get_judge()` resolves to — the **same** judge the adjacent decimal-window wedge already uses, so 0b introduces no new judge inconsistency. File the Qwen/Granite migration as a **separate lock-governed Issue**. *(Codex scope question §9: rule whether that migration must fold into 0b or stay separate.)*

---

## 5. WHAT STAYS BYTE-IDENTICAL (the wedge to preserve exactly)

For any sentence when `PG_VERIFY_REASONING_MODE` is OFF, and for any FACTUAL-classified or already-PASS sentence when ON, ALL of the following are UNCHANGED (verified against the real code):

- **`no_provenance_token` absolute drop** — `:957-964`. (STAYS — Constraint #2; the lane never rescues token-less prose.)
- **Every-decimal-must-appear-in-span** — `:1029-1076`, incl. `_find_local_support_window` ≤400-char window (`:651-771`) and token-exact (`50`≠`150`) matching.
- **`no_integer_overlap_any_cited_span` / `number_not_in_any_cited_span`** — the numeric regimes that correctly drop CASE 5/6. Not eligible for the lane.
- **≥2 content-word overlap floor against the cited byte-range** (`:1135-1144`) for FACTUAL/OFF paths. The lane does NOT lower the floor (still ≥2); it only re-evaluates the floor against the **full cited rows** for ANALYTICAL sentences, then re-binds entailment.
- **Named-study identity** (M-25a trial-name gate `:1146-1169`, SURMOUNT-1≠SURMOUNT-3 lock, title-authority span-fallback `:904-927`).
- **Entailment fail-closed on NEUTRAL/CONTRADICTED** with bounded-window discipline (`:1183-1291`). The lane EXTENDS the rescue to non-numeric prose; it never converts a NEUTRAL to a PASS without an explicit ENTAILED re-judge on a bounded window.

The router NEVER edits the body of `verify_sentence_provenance`; it wraps it. **No factual/numeric/trial rule is touched.** If any is, that is a P0.

---

## 6. HEAVY OFFLINE SMOKE (`tests/polaris_graph/test_verification_mode_router.py`) — targets the REAL failure mode

Deterministic fake judge, `PG_STRICT_VERIFY_ENTAILMENT=enforce`, zero network/spend. The 10 groups mirror the `scripts/rediagnose_gap18.py` battery so the test proves the SAME deltas the diagnosis proved.

1. **OFF byte-identity.** For all 10 fixtures, `verify_sentence_with_mode(...)` with mode OFF returns a result equal (is_verified + failure_reasons) to `verify_sentence_provenance(...)`. No judge call in OFF for FACTUAL/no-token cases.
2. **Union-already-works baseline (CASE 1/4/8).** A∧B token-bearing number-free sentence that the judge ENTAILS is `is_verified=True` BOTH OFF and ON — proves the rescue is NOT a duplicate union rescue (it is never invoked here because base already PASSES).
3. **Delta 1 rescue (CASE 3b).** Narrow-byte-range sentence dropped `no_content_word_overlap_any_cited_span` OFF → ON, full-cited-row overlap ≥2 + judge ENTAILS bounded window → `is_verified=True` with `analytical_rescue:content_floor_full_row`. Companion: SAME fixture where the full rows still share <2 content words → stays dropped ON (proves the floor still bites; no blanket pass).
4. **Delta 2 rescue (CASE 7-positive).** Non-numeric sentence dropped `entailment_failed` (NEUTRAL on narrow span) OFF → ON, judge ENTAILS the bounded content-words window → rescued. Companion: judge NEUTRAL on the window too → stays dropped ON (fail-closed).
5. **Delta 3 hard test — judge-error sentinel DROP (CASE 9).** A fake judge **RETURNING** `("ENTAILED", "judge_error: ConnectError")` → ON yields `is_verified is False` with `analytical_judge_unusable:` in `failure_reasons`. **Companion** assertion: the SAME sentence with a clean `("ENTAILED","ok")` judge IS rescued ON — isolates the sentinel as the cause (prevents a test that trivially drops everything). A *raising* fake judge is explicitly NOT used for this assertion (wrong code path).
6. **Unsupported inference still drops (CASE 5).** Planted unsupported A∧B inference, judge NEUTRAL on every window → DROP ON (the safety property).
7. **Factual numeric still drops (CASE 6).** Number absent from every span → `no_integer_overlap_any_cited_span` → not lane-eligible → DROP ON, byte-identical to OFF.
8. **`no_provenance_token` stays absolute (CASE 2).** Token-less reasoning → DROP ON, `failure_reasons == ['no_provenance_token']`, unchanged from OFF, ZERO judge calls (Constraint #2).
9. **Classifier fail-safe direction.** A sentence with an incidental year/count or a dose token is classified FACTUAL → routed to base path → not rescued (over-route-to-FACTUAL is safe). Assert a qualitative-negation sentence ("did not reduce") is FACTUAL, never analytical.
10. **Determinism + no shadow spend.** Two ON runs on the same fixture give identical results; the judge-call counter is 0 for every OFF case and for every FACTUAL/no-token ON case (no shadow judge billing).

Plus: `pytest tests/polaris_graph/` stays green (cancer-50% window, SURMOUNT identity, dash/range, comma/range, trial-alias regressions all pass — the wedge is untouched).

---

## 7. KILL-SWITCH + LAW VI (zero hard-coding)

- `PG_VERIFY_REASONING_MODE` — default OFF; the ONLY switch that activates the lane. Read at call time.
- The content-overlap floor stays `MIN_CONTENT_WORD_OVERLAP` (env `PG_PROVENANCE_MIN_CONTENT_OVERLAP`, `:813-815`); the lane does not introduce a second magic threshold.
- The ≤400-char window reuses the existing `window=400` constant in `_find_local_support_window` (`:655`); no new literal.
- The judge model stays `PG_ENTAILMENT_MODEL` (`entailment_judge.py:131-133`); no hard-coded slug in the router.
- No file path, threshold, or batch size is hard-coded in `verification_mode_router.py`; all derive from the existing env/config surface (LAW VI).

---

## 8. EXIT CRITERION

0b is GREEN when: (a) `PG_VERIFY_REASONING_MODE` OFF is byte-identical to today across all 10 fixtures (smoke group 1); (b) the three deltas rescue ONLY genuinely-grounded analytical sentences (groups 3/4/5 positive) and DROP every unsupported/numeric/token-less/judge-error case (groups 5/6/7/8 negative); (c) `no_provenance_token`, the numeric regimes, and the trial-identity gate are untouched (groups 7/8 + full suite green); (d) no new served model, no live spend, ≤200 LOC; (e) Codex APPROVE on brief and diff.

---

## 9. RISKS + Codex-web-verify list

**Risks (P-classified honestly):**
- **R1 (P2):** the Delta-1 full-cited-row widening could, in principle, let a synthesis sentence clear the floor against vocabulary in a part of the cited row the writer did not point at. **Mitigation:** the floor-clear only PROPOSES a candidate; the **bounded ≤400-char window** + the ENTAILED re-judge BINDS, fail-closed — identical discipline to the accepted I-gen-005 numeric widening. Codex should confirm the bounded-bind preserves the composition lock.
- **R2 (P3):** classifier over-routing legitimately number-free analytical prose with an incidental year to FACTUAL costs recall (the sentence gets today's strict path). This is the SAFE direction (Codex already confirmed); no faithfulness loss.
- **R3 (P2):** `analytical_rescue:*` soft-warnings add manifest fields; additive-only on `SentenceVerification.soft_warnings` (`:407`), no consumer breaks.

**Codex must web-verify (flagged per task rules — attribution-technique correctness):**
1. **Full-cited-row content-floor widening faithfulness** to the 2026-05-30 composition lock (whole-row *proposes*, bounded window *binds*): is leave-one-span-out / ALCE citation-precision the right guard against "cite a vocabulary-rich row to launder overlap," or is the bounded-window + ENTAILED re-judge sufficient on its own? (ALCE: https://aclanthology.org/2023.emnlp-main.398.pdf)
2. **NEUTRAL-on-missing-premise as fail-closed** on the resolved judge (MiniCheck/Granite grounded-entailment): confirm NEUTRAL behaves as DROP on the model `_get_judge()` actually resolves to. (https://aclanthology.org/2024.emnlp-main.499/)
3. **Scope ruling:** does token-less reasoning attribution (CASE 2 / `no_provenance_token`, the deferred phase in §1.3) belong in 0b, or as a separate attribution-generation Issue? And does the Qwen/Granite judge migration (§4) fold into 0b or stay a separate lock-governed Issue? These are scope calls per §8.3.10 — Codex decides.

---

## Output schema bound (§8.3.9)

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

## ADDENDUM — Codex brief-gate iter-2 P1 (Delta 3 made executable; 2026-05-31). BINDING.

Codex iter-2 (continuing P1): the proposed wrapper returns `base` when `base.is_verified` is True, but the current
verifier marks `("ENTAILED","judge_error: ...")` as `is_verified=True` and `SentenceVerification` does NOT carry the
judge reason — so the ON-mode judge-error DROP cannot fire. CORRECTED Delta-3 design:

1. **Additive flag (OFF byte-identical):** add `judge_error: bool = False` to `SentenceVerification` (`:398-407`,
   additive default False → OFF behavior + existing fields UNCHANGED, byte-identical). In `verify_sentence_provenance`,
   at the judge call (`:1200-1204`), when `result == "ENTAILED" and reason.startswith("judge_error:")`, set
   `judge_error=True` on the returned `SentenceVerification` (still `is_verified=True` in OFF — preserves today's
   behavior exactly, the pre-existing fail-open is NOT changed in OFF).
2. **ON-mode fail-closed (executable now):** the verification-mode router, after calling the base verifier, in
   shadow/enforce mode: `if base.judge_error: DROP` (fail-CLOSED) REGARDLESS of `base.is_verified`. So ON mode
   fails-closed on a judge crash even though the base returned verified.
3. **Smoke (real sentinel, both modes):** fake judge returns `("ENTAILED","judge_error: ConnectError")`; assert OFF →
   `is_verified=True` + `judge_error=True` (byte-identical pass, flag set, inert); ON/enforce → DROPPED (fail-closed).
4. **The OFF fail-open is filed as a SEPARATE pre-existing safety issue** (verifier should fail-closed on judge_error
   in OFF too, but that changes OFF behavior → its own gated change). 0b does NOT silently change OFF.

This makes Delta 3 executable while keeping OFF byte-identical. Deltas 1+2 unchanged (Codex confirmed real+distinct).
Re-run note: `scripts/rediagnose_gap18.py` needs repo root on PYTHONPATH (`PYTHONPATH=. python scripts/rediagnose_gap18.py`).
