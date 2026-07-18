# Deep-Research Pipeline — Complete Design, Evidence & Fix Lock-Down

**Status:** authoritative reference as of 2026-07-18. Branch `gate-inversion`.
**Scope:** the task-72 deep-research pipeline (DeepResearch Bench, RACE metric), the "Research Planning Gate," the measured root-cause of the score deficit, and the locked fix design.
**Evidence base:** 3 independent max-capability audits (Codex/GPT-5.6-Sol, Fable 5, Kimi K3) + direct checkpoint forensics + a decisive pre-checker rescore.

---

## 0. THE HEADLINE (read this first)

**The generation is already near-champion. The pipeline destroys it after the fact.**

| Report | Comp | Insight | IF | Read | **RACE Overall** |
|---|---|---|---|---|---|
| **A — RAW LLM draft, pre-checker** | 0.440 | 0.419 | 0.446 | 0.412 | **0.4305** |
| A — after checker+render (shipped) | 0.414 | 0.384 | 0.429 | 0.348 | 0.3992 |
| **B — RAW LLM draft, pre-checker** | 0.425 | 0.362 | 0.453 | 0.389 | **0.4069** |
| B — after checker+render (shipped) | 0.383 | 0.339 | 0.387 | 0.320 | 0.3610 |
| **Champion (`polaris_step3_control`)** | — | — | — | — | **0.4447** |

- The checker+render pipeline costs **−0.031 (A)** and **−0.046 (B)** of RACE, on every dimension.
- **A-RAW (0.4305) is within 0.014 of champion (0.4447)** — *with a handicap* (raw `[ev_]` tags, no bibliography, no title polish).
- Therefore: **the deficit is not the corpus and not the generation. It is the post-generation pipeline deleting good content and stapling on chrome.** Fix the pipeline → ≥0.4447, no corpus change, no faithfulness weakening.

RAW reports are saved at `outputs/gate_task72_{A,B}/workforce/drb_72_ai_labor/report_RAW_prechecker.md`; scores under `third_party/deep_research_bench/results/race/gate_task72_{A,B}_RAW/`.

---

## 1. PURPOSE & BENCHMARK

- **Task 72:** "a literature review on the restructuring impact of AI on the labor market," with an instruction to cite high-quality English-language journal articles.
- **RACE metric** (GPT judge, `scripts/score_report_race.py` → `third_party/deep_research_bench`). Task-72 dimension weights: **Insight 0.32, Comprehensiveness 0.29, Instruction-Following 0.25, Readability 0.14.**
- **FACT metric** (citation faithfulness) — currently unscoreable in our runs because D8 four-role never adjudicates (see §5.4).
- **Champion baseline:** `polaris_step3_control` = **0.4447** (the true reproducible champion; the earlier-cited `step3_rescore_r2` 0.4291 was a weaker variant). Calibration ceiling: `fable5_scoped_calibration` 0.5065.

---

## 2. END-TO-END PIPELINE ARCHITECTURE

Entry: `scripts/run_gate_e2e.py` → `scripts/run_honest_sweep_r3.py::run_one_query`.

```
PROMPT
 └─ RESEARCH PLANNING GATE (compile a typed ResearchContract from the prompt)
     • clause ledger + deontic detection (planning/); deterministic-authoritative, LLM additive-only
     • pin artifact (planning_gate_artifact.json, contract_sha256) — the KEYSTONE hand-off
 └─ RETRIEVAL (contract-scoped)
     • FS-Researcher query-gen → SERPER / S2 / OpenAlex / PMC fetch (live_retriever)
     • credibility LLM tiering (WEIGHT, no drop)
     • eligibility: source-kind + topicality + opaque (Phase C mask; kept-in-corpus, withheld-from-grounding)
     • content-relevance reranker (Qwen3-Reranker-0.6B; PG_CONTENT_RELEVANCE_SCORE_CHUNK caps OOM)
     • corpus_snapshot.json written at the selection seam (resume point)
 └─ COMPOSE (the LLM writes the report — CLEAN at this stage)
     • ComposeRenderProjection.from_contract → compose_projection (deliverable kind/sections/voice) injected
       into the section-writer + outline-agent PROMPTS (compose-contract injection, commit 053e93c)
     • multi_section_generator: outline → per-section drafts (raw_drafts) → postgen_checkpoint.json  ← CLEAN
 └─ VERIFY / DEDUP (THE DAMAGE — see §4)
     • strict_verify (provenance_generator.py / clinical_generator/strict_verify.py): per-sentence
       span-scoped numeric + qualifier + NLI check → DROP
     • fact_dedup (generator/fact_dedup.py): rewrite "duplicate" sentences into navigation pointers → DROP-on-fail
     • depth_synthesis corroboration → postverify_checkpoint.json
 └─ RENDER (chrome injection — see §4.4)
     • title = "# Research report: <raw prompt>"  (run_honest_sweep_r3.py:17657)
     • D8 "UNVERIFIED-by-D8" banner (provenance_generator.py:3236 → written :21280)
     • "Completeness checklist: 0/0" telemetry (:16989); corpus-ledger audit appendix (:4245)
 └─ report.md → clean_article.py → RACE/FACT scoring
```

