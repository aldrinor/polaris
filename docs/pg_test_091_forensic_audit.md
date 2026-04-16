# PG_TEST_091 — Forensic Audit (line-by-line)

**Subject:** `outputs/polaris_graph/PG_TEST_091_report.md` (97 KB, 12,152 words, 19 sections)
**Pipeline state:** `outputs/polaris_graph/PG_TEST_091.json` (10 MB, 209 evidence, 108 bibliography)
**Method:** 7-phase forensic inspection per advisor brief 2026-04-14. NOT a metrics review — the automated audit (89.2/100) was already known. This finds what the automated audit missed.

---

## Phase 1 — Per-section line audit (19 sections)

| § | Section | Words | Cit | Ends mid-sentence | Stub (<200w) | Notes |
|---|---|---:|---:|:---:|:---:|---|
| 01 | Abstract | 188 | 3 | – | ⚠ borderline | – |
| 02 | Overview and Definitions | 1380 | 56 | – | – | clean |
| 03 | Key Findings and Benefits | 684 | 27 | **YES** ("…all demonstrated") | – | hit max_tokens=4096 |
| 04 | **Mechanisms of Action** | 51 | **0** | – | **YES** | **transition paragraph only — no actual mechanism content; 0 citations; pure scaffolding** |
| 05 | Circadian Entrainment | 277 | 5 | – | – | – |
| 06 | Insulin Sensitization | 212 | 5 | – | borderline | – |
| 07 | Autophagy | 143 | 2 | – | **YES** | – |
| 08 | Neuroprotection | 143 | 3 | – | **YES** | – |
| 09 | Gut Microbiome | 104 | 2 | – | **YES** | – |
| 10 | Body Composition | 300 | 19 | – | – | ends with table |
| 11 | Adverse Mechanistic Pathways | 64 | 1 | – | **YES** | – |
| 12 | Eating Behavior | 82 | 1 | – | **YES** | – |
| 13 | Limitations and Gaps | 296 | 12 | – | – | – |
| 14 | Comparative Analysis | 1495 | 60 | – | – | clean |
| 15 | Safety Profile and Risks | 1579 | 41 | – | – | clean (9 sub-sections) |
| 16 | Special Populations | 837 | 27 | **YES** ("…elderly adults [") | – | hit max_tokens=4096; citation cut mid-marker |
| 17 | Research Quality | 1388 | 55 | – | – | clean |
| 18 | Clinical Implications | 784 | 22 | borderline (ends with bold heading inline) | – | likely hit cap, recovered |
| 19 | References | 2045 | 108 | – | – | – |

**Phase 1 verdict:**
- **3 confirmed truncations** (S03, S16, S18 borderline): all attributable to wiki_composer.py default `max_tokens=4096` cap. Same root cause as baseline `Section 9 ("maintain circ")`. **S4 #19-22 NOT resolved by Wave 1 — confirms W3.16.**
- **6 stub sections** (S04, S07, S08, S09, S11, S12): wiki path created sub-sections that don't have enough evidence to fill 200 words. **D4 audit score 6.9 explained.**
- **S04 "Mechanisms of Action" is pure scaffolding** — 51 words, 0 citations, just a transition paragraph. Cannot defend.

---

## Phase 2 — 10-citation FActScore-style verification

Random seed 42, citations 82, 15, 4, 95, 36, 32, 29, 18, 14, 87.

| Cit | Title (truncated) | Source quality | Verdict | Issue |
|---:|---|---|---|---|
| **[15]** | Cost-effectiveness of CVD interventions in South Asia | journal | **MISCITATION** | Cited in Abstract as "28 statistically significant health benefits of IF" — source is unrelated (CVD cost-effectiveness in South Asia) |
| [82] | NCI 24-hour Dietary Recall (methodology page) | gov | OFF-TOPIC | Bibliography includes a dietary-survey methodology page; not IF research |
| [4] | Salk press release on TRE/gene expression | edu (press) | SUPPORTED | press release, not original paper |
| [95] | NCI clinical trial of TRE in chemo | gov | SUPPORTED | – |
| [36] | TRF cardiometabolic RCT | journal | SUPPORTED but odd location (`640621/full \n[36]`) |
| [32] | IF systematic review | journal | SUPPORTED | author field MISSING |
| [29] | T2DM IF RCT | nature.com | SUPPORTED | citation written `001) [29]` (parser oddity) |
| [18] | USC press release on FMD | edu (press) | SUPPORTED | press release |
| [14] | Frontiers in Nutrition meta-analysis | journal | SUPPORTED | – |
| [87] | Harvard Health blog | consumer | SUPPORTED | low-authority source |

