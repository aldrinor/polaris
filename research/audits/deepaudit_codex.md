# Forensic verdict

The operator is directionally right: faithfulness-on is the largest proven discrete score killer. But the deepest root cause is not simply “strict_verify is too strict.” It is a destructive transaction across three stages:

1. The span binder assigns incomplete or wrong 800-byte slices.
2. `strict_verify` correctly observes that those slices do not support every atom.
3. The orchestrator deletes the whole sentence instead of splitting, rebinding, regenerating, and re-verifying it.
4. Separately, `fact_dedup` rewrites 44 already-verified sentences into source-cited document-navigation prose; all 44 replacements fail verification, and the code does not restore the originals.
5. Rendering then pads the thinned 1,788-word verified body back into a 4,549-word scored artifact with prompt-title, warning banner, audit prose, and telemetry.

The most important hidden accounting correction is:

> “147 sentences DROPPED” does **not** mean 147 distinct raw LLM sentences failed `strict_verify`.

The matching artifacts show:

- 103 failed sentence candidates in `dropped`.
- 44 previously verified originals in `dropped_by_dedup_redundant`.
- Of the 103 candidates, 44 are newly generated `fact_dedup` cross-reference replacements.
- Therefore the raw-draft flow is approximately:

```text
158 raw sentence units
├── 59 fail first-pass strict verification
└── 99 initially verify
    ├── 55 survive
    └── 44 removed by fact_dedup
        └── 44 replacement pointers generated
            └── 44/44 fail re-verification
```

The reported 147 is therefore:

```text
59 original verifier failures
+ 44 removed verified originals
+ 44 failed replacement pointers
= 147 accounting drops
```

That decomposition is proven by `dedup_redundant_count=44`, `n_rewrites_strict_verify_drop=44`, `sentences_verified=55`, and `sentences_dropped=147` in the matching [manifest](/home/polaris/wt/outline_agent/outputs/gate_task72_B/workforce/drb_72_ai_labor/manifest.json:211) and [verification details](/home/polaris/wt/outline_agent/outputs/gate_task72_B/workforce/drb_72_ai_labor/verification_details.json:2).

## 1. The 34 displayed drops, line by line

Classification:

- 17/34 are clean or near-clean findings killed mainly by span addressing, numeric normalization, qualifier false positives, or failure to combine multiple real spans.
- 7/34 contain a supported, valuable core plus an unsupported interpretive tail. The correct action was trim/split/regenerate—not delete the whole sentence.
- 1/34 is useful synthesis but genuinely inadmissible as written because it has no provenance.
- 9/34 are `fact_dedup`-generated navigation pointers, not raw research findings.
- 0/34 are shown to be contradicted or fabricated.

### Drops 1–10

1. **Wrongly killed; jointly supported.**  
   Claim: “*2011 Hannover Fair … cyber-physical systems, cloud computing … AI … merging physical, cyber, and biological systems*.”  
   The first cited span actually says “*Industry 4.0 builds on this with … IoT, Cyber-Physical Systems … cloud computing, big data analytics, AI*” and ends with “*2011’s Hannover Fair marked the debut*”; the second says it “*is merging the physical, cyber and biological systems together*.” The NLI judge failed to integrate the two spans. This is a multi-span entailment false negative.

2. **Definite numeric-parser false drop.**  
   Failure: “`missing=['375']`.”  
   Span: “*automation could displace 75-375 million workers by 2030*.”  
   Claim: “*75 to 375 million workers*.”  
   The number is in the exact cited slice. `_NUMBER_RE = -?\d+...` interprets the ASCII range hyphen as the sign of `-375`; the sentence contains positive `375`. This is not a faithfulness win.

3. **Qualifier-retention false positive.**  
   The cited span explicitly states the claimed decline “*from 7.5 to 5.7 percent, a reduction of 25 percent*” and the productivity comparison “*between 4 and 5 percent … compared to … 2 percent*.”  
   The likely trigger is an earlier occurrence: “*steady at around 7.5 percent … between 2003 and 2013*.” The qualifier matcher sees `around` near one occurrence of `7.5` and incorrectly binds it to the later, exact 2013–2023 finding. Good content was killed.

