# TAIL-GATE GHOST AUDIT — outline_agent

**Repo:** `/home/polaris/wt/outline_agent` @ `b67506a` (branch `gate-inversion`)
**Champion baseline:** `bot/outline-agent-box` @ `df4118a` — scored report at `/home/polaris/polaris_project/SECURED_0.44_champion/champion_0.4447_report.md` (RACE 0.4447)
**Mode:** READ-ONLY. Nothing edited. No verifier / provenance / NLI / D8 / drop-rule / threshold touched.
**Constraint honored:** faithfulness is FROZEN. This audit characterizes and quantifies the tail, then proposes faithfulness-SAFE levers only. Where the frozen verifier itself is the culprit, it is said plainly and priced.

---

## 1. GHOST VERDICT — YES (structural, and present in the BAR itself)

The tail gate **is** killing high-RACE-value synthesis / insight / analysis. This is not a gate-run regression; it is baked into the champion too.

**Quantified basis (all from primary telemetry, re-confirmed this run):**

### Gate run — `outputs/gate_e2e_final2/workforce/drb_72_ai_labor/verification_details.json`
- `sentences_verified = 44`, `sentences_dropped = 84` (of which 10 dedup, 74 faithfulness-failure). **Verifier checked 118 sentences; 63% dropped.**
- Drop-reason census: `entailment_failed 41`, `percent_not_in_cited_span 18`, `no_integer_overlap_any_cited_span 13`, `binding_qualifier_dropped 13`, `number_not_in_any_cited_span 2`, `no_content_word_overlap 2`, `no_provenance_token 2`.
- **The structural crux, re-verified: of the 41 entailment failures, 40 are NEUTRAL and exactly 1 is CONTRADICTED.** The tail is not catching *false* claims. It is dropping claims whose interpretation/framing the single cited span did not literally restate. Zero of the NEUTRAL drops were shown to be wrong.
- Content classification of the 74 failure-drops: **~24 (32%) are cross-source SYNTHESIS/INSIGHT/ANALYSIS** ("suggesting…", "indicating…", "underscoring…", "rather than", historical-analogy framing); ~43 (58%) are atomic facts whose number was correct but sat outside the cited byte-offset (a citation-precision failure, not a fabrication); ~7 (10%) are navigational cross-ref stubs correctly dropped.
- **Per-section gutting (re-verified):** the two most synthesis-dense sections were hit hardest.
  - S5 "Data Gaps and Forecasting Uncertainties" — **kept 1 / dropped 16 (94%)**. The report's single best 5-source capstone ("these overlapping uncertainties… collectively suggest that existing models… remain preliminary") dropped NEUTRAL.
  - S1 "How AI Disrupts Labor Markets" — kept 4 / dropped 13 (76%).
  - Others: S0 9/8, S2 10/8, S3 6/12, S4 6/9, S6 8/8.

### Champion (RACE 0.4447) — same query, same model
- From `compose_summary.json`: `total_sentences_verified = 86`, `total_sentences_dropped = 96` → **52.7% drop rate** on everything the writer composed.
- Its dedicated "Cross-Study Synthesis" section collapses to **2 single-source paraphrases**. The champion body is overwhelmingly one-`[N]`-per-sentence single-source restatement; the apparent "multi-source" hits are mostly the sentence splitter gluing a sentence to the next heading.
- Champion RACE breakdown (from `champion_0.4447_score.txt`): Overall **0.4447**, Insight **0.4293**, Comprehensiveness **0.4569**, Instruction-Following 0.4587, Readability 0.4310.

**Structural vs run-specific:** STRUCTURAL. The champion — the highest report we have — already pays a 52.7% drop tax and ships a 2-sentence synthesis section. The ghost is in the bar, not just the gate run. The gate run's *lower* score is over-determined by confounds (below), but its insight erosion is directionally the same mechanism.