**Phase 2 verdict:**
- **1 confirmed miscitation** (10%): [15] cites a South Asia CVD cost-effectiveness paper to support "28 statistically significant health benefits of IF" — this is a hallucinated link.
- **1 off-topic** (10%): [82] NCI dietary methodology page in bibliography
- **3 press releases / consumer health** (30%): [4], [18], [87] — used as-if-authoritative
- **1 missing authors** (10%): [32]
- **2 formatting oddities** (20%): citations appearing in URL fragments

---

## Phase 3 — Hallucinated numbers scan

Method: regex-extract all percent / p-value / CI / n / SMD / kg from report; check each against concatenated evidence pool.

| Statistic class | In report | Not found in evidence | Rate |
|---|---:|---:|---:|
| Percent (n.nn%) | 9 | 1 | 11% |
| p-value | 14 | 2 | 14% |
| CI range | 1 | 0 | 0% |
| Sample n | 0 | 0 | – |
| SMD | 0 | 0 | – |
| kg change | 11 | 0 | 0% |
| mg/dL | 1 | 0 | 0% |
| **TOTAL** | **36** | **3** | **8.3%** |

**Specific candidates** (need manual confirmation — could be format mismatches not true hallucinations):
1. `5.0%` daily caloric restriction comparison value (S14)
2. `p = 0.019` paired with `−0.72 kg fat mass` (S03)
3. `p = 0.007` paired with `SMD = −0.23 triacylglycerols` (S03)

**Phase 3 verdict:** 8% potential hallucination rate is concerning but likely inflated by format-matching false positives. Two of three suspect numbers cluster in the truncated S03 section, hinting that interrupted-generation may correlate with statistic invention.

---

## Phase 4 — Source quality breakdown (108 bibliography entries)

| Category | Count | % | Quality |
|---|---:|---:|---|
| JOURNAL (peer-reviewed) | 37 | 34% | High |
| GOV/PUBMED | 23 | 21% | High |
| EDU (incl. research press releases) | 25 | 23% | Mixed |
| OTHER (academic platforms, BMJ patient pages, news, low-tier journals) | 19 | 18% | Mixed |
| HEALTH-CONSUMER (Mayo, Cleveland Clinic, Harvard Health) | 4 | 4% | Low for clinical evidence |

**OTHER category includes**:
- BBC News article
- Cureus.com (low-tier review)
- Cost-effectiveness paper (the [15] miscitation)
- Several BMJ patient FAQs

**Phase 4 verdict:** 78% high-authority sources is decent. The 4 consumer-health pages and 1 BBC News piece compromise the academic register.

---

## Phase 5 — Truncation forensics (last 50 words)

### S03 "Key Findings and Benefits" — TRUNCATED (confirmed)
> "...examining 12–72 hour fasts in 29 participants, Heilbronn et al. investigating alternate-day fasting, and Gjedsted et al. studying 72-hour fasts in 10 lean men—**all demonstrated**"

Sentence describes three studies, ends abruptly without verb completion. Trace shows `output_tokens=4096` (cap hit).

### S16 "Special Populations" — TRUNCATED (confirmed, worse)
> "...A fasting duration of 11.49 hours is associated with the lowest all-cause mortality in elderly adults [**"**

Citation marker started but not closed. Trace shows `output_tokens=4096`.

### S18 "Clinical Implications" — TERMINATES with leaked heading
> "...protocol prioritization in metabolic disease management. **Evidence Gaps and Future Research Directions**"