4. **Good core; selected span incomplete.**  
   The cited slice explicitly says “*growth projections are somewhat weaker for jobs with more observed exposure*” and “*for every 10 percentage point increase … drops by 0.6 percentage points*.”  
   “Through 2034” exists elsewhere in the same evidence record. Correct action: add the second span or split the timeframe atom—not delete the regression result.

5. **Good finding; number just outside the chosen slice.**  
   `ev_312:0-800` supports “*older, female, more educated, and higher-paid*” but not `47%`. Another slice from the same source says “*They earn 47% more, on average*.” This is a citation-address failure.

6. **Dedup-generated meta pointer.**  
   “*The post-1987 weakening … is detailed under [local section title]*” is not source prose. The source correctly contains the substantive finding—“*wage growth … 1.3% … reinstatement … 0.35% … displacement … 0.70%*”—but `fact_dedup` replaced that finding with a report-navigation sentence. The verifier is right to reject the pointer; `fact_dedup` is wrong to remove the verified original before its replacement passes.

7. **Supported concept plus over-compressed synthesis.**  
   The span supports “*creative destruction*”; other evidence supports AI/Fourth Industrial Revolution framing. But “*simultaneously displaces and creates jobs through mechanisms scholars characterize as both destructive and creative*” compresses several propositions into one citation unit. Split and rebind; do not retain unchanged.

8. **Good task-framework content; incomplete span combination.**  
   `ev_165` directly supports “*capital takes over tasks previously performed by labor*”; `ev_001` supports “*automation, new task generation*.” The chosen slices omit the exact phrase “reinstatement effect,” although the same work contains it elsewhere. Repair the span set.

9. **Clear wrong-offset failure.**  
   Claim: `0.7`, `0.35`, `1.3`.  
   Tokens point to both sources at `0-800`, which are front matter/abstract material. The values occur later in the same records. The verifier correctly rejects the cited addresses, but the pipeline should rebind rather than erase the finding.

10. **Same parser defect as Drop 2.**  
    Exact source text is `75-375`; claim uses “75 and 375.” False drop.

### Drops 11–20

11. **Qualifier false positive.**  
    The exact slice states “*retail sales declined by 850,000 … share … 7.5 to 5.7 percent, a reduction of 25 percent*.” Nothing material is unsupported.

12. **Valuable numeric finding plus unsupported explanation.**  
    The source exactly supports `6.5%`, `10%`, and `more than 50%`. The tail “*reflecting rising demand for new technical skills*” is interpretive. Correct result: preserve the quantitative sentence and drop/regenerate only the explanatory clause.

13. **Main claim supported; timeframe needs another span.**  
    The `10 → 0.6` regression is exact. “Through 2034” is elsewhere in the source. Multi-span repair required.

14. **Composite finding split across the same source.**  
    The selected slice supports demographics and no systematic unemployment increase since late 2022; another slice supports `47%`. This should become two separately cited sentences.

15. **Supported barrier list plus speculative tail.**  
    The span explicitly lists “*Infrastructure*,” “*Lack of Trained and Skilled Workforce*,” “*Scalability*,” and “*Funding*.” The phrase “*may limit the job-creation potential of AI*” is added synthesis. Trim or regenerate only that tail.

16. **Exact fact plus rhetorical tail.**  
    The source says the macro trend is adoption of frontier technologies “*with an 86.2% rate*.” “*Underscoring the urgency of understanding how AI restructures labor markets*” is authorial framing, not source evidence. Preserve the fact; remove or label the synthesis.

17. **Dedup pointer.**  
    The source supports the 1947–1987 effects; it cannot support “*detailed under [our section title]*.”

18. **Dedup pointer.**  
    The underlying manufacturing finding is valid and specific—`1.1% per year`, `30% cumulatively`—but the replacement merely says it is “*detailed under*” a local heading.

19. **Dedup pointer.**  
    The source supports the “*13-fold*” investment increase. The local section title is necessarily absent from the source.