**Design principle the pipeline claims but violates:** the dedup module docstring states *"the pipeline is WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP (§-1.3)."* strict_verify + fact_dedup are the un-audited §-1.3 violations.

### 2.1 The Research Planning Gate (the "smart gate")
Built over gate-inversion (commits `78fe2ca` → `d44ee36` → `b67506a` → `053e93c` → `ce5f2ee`):
- **Deterministic-authoritative** contract compilation (lossless clause ledger; LLM additive-only); generic IR (operators IN/NOT_IN/GTE); OPAQUE preservation.
- **KEYSTONE hand-off:** the pinned contract reaches retrieval AND compose (verified live: `contract_sha256` match, `from_artifact` projection).
- **Generalized (not task-72-hardcoded):** Fix 4 = closed archetype table off `deliverable.kind`; Fix 5 = credibility-tier + kind-driven eligibility (T1 = peer-reviewed-journal OR gov/primary; exclusion wins; adequacy+receipt-gated hard mask). 67 metamorphic tests across review/memo/brief/comparison/explainer.
- **Compose-contract injection (`053e93c`):** deliverable kind/sections/voice now steer the section-writer + outline prompts (not post-hoc block-shuffle).
- **Faithfulness:** `provenance_generator.py` verified 0-diff vs champion `df4118a` throughout the gate work.

---

## 3. THE DECISIVE MEASUREMENT (pre-checker rescore)

We assembled the raw LLM section drafts from `postgen_checkpoint.json` (before verify/dedup/render) into a plain report and scored it. Result: §0 table. **Every dimension is higher pre-checker.** Readability jumps +0.064 (A) / +0.069 (B) once the banner/telemetry are gone; IF +0.066 (B).

**This overturns the "corpus is the biggest lever" hypothesis:** the earlier audit inferred a −0.078 corpus cap from `champ_ourcorpus` = 0.3671 (champion *pipeline* on our corpus). But our RAW draft on the *same* corpus scores **0.4305** — so the corpus was never the cap; champion's pipeline *also* mangles our corpus down to 0.367. **The mangling is the story.**

---

## 4. ROOT CAUSE (3-model convergence + checkpoint proof)

Measured cost of the checker: A(partly-off) 0.3992 vs B(on) 0.3610 = −0.038, and RAW-vs-shipped = −0.031/−0.046. Full audit: `research/FORENSIC_DEEP_AUDIT.md`.

### 4.1 strict_verify deletes true content — 147 drops to catch 2 lies (run B)
- `postverify_checkpoint` totals: **147 sentences dropped, 55 verified**; only **2 CONTRADICTED** in the whole report (98.6% false-positive-on-truth).
- Accounting (Codex): 147 = **59** genuine first-pass fails + **44** verified originals destroyed by fact_dedup + **44** failed replacement pointers.
- drop_reason_counts (B): entailment_failed(NEUTRAL) 66 | no_integer_overlap 21 | percent_not_in_cited_span 15 | no_content_word_overlap 11 | number_not_in_any_cited_span 9 | binding_qualifier 8 | temporal_scope 1 | no_provenance 1.