**Honest confound note (gate run only):** the drb_72 gate run additionally suffered (a) a degenerate compose contract — `document_type=""`, `required_section_count=0`, `has_voice=false`, all 7 SCOPE terms UNKNOWN; (b) no reranker (`rerank_not_selected=0`, 46% UNKNOWN-tier corpus); (c) D8 never ran (`adjudicated=false`, transport failure). These depress Instruction-Following/Readability independent of the tail and mean 0.3568 must NOT be read as a pure tail-gate cost. The tail-drop is the *second-order* problem in that specific run — real and quantified, but not the first thing to fix there.

---

## 2. THE CULPRIT LAYER — the FROZEN verifier (be honest)

**Single stage most responsible: `strict_verify` / `verify_sentence_provenance` in `src/polaris_graph/generator/provenance_generator.py`** — specifically its per-sentence, span-scoped lexical + NLI floor applied to LLM-redrafted synthesis prose:
- mandatory provenance token `:2186-2193` (uncited synthesis dropped before NLI ever runs),
- span-scoped numeric legs `:2247-2371` (every decimal/percent-int must sit inside a *cited* byte-range),
- ≥2-verbatim-content-word overlap floor,
- NLI entailment on the union of cited spans `:2548-2588`, default mode `enforce`, NEUTRAL/CONTRADICTED → drop.

**FROZEN or ADJUSTABLE?** The drop rule / NLI / numeric floor is **FROZEN**. And the unvarnished truth the operator asked for: **the frozen lexical + single-/union-span NLI floor IS the proximate culprit.** It is a verbatim-overlap-and-entailment test that structurally cannot pass a faithful cross-source inference (span A + span B → interpretation C is never entailed by A alone or B alone). The in-tree proof is `depth_synthesis.py:107-110`: the multi-source synthesis layer "returns []" — ~11 eligible multi-source baskets go 3→0, all dropped. The `synthesis_entailment_verify.py` header states the same verbatim: a "genuine PARAPHRASE that consolidates several corroborating spans… is DROPPED — even though it is a faithful, number-matched, ENTAILED restatement."

**Secondary subtractor (also frozen-in-spirit):** the render-verdict gate `apply_render_verdict_gate` in `src/polaris_graph/roles/report_redactor.py:1069` + `reconcile_report_against_verdicts:254`. It re-judges strict_verify survivors with the stronger 4-role D8 stack and **redacts every non-VERIFIED verdict — including PARTIAL** — by default (`PG_RENDER_VERDICT_GATE=1`, `admit_partial=0`). `_compose_final_verdict` (`role_pipeline.py:279-317`) is locked downgrade-only: "a worse Judge verdict is NEVER upgraded." **D8 is a net subtractor — it never rescues a strict_verify drop.** The one flag on this gate (`admit_partial`) is ADJUSTABLE and is the single highest-leverage safe lever (see §4).

`key_findings.py` refilter and render-chrome/truncation screens are hygiene-only and fail-conservative — they do NOT chop insight; they delete redaction *residue* left by upstream drops.

---

## 3. RACE IMPACT — modeling the Insight(0.32)+Comprehensiveness(0.29) cost

RACE weights per the brief: Insight 0.32, Comprehensiveness 0.29, Instruction-Following 0.25, Readability 0.14.

**Anchoring on measured density, not speculation.** Champion Insight = 0.4293 with ~27% insight-flavored surviving sentences. Gate run insight-density ~16% (74 dropped, of which ~24 pure/numbered synthesis). The gate run is *longer* (5,076 words) yet *less* insight-dense than the champion (3,914 words) — the tail preferentially removed the interpretive layer, leaving fact-list-shaped survivors.

**Rough model (order-of-magnitude, not a promise):**
- The tail removes ~24 of ~30 cross-source insight sentences in the gate run (~80% of the interpretive layer). Insight is a graded dimension; recovering even half of that interpretive layer plausibly moves the Insight sub-score by **~0.03–0.06** and Comprehensiveness by **~0.02–0.04** (more sourced coverage surfaces).
- Weighted: `0.32 × ~0.045 + 0.29 × ~0.03 ≈ 0.014 + 0.009 ≈ **~0.02–0.03 RACE points** plausibly recoverable` on a run where the confounds are otherwise fixed. On the champion itself (where confounds are already absent), the recoverable insight is the more valuable slice — the champion is already at the frontier, so even **+0.01–0.02** matters at that altitude.
- Caveat: this is an upper-plausible estimate. A chunk of the recovered synthesis would ship *disclosed/hedged* (via the safe levers), which the scorer may reward less than clean VERIFIED prose. Treat ~0.02–0.03 as the ceiling of the honest-safe path, not the expectation.