20. **Useful but genuinely unsupported as written.**  
    “*AI adoption is fundamentally reshaping the task content … generating both displacement and reinstatement effects*” has no provenance token. It should not pass unchanged. It should be cited to the task-framework sources or labeled as synthesis derived from already verified claims.

### Drops 21–30

21. **Wrong offsets.**  
    The `0.7`, `0.35`, and `1.33` figures are real but not at the cited `0-800` slices. Rebind.

22. **Whole-sentence deletion for a partial address failure.**  
    The selected span supports “*20% in 1979 to 39% in 2018*.” It does not contain `67%` and `91%`, likely because those values live in the associated figure or another slice. Preserve the first finding; separately resolve or delete the second.

23. **Same qualifier false positive as Drops 3 and 11.**  
    The source states the retail and productivity values almost verbatim.

24. **Two defects.**  
    `375` is present as `75-375`, triggering the parser bug; “*reflecting the scale of occupational restructuring anticipated across sectors*” is an uncited interpretive tail. Normalize the range and trim the tail.

25. **Supported core plus overreach.**  
    Span: “*contradictions … around labor replacement, skills gaps, and increasing digital divide, especially in developing economies*.”  
    Added claim: “*wage and skill impacts … vary significantly by occupation and regional context*.” Preserve the first clause; regenerate or omit the second.

26. **Dedup pointer.**

27. **Dedup pointer.**

28. **Dedup pointer.**

29. **Dedup pointer.**

30. **Definite parser false drop.**  
    The exact span contains both `75-375 million` and Keynes’s 1930 technological-unemployment concern. The sentence is supported.

### Drops 31–34

31. **Gross span-selection failure.**  
    The claim combines STEM figures around offsets `1100-1900` with retail figures around `8100-8900`. Because no single 800-character window can contain both, the span finder falls back to `0-800`—the source’s title page. Every number then fails. This sentence should be split into two citations.

32. **Mostly supported across multiple source locations.**  
    The selected slice contains actual Claude-usage material plus the `10 → 0.6` BLS result; “through 2034” is in the source’s earlier summary. Split/rebind.

33. **Supported main insight plus broadened tail.**  
    The span says AI may “*alter political and economic landscapes … by reconfiguring labor markets, economies*.” The conclusion about Fourth Industrial Revolution effects extending into “*broader societal disruption*” is an extrapolation. Keep the sourced proposition; trim the extrapolation.

34. **Dedup pointer.**  
    The source supports four technological revolutions and automation dynamics, not the local report heading.

### Quantified Insight/Comprehensiveness loss

The RACE component results give the best observed treatment estimate:

| Metric | Faith OFF A | Faith ON B | Loss | Share of B→champion gap |
|---|---:|---:|---:|---:|
| Comprehensiveness | 0.4138 | 0.3828 | **−0.0310** | **41.9%** |
| Insight | 0.3837 | 0.3388 | **−0.0449** | **49.6%** |
| Instruction following | 0.4288 | 0.3865 | −0.0423 | 58.6% |
| Readability | 0.3478 | 0.3203 | −0.0276 | 24.9% |
| Overall | 0.3992 | 0.3610 | **−0.03825** | **45.7%** |

Those values are in the stored [A result](/home/polaris/wt/outline_agent/third_party/deep_research_bench/results/race/polaris_gate_task72_A/raw_results.jsonl:1), [B result](/home/polaris/wt/outline_agent/third_party/deep_research_bench/results/race/polaris_gate_task72_B/raw_results.jsonl:1), and [champion result](/home/polaris/wt/outline_agent/third_party/deep_research_bench/results/race/polaris_step3_control/raw_results.jsonl:1).

This is a configuration-run estimate, not a same-draft counterfactual, because A and B generated different outlines. But it is still the strongest observed ablation, and the direction is unambiguous.

## 2. The “45 number-mismatch drops”

First correction: **45 is not 45 unique dropped sentences.**

