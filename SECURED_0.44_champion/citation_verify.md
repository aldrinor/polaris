# Champion citation reproducibility — DEFINITIVE verification

**Question:** Can the champion report be reproduced from cp4 ALONE, or does it cite sources that
came from live web-search (making cp4 insufficient to preserve the champion)?

**Answer: NO — cp4 alone cannot reproduce the champion's citations. Proven at the mechanism level.**
23 of the 37 cited sources are absent from cp4; live web-search demonstrably fired during the
champion compose and its fetched sources were folded into the working pool and cited.

---

## The mechanism artifact was found (identity proven)

- `/home/polaris/wt/outline_agent/outputs/step3_control/report.md` is **byte-identical** to the
  champion: `md5 = 4f57c31b83edb892be7ef795d6ef8d05` == `/home/polaris/polaris_project/SECURED_0.44_champion/champion_0.4447_report.md`.
- Sidecars in the same dir: `bibliography.json` (37 entries, each maps ref number -> evidence_id),
  `compose_summary.json`, `methods.md`, `multi_section_outline.json`.
- Compose log survives: `/home/polaris/wt/outline_agent/outputs/step3_control_compose.log` (417 KB).
- Corpus used at compose: `cp4_corpus_s3gear_329.corrected.json` (per compose_summary). On disk both
  `cp4_corpus_s3gear_329.json` and `...corrected.json` contain **997 evidence rows, max id `ev_1270`**.

Note: `champ_ourcorpus/` (Jul 15) is a *different* run on `cp4_corpus_from_newcards.json` (838 rows,
DOI-only refs) — NOT the champion. Ignore it for this question.

---

## PART 1 — Mechanism-level citation membership (DEFINITIVE)

Every cited evidence_id was extracted from `step3_control/bibliography.json` and tested for
membership in the cp4 evidence-id set (identical result for `.json` and `.corrected.json`, 997 ids).

- **14 / 37 cited ids ARE in cp4** — refs [7,13,14,16,17,19,24,27,28,29,34,35,36,37].
  (Includes 2 named-seed entities present in cp4: `acemoglu_restrepo_automation_tasks`, `eloundou_gpts_are_gpts`.)
- **23 / 37 cited ids are NOT in cp4** — refs [1,2,3,4,5,6,8,9,10,11,12,15,18,20,21,22,23,25,26,30,31,32,33].

**Decisive signature:** cp4's maximum evidence id is `ev_1270`. **All 23 absent cited ids are
`ev_1271` or higher** (ev_1271, 1273, 1275, 1276, 1282, 1289, 1298, 1299, 1300, 1317, 1318, 1319,
1321, 1341, 1342, 1346, 1354, 1355, 1356, 1360, 1361, 1372, 1374) — i.e. exactly the block appended
*after* the cp4 corpus ceiling. This is the fingerprint of rows added at compose time.

The 23 not-in-cp4 references (number | title | URL):
```
[1]  The Fourth Industrial Revolution: what it means and how to respond   weforum.org/stories/2016/01/...
[2]  Fourth Industrial Revolution - Wikipedia                             en.wikipedia.org/wiki/Fourth_Industrial_Revolution
[3]  Artificial intelligence and technological unemployment               sciencedirect.com/.../S2199853125001428
[4]  The Fourth Industrial Revolution – Smart Technology...                pmc.ncbi.nlm.nih.gov/articles/PMC9301265/
[5]  Unlocking the value of AI in HRM through AI capability framework      doi.org/10.1016/j.hrmr.2022.100899
[6]  4IR between Knowledge Management and Digital Humanities               doi.org/10.3390/info13060292
[8]  Robots, AI, and automation: the 4th industrial revolution is here     tomorrow.city/robots-ai-and-automation-...
[9]  Automation and New Tasks (Acemoglu-Restrepo, JEP)                     doi.org/10.1257/jep.33.2.3
[10] How Technology Displaces and Reinstates Labor (MIT mirror)            shapingwork.mit.edu/.../acemoglu-restrepo-2019...pdf
[11] How Technology Displaces and Reinstates Labor (2nd mirror)            concetticontrastivi.org/.../acemoglu-restrepo-2019...pdf
[12] The Labor Market Impacts of Technological Change (NBER w30074)        nber.org/system/files/working_papers/w30074/...
[15] AI and the Labour Market in Korea - OECD                              oecd.org/.../the-impact-of-ai-on-the-labour-market_...
[18] The Impact of AI on the Labor Market (Michael Webb)                   michaelwebb.co/webb_ai.pdf
[20] 59 AI Job Statistics - National University                           nu.edu/blog/ai-job-statistics/
[21] AI and Jobs: Limited Disruption So Far - Morgan Stanley               morganstanley.com/insights/articles/ai-jobs-modest-impact-...
[22] The AI Revolution in Labor...                                        japksu.com/index.php/esj/article/download/819/129
[23] AI, Task Changes in Jobs, and Worker Reallocation (IZA)               docs.iza.org/dp17554.pdf
[25] AI and Economic Development: A Systematic Review                      doi.org/10.1007/s13132-026-03385-w
[26] ILO Research Brief (GenAI on jobs and work organization)              ilo.org/.../Research Brief_The impact of GenAi...pdf
[30] The economic impact of AI on employment and income disparities        econstor.eu/.../Sholler-and-MacInnes.pdf
[31] Business students' perceptions of AI's impact on labor market         doi.org/10.3846/jbem.2025.24349
[32] Automation and Industry 4.0 in production engineering                 doi.org/10.7862/rm.2025.14
[33] Occupations and Inequality: Theoretical Perspectives                  doi.org/10.1007/s11577-020-00685-0
```