---

## 4. FAITHFULNESS-SAFE LEVERS (ranked)

All of these preserve insight WITHOUT editing the frozen verifier / NLI / drop rule / D8 thresholds. Pure-safe levers are marked ✅. Levers that would require relaxing the frozen rule are flagged ⚠️ **operator-decision-only, not recommended without sign-off.**

### ✅ Lever 1 — `PG_RENDER_VERDICT_GATE_ADMIT_PARTIAL=1` (adjustable render disposition)
- **What:** stop the render-verdict gate from dropping PARTIAL synthesis; keep + label them instead. The frozen D8 verdict is untouched — only the *render disposition* of a PARTIAL flips from drop to keep-with-caveat. FABRICATED/UNSUPPORTED still drop.
- **Insight recovered:** high — PARTIAL is exactly where cross-source inference lands. Directly reinstates the redacted interpretive layer.
- **Faithfulness risk:** low — partial-grounding is disclosed, not asserted. Nothing uncited ships.
- **Effort:** trivial (one flag, currently default-OFF and not in the slate). **Highest leverage-per-effort.**

### ✅ Lever 2 — Confirm C1+C2+C3 synthesis-rescue are actually ON at runtime
- **What:** `PG_SYNTH_ENTAILMENT_VERIFY` (C1: additive entailment-union verify — a pure superset that can only ADD to strict_verify's kept set, zero new spend, resident cross-encoder), `PG_SYNTH_SINGLE_SOURCE` (C2), `PG_SYNTH_D8_PROMOTE` (C3), plus `PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK`. All default-ON — but they were NOT visibly pinned in the live slate flag block around `run_gate_b.py:636`. **Verify they aren't silently dark**, and that C1's rescued output survives the D8 redactor rather than being re-killed at stage 10.
- **Insight recovered:** medium-high — C1 is the sanctioned recovery of entailed, number-clean paraphrases the ≥2-verbatim leg drops.
- **Faithfulness risk:** none — C1 only keeps sentences the resident NLI already entails; it is additive by construction.
- **Effort:** low (audit the slate, pin the flags).

### ✅ Lever 3 — Ground synthesis better at COMPOSE time (the *right* fix)
- **What:** two upstream authoring fixes, both zero-verifier-change: (a) **citation-offset emission** — ~31 gate-run drops are `number/percent/integer not in cited span` where the value is *correct* but the byte-offset is wrong; widen/re-locate the emitted span to the exact offset containing the number and the frozen verifier passes them unchanged (recovers ~40% of all drops, pure mechanical win). (b) **Richer `direct_quote` capture at retrieval** — the operator's own logs blame corpus density ("rows are mostly titles/abstracts lacking rich direct_quotes"); more verbatim overlap lets synthesis clear the ≥2-word floor *honestly*.
- **Insight recovered:** high on facts (offset fix), medium on synthesis (richer grounding).
- **Faithfulness risk:** none — this is pure provenance improvement; claims become *more* grounded, not less.
- **Effort:** medium (compose-time offset logic + retrieval quote capture). This is the durable fix.

### ✅ Lever 4 — Route synthesis to a disclosed rendered section (adjustable non-frozen layer)
- **What:** `analyst_synthesis_deviation_check.py` ships `PG_ANALYST_SYNTHESIS_DISCLOSED_KEEP` (default-OFF) — renders hedged interpretation under an "interpretive commentary… not individually span-verified" preamble instead of dropping it; fabrications (uncited + a number/named study absent from pool) still drop. Its own comments quantify prior loss ("box2: 79/81 real cited cross-source sentences dropped"). Pair with `PG_ANALYST_SYNTHESIS_BASKET_MODE`/`_FULLTEXT`.
- **Insight recovered:** high — this is the label-not-delete path for exactly the NEUTRAL synthesis.
- **Faithfulness risk:** low-medium — content ships under an explicit not-span-verified disclosure with an anti-fabrication floor. Risk is presentational (scorer/reader trust of a disclosed block), not hallucination.
- **Effort:** low (flags exist) + one A/B to confirm the scorer rewards disclosed synthesis.

### ✅ Lever 5 — `PG_STRICT_VERIFY_JUDGE_ERROR_ALWAYS_RELEASE=1`
- **What:** stops the entailment leg from fail-closing span-grounded synthesis on a transport fault; keeps-with-label instead. Also restore the D8 transport (it never ran in drb_72) so the sanctioned adjudication lane exists at all.
- **Insight recovered:** low-medium (only the transport-fault slice).
- **Faithfulness risk:** none — only changes disposition on judge *errors*, not on real NEUTRAL verdicts.
- **Effort:** low.

### ⚠️ Lever 6 — Relax the ≥2-verbatim floor / accept union-span NLI for synthesis — OPERATOR-DECISION-ONLY
- This is editing the frozen verifier. **Not recommended without explicit sign-off.** Listed only so the operator knows the residual cost that the safe levers above *cannot* reach: a genuine cross-source inference that no single span nor the union entails will still drop, by design. The safe levers reinstate the *disclosed/partial* slice; they do not make the frozen NLI pass a true multi-source leap. That final slice is a frozen-rule decision, priced but off-limits here.

---

## 5. BOTTOM LINE

**Land a safe lever first; do not re-run as-is.** A latency-fixed re-run of the gate config would still ship through the same frozen strict_verify + default-drop render gate, so it would reproduce the 60%+ drop and the gutted synthesis sections — you would pay the compute to re-confirm the ghost, not to beat it. The cheapest, faithfulness-safe, highest-leverage change is to **(1) flip `PG_RENDER_VERDICT_GATE_ADMIT_PARTIAL=1` and (2) confirm the C1/C2/C3 synthesis-rescue flags are actually ON in the live slate**, then re-run persisting `verification_details.json` and measure kept cross-source findings + RACE delta. In parallel, the durable win is the **compose-time citation-offset fix** (recovers ~31 correct-but-mis-offset facts with zero verifier change). For the gate run specifically, also fix the two confounds (degenerate compose contract, missing reranker) — they hurt that run more than the tail does. The frozen verifier is honestly the proximate culprit for the cross-source-insight class, and we are not touching it — but the safe levers above plausibly recover ~0.02–0.03 RACE without ever editing it, which is the right first move before anyone reopens the frozen rule.

---

### Key file:line references
- Frozen verifier: `src/polaris_graph/generator/provenance_generator.py` — token-required `:2186-2193`, numeric legs `:2247-2371`, NLI-on-union `:2548-2588`, drop loop from `:3598`.
- Clinical twin + synthesis exemption (NOT on live Gate-B path): `src/polaris_graph/clinical_generator/strict_verify.py:386,418-421,508-573`.
- In-tree ghost proof + C1 rescue: `src/polaris_graph/synthesis/synthesis_entailment_verify.py:1-27`; `src/polaris_graph/generator/depth_synthesis.py:107-110,214-262`.
- Adjustable render dropper: `src/polaris_graph/roles/report_redactor.py:1069` (`apply_render_verdict_gate`), `:254`; downgrade-only composition `src/polaris_graph/roles/role_pipeline.py:279-317`; live pin `scripts/dr_benchmark/run_gate_b.py:636`.
- Disclosed-keep lever: `src/polaris_graph/generator/analyst_synthesis_deviation_check.py`.
- Primary telemetry (numbers above): `outputs/gate_e2e_final2/workforce/drb_72_ai_labor/verification_details.json` (44 kept / 84 dropped, 40 NEUTRAL / 1 CONTRADICTED, S5 1/16); champion `SECURED_0.44_champion/champion_0.4447_report.md`, `.../champion_0.4447_score.txt` (0.4447; Insight 0.4293), `compose_summary.json` (86 kept / 96 dropped).
