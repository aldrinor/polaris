# Codex V30 Phase-2 run-12 audit

**7-dimension verdict**: BB=1/7 | BO=4/7 | LB=2/7 | TIE=0/7

## Ship classification

- Gate: `ITERATE`
- Net progress vs run-11: `BB+0, BO+0, LB+0`
- `SURPASS-5` reverted from a populated primary-trial frame to all-gap (`run-12 report.md:23`; `run-11 report.md:23`)
- Thomas clamp lost population + glucagon detail (`run-12 report.md:41`; `run-11 report.md:41`)
- `Trial Summary` row refs are off by one from `SURPASS-3` onward (`run-12 report.md:86-88`; bibliography `run-12 report.md:128-131`)

## V31 + V32 effectiveness

M-70 materially improved regulatory readability: FDA Mounjaro, FDA Zepbound, EMA, and TA924 are now prose paragraphs or sentences instead of stub lists (`run-12 report.md:47-59`) compared with run-11's mostly `not extractable` blocks (`run-11 report.md:47-84`). That is real progress, but not enough to lift Regulatory because the section still lacks U.S./EMA comparison, TA1026 and Health Canada remain gap-only, and the EMA/NICE coverage is still thin or misaligned (`run-12 report.md:53-67`).

M-71 succeeded on hedging discipline: Qwen moved `hedging_appropriateness` to `acceptable` (`qwen_judge_output.json:20-22`), and the narrative now aligns the headline limitation with the 13-item contradiction appendix (`run-12 report.md:92,106-123`; `run_log.txt:14`). But the report is still only about 3.3K words versus ChatGPT 4.8K and Gemini 6.8K, and most of Efficacy/Mechanism still reads as slot-stacked fragments (`run-12 report.md:5-41`). Narrative depth stays `LB`.

## Qwen citation_tightness flag

Verdict: partially fair, but overcalled if framed as a PRISMA failure.

The `Limitations` criticism is mostly overflagging. The generator contract explicitly treats Limitations as telemetry-grounded rather than bibliography-grounded: when a telemetry block is supplied, `strict_verify` checks limitation numbers against telemetry; otherwise it preserves a backward-compatible uncited limitations paragraph (`src/polaris_graph/generator/provenance_generator.py:916-930,952-972`; `tests/polaris_graph/test_m204_limitations_verify.py:10-13,129-160`; `tests/polaris_graph/test_limitations_gap3.py:88-132`). Run-12's limitation sentence matches local telemetry: T1/T4/T7 fractions in `manifest.json:21-30` and `corpus_approval.json:504-512`, 13 contradictions in `manifest.json:16` and `run_log.txt:14`, and the 2010 start date in `protocol.json:21-23`.

Under PRISMA 2020, Methods and Discussion/Limitations need transparent reporting of information sources, dates, synthesis methods, and limitations of the evidence base; PRISMA does not require inline numbered citations for each internally generated telemetry sentence. So Qwen is overflagging if this is read as a PRISMA-rule violation.

The `Methods` criticism is directionally fair as a traceability/style issue, but not because PRISMA requires adjacent literature citations. Run-12 exposes internal pipeline facts (`run-12 report.md:95-104`) without inline pointers to the artifacts that substantiate them. Some are recoverable from local telemetry (`manifest.json:2-30,851`; `run_log.txt:6-15`), but some, such as `scope_query_validator: 41 kept / 23 dropped`, are only surfaced in the report (`run-12 report.md:96`). So Qwen is right that traceability is weaker than the rest of the report; it is wrong if interpreted as "PRISMA demands [N] markers in Methods/Limitations." The real fix is artifact-backed method citations or parenthetical file pointers, not converting telemetry prose into ordinary evidence bibliography claims.

## 7-dim analysis

### 1. Citations — BO

Flat versus run-11. Run-12 still beats Gemini on source hierarchy because its bibliography remains dominated by T1/T2/T3 and official regulatory sources, whereas Gemini's works cited visibly include Pharmacy Times, Lilly promo, and other low-tier or media items (`run-12 report.md:127-159`; `state/compare_gemini_dr.txt:680-688`).

It still loses to ChatGPT and does not reach `BB`. The `Trial Summary` cites the wrong references from `SURPASS-3` onward (`run-12 report.md:86-88` versus bibliography `128-131`), several T1 bibliography items still have blank URLs (`run-12 report.md:127,129-135`), and Methods/Limitations contain uncited telemetry prose (`run-12 report.md:92,95-104`). ChatGPT remains tighter on adjacent support and source prioritization (`state/compare_chatgpt_dr.txt:51-53,966-982`).

### 2. Regulatory — LB

Improved surface quality, but no category lift. M-70 converts four regulatory subsections from stub lists to usable prose (`run-12 report.md:47-59`) versus run-11's mostly `not extractable` blocks (`run-11 report.md:47-84`).