---

## PART 2 — Work-identity match of the 37 rendered references vs cp4

Best-identity matching (exact URL -> DOI -> normalized-title token overlap) of the 23 not-in-cp4-by-id
references, to distinguish genuine absence from URL-form/mirror duplicates of a work cp4 DOES hold:

- **Same WORK exists in cp4 (URL-form / mirror / DOI duplicate) — ~6 refs:**
  - [9] Acemoglu-Restrepo JEP -> DOI `10.1257/jep.33.2.3` == cp4 `acemoglu_restrepo_automation_tasks`.
    [10] and [11] are PDF mirrors of the SAME Acemoglu-Restrepo 2019 work (also in cp4).
  - [15] Korea OECD -> title match to cp4 `ev_207` (~0.83).
  - [18] Michael Webb, "The Impact of AI on the Labor Market" -> title match cp4 `ev_044` (1.00).
  - [31] Business students' perceptions -> DOI `10.3846/jbem.2025.24349` == cp4 `ev_199`.
- **Genuinely absent works cp4 cannot supply — ~17 refs:** [1] weforum, [2] wikipedia,
  [3] sciencedirect S2199853125001428, [4] PMC9301265, [5] hrmr.2022.100899, [6] info13060292,
  [8] tomorrow.city, [12] NBER w30074, [20] nu.edu blog, [21] morganstanley, [22] japksu,
  [23] IZA dp17554, [25] s13132-026-03385-w, [26] ILO research brief, [30] econstor Sholler-MacInnes,
  [32] rm.2025.14, [33] s11577-020-00685-0.
  (The flagged non-journal hosts — weforum.org, wikipedia.org, tomorrow.city, nu.edu/blog,
  morganstanley.com — are ALL genuinely absent from cp4, not URL-form mismatches.)

Classification of all 37: **14 IN_CP4** (by id), **~6 WORK-coverable-but-cited-row-absent**,
**~17 NOT_IN_CP4 at the work level**. Even the 6 work-coverable ones are cited via live-added rows
(ev_1271+), so the exact cited row is not reproducible from cp4 for any of the 23.

---

## PART 3 — Did live search actually fire? YES (proven from the compose log)

`outputs/step3_control_compose.log` (`polaris_graph.live_retriever`) shows the outline agent's
live-web tool firing repeatedly during the champion compose:

- **9 SERPER + 10 Semantic-Scholar (S2) search rounds** (one per section, plus retries),
  02:32–02:46, queries like `SERPER q='Artificial Intelligence Fourth Industrial Revolution labor market restructuring'`.
- Each round: `31 unique candidates from search` -> relevance gate -> `fetch_ok` on live URLs.
  The fetched URLs include the exact champion citations absent from cp4, e.g.:
  `fetch_ok https://www.weforum.org/stories/2016/01/...` (=ref[1]/ev_1271),
  `...en.wikipedia.org/wiki/Fourth_Industrial_Revolution` (ref[2]/ev_1275),
  `...pmc.ncbi.nlm.nih.gov/articles/PMC9301265/` (ref[4]/ev_1276),
  `...doi.org/10.1016/j.hrmr.2022.100899` (ref[5]/ev_1282),
  `...doi.org/10.3390/info13060292` (ref[6]/ev_1289),
  `...tomorrow.city/robots-ai-and-automation-...` (ref[8]/ev_1273).
- **Fold-in into the working pool is logged explicitly:** `[outline_agent] auto-assign: routed N new
  ev_id(s) to section '...'` — 26+19+23+16+4+1+12+2+4 = **107 new evidence rows** added.
  `997 (cp4) + 107 = 1104`, which **exactly matches** `compose_summary.evidence_rows = 1104`.
- Config confirms availability: `src/polaris_graph/outline/outline_agent.py:212` returns
  `PG_OUTLINE_WEB_SEARCH` default ON ("champion path", line 209); the driver
  `scripts/compose_agentic_report_s3gear329.py` never sets it to 0.

So live search did not merely *have* the tool available — it CALLED it 9× and 23 of its
newly-fetched sources ended up cited in the final report.

---

## PART 4 — VERDICT

**(a) Sources genuinely NOT in cp4:** **23 of 37 cited sources** (definitive, from the mechanism
artifact: their evidence_ids ev_1271–ev_1374 are not in cp4's 997-row / max-`ev_1270` set). At the
looser work-identity level, ~17 are genuinely-absent works and ~6 are live-added duplicates of works
cp4 also holds — but all 23 cited *rows* are non-cp4.

**(b) Live search demonstrably fired:** YES. 9 SERPER + 10 S2 rounds; 107 live rows folded in
(`auto-assign: routed ... new ev_id(s)`); fetched URLs match the non-cp4 citations one-to-one.
Proven from `outputs/step3_control_compose.log`, not inferred.

**(c) Bottom line — can cp4 ALONE reproduce the champion's citations? NO.**
- Proven from the mechanism artifact (not inferred from URL/title matching).
- The gap = the 23 references listed in Part 1 (ev_1271–ev_1374), which entered only via the
  compose-time `live_retriever`. cp4 (997 rows, max ev_1270) supplies only the 14 in-cp4 citations;
  the remaining 23 — including every 4IR framing source (weforum, wikipedia, tomorrow.city) and the
  headline stats sources (Morgan Stanley, NU blog, IZA, ILO brief) — cannot come from cp4.

**Confidence:** Part 1/3 are definitive (byte-identical artifact + surviving compose log with logged
fold-ins whose count reconciles exactly to compose_summary). Part 2's genuine-vs-mirror split is
high-confidence but relies on DOI/title matching.