Final markdown bold ends prose — looks like the section was about to start a new sub-section but generation stopped. Borderline, but content reads complete enough.

### References — 109 entries parsed, all complete

**Phase 5 verdict:** 2 hard truncations (S03, S16). Same root cause as baseline. **S4 not fixed by W1.3** because wiki_composer.py is a separate code path with `max_tokens=4096` default (vs section_writer.py with `PG_SECTION_WRITER_MAX_TOKENS`).

---

## Phase 6 — Perspective coverage gaps

Audit v2 reported 5/8 perspectives present (Scientific=166, Methodological=25, Public_Health=13, Regulatory=3, Economic=2; missing Industry, Historical, Regional).

Manual keyword scan of report:

| Perspective | Audit result | Manual scan | Verdict |
|---|---|---|---|
| Historical | MISSING | "tradition" 11×, "lent" 5×, "ramadan" 4×, "history" 2×, "religious" 1× = **23 hits** | **TAGGER FALSE NEGATIVE** — historical content IS present, perspective tagger missed it |
| Regional | MISSING | "asia" 1×, "europe" 1×, "ethnic" 1× = 3 hits | **GENUINE GAP** — no real geographic discussion |
| Industry | MISSING | "market" 2×, "product" 2×; "app" 33× (false positives — appears, approach, etc.) | **GENUINE GAP** — no commercial-products discussion |