### 4.2 The specific bugs (quoted, reproducible)
1. **Sign-regex bug** — `_NUMBER_RE = -?\d+` glues the hyphen to the digits: `"75-375 million"` → searches for `-375` (absent); `"post-1987"` → searches for `-1987` (absent). Correct numbers flagged as hallucinations. Fix: normalize en-dash/hyphen ranges; strip leading sign from range tokens.
2. **Window truncation / wrong offset** — strict_verify checks only one generator-asserted 800-byte cited span. If the number lives elsewhere in the *same* document, it "fails." Proof of self-refutation: "47%" is dropped in one sentence yet **passes in another from the same `ev_312`**; the BLS 0.6pp claim dropped 3× yet appears 3× in the final. Root: `_find_best_span_for_sentence` (`generator/live_deepseek_generator.py:352`, fallback `:437`) returns `(0,800)` — the title page — when no single window holds all atoms.
3. **`fact_dedup` non-transactional** (`generator/fact_dedup.py:846` prompt; integration `generator/multi_section_generator.py:~11155`): removes a verified sentence, re-verifies a "detailed in {SECTION}" pointer, and on failure **does not restore the original**. Run B: `n_rewrites_applied=44, pass=0, drop=44` → 44 verified sentences destroyed. (`content_dedup_consolidate.py` is EXONERATED — KEEP-ALL, annotation-only.)
4. **Category error** — NEUTRAL-entailment (66) is collapsed with CONTRADICTION into the same DROP action. The judge is executing synthesis/interpretation ("the 2011 Hannover Fair", "through 2034", "reflecting rising demand"), i.e. the Insight RACE rewards. It amputated the review's organizing framework (Acemoglu-Restrepo displacement/reinstatement).

### 4.3 The invisible multiplier (coverage coupling)
`s2_cited_bibliography_records` keys required-entity coverage on `cited_reference_numbers(body)`, and body `[N]` markers "live in strict_verify-PASSED prose." Each drop de-cites a source → demotes it to the ledger → strips coverage credit → fires a *fail-safe UNDER-credit*. **The faithfulness failure surfaces as a Comprehensiveness/Coverage weakness — never as "faithfulness" — which is why it hid.**

### 4.4 Render chrome (secondary, ≤0.006, render-injected)
Absent from raw draft, present in scored text: raw-prompt title (`:17657`; `_strip_injected_instruction_appendix` fails to strip the "Ensure the review only cites…" clause), the D8 UNVERIFIED banner (`:21280`), "Completeness checklist: 0/0" (`:16989`), corpus-ledger appendix (`:4245`). ~120 words but semantically damaging (advertises poor quality to the judge).

### 4.5 IMPORTANT CORRECTION — "faithfulness off" (Run A) was never fully off
A used flags PG_RENDER_VERDICT_GATE=0, PG_STRICT_VERIFY_ENTAILMENT=off, PG_PROVENANCE_MIN_CONTENT_OVERLAP=0, PG_REQUIRE_NUMBER_MATCH=0. **A still dropped 56 sentences** (number-match 27 + dedup 41). `PG_REQUIRE_NUMBER_MATCH` (committed `ce5f2ee`) only gated ONE minor call site (`multi_section_generator.py:4571`, `_recover_comparative_synthesis`); the main verify path ignored it. So the A/B −0.038 is "partly-off vs on," understating the true checker cost — and even A (0.3992) is a *mangled* run. The genuinely-clean number is the RAW rescore (§0/§3): 0.4305.

---

## 5. THE LOCKED FIX DESIGN (ranked by RACE leverage) — NOT "disable faithfulness"

The guarantee is unchanged: **CONTRADICTED is always dropped; every surviving claim still traces to a corpus span.** The change is **repair/re-bind before delete.** This is the opposite of the cellcog failure (which weakened the verifier); here the verifier gets *smarter*.

**Fix #1 — Verdict-gradation + relocate/repair-not-drop in strict_verify (leverage +~0.031–0.046 + coverage recovery).**
- CONTRADICTED → drop (the ~2 genuine ones).
- NEUTRAL → re-ground against the full evidence doc → corpus; if grounded, re-bind citation + KEEP; else one bounded regenerate pass; drop last.
- Number-mismatch → search full doc/corpus with normalization (fix sign-regex; en-dash ranges; words↔digits; %↔percent; magnitudes like "375 million"; derived-number tolerance e.g. "a 25% reduction" = arithmetic on 7.5→5.7) → re-bind offset + KEEP; drop only if truly absent everywhere.
- binding_qualifier → re-attach the qualifier; no_provenance → auto-ground/regenerate.

