# DUAL INDEPENDENT AUDIT — I-meta-008 #1034: thin oa_full_text stub blocks OpenAlex fallback

You are one of TWO independent auditors (Claude + Codex) running in parallel per the
POLARIS §-1.1 line-by-line standard. Audit claim-by-claim against the actual code + the
run-6 evidence. Do NOT rubber-stamp. Surface every real finding.

## The change under review (v2 fix, committed)
`src/polaris_graph/retrieval/frame_fetcher.py` + tests. The diff is in
`.codex/I-meta-008-thinstub/codex_diff.patch`.

Summary of the v2 logic:
- New `_OA_FULLTEXT_MIN_CHARS` (default 1200). An OA full-text fetch shorter than this is
  treated as a STUB, not real full text.
- Step 4 OpenAlex fallback now fires when `not abstract_crossref and not abstract_pubmed
  and (not oa_full_text or len(oa_full_text) < _OA_FULLTEXT_MIN_CHARS)`.
- `_pick_richest_abstract(crossref, openalex, pubmed, partial_full_text)` chooses the
  LONGEST text; ties keep priority order (CrossRef > OpenAlex > PubMed > thin-partial).
- Decision: real full text (>= threshold) wins; else the richest abstract; a 540-char
  stub loses to a 1331-char OpenAlex abstract. Provenance OPEN_ACCESS if an OA locator
  existed, else ABSTRACT_ONLY.

## The diagnosis to verify (run-6 evidence in run6_frame_evidence.txt)
Claim: in run 6, `acemoglu_restrepo_automation_tasks` (the foundational "Automation and
New Tasks" JEP paper, DOI 10.1257/jep.33.2.3) came back provenance=open_access with
oa_full_text PRESENT but crossref_abstract ABSENT — i.e. the aeaweb PDF 403'd and Jina
returned a ~540-char STUB that was used as direct_quote, which the generator could not
extract fields from -> "not extractable". The old #1033 fallback was blocked because
oa_full_text was truthy. OpenAlex holds the real 1331-char abstract.

## What I need you to independently audit (line-by-line)
1. **Diff correctness**: is `_pick_richest_abstract` deterministic? (ties -> priority via
   strictly-greater while iterating; positions of equal length.) Any off-by-one / wrong
   branch / wrong provenance label?
2. **Threshold logic**: does the v2 change correctly let OpenAlex fire on a thin stub
   while still preferring a real long full text? Is 1200 a defensible boundary (a real
   full-text extraction is much longer; a paywall stub is ~540)? Any case where a
   legitimately short-but-real abstract is mishandled?
3. **Does v2 actually fix run-6's failures?** Walk EACH of the 7 entities in
   run6_frame_evidence.txt and state whether v2 grounds it, and with which source:
   - acemoglu_automation (oa_full_text stub, no crossref): does OpenAlex now fire + win?
   - acemoglu_robots (metadata_only): helped by #1033 already?
   - autor / frey_osborne (oa_full_text present, got real content run-6): unchanged?
   - brynjolfsson / eloundou (crossref_abstract present): NOT helped by OpenAlex — is that
     an honest residual (the effect number isn't in the abstract / generator-extraction
     issue), or does the diff need to also fire OpenAlex when crossref abstract is thin?
4. **Any OTHER bug** in the fetch path exposed by this change (determinism, the DOI guard,
   network discipline, the provenance downgrade when any_oa_url but empty quote)?
5. **Regression risk**: existing M-66b-T test uses full_text ~1650 chars (>=1200 -> still
   real full text). Confirm no existing behavior breaks.

## Output (required schema)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
per_entity_fix_assessment:
  acemoglu_automation: <fixed-by-openalex | still-broken | ...>
  acemoglu_robots: ...
  autor: ...
  frey_osborne: ...
  brynjolfsson: ...
  eloundou: ...
honest_residual: <what still reads as 'not extractable' after v2, and is that a fetch bug or a generator-extraction issue>
```
End with the schema as your final lines.
