# Compose gear-loop iter 1 (fresh round) — line-by-line CONTEXT read

Run: current committed ghost-free code (HEAD 4bc05bb, Fable fix waves), gear-loop config
(iter-3 flag set, GLM-5.2 gen+entail, cap-primary 5).
Inputs resolved NEWEST: cp4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json (22:31),
cp3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json (23:48),
cp2=/workspace/POLARIS/outputs/s2_hamster_i1_scope/cp2_corpus_snapshot.json.
Out: outputs/s5_gear_iter1/cp5_generation_snapshot.json (22795 bytes, sha 2a0296faa8a14b0c, 5 sections).
acceptance=False (reasons: gap-stub [0,1,3,4]; quote_dump-dominant 17/25 = 68%).

## The dominant defect this round: COVERAGE COLLAPSE, worse than iter-3
Only Section 2 produced verified synthesis (4 verified, 14 dropped, regen=True, 450s).
Sections 0,1,3,4 ALL gap-stubbed (0 verified). Section 1 — which in iter-3 was the ONE genuine
section (10 verified) — now gap-stubs with 0 verified (177s, regen=False). Writer-yield collapse
deepened: 1/5 sections survive strict_verify. cp3=s3_gear was refreshed at 23:48 (newer basket
content); the drafts now fail entailment for 4/5 sections. Log shows entailment judge hitting
total_deadline_exceeded_150s retries during S2/S4.

## Section 2 IS genuine readable synthesis (the composer CAN do it)
"The OECD reports that the share of the employed population with AI skills remains small—at most
 0.3% of those employed in OECD countries on average—but growing rapidly.[1][2] Among SMEs that use
 generative AI and have experienced a skill gap, 39% report that generative AI helped compensate for
 it, and this figure rises to 46% where SMEs report that generative AI has improved employee
 performance ... .[3] University cost exhibited the strongest effect size in predicting selection
 within that study, with high-cost university candidates selected 26.35% of the time compared to
 1.46% for low-cost university candidates, while race also played a non-negligible role.[4]"
On-topic (skill gaps + algorithmic hiring bias), well-cited, NO chrome/splice/meta/repetition.

## 5-defect CONTEXT read (composed prose vs exhausted-label fallback vs final md)
- splice nonsense (in contrast/Tension): NONE. Scan of composed prose + final md = 0 hits for
  "in contrast"/"tension"/"however"/"whereas".
- repetition / reworded near-dup: MINOR. Section 1 raw fallback fragments restate the SAME claim
  twice: "...decrease per capita disposable income by 26% (95% interval, 20.6-31.8%)..." and
  "...decrease per capita disposable income by 26%, and decrease the consumption index by 21% by
  mid-2050." Near-duplicate. Lives ONLY in gap-stub fallback fragments; sanitizer drops it so the
  final assembled_report_md shows no repetition. NOT in composed prose.
- chrome as prose: YES, via the gap-stub exhausted-label fallback only. Raw span fragments dump
  chrome: S0 "er waves &gt; 5As Meijer (2018)" (HTML entity + welded page-num + mid-word cut);
  S4 "9/ssrn.4164068/. #38 Generative AI and the Future of Work \ 5" (URL frag + ref# + pagination).
  Mid-word truncations SURVIVE the sanitizer into the FINAL md: "usand workers reduces the
  employment-to-population ratio by 0.2 percentage points" (S1), "sion are slower" (S4),
  "concentration of robots has" (S2). Composed prose (S2 verified) has NO chrome.
- vacuous meta ("the document includes a section titled..."): MINOR. TOC/methodology
  self-description in raw fallback: S2 "...introduces our methodology and data. Section 4 presents
  and discusses our results. Section 5 provides..."; S3 "...154 most relevant works. Our analysis
  uncovers which...". Sanitized out of final md. NOT in composed prose.
- off-topic: MINOR borderline tangents only in fallback fragments (software-engineering-paradigm
  "Software 1.0 Engineer/Meijer 2018" S0; industrial-robots concentration S2/S4). Composed prose
  fully on GenAI-and-employment.

## Final assembled_report_md (post-sanitize, units_removed=16, 4173->1643 chars)
Near-EMPTY report: "Positive Views" + "Future Opportunities" sections render BLANK; "Negative Views"
= one truncated chrome fragment ("usand workers..."); "Additional Corroborated Findings" = one
truncated bullet ("sion are slower."); ONLY "Specific Challenges" (S2) carries real synthesis.
The sanitizer converts the coverage collapse into an empty report rather than a fragment-dump.

## Verdict
reads_like_synthesis: Section 2 = TRUE synthesis; report overall = FALSE (1/5 sections; 4/5 empty or
  truncated fallback).
acceptance_met: FALSE.

## Root for Fable to scope (unchanged direction, deeper): writer-yield collapse is the blocker.
Why do 4/5 sections yield ZERO strict_verify-passing drafts on the refreshed s3_gear baskets?
Two follow-ups persist from iter-3: (a) writer/entailment yield collapse (S1 regressed to 0 verified;
entailment judge hit total_deadline_exceeded_150s retries — deadline starvation may be killing
drafts); (b) the exhausted-label fallback must emit a CLEAN labeled gap, never a raw truncated chrome
span fragment (the chrome/repetition/meta ALL enter through this one path).