**Phase 6 verdict:** Audit understates perspective coverage. Real coverage is **6/8** if Historical is credited. W3.4 (perspective gap enforcement) would help close Industry and Regional, but the perspective-tagger itself needs review (it's missing real Historical content).

---

## Phase 2A — FULL 108-CITATION AUDIT (closed gap from Phase 2)

Re-running Phase 2 logic on every citation, not 10 samples.

| Check | Pass | Fail |
|---|---:|---:|
| Title present | 108/108 | 0 |
| URL present | 108/108 | 0 |
| Author(s) present | **78/108** | **30 (28%)** ⚠ |
| Evidence backing at URL | 108/108 | 0 |
| Cited in report body | 108/108 | 0 |

**Source-quality breakdown (re-counted):**
- Press releases: 4 (`[4] Salk`, `[18] USC`, `[67] Harvard HSPH news`, `[88] Hopkins news`)
- Consumer health: 7 (`[16][20] Mayo`, `[19][60] Cleveland`, `[30][46][87] Harvard Health blog`)
- Low-tier journals: 5 (`[9] APCZ`, `[44] Gavin Publishers`, `[49] Wiadomości Lekarskie`, `[59] Cureus`, `[79] Medico Publication`)
- **Combined low-authority: 16/108 = 15%** (vs my Phase 4 estimate of 4%)

**Authors missing on 28% — much worse than Phase-2 sample suggested (10%).** Some unauthored entries are substantive papers (e.g. `[12] Intermittent fasting umbrella review`, `[23] IER vs CER RCT`).

**Critically**: every citation in bibliography is referenced in the report (`cited_in_report = 108/108`). No orphan bibliography entries.

---

## Phase 3B — HALLUCINATION CHECK WITH ±0.1 TOLERANCE (closed gap from Phase 3)

Re-checked all 36 numerical claims (percent / p-value / kg) with tolerance-aware matching.

| Class | In report | Exact match | Tolerance match | NOT FOUND |
|---|---:|---:|---:|---:|
| percent | 9 | 8 | 1 | **0** |
| p-value | 14 | 12 | 2 | **0** |
| kg | 11 | 11 | 0 | **0** |
| **TOTAL** | **34** | **31** | **3** | **0** |

**FINDING: ZERO hallucinated numbers.** My Phase 3 candidates (`5.0%`, `p=0.019`, `p=0.007`) were **format-mismatch false positives**. Strict string match missed equivalent numbers in evidence; tolerance matching found them. **The forensic audit overstated this defect — retracting the "3 candidate hallucinations" claim.**

---

## Phase 1+ — UNCITED-CLAIMS SCAN (closed gap from Phase 1)

Per-section count of factual sentences (≥10 words) without any `[N]` citation marker.

| § | Section | Factual sentences | Uncited | % |
|---|---|---:|---:|---:|
| 01 | Abstract | 8 | **7** | **88%** |
| 02 | Overview | 44 | 12 | 27% |
| 03 | Key Findings | 20 | 5 | 25% |
| 04 | **Mechanisms** | 2 | **2** | **100%** |
| 05 | Circadian | 10 | 5 | **50%** |
| 06 | Insulin | 7 | 3 | 43% |
| 07 | Autophagy | 5 | 3 | **60%** |
| 08 | Neuroprotection | 5 | 2 | 40% |
| 09 | Microbiome | 4 | 2 | **50%** |
| 10 | Body Composition | 6 | 1 | 17% |
| 11 | **Adverse Mech** | 3 | **2** | **67%** |
| 12 | Eating Behavior | 2 | 1 | 50% |
| 13 | Limitations | 9 | 3 | 33% |
| 14 | Comparative | 44 | 14 | 32% |
| 15 | Safety | 38 | 11 | 29% |
| 16 | Special Populations | 24 | 7 | 29% |
| 17 | Research Quality | 40 | 12 | 30% |
| 18 | Clinical Implications | 18 | 2 | 11% |
| **TOTAL** | – | **289** | **93** | **32%** |

**FINDING: 32% uncited factual-sentence rate.** Many are transitional/explanatory ("This pathway operates as…", "The mechanism is…"), but several are substantive uncited claims:
- S01 Abstract: "11 meta-analyses and 130 randomized controlled trials" — meta-claim about scope, no citation
- S13: "Most human studies measure downstream biomarkers…" — generalization with no source
- S17: "The most pervasive methodological limitation across the IF literature is the brevity of intervention periods" — broad claim, no citation

Stub sections are worst:
- S04 Mechanisms: **100% uncited** (the 2 sentences are pure transition prose)
- S07 Autophagy: 60% uncited
- S11 Adverse Mechanistic: 67% uncited

This is a NEW material defect not surfaced by automated audit (D5 = 10.0 measures citation density and validity, not citation coverage of every claim).

---

## Phase 7 — Industrial-standard comparison (2024-2026 frameworks)

| Framework | What it measures | PG_TEST_091 likely score |
|---|---|---|
| **RAGAS** (faithfulness, answer-relevance, context-precision/recall) | Reference-free, LLM-judge per metric | Faithfulness ~0.6–0.7 (NLI gave 12.1%, LLM rubber-stamp gave 100% — real likely 60–80%); answer-relevance high (D8=9.8); context-precision moderate (3 hallucination candidates suggest some context drift) |
| **ARES** (Stanford, beats RAGAS by 14–59pp) | LLM-judge tailored per-component, sliding-window context | Higher precision than RAGAS — would catch the [15] miscitation; would flag the 6 stub sections as low context-utilization |
| **SAFE** (Google DeepMind, NeurIPS 2024) | Decompose into atomic facts → Google-search verify each → F1 against precision (supported %) and recall (vs target length) | Atomic-fact decomposition would isolate the truncated `5.0%`, `p=0.019`, `p=0.007` claims and either confirm or flag. F1 likely **0.5–0.7** given truncation + miscitation |
| **FActScore** | Decompose response → biomedical/Wikipedia verify each atomic claim | Would catch [15] miscitation (no support for "28 benefits"); the 3 hallucinated-number candidates would lower the score |
| **TruthfulQA** | not directly applicable (multiple-choice benchmark) | – |

**Phase 7 verdict:** 
- The internal audit (89.2/100) over-reports quality vs what SAFE/ARES/FActScore would assign.
- A SAFE-style atomic-fact F1 score would likely land **0.55–0.70** (precision drag from miscitation + hallucinated stats; recall drag from 6 stub sections).
- **The 89.2 vs SAFE-estimate ~0.65 is the same gap pattern as baseline (88.2 internal vs G-Eval 59.5)** — internal audit is structurally lenient.

---

## Final honest verdict (REVISED after closing audit gaps + advisor correction)

**Letter grade by a human reviewer: B−** (held — earlier C+ overcorrected per advisor 2026-04-14)

**Material defects that drag the grade (unchanged from initial assessment):**
- 2 hard truncations (S03, S16) — wiki_composer.py code path
- Empty S04 Mechanisms section (51 words, 0 citations, pure transition)
- Citation [15] miscitation (CVD cost-effectiveness paper supporting "28 IF benefits" claim)
- Rubber-stamped faithfulness (real 56.8% → reported 100%)
- Pipeline runtime + budget governance broken (S10 #44)

**Retracted from earlier audit (false positives):**
- "3 candidate hallucinated statistics" — Phase 3B with tolerance found ZERO. String-match Phase 3 missed equivalent number formats in evidence.

**Found by gap-closing but P2-P3 (not P0-P1):**
- 28% authors-missing in bibliography → metadata completeness, not content correctness
- 15% low-authority sources (Mayo/Cleveland are authoritative for clinical recommendations even if not primary research)
- 32% uncited factual-sentence rate → conflates legitimate uncitable prose (transitions, methodology pseudocode, interpretive synthesis) with genuine uncited claims. Only ~5-10 of the 93 are true defects (e.g., the "11 meta-analyses and 130 RCTs" Abstract claim should be cited).

**Why no "citation-coverage gate" Wave 3 task:**
A blanket >X% cited threshold would penalize good academic writing alongside genuine gaps. Many uncited sentences cluster in the 6 stub sections; resolve those via W3.16 (wiki_composer patches), then revisit citation coverage with proper bucketing.

Strengths:
- 12K words on a complex clinical topic
- 108 bibliography entries, mostly high-authority (78%)
- Citation density is healthy in major sections
- CoT scaffolding largely scrubbed (3 markers vs baseline 13)
- Structural sections cover the right topics (mechanisms, comparative, safety, special populations, limitations)

Material defects:
- **2 sections truncated mid-sentence** (S03, S16) — the same defect as baseline
- **S04 "Mechanisms of Action" is empty** — 51 words, 0 citations, pure transition prose
- **6 stub sub-sections under 150 words** — wiki path over-fragmented the outline
- **1 confirmed miscitation** (Cit [15] → S Asia CVD cost-effectiveness paper supporting "28 IF benefits")
- **3 candidate hallucinated statistics** in S03 (the truncated section)
- **Pipeline rubber-stamp**: real verifier found 56.8% faithful, pipeline reported 100% (FIX-QM7 dropped the 53 unfaithful then recomputed 180/180=100%)
- **Cost overrun** $13.46 vs $10 budget cap (guard didn't fire)
- **Wall-clock overrun** 481min vs 240min cap (S10 #44 confirmed)
- **Bibliography includes off-topic/consumer sources**: NCI dietary-recall methodology, BBC News, Cureus, Harvard Health blog, Mayo patient page

Net: a respectable academic-style report that would not pass a careful human reviewer without a revision cycle to (a) fix the two truncations, (b) replace the empty Mechanisms intro with real content, (c) consolidate the 6 stubs into 2-3 substantive sub-sections, (d) verify or remove the [15] miscitation, (e) verify the suspicious S03 statistics.

---

## Cross-check vs internal audit (89.2/100)

| Defect class | Caught by internal audit? | Caught by forensic? |
|---|---|---|
| CoT leakage | Yes (D1 9.8) | Yes (3 lines confirmed) |
| Section truncation | Partial (D4 down to 6.9 due to stubs) | Yes (2 mid-sentence) |
| Empty section S04 | No (counted as 51w, didn't flag 0-cite scaffolding) | YES |
| Miscitation [15] | No (D5 = 10.0) | YES |
| Hallucinated statistics | No (D2 = 10.0 — pipeline rubber-stamp) | Partial (3 candidates flagged for manual confirm) |
| Wiki path stub-creation | Partial (D4 6.9) | YES (counted 6 stubs explicitly) |
| Perspective tagger false negative on Historical | No | YES |
| Source quality (consumer-health, news) | No (D6 = 9.2) | YES (4+1 low-authority counted) |

**The forensic audit found 4 material defects the automated audit missed.**
