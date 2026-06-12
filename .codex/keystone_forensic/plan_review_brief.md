# Codex PLAN review — keystone distill RECALL+COLLAPSE diagnosis & next-step plan (#1217)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the plan is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this is
This is a **plan/diagnosis review**, NOT a diff gate. The keystone map-reduce distiller (`src/polaris_graph/generator/evidence_distiller.py`, flag `PG_SECTION_DISTILL`) collapsed on a paid VM A/B re-prove. Before I write any more code or spend more, the operator wants you to review my diagnosis + plan and converge on a plan we BOTH agree on. Give me raw verification of the EVIDENCE below, correct my diagnosis if wrong, and approve/repair the plan. You have full repo read access — verify against the real file, do not trust my paraphrase.

## CONTEXT (one paragraph)
The distiller does per-source MAP extraction → `_validate_finding` → a findings ledger → a section REDUCE that writes cited prose → the UNCHANGED legacy `_rewrite_draft_with_spans` + `strict_verify` (the SOLE faithfulness authority). Section under test: "Safety and contraindications" of a gut-microbiota/CRC question, MAXEV=8, model deepseek/deepseek-v4-pro, on the OVH VM. A/B = same 8 sources, `PG_SECTION_DISTILL` OFF (legacy) then ON (distill).

## EVIDENCE (raw, verbatim — verify each against the repo/artifacts)

### E1 — replay A/B result (paid, this run)
```
verified: legacy=11 -> distill=0 (delta -11); drop_rate 0.08 -> 1.00; body_words 265 -> 29
distill_on: sentences_verified=0, sentences_dropped=1, body_words=29 (= the 29-word "no claim survived ... curator-actionable gap" placeholder)
```
A PRIOR smoke (short-marker fix only) had distill=1 / legacy=6. So distill swings 0–1 verified while legacy is 6–11. Distill is in near-total collapse either way.

### E2 — PG_DISTILL_DEBUG dump (verbatim, this run)
```
[DISTILL_DEBUG] section='Safety and contraindications': ledger=1 findings; REDUCE raw=115 chars / 2 sentences; raw_sample='Colibactin induces double-strand breaks in cultured cells. [[finding:f002_000]] [ev_colibactin_pks_ecoli_mechanism]'
[DISTILL_DEBUG] section='Safety and contraindications': filter kept 1/2 sentences -> output=35 chars; out_sample='[ev_colibactin_pks_ecoli_mechanism]'
```
Read this carefully: the REDUCE wrote the claim sentence `"Colibactin induces double-strand breaks in cultured cells."` and then, AFTER the period, the markers `"[[finding:f002_000]] [ev_colibactin_pks_ecoli_mechanism]"`. `split_into_sentences` splits on the period → 2 "sentences". `filter_and_strip_reduce_markers` (lines 1086–1112) KEEPS the second fragment (it carries the markers) and DROPS the actual claim sentence (it has NO marker). Output = a bare `[ev_...]` marker with no prose → strict_verify drops it → 0 verified → placeholder.

### E3 — the 8 sources actually fed (I inspected the pool; the operator made me verify)
- [0] `probiotic_crc_inflammation_rct` — **direct_quote length = 0 (EMPTY)**. Cannot yield any finding.
- [1] fiber/whole-grain CRC meta (25k chars) — mechanism/benefit, not safety.
- [2] `colibactin_pks_ecoli_mechanism` (24.6k) — genotoxin mechanism; produced the 1 kept finding.
- [3] fusobacterium genotoxin (25k) — mechanism, not safety.
- [4] `probiotic_immunocompromised_contraindication` (25k) — **THE CDC S. boulardii fungemia safety source.** Contains the exact numbers the legacy arm verified: OR 14 (95% CI 4–44), case-fatality 22% (day 7) / 37% (day 28), and the explicit "not recommended for immunocompromised / indwelling catheters / critically ill" contraindication.
- [5] secondary bile acids (11.5k) — mechanism.
- [6] childbearing-age paper (9.6k) — off-topic.
- [7] general cancer (5.7k) — weakly relevant.
Legacy mined ~9–11 sentences essentially from source [4] (+ colibactin [2]). The distill ledger kept **0 findings from source [4]** and 1 from [2].

### E4 — the per-source data ALREADY EXISTS (I think I over-proposed instrumentation)
`_distill_one_source` (lines ~717–915) already returns a `CoverageRow` per source with `status ∈ {mapped, no_relevant_findings, map_failed, validation_failed}`, `n_findings`, and `reason`. For the validation-failed case (line 881–885) the reason is literally `f"{len(raw_findings)} proposed, 0 validated"`. So per-source proposed-vs-validated + status ALREADY exists in `SectionDistillate.coverage`. The replay harness (`scripts/dr_benchmark/offline_distill_replay.py`) just DISCARDS coverage (it saves only metrics + prose). What's MISSING is only WHICH validation step killed each finding.