The counts `21 + 15 + 9 = 45` are nonexclusive reason tags across only **26 unique sentences**:

- 11 sentences carry one numeric reason.
- 11 carry two numeric reasons.
- 4 carry all three.

For example, Drop 5 carries both `no_integer_overlap` and `percent_not_in_cited_span`; Drop 9 carries numeric, percent, and content-overlap failures.

The exact-span requirement is a legitimate faithfulness invariant: a citation should point to the bytes that support the number. But converting a correct fact with a defective citation address into permanent content deletion is a self-inflicted wound.

Three distinct bugs are mixed together:

1. **Representation bug:** `75-375` becomes `75` and `-375`, so positive `375` appears “missing.”
2. **Wrong offset:** `47%` is elsewhere in the same source; the binder chose the demographic summary without the number.
3. **Impossible composite span:** Drop 31 combines facts thousands of characters apart, while the binder requires one 800-character window and falls back to the title page.

The root is visible in `_find_best_span_for_sentence`: it hard-requires only fractional decimals, ignores integer/percent claims, and if no window contains all decimals it returns `(0, window)` so verification can drop the sentence. See [live_deepseek_generator.py](/home/polaris/wt/outline_agent/src/polaris_graph/generator/live_deepseek_generator.py:352), especially the fallback at line 437.

Verdict: **the gate correctly diagnoses bad citation addresses, but the pipeline response is wrong.** Fix/rebind the address; do not weaken numeric faithfulness and do not delete the correct claim prematurely.

## 3. What verify and render did to the raw draft

The raw checkpoint contains zero occurrences of:

- `# Research report:`
- `STRONGEST VERIFIER`
- `Completeness checklist:`
- `This report reviews the available evidence on`
- `Scope: this review is bounded`

The final report contains one of each.

Code proves their origin:

- Title: `_assembled_title = f"# Research report: ... q['question']"` in [run_honest_sweep_r3.py](/home/polaris/wt/outline_agent/scripts/run_honest_sweep_r3.py:17657).
- Banner text: `build_d8_unadjudicated_banner()` in [provenance_generator.py](/home/polaris/wt/outline_agent/src/polaris_graph/generator/provenance_generator.py:3236), written into `report.md` after final reconciliation at [run_honest_sweep_r3.py](/home/polaris/wt/outline_agent/scripts/run_honest_sweep_r3.py:21280).
- Telemetry: `Completeness checklist: {covered}/{applicable}` is constructed at [run_honest_sweep_r3.py](/home/polaris/wt/outline_agent/scripts/run_honest_sweep_r3.py:16989) and inserted into Methods.
- The intro and scope are also deterministic render templates, not LLM draft prose; see [report_skeleton.py](/home/polaris/wt/outline_agent/src/polaris_graph/generator/report_skeleton.py:267).

The three explicitly identified chrome blocks are about:

- 50 words of prompt-as-title.
- 65 words of D8 warning.
- 5 words of `0/0` telemetry.

That is 120 words, about 2.6% of the 4,549-word scored artifact. The deterministic framing adds another 118 words, taking known injected front matter to roughly 5.2%.

More importantly, the manifest identifies only **1,788 words as verified section prose**. Against the supplied 5,823-word raw draft, only 30.7% of the draft’s prose survived into that verified body. The apparently modest “−22% net” is misleading because render subsequently backfills the document with methods, references, summaries, disclosures, and chrome.

## 4. Final B versus the true champion

It is all three: corpus/selection, composition, and post-processing damage. Post-processing is a large avoidable component, but it is not the entire 0.0837 gap.

| Property | Final B | True champion |
|---|---:|---:|
| Verified sentences | 55 | 91 |
| Verified body words | 1,788 | 3,230 |
| Cited bibliography entries | 14 | 37 |
| RACE Comprehensiveness | 0.3828 | 0.4569 |
| RACE Insight | 0.3388 | 0.4293 |
| Overall | 0.3610 | 0.4447 |

Champion statistics are recorded in [compose_summary.json](/home/polaris/wt/outline_agent/outputs/step3_control/compose_summary.json:24).

