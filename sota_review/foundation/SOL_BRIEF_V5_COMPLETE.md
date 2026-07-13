# THE COMPLETE SITUATION — POLARIS vs DeepResearch Bench (RACE), task 72

## 0. MISSION AND NON-NEGOTIABLE
Beat cellcog (#1, 0.5603). Not parity. Not bodhi. FIRST PLACE.
Build a research system that beats SOTA on ANY question — not a machine that answers task 72.

THE ONE RULE THAT IS NOT FOR SALE:
  Every sentence is either ATTRIBUTED or OWNED.
  ATTRIBUTED names a source -> must be ENTAILED by THAT source's verbatim span.
  OWNED is the reviewer's voice -> names no source, carries NO new particular, and is EXPLICITLY
  ALLOWED to be non-entailed, because that is what INSIGHT IS.
  Fabrication = an ATTRIBUTED sentence its source does not entail.
  Insight     = an OWNED sentence its premises do not entail.
  SAME LOGICAL SHAPE — distinguished by WHOSE VOICE, not by entailment.
  A 0.60 obtained by fabricating is a 0.00. The artifact is burned regardless of score.

## 1. THE SCOREBOARD (measured, k=5 paired; judge noise SD=0.0074; smallest resolvable effect +0.0094)
  turn 1 baseline (rank10) 0.4292      <- pinned baseline
  turn 2                   0.4224      LOST (I changed corpus+structure+contract+attribution AT ONCE)
  turn 3                   0.4603      WON +0.0310 = 4.2x the smallest resolvable effect
  bodhi   (#2)             0.5441
  cellcog (#1)             0.5603      <- THE TARGET.  gap = 0.1000
  the reference article    8.041/10 weighted mean when judged against us

  score = T/(T+R). R IS NOT A CONSTANT: the same reference scores 8.033 vs us, 7.545 vs bodhi,
  7.363 vs cellcog. A STRONGER TARGET DRAGS THE REFERENCE DOWN. So the required T is lower than
  a naive calculation suggests — but we still must go from a weighted mean of 6.857 to ~9.4/10.

## 2. HOW TURN 3 WON — READ THIS CAREFULLY, IT REFRAMES EVERYTHING
  It won by FIXING BUGS, not by a new idea. Every one of these was mutilating the report before
  the judge ever read it:
   - THE FAITHFULNESS GATE WAS INVERTED: it fired ONLY on sentences that do NOT name a source. So
     ATTRIBUTED sentences (where a lie is fraud) were 100% UNGATED, and OWNED sentences (where
     non-entailment IS insight) were the only lane checked — and 97% of them were deleted.
   - THE SPLITTER AMPUTATED EVERY 'et al.' SENTENCE: re.split(r'(?<=[.!?])\s+') cut 'Autor et al.'
     into a stump + an orphan predicate. 5 stumps and 42 orphans SHIPPED TO THE JUDGE.
   - A RACE CONDITION: a module global mutated by 6 threads; the gate validated one subsection's
     prose against another subsection's cards.
   - THE GATE DELETED EVERY CROSS-SOURCE COMPARISON (found after turn 3 was scored, now fixed):
     the classifier credited a whole sentence to the FIRST author it recognised, then checked the
     SECOND paper's content against the FIRST paper's span. CONTENT_NOT_IN_SOURCE. Deleted. 3 of 3
     in a direct test. That is why our Critical Synthesis section was 210 WORDS OUT OF 8,012 — 2.6%
     of the report for 8% of the score.

## 3. THE FULL CRITERION LEDGER (turn 3, k=5. w = effective global weight, sums to 1.0)
     w      criterion                                        baseline -> TURN 3
  .0800  Analytical Depth in Characterizing AI-Driven Labor Mkt 6.90 -> 7.96  
  .0800  Critical Synthesis and Nuanced Evaluation            5.36 -> 6.36  JOINT-HEAVIEST
  .0725  Breadth of Labor Market Restructuring Dimensions     8.04 -> 7.78  REGRESSED
  .0725  Scope of Industry-Specific Analysis                  6.60 -> 5.76  REGRESSED -0.84
  .0640  Identification/Articulation of Emergent Themes       5.86 -> 7.20  
  .0500  Consistent Focus on the Question                     6.70 -> 8.04  
  .0480  Value and Foresight in Implications / Future         6.10 -> 5.42  REGRESSED -0.68
  .0480  Insightful Integration of AI within the 4IR          5.56 -> 6.46  
  .0435  Depth and Representativeness of Literature           5.16 -> 7.16  
  .0435  Exploration of AI's Disruptive Character and Scale   7.34 -> 7.14  REGRESSED
  .0375  Coverage of AI's Impact on VARIOUS INDUSTRIES        6.60 -> 5.82  REGRESSED -0.78
  .0375  Explicit Addressal of Significant Disruptions        7.66 -> 7.78  
  .0375  Integration of AI as Key Driver of the 4IR           6.60 -> 7.14  
  .0375  Exclusive Citation of HIGH-QUALITY JOURNAL ARTICLES  1.50 -> 7.32  biggest win; CAPPED by having NO REFERENCE LIST
  .0290  Balanced Discussion                                  7.10 -> 7.86  
  .0290  Grounding in AI and the 4IR                          6.40 -> 6.76  
  .0280  L1 Language Clarity, Precision, Academic Tone        4.90 -> 5.22  
  .0280  S1 Overall Structure and Logical Organization        5.36 -> 5.82  
  .0250  Adherence to Literature Review Format                6.26 -> 7.90  
  .0250  Exclusive Citation of ENGLISH-LANGUAGE journals      5.10 -> 8.86  
  .0210  S2 PARAGRAPH COHESION AND TRANSITIONS                3.96 -> 4.90  OUR LOWEST
  .0210  P1 Clarity and Synthesis in Presenting Sourced Info  4.44 -> 5.68  
  .0140  A1 Audience Adaptation                               5.16 -> 5.76  
  .0140  F1 Formatting, Layout, Visual Consistency            5.30 -> 6.06  
  .0140  D1 CLARITY OF DATA/EVIDENCE                          4.80 -> 5.90  CELLCOG SCORES 9.20 HERE

  JUDGE'S OWN WORDS ON US:
   D1: "rarely presents quantitative evidence clearly... often describes findings in generic terms.
        Some evidence summaries are incomplete, such as SECTIONS WHERE CITATIONS ARE NAMED BUT
        FINDINGS ARE MISSING."
   S2: "fragmented narrative... without adequate transitions"
   Citation: "the article LACKS A FORMAL REFERENCE LIST, making verification difficult"
  JUDGE'S OWN WORDS ON CELLCOG (#1):
   D1 9.2: "clearly reports quantitative findings — robot effects on employment and wages,
            meta-analytic results, productivity gains... ITS SECTORAL TABLE IS CLEAR AND USEFUL."

## 4. THE BIGGEST MEASURED DEFECT: WE HAVE NO EVIDENCE IN THE REPORT
  quantitative claims we PRINT : 2   in 8,012 words
  bodhi prints                 : 43
  CELLCOG PRINTS               : 202  (12.4 per 1,000 words)
  quantitative claims AVAILABLE in fulltext WE ALREADY HOLD : 3,990
  -> the extractor NEVER ASKED FOR NUMBERS. The gate then correctly deleted every figure it could
     not find in a span — because the spans never contained any. THE GATE WAS STARVING, NOT CENSORING.
     Relaxing the gate would 'fix' this by shipping fabrications. WE WILL NOT DO THAT.
     FIX IS BUILT, NOT YET RUN: extractor now demands the figure IN the verbatim span.

## 5. THE CORPUS — AND WHY 4 CRITERIA REGRESSED
  70 journal papers: FULLTEXT=21, CITATION_ONLY=14, ABSTRACT_ONLY=35
  INDUSTRY COVERAGE (papers mentioning it in title/abstract):
     healthcare     2
     manufacturing  2
     retail         0
     finance        2
     transport      2
     education      1
     legal          1
     agriculture    0
  THE OUTLINE ASKS FOR A 4-SUBSECTION INDUSTRY SECTION (manufacturing / financial+professional /
  healthcare+education / creative). THE OUTLINE WRITES CHEQUES THE CORPUS CANNOT CASH.
  This is the SAME failure that lost turn 2: we traded a broad corpus for a narrow one.

## 6. PROVEN DEAD LEVERS — DO NOT PROPOSE THESE
  * STRUCTURE IS DEAD, proven by intervention: 677w->106w paragraphs and 0->21 H3 moved readability
    by -0.08. The judge's complaint is COHESION (transitions), NOT paragraph size or heading count.
  * LENGTH SATURATES at ~8,000 words (898-article panel, 9 systems x 100 tasks). It is a FLOOR
    (~5,000w), not a lever. We are at 8,012w. More words buys nothing.
  * MORE SECTIONS: dead. sections/H3 = +0.0020/SD on the panel.
  * [n] CITATION MARKERS AND REFERENCE LISTS ARE DELETED by an LLM 'ArticleCleaner' BEFORE the judge
    reads anything (measured: our 345 markers -> 0; our 105-entry bibliography -> deleted).
    BUT TABLES SURVIVE — the judge read cellcog's table and praised it. AND the judge STILL penalised
    us for having no reference list. Both facts are true and they are in tension. RESOLVE THIS.

## 7. THE 7 PLANNED FIXES WE HAVE **NOT** DONE
  1. SEQUENTIAL COHESION PASS      -> S2 = 4.90, our LOWEST criterion. Judge: 'fragmented narrative'.
  2. DEDICATED IMPLICATIONS PASS   -> Value/Foresight REGRESSED to 5.42 (w=.0480). No such pass exists.
  3. INDUSTRY CORPUS EXPANSION     -> Industry scope REGRESSED to 5.76 (w=.0725) + Various Industries 5.82 (w=.0375)
  4. BROADEN EXTRACTOR FOR 4IR     -> 7 corpus papers discuss the 4IR; ZERO 4IR cards extracted.
                                      Three 4IR criteria total w=.1145 and all sit at 6.4-7.1.
  5. RESTORE A FORMAL REFERENCE LIST -> judge explicitly caps our BEST criterion (7.32) for its absence
  6. CARD-PARTITION LEDGER         -> the same card is narrated up to 5x; ~1,500-2,000 restatement words
  7. MEASURE GENERALITY            -> all 38 scored runs are task 72. WE DO NOT KNOW what we score on an
                                      unseen question. The mission is a GENERAL system.

## 8. WHAT IS ALREADY BUILT AND GREEN (canary 12/12)
  - gate un-inverted; ATTRIBUTED lane checks numbers AND content against the cited source's own span
  - CROSS-SOURCE SYNTHESIS lane: a comparative sentence is a CONJUNCTION OF ATTRIBUTED CLAUSES, each
    clause gated against the source IT names. Fabricated binding still dies inside a comparison.
  - number gate closed a substring leak ('0.2' in '10.25' is True in Python)
  - EVIDENCE TABLE built deterministically from span-verified cards (fabrication structurally impossible)
  - extractor rewritten to demand figures IN the span; writer must report the figure; attribution rotates
  - working-paper fetcher (NBER/IZA/RePEc/arXiv) — Autor/Levy/Murnane is paywalled in QJE but free as
    NBER WP 8337. In economics THE WORKING PAPER IS THE PAPER and we were never looking there.

## 9. FILES YOU CAN READ (you have filesystem access — READ THEM, LINE BY LINE)
  /home/polaris/wt/flywheel/outputs/cellcog_arm/report.md   <- OUR 0.4603 ARTIFACT
  /home/polaris/wt/flywheel/outputs/cellcog_72.md           <- CELLCOG, #1, 0.5603
  /home/polaris/wt/flywheel/outputs/bodhi_72.md             <- BODHI, #2, 0.5441
  /home/polaris/wt/flywheel/outputs/judge_feedback_cellcog.json  <- the judge's WRITTEN critique of cellcog
  /home/polaris/wt/flywheel/outputs/judge_feedback_turn2.json    <- the judge's WRITTEN critique of US
  /home/polaris/wt/flywheel/scripts/cellcog_composer.py     <- the whole pipeline
  /home/polaris/polaris_project/FLYWHEEL_PROGRESS.md        <- every finding and retraction

## 10. THE QUESTION
  Give ONE COMPREHENSIVE FIX PLAN we can execute ALL AT ONCE this round — not a menu, a plan.
  For EVERY item:
     (a) the exact mechanism (what code/prompt/corpus change),
     (b) WHICH criterion it moves and WHY the judge would score it higher,
     (c) expected delta IN SCORE UNITS (not raw criterion points — a w=.0435 criterion must move
         +4.8 raw points to shift the score by the +0.0094 we can resolve),
     (d) how it could FAIL / what it might break,
     (e) whether it is safe to stack with the others in ONE turn (we lost turn 2 by stacking blindly).
  Then: RANK them, and say which of the 7 planned fixes are WORTHLESS and should be dropped.
  Then: is 0.5603 reachable with this architecture? If not, say so plainly and say WHAT WOULD REACH IT.
  Be adversarial. Attack our assumptions. If the whole approach is wrong, say that.