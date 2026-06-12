# Keystone map-reduce collapse — consolidated forensic (Claude + Codex, #1217)

**Both independent forensics CONVERGED on the same structural root cause, with file:line proof.** This consolidates the parallel Claude-agent forensic and the Codex forensic, reconciled with the live-run facts and the `PG_DISTILL_DEBUG` dump.

## The symptom
The map-reduce evidence distiller (#1209 keystone) makes every section EMPTY on the real model. 3 live drb_76 Safety-section runs (deepseek-v4-pro): the DISTILL arm always yields **0 strict_verify-VERIFIED sentences** (drop_rate 1.00, output = the 29-word "no claim survived ... curator-actionable gap" placeholder), while the LEGACY arm on the same evidence yields 6–9 verified (drop_rate ~0.5).

## ROOT CAUSE (both agree): who computes the provenance span offsets
- **LEGACY** (`multi_section_generator.py:1754-2057`): the writer emits only SHORT `[ev_XXX]` markers and never picks character offsets. `_rewrite_draft_with_spans` (`live_deepseek_generator.py:335-386`) recognizes them via `_EV_MARKER_RE` (`:64` = `\[([A-Za-z_][A-Za-z0-9_]*)\]`) and calls `_find_best_span_for_sentence` (`:244-332`), which scans the whole `direct_quote` and returns the span maximizing decimal + content-word overlap with the ACTUAL sentence — i.e. it computes spans **designed to pass strict_verify**.
- **REDUCE (broken)**: `_REDUCE_SYSTEM` (`evidence_distiller.py:183-192`) told the model to emit the FULL `[#ev:evidence_id:start-end]` token itself, copying `span={start}-{end}` from the ledger (`render_reduce_user`). That full token starts with `[#`, and `#` is NOT in `_EV_MARKER_RE`'s character class — so `_rewrite_draft_with_spans` passes the REDUCE sentence through **UNCHANGED** (`live_deepseek_generator.py:349-352`). The model's hand-typed offsets are frozen and never re-fit to the prose.

The 100% drop is **overdetermined by two output-side killers** (Claude's precision), both downstream of the (non-empty) ledger:
- **Killer A:** model-transcribed offsets fail the span-bounds check (`provenance_generator.py:1635-1644`) → `valid_token_found=False` (`:1645`); every rescue is gated on that flag → drop with no recovery. Even in-bounds-but-off offsets miss the ≥2 content-word overlap (`:1809-1813`) + enforce-mode entailment (`strict_verify.py:173,187`). A MAP support_quote span is NARROW (one atomic finding); the REDUCE sentence is a SYNTHESIS, so a narrow span shares <2 content words with it.
- **Killer B:** `filter_and_strip_reduce_markers` hard-required a KNOWN `[[finding:fXXX]]` marker whose synthetic id the model must reproduce verbatim. If the model didn't echo it, the sentence died at the filter before strict_verify ran.

**Refuted suspects:** (d) "different text" — strict_verify resolves against `direct_quote`, the SAME text the distiller validates against (refuted); (e) reasoning-starvation — the REDUCE wrote 50/57/709 content tokens, yet 0 survived (refuted). The `PG_DISTILL_DEBUG` dump confirmed: ledger=1 finding, REDUCE raw prose present, but the model emitted `[#ev:f004_000:5430-5539]` (finding_id as evidence_id, on a separate sentence) → filter kept only the bare token, prose dropped.

## Why the 3 prior fixes missed it
All three acted MAP/ledger-side: (1) span-recovery improved the LEDGER not the model-typed OUTPUT offsets; (2) the relaxed marker filter still kept the `has_known_finding` gate; (3) non-blocking per-finding entailment grew the ledger but the final per-sentence strict_verify on the model-authored token was unchanged. The wall is the REDUCE-output citation FORMAT, which none touched. (This empirically refuted the earlier H1 "entailment starves the ledger" call — fix #3 changed nothing.)

## THE FIX (both agree; strict_verify UNWEAKENED)
Stop trusting the LLM's offsets; emit the SAME short-marker contract legacy uses and let the deterministic prose-matched span finder compute offsets.
1. `_REDUCE_SYSTEM` + `render_reduce_user` (`evidence_distiller.py:183-192, 241-274`): cite each sentence with short `[<evidence_id>]` (legacy `[ev_XXX]` shape); drop `span=` from ledger lines so offsets are never transcribed; "Do not emit `[#ev:...]` span tokens."
2. `filter_and_strip_reduce_markers` (`:1028-1087`): accept a bare `[ev_XXX]` marker for a known source (normalize any stale `[#ev:...]` back to `[ev_XXX]`); strip `[[finding:...]]`, KEEP the short marker for `_rewrite_draft_with_spans`. (Killer-B residue: if the `has_known_finding` requirement still drops prose, relax `[[finding]]` to optional — require only a known short `[ev_id]`.)
3. `multi_section_generator.py:2407` UNCHANGED — `_rewrite_draft_with_spans` now sees the short marker and computes prose-matched offsets via the identical legacy machinery (removes Killer A).

**Faithfulness untouched:** `strict_verify` still re-validates every span (numbers-in-span + ≥2 overlap + enforce entailment). **Map-reduce is NOT incompatible with strict_verify — only emitting final machine tokens FROM the LLM is.** This is also exactly what the distiller's own module docstring already described ("cite findings with the same legacy `[ev_XXX]` markers"); the implementation had drifted from its stated contract.

## Verification plan (the operator's loop)
1. Forensic (Claude + Codex) — DONE, converged. ✓
2. Consolidate — this doc. ✓
3. Fix — applied (short markers). 17 distiller tests pass.
4. PAID smoke on the VM (cheap A/B, `PG_DISTILL_DEBUG=1`) — confirmed: REDUCE emits short `[ev_XXX]` inline, prose survives, distill drop_rate 1.00 → 0.00 (was empty placeholder; now a real verified cited sentence). ✓ But distill kept only **1** verified vs legacy **6** — a RECALL gap surfaced (below).
5. Claude + Codex BOTH run forensic AGAIN on the fixed output — DONE, converged (below). ✓

---

## PART 2 — the RECALL gap (#1217 second collapse layer; both re-forensics AGREE)

After the short-marker fix removed the 100% collapse, the cheap 8-source VM smoke showed **distill 1 verified vs legacy 6**. Both independent re-forensics (Claude agent `a4faf584...`, saved `.codex/keystone_forensic/claude_reforensic_verdict.md`; Codex `.codex/keystone_forensic/codex_reforensic_verdict.txt`) converged on the same root cause and the same one-line fix.

**§-1.1 faithfulness of the fixed output — VERIFIED, zero fabrication (both):** the one kept distill sentence "Colibactin induces double-strand breaks in cultured cells [colibactin_pks_ecoli_mechanism]." is a near-verbatim, correctly-scoped restatement of the source `direct_quote` (~offset 5772: "...and **induces double-strand breaks in cultured cells**3."). Hedge handling faithful (the source's "is believed to" scopes to the alkylation clause, which the distiller dropped; the DSB clause is stated by the source as fact). No number distortion. The keystone fix introduced **no fabrication** — it only collapsed recall.

**Recall root cause (both):** `_validate_finding` step 4 `_all_numbers_in_span` (`evidence_distiller.py:584`) is a HARD reject when a claim's declared number is not inside the model's NARROW `support_quote`. But that quote never reaches the output — the REDUCE writes fresh prose cited `[ev_XXX]`, and the unchanged legacy `_rewrite_draft_with_spans` → `_find_best_span_for_sentence` (`live_deepseek_generator.py:244`) re-fits an 800-char prose-matched span over the WHOLE ~24.6k-char `direct_quote`, then strict_verify (`require_number_match=True`) re-checks numbers against THAT span. So step 4 is STRICTER than the final gate and pure recall loss with zero faithfulness benefit. Concrete killer (Codex): the CDC stat "14 (95% CI 4–44)" tokenizes "4–44" as ONE range token here while the model declares "4" and "44" separately → a perfectly extractable numeric finding is rejected before REDUCE; final strict_verify normalizes the range dash and would accept/drop the published span correctly. Evidence step-4-dominant: legacy's 6 verified are all numeric-heavy (OR 14, CI 4–44, 22%/10, 37%/17, 5,876 genomes); the lone distill survivor is the ONLY non-numeric claim — exactly what a narrow numbers-in-span filter leaves standing.

**THE FIX (both agree, candidate (b)):** make step 4 **non-blocking** at `evidence_distiller.py:584` — compute `numbers_in_span = _all_numbers_in_span(...)` for telemetry/debug, but do NOT `return None`. Mirrors EXACTLY the step-6 entailment treatment (lines 624–635: verdict computed, never gates). Step 4's own docstring says its only job was a "cheap local pre-filter ... before the (more expensive) entailment call" — and entailment is already non-blocking, so the pre-filter's rationale is dead. Brings distill to parity with legacy (which does zero numeric checking at extraction) WITHOUT weakening any gate.

**Faithfulness untouched:** `strict_verify` on the final REDUCE prose stays the SOLE publication authority (numbers-in-span AND ≥2 content-word overlap AND enforce-mode entailment); 4-role / D8 byte-untouched. A genuinely fabricated number cannot reach the report — the final gate drops it.

**Rejected alternatives (both):** (a) wider MAP quote — prompt-brittle, makes step-1 locate HARDER; (c) fuzzy locate — larger new mechanism with its own false-accept surface, keep step 1 as the "real source slice exists" gate; (d) multiple findings/source — doesn't address rejection (all 8 MAP calls already produced findings; the loss is validation, not generation). **(b) is also diagnostic:** after it, step-1 locate is the only substantive rejector left; if recall still < legacy on re-prove, the residual is step-1 paraphrase and (c) is the surgical follow-up.

**Applied:** `evidence_distiller.py:583-593` step-4 made non-blocking (+ debug log); `test_map_rejects_out_of_span_numbers` → `test_map_keeps_out_of_span_numbers_nonblocking_1217` (asserts KEPT at MAP, final strict_verify is the number authority). 17/17 distiller tests pass. Next: scp to VM, cheap re-prove MAXEV=8 `PG_DISTILL_DEBUG=1`, confirm distill verified ≥ legacy + §-1.1 on the output, THEN Codex DIFF-gate before commit.

---

## PART 3 — RESOLUTION (committed 8d74d1bb, Codex diff-gate iter2 APPROVE)

The step-4-only fix from PART 2 was NOT sufficient — the live re-prove still collapsed (distill 0). The full root cause was **three stacked bugs**, all now fixed and committed. strict_verify / 4-role / D8 are byte-UNCHANGED.

### Bug A — orphaned-citation collapse (deterministic, 100% drop)
The REDUCE placed its `[[finding]]`/`[ev]` markers in a SEPARATE sentence after the claim's period (`split_into_sentences` → a marker-only fragment; the filter kept the fragment, dropped the claim prose → bare marker → strict_verify drops → placeholder). Reproduced offline on the exact VM string. **Fix:** `_is_marker_only_fragment` + a reattach pre-pass in `filter_and_strip_reduce_markers` (reattach an orphan to the preceding sentence; drop a leading orphan); tightened `_REDUCE_SYSTEM` / `render_reduce_user` to require markers inside the sentence before the terminal period (inline example).

### Bug B — paraphrased support_quote rejected at locate (the real recall collapse)
The single-source MAP **probe** on the CDC safety source [4] (`scripts/dr_benchmark/probe_source_map.py`) showed **"3 proposed, 0 validated"** — all 3 contraindications rejected at `step1_locate` because the MAP paraphrases (drops markdown italics `_S. cerevisiae_`, atomizes one source sentence) so the quote is not a verbatim/whitespace substring. These were the exact claims legacy verified. **Fix:** `_fuzzy_locate_span` (+ `_locate_span_with_method`) recovers the REAL source window by content-word overlap (threshold `PG_DISTILL_FUZZY_MIN_OVERLAP`, default 0.6), **EXPANDED to the enclosing sentence/clause** so a leading negation ("not recommended") is never dropped before the entailment check (Codex diff-gate P2, clinical). A FUZZY recovery must additionally **ENTAIL** the claim (blocking entailment for fuzzy ONLY — content-overlap is blind to "all"→"some"/negation flips); exact/whitespace stay non-blocking and **SKIP** the slow verifier call (Codex P2 perf — was per-finding, prohibitive at MAXEV=40).

### Bug C — stale cache masked the fix
`_cache_key` includes `DISTILLER_VERSION` but the validation logic changed without a bump, so a stale `section_distiller_v2` cache served pre-fix results (ledger=1, zero KEPT/REJECT traces) and the fuzzy-locate never ran on the 8-source A/B. The single-source probe worked only because it used a fresh temp cache. **Fix:** `DISTILLER_VERSION` v2→v4 + `_cache_key` now also includes `PG_DISTILL_FUZZY_MIN_OVERLAP` (threshold retuning must miss the cache). Diagnosed via the new `PG_DISTILL_DEBUG` per-rejection trace (`raw_index`/`step`/`reason`) + KEPT method trace.

### Live proof (clean fresh-cache MAXEV=8 A/B, deepseek-v4-pro, OVH VM)
distill no longer collapses: drop_rate 1.00 → 0.33, produces faithful verified contraindication prose; ledger findings fuzzy-recovered + entailed. **§-1.1 on the distill output = zero fabrication** — the one strict_verify-dropped numeric sentence cited a REAL source odds ratio ("OR 10, 95% CI 3–32"; both it and legacy's "OR 14, 95% CI 4–44" are in the source), dropped only on number-span binding.

### Codex diff-gate
iter1 APPROVE (mergeable_now, density not a blocker) + iter2 APPROVE (`faithfulness_fuzzy_gate_sound=true`, zero P0/P1/P2). 21/21 distiller + 100/100 generator tests; negation regression added.

### Remaining (filed as #1218 / I-perm-026 — NOT a faithfulness defect)
distill 2 < legacy 6: the MAP under-extracts on-topic safety numerics, and the REDUCE synthesizes numeric sentences whose numbers don't all bind to one span (→ strict_verify drops them, related to I-gen-005). The fix is a denser MAP prompt + one-number-per-sentence REDUCE. #1217 stays OPEN until #1218 closes the richness gap (distill ≥ legacy on the Safety section).

---

## PART 4 — THINNESS RESOLVED (#1218 / I-perm-026, committed 2e4d1a3a, Codex diff-gate APPROVE)

Dual Claude+Codex line-by-line forensic, then **four land mines cleared** (each found by reading the actual live output, not guessing). strict_verify / `_find_best_span_for_sentence` / 4-role / D8 byte-UNCHANGED; every change is MAP-extraction-side or REDUCE-output-shaping-side.

1. **MAP under-extraction** → `_MAP_SYSTEM`/`_render_map_user` told to extract EVERY distinct on-topic finding incl. every on-topic numeric outcome, each with a CONTIGUOUS support_quote holding all its numbers (split scattered).
2. **REDUCE numeric span-binding** → one numeric statistic per sentence (no multi-source numeric conjunctions) so numbers bind to one span; use EVERY finding; rewrite `[OR]`→`(OR)`.
3. **Off-topic over-extraction (the over-correction)** → an un-scoped "be exhaustive" intermediate strip-mined the bile-acid carcinogenesis source and wrote 19 OFF-topic disease-mechanism sentences (a count-win, §-1.1 fail). Fixed with an explicit on-topic SCOPE GUARD: safety section ON-TOPIC = harms/AE/contraindications/toxicity/infections/risks of THE INTERVENTION; OFF-TOPIC = general disease-causation mechanisms → `no_relevant_findings`. **Lesson: the harness's "distill verified count ≥ legacy" acceptance is GAMEABLE by off-topic over-extraction; the real gate is §-1.1 + on-topic relevance.**
4. **`ev_`-prefix marker resolution (data inconsistency)** → the evidence pool is inconsistent (457/462 ids start with `ev_`, a few key safety ids do NOT); the REDUCE sometimes added an `ev_` prefix so the marker failed to resolve and strict_verify dropped the faithful sentence (the v6 0-verified collapse). Fixed with `_normalize_ev_prefix` in `filter_and_strip_reduce_markers` (rewrite to the real ledger id) + REDUCE "copy cite verbatim". Offline-confirmed before any paid run.

`DISTILLER_VERSION` v4→v7. **Live (clean fresh-cache MAXEV=8 A/B, deepseek-v4-pro, OVH VM): distilled verified 2→13 vs legacy 7** (drop_rate 0.50→0.13); ledger=15 ALL from the CDC safety source (on-topic). **§-1.1 line-by-line on all 13 distilled sentences = ZERO fabrication** (S. boulardii fungemia OR 14 (95% CI 4-44) correctly attributed vs the distinct nonblood OR 10; 22%/37% fatality; "at least 20 (43%) of 46 fungemia patients"; antifungal changed for 23 (50%); the contraindications; the septic-shock death). Codex diff-gate APPROVE (zero P0/P1, faithfulness_risk LOW). 22/22 distiller + 100/100 generator tests. P2 follow-ups (de-dup duplicate numeric sentence; render_reduce_user wording) → #1219.

**The keystone now delivers its goal: faithful AND on-topic AND richer-than-legacy.**