The champion has entire evidence families missing from B’s raw drafts:

- LLM task exposure and software-complement scenarios.
- OECD white-collar exposure.
- Korean firm and task-replacement evidence.
- Cross-country and Chinese regional coefficients.
- Noy’s 453-professional experiment.
- Organization Science online-labor-market evidence.
- ILO productivity/time-use evidence.
- Firm adoption, platform-worker pay, and policy mobility models.

By contrast, B’s raw drafts repeatedly recycle a narrow fact portfolio:

- `75 to 375` appears seven times.
- `13-fold` appears eight times.
- `0.6 percentage` appears nine times.
- `1947 and 1987` appears nine times.
- Retail and STEM findings each appear about eight or nine times.

That is a composition defect before verification. The raw prose is locally fluent, but it is not champion-level research composition: too much repeated Industry 4.0 context, too few independent empirical studies, and insufficient study-by-study synthesis.

The section collapse is stark:

- Context section: 20 kept / 7 dropped.
- Cross-sector: 4 / 16.
- Previous revolutions: 4 / 20.
- Adoption outcomes: 3 / 18.
- Forecasts: 4 / 21.
- Synthesis: 3 / 19.

The separate `champ_ourcorpus` result reached only 0.3671—just 0.0061 above B—and its Insight was 0.3411 versus B’s 0.3388. That is evidence that a better writer alone cannot turn the weaker/repetitive evidence portfolio into 0.4447. But B’s verifier damage still explains nearly half the observed B→champion gap.

## 5. Root causes and RACE-ranked fixes

### Rank 1 — Claim-atomic repair/rebind before destructive drop

Highest expected RACE leverage because it restores distinct findings rather than repeated copies.

Current chain:

```text
one long sentence
→ one/few imperfect 800-byte spans
→ any failed atom marks whole sentence false
→ whole sentence deleted
```

Required chain:

```text
sentence
→ decompose into atomic factual clauses
→ resolve each atom to one or more bounded spans
→ minimally trim/regenerate only unsupported atoms
→ full numeric + qualifier + NLI verification
→ commit only passed atoms
→ disclose genuinely unresolved atoms
```

This preserves faithfulness. No atom ships because it “seems true”; each repaired atom must pass the unchanged hard verifier. It directly fixes Drops 4, 5, 8, 9, 12–16, 21–25, and 31–33.

The existing one-retry sentence repair is too late and too coarse; the architecture must make repair/rebind the normal response to `NEUTRAL` or address mismatch, with drop as the terminal response only after bounded repair fails.

### Rank 2 — Make `fact_dedup` transactional

This is the most concrete code defect.

The prompt explicitly instructs the LLM to generate:

> “*the same finding is detailed in {PRIMARY_SECTION}*”

See [fact_dedup.py](/home/polaris/wt/outline_agent/src/polaris_graph/generator/fact_dedup.py:846).

The integration then:

1. Removes the original verified sentence.
2. Re-verifies the replacement.
3. Omits the replacement if it fails.
4. Does **not** restore the original.

That drop-on-failed-replacement behavior is visible at [multi_section_generator.py](/home/polaris/wt/outline_agent/src/polaris_graph/generator/multi_section_generator.py:11084), especially the “else: drop” assembly around line 11155.

Run B result:

> `n_rewrites_applied=44`  
> `n_rewrites_strict_verify_pass=0`  
> `n_rewrites_strict_verify_drop=44`

Root fix:

- Verify replacement before mutation.
- If replacement fails, roll back to the original verified `SentenceVerification`.
- Better: stop generating source-cited navigation prose entirely. Consolidate duplicate citations into the primary fact and omit later duplicates only after deterministic equivalence proof.
- A document-navigation sentence must never cite a research source as though that source proves the report’s local heading.

The `content_dedup_consolidate` module in the pack is innocent: it explicitly keeps all rows and only annotates clusters. The damaging module is `generator/fact_dedup.py`, not [content_dedup_consolidate.py](/home/polaris/wt/outline_agent/src/polaris_graph/synthesis/content_dedup_consolidate.py:1).

