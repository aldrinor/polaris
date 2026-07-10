# Compose gear-loop iter 3 — line-by-line CONTEXT read

Run: current committed code (HEAD b702fd7, Fable 9-fix wave). NEWEST cp4=s4_gear, NEWEST cp3=s3_gear, cp2=s2_hamster_i1.
Out: outputs/s5_gear_iter3/cp5_generation_snapshot.json (cap-primary 5, disclosed subset). acceptance=False.

## The fix wave WORKED where the writer actually composed
Section 1 (434s, regen=True, 10 verified sentences) is GENUINE readable synthesis, well-cited,
NO chrome, NO splice, NO meta, NO repetition. Example real sentences:
  "Eloundou et al. estimate that around 80% of the US workforce could see at least 10% of their
   tasks affected by large language models, while approximately 19% of workers may have over half
   of their tasks impacted.[2]"
  "A Harvard University study tracking 62 million workers across 285,000 US firms found junior
   positions shrinking at companies integrating AI since 2023, warning that AI is eroding the bottom
   rungs of career ladders.[10]"
This proves the NO_RAW_SPAN + LLM-body root-chain fix: the pre-fix chrome/quote-dump AS VERIFIED
PROSE is GONE for the composed section.

## But 4 of 5 sections gap-stub -> COVERAGE COLLAPSE (the new blocking defect)
Sections 0,2,3,4 produced ZERO verified sentences. Section 2 DID attempt (266s) but every draft
failed strict_verify; sections 0/3/4 bailed in 0-39s. All fell to the labeled
"[unverified synthesis -- abstractive re-write exhausted]" disclosure path.

## 5-defect read (CONTEXT level, at the composed prose)
- splice nonsense (in contrast/Tension): NONE in verified prose.
- repetition / reworded near-dup: NONE in verified prose. (One Australian "-26% disposable income"
  claim is restated inside a section-1 trailing EXHAUSTED-LABEL fragment, not in composed prose.)
- chrome as prose: NONE in verified prose. Chrome STILL leaks via the gap-stub exhausted-label
  fragments: "9/ssrn.4164068/. #38 Generative AI and the Future of Work \ 5", "&gt;" entity,
  mid-word truncation "er waves", "sion are slower".
- vacuous meta ("the document includes a section titled..."): NONE in verified prose. A TOC-ish
  fragment "Section 4 presents... Section 5 provides" appears only inside a section-2 exhausted label.
- off-topic: NONE. All on GenAI-and-employment.

## Verdict
reads_like_synthesis: section 1 = TRUE synthesis; report overall = FALSE (4/5 gap-stub).
acceptance_met: FALSE (script agrees: gap-stub [0,2,3,4] + quote_dump-dominant is the exhausted-label
  fragments, not the verified prose).

## Next (Fable to scope -- root is now COVERAGE not chrome)
Why does only 1/5 sections survive? Section 2 attempted for 266s yet 0 drafts passed strict_verify;
0/3/4 short-circuit fast. Two follow-ups: (a) writer-yield collapse -- drafts failing strict_verify
or writer bailing early for most sections; (b) the exhausted-label fallback should emit a CLEAN
labeled gap, never a raw truncated chrome span fragment.