That still trails both comparators. ChatGPT gives an explicit U.S./EMA warning/contraindication comparison (`state/compare_chatgpt_dr.txt:36-49,966-982`). Gemini is overclaimed, but it still delivers fuller FDA/Health Canada warning narrative (`state/compare_gemini_dr.txt:530-645`). Run-12 still has TA1026 and Health Canada as gap-only (`run-12 report.md:63-67`), the EMA subsection is only one sentence and does not match its pediatric-heavy heading (`run-12 report.md:53-55`), and the TA924 sentence oddly attributes NICE content to the "EPAR" (`run-12 report.md:57-59`). Regulatory remains `LB`.

### 3. Jurisdiction — BO

Flat versus run-11. Run-12 still explicitly spans the U.S., EU, U.K., and Canada in-body (`run-12 report.md:45-67`), which keeps it broader than Gemini's mainly FDA/Health Canada discussion (`state/compare_gemini_dr.txt:530-645`).

It still loses to ChatGPT on jurisdictional usability because ChatGPT materially contrasts U.S. and EMA labeling rather than merely listing authorities (`state/compare_chatgpt_dr.txt:36-49,966-982`). So Jurisdiction remains `BO`, not `BB`.

### 4. Claim-frames — BO

Category unchanged, but weaker inside the category. Run-12 still benefits from explicit slot discipline and honest gap language across the contract scaffold (`run-12 report.md:5-41`), which remains safer than Gemini's fuller but more overclaimed framing (`state/compare_gemini_dr.txt:191-213,329-352,419-433`).

But this run regresses materially at the slot level. `SURPASS-5` falls back to all-gap (`run-12 report.md:23`) after run-11 had a populated primary-trial result (`run-11 report.md:23`), Thomas clamp loses population and glucagon detail (`run-12 report.md:41`; `run-11 report.md:41`), and `SURPASS-6` plus `SURPASS-CVOT` remain gap-only (`run-12 report.md:27,31`). ChatGPT still clearly leads on pivotal-trial completeness, especially `SURPASS-6` and CVOT (`state/compare_chatgpt_dr.txt:455-510,522-540`). `BO` holds, but narrowly.

### 5. Structure — BO

Slightly better than run-11, but still not `BB`. The report keeps the contract slot scaffold across efficacy, mechanism, regulatory, safety, comparative, subgroups, methods, and contradiction disclosures (`run-12 report.md:5-123`). It also fixes the worst run-11 table problem by replacing the stale 2-row SURMOUNT-only summary and dropping the broken timeline (`run-12 report.md:81-88`; `run-11 report.md:98-110`).

However, the remaining table is still shallow and partly misbound: the row references are off from `SURPASS-3` onward (`run-12 report.md:86-88,128-131`), and the summary abstracts away too much of the underlying trial detail. ChatGPT still offers the better end-to-end structural arc because it pairs study architecture with an explicit evidence timeline (`state/compare_chatgpt_dr.txt:50-55,1096-1110`). Run-12 still beats Gemini on auditability, so Structure stays `BO`.

### 6. Contradictions — BB

Still the strongest dimension. Run-12 keeps a clear contradiction appendix, explains detector over-grouping, and explicitly tells the reader that body claims are strict-verify traceable (`run-12 report.md:106-123`). The headline limitation now numerically matches the appendix and run telemetry at 13 contradictions (`run-12 report.md:92,107`; `manifest.json:16`; `run_log.txt:14`).

ChatGPT discusses uncertainty but not in an equivalent machine-auditable contradiction inventory (`state/compare_chatgpt_dr.txt:1065-1086`). Gemini closes with confident synthesis and no comparable contradiction layer (`state/compare_gemini_dr.txt:664-679`). `BB` holds.

### 7. Narrative depth — LB

No lift. M-71 clearly improved hedging discipline and contradiction-awareness (`qwen_judge_output.json:20-22`; `run-12 report.md:90-123`), and the report is modestly longer than run-11.

But the core problem remains: most of Efficacy and Mechanism are still terse slot bundles rather than sustained synthesis (`run-12 report.md:5-41`), and the total length is still well below ChatGPT and Gemini. ChatGPT sustains the strongest continuous clinical narrative across efficacy, safety, regulation, uncertainty, and timeline (`state/compare_chatgpt_dr.txt:593-630,915-985,1058-1112`). Gemini remains broader on `SURPASS-5/6`, `SURMOUNT-2`, CVOT, and regulatory updates even though parts are overclaimed (`state/compare_gemini_dr.txt:191-213,329-352,419-457,530-645`). Narrative depth remains `LB`.

## Recommended action

`ITERATE-narrow`

Do not ship or checkpoint this run. V31/V32 produced real gains, but the category tally is still `1 BB | 4 BO | 2 LB`, so it misses both gates. The narrowest high-value next pass is:

- restore `SURPASS-5` and Thomas claim-frame quality while finally extracting `SURPASS-6`;
- finish Regulatory as actual cross-jurisdiction synthesis, especially EMA/Health Canada/TA1026;
- add artifact-backed inline method/limitations pointers so telemetry prose is traceable without pretending it is ordinary evidence bibliography.