### E5 — `_validate_finding` step list (lines 511–668), for the recall question
- step 1 `_locate_span_in_source` (exact → stripped → whitespace-flexible regex; reworded quote → None → REJECT).
- step 3 adopt real source slice; empty → REJECT.
- step 4 `_all_numbers_in_span` — **now NON-BLOCKING** (my just-applied #1217 fix, line ~583; computes the bool, logs, never returns None).
- step 5 atom mapping — KEEP even if no section-local atom.
- step 6 entailment via `verify_sentence_provenance` — NON-BLOCKING (computed, never gates); the `except` is the only fail-closed REJECT here.
Empirically ledger stayed at 1 BEFORE and AFTER the step-4 fix → step 4 was NOT the dominant rejector. So the remaining hard rejectors are step 1 (locate) and step 3 (empty slice) — OR the MAP simply returned `no_relevant_findings`/fewer proposals for source [4].

## MY DIAGNOSIS — TWO STACKED BUGS
- **Bug A (deterministic, offline-reproducible): orphaned-citation collapse.** When the REDUCE places its `[[finding]]`/`[ev]` markers on a separate sentence/line from the claim, the splitter + `filter_and_strip_reduce_markers` keep the marker-only fragment and drop the prose. This zeroes ANY ledger, regardless of recall. This is the proximate cause of distill=0 in E2.
- **Bug B (recall, cause UNCONFIRMED): the rich safety source [4] yields 0 ledger findings** while legacy mines ~9 from it. Could be (i) MAP returned `no_relevant_findings`/few proposals for [4], or (ii) step-1/step-3 rejected its proposals. I have NOT measured which. The step-4 fix did not change ledger=1, so step-4 is ruled out.

## MY PROPOSED PLAN (review + repair this)
1. **Surface existing coverage (no new pipeline instrumentation):** make the replay harness dump `SectionDistillate.coverage` (per-source status + n_findings + reason) for both arms. Near-zero code, no spend.
2. **Add per-rejected-finding step trace in `_validate_finding`** (gated by `PG_DISTILL_DEBUG`): for each proposed finding log which step killed it (locate-fail / empty-slice / except) or KEPT. Faithfulness-inert (logging only).
3. **Fix Bug A offline + unit test:** feed the EXACT E2 string through `filter_and_strip_reduce_markers` and assert the claim sentence is KEPT with its marker. Candidate fix: before dropping, RE-ATTACH a trailing marker-only fragment to the preceding sentence (so "claim." + "[[finding]] [ev]" → "claim. [ev]"), AND/OR strengthen the REDUCE prompt to force the marker INLINE at end of each sentence. Faithfulness unchanged — strict_verify still re-checks the reassembled sentence.
4. **One targeted paid probe (~1 LLM call, ~$0.01):** run the MAP stage on source [4] ALONE with the step-3 trace; read proposed vs validated + reject reasons for the CDC safety findings. Isolates Bug B on the one source that matters.
5. **Fix Bug B's dominant rejector** per the probe (e.g. candidate (c) fuzzy-locate if step-1 paraphrase; or MAP-prompt fix if proposals are missing), then cheap re-prove MAXEV=8.
6. Dual Claude+Codex review the diff; on APPROVE commit, push, re-prove, then scale MAXEV=40 + §-1.1 audit; only THEN full Q1.

## QUESTIONS FOR YOU (Codex)
1. Do you AGREE with the two-bug diagnosis from E1–E5? Correct anything mis-read.
2. **Bug A fix:** re-attach orphaned trailing markers to the preceding sentence, vs force inline markers in the REDUCE prompt, vs BOTH — which is robust AND faithfulness-safe? Any way re-attachment could attach a marker to the WRONG sentence?
3. Did I correctly conclude the per-source proposed/validated data already exists in `CoverageRow` (E4), so step 1 of my plan is just "dump it," not "build it"?
4. Is the single-source probe on [4] sufficient, or must I probe all 8 to avoid a wrong generalization?
5. Any FAITHFULNESS risk in steps 3/5? strict_verify / 4-role / D8 must stay byte-untouched and the SOLE publication authority.
6. Is there a CHEAPER or more decisive diagnostic I'm missing (e.g., can Bug B be measured with zero spend from the cache or coverage of THIS run — note coverage of this run was not persisted)?
7. Anything in `filter_and_strip_reduce_markers` or `_validate_finding` you'd change that I haven't named?

## OUTPUT SCHEMA (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_agree: true | false   # two-bug diagnosis correct?
corrections: [...]              # any evidence I mis-read
bug_a_fix_recommendation: <reattach | prompt | both | other>
plan_changes: [...]             # concrete edits to my 6-step plan
novel_p0: [...]
p1: [...]
p2: [...]
faithfulness_risk: [...]        # any way a gate gets weakened
agreed_plan: [ ordered steps we BOTH commit to ]
convergence_call: continue | accept_remaining
```