**Fix #2 — Make `fact_dedup` transactional** (roll back to the verified original if the replacement fails; better: stop emitting source-cited navigation pointers entirely).

**Fix #3 — Decouple coverage credit from verify survival** (map `[#ev:ev_N]` → bibliography `[N]` before citation stripping, so a dropped sentence never silently demotes a cited source; stops the S2 fail-safe under-credit firing on healthy reports).

**Fix #4 — Strip render chrome from the SCORED text** (derive a clean title; fix `_strip_injected_instruction_appendix`; relocate the D8 banner + telemetry to `manifest.json` where the disclosure already lives — honesty by relocation, not suppression; do NOT fake a D8 run). Also **build a real bibliography** (the RAW rescore had none — this is upside beyond parity). ~zero cost.

**Fix #5 — Corpus enrichment to champion grade (upside past parity, +0.045+):** retrieve the study-grade sources the champion cites — Noy et al. (453 professionals), WEF Future of Jobs (85M/97M), PwC ($15.7T), Autor 1940–2018, Eloundou (1.8%→46%), OECD exposure, Korean firm survey, platform-wage studies, Oberfield-Raval. (Downgraded from "biggest lever" — see §3.)

**Rejected / DO-NOT (all 3 auditors):** turn faithfulness fully off (re-admits the 2 lies, forfeits the product's reason to exist); strip the banner while leaving the verifier (≤0.006); chase the "deferral-pointer disease" (it does not exist in the scored text — a prior-audit hallucination); weaken the ≥2-content-word / NLI thresholds downward (cellcog).

---

## 6. ABSOLUTE RULES (updated)

1. **Faithfulness = repair-not-drop, never weaken.** The verifier must still drop CONTRADICTED and still require every surviving claim to trace to a corpus span. It must NOT delete NEUTRAL/number-offset content without a bounded repair attempt. No new "verification pass" that adds drops.
2. **Enforce scope at RETRIEVAL, never filter a frozen corpus.** (Unchanged.)
3. **Score only the clean report body.** Audit chrome (banner, telemetry, ledger) lives in `manifest.json`/sidecar, not the scored `article`.

---

## 7. REPRODUCTION

```bash
# Score the pre-checker RAW draft (the clean ceiling):
python3 scripts/score_report_race.py --report outputs/gate_task72_A/workforce/drb_72_ai_labor/report_RAW_prechecker.md \
  --task-id 72 --model-name gate_task72_A_RAW
# Inspect the checker's damage:
python3 -c "import json;pv=json.load(open('outputs/gate_task72_B/workforce/drb_72_ai_labor/postverify_checkpoint.json'))['verification_details'];print(pv['totals'],pv['drop_reason_counts'])"
# Live run (unbounded; PG_E2E_RESUME=1 resumes from corpus_snapshot):
# flags: PG_PLANNING_GATE_LIVE=1 PG_QGEN_FS_RESEARCHER=1 PG_AUTHORIZED_SWEEP_APPROVAL=1 PG_TOPICALITY_ELIGIBILITY=1
#        PG_OPAQUE_ELIGIBILITY=1 PG_CREDIBILITY_LLM_TIERING=1 PG_REPORT_SHAPE=1 PG_CONTENT_RELEVANCE_SCORE_CHUNK=2
```
Provider routing (GLM-5.2 latency fix): `config/settings/openrouter_provider_routing.yaml` re-pinned to friendli/fireworks/baseten (dropped slow z-ai/phala tail).

---

## 8. AUDIT PROVENANCE
- 3-model deep audit (Codex/GPT-5.6-Sol, Fable 5, Kimi K3), all returned in full, evidence-locked → `research/FORENSIC_DEEP_AUDIT.md`; raw model outputs in the session scratchpad (`scratchpad/deepaudit/{fable,codex,kimi}.md`).
- Prior (superficial) audits — corrected here — invented a non-existent "deferral-pointer disease" and blamed `content_dedup_consolidate` (exonerated). The real culprit is `strict_verify` + `fact_dedup`.
- Kimi K3 integration note: works via a direct OpenRouter call (`moonshotai/kimi-k3`, 1M ctx, capture `content` OR `reasoning`); prior failures were a flaky workflow-agent-writes-a-script indirection, not the model.