### Rank 3 — Fix numeric canonicalization and span selection

Specific changes:

- Normalize ASCII digit-hyphen-digit ranges so `75-375` yields positive endpoints `75` and `375`.
- Make the span finder consider every claimed integer, decimal, percentage, currency, and multiplier—not fractional decimals only.
- Never return `0-800` as a nominal citation when no single window contains all atoms. Return a structured “needs split/multi-span” result.
- Permit multiple bounded spans from the same evidence row for a composite sentence.
- Preserve exact-span verification after rebinding.

This fixes the number mismatch without opening whole-document numeric laundering.

### Rank 4 — Replace qualifier proximity with mention-level binding

Current `_marker_binds_numeral_in_span` asks whether any occurrence of a shared numeral is near a qualifier. It does not determine whether that qualified occurrence is the occurrence supporting the claim. See [strict_verify.py](/home/polaris/wt/outline_agent/src/polaris_graph/clinical_generator/strict_verify.py:273).

That is why “*around 7.5*” in the 2003–2013 clause can contaminate the later exact `7.5 → 5.7` finding.

Fix:

- Align the claim’s numeral to the matching source clause/occurrence.
- Compare qualifiers on the aligned mention, not anywhere in the 800-character span.
- On ambiguity, regenerate with the source qualifier and re-verify.
- Do not disable qualifier retention globally.

### Rank 5 — Separate scored answer text from audit artifact

Keep the honesty disclosures, but do not score them as report content.

- Scored title: a concise research title, not the entire raw user instruction.
- Scored article: verified literature-review body.
- Audit appendix/sidecar: D8 status, `0/0` checklist, model telemetry, retrieval health, source ledger.
- Full product artifact can retain both; the benchmark `article` field should contain the answer body only.

This is not a cosmetic substitute for the verifier fix. It removes an avoidable Instruction/Readability penalty after content survival is repaired.

### Rank 6 — Champion-style evidence selection and composition

Even faith-off A scores only 0.3992. After repairing destructive post-processing, the remaining path to 0.4447+ is:

- Broader independent study portfolio.
- Fewer recycled facts.
- Study-specific empirical sections.
- Cross-study agreement/conflict synthesis.
- Conclusions and gaps composed from the verified body.
- Approximately champion-level source utilization: 37 load-bearing references rather than 14.

## 6. Faithfulness verifier versus render chrome

The operator is right: **faithfulness-on is the bigger proven loss.**

Numerical adjudication:

- Faith OFF → ON: **−0.03825 overall**.
- B → champion gap: **0.08373**.
- Therefore the faith-on configuration explains about **45.7% of the overall gap**.
- It explains **49.6% of the Insight gap** and **41.9% of the Comprehensiveness gap**.
- Only 2 of 66 entailment failures were `CONTRADICTED`; the other 64 were `NEUTRAL`. Many NEUTRALs were address problems, incomplete multi-span binding, supported-core-plus-tail cases, or dedup navigation prose.

The three explicit chrome blocks are only about 120 words, although their semantics are unusually damaging: a raw prompt as title, “UNVERIFIED-by-D8,” and “0/0” advertise poor quality directly to the judge. They likely contribute disproportionately to Instruction Following and Readability, but there is no render-only ablation proving a loss larger than 0.03825.

The faith-off A run still trails the champion by 0.04548 overall, so faithfulness damage is not the whole story. That residual contains corpus quality, source selection, repetitive composition, and render bloat. It cannot honestly be assigned to chrome alone.

Final ranking of causal responsibility:

1. **Atomic/span-binding failure followed by destructive whole-sentence deletion.**
2. **`fact_dedup`’s non-transactional 44-for-44 verified-content destruction.**
3. **Narrow/repetitive pre-verification composition and underused corpus.**
4. **Scored render chrome and audit-density dilution.**

The root fix is therefore not “turn faithfulness off.” It is: **repair and accurately re-address claims before dropping them, never destroy a verified original until its replacement passes, then score only the clean verified report body.**
