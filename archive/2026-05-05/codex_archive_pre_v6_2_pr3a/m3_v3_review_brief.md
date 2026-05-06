M-3 v3 — re-review (DOI/PMID identifier resolver).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-3 v2 verdict: STILL-PARTIAL — 6/7 fixes integrated, but the
URL-stem resolver only bridged surpass_5_primary (the only entity-
anchored biblio entry with a non-empty URL). All other surpass_X
entries have empty URL, so URL-stem secondary match couldn't help.

You also flagged a separate issue: urlStem was over-lossy because it
stripped query strings, which could collapse distinct URLs into one
key.

## What changed in v3

1. **Replaced URL-stem resolver with canonical identifier resolver.**
   New `extractIdentifiers(url)` returns a set of `{doi:..., pmid:...,
   url:...}` tokens. New `bibIdentifiers(bib, ir)` collects all
   identifiers for a biblio entry from its `frame_coverage_report.entry`
   (doi, pmid, retrieval URLs).
   - DOI regex: `\b10\.\d{4,9}/[^\s?#&]+`
   - PMID via pubmed.ncbi.nlm.nih.gov/NNNNNNNN
   - PMID via efetch.fcgi?id=NNNNNNNN
   - Full URL stem (no longer strips query)
   - Index `clustersByIdentifier` is O(1) lookup

2. **urlStem no longer strips query strings.** Codex over-joining
   concern addressed.

Tests: 99 → 101. New tests verify extractIdentifiers, bibIdentifiers,
clustersByIdentifier, DOI/PMID patterns, query-string preservation,
and end-to-end DOI bridge plumbing.

## Run-14 honest assessment

Most surpass_X biblio trials have DOIs in `frame_coverage_report.entries[].doi`
(verified at the API surface). But the corpus contradictions reference
DIFFERENT papers — mdpi.com, frontiersin.org, doi.org/10.2337/... — not
the SURPASS primary publications. So even with DOI/PMID matching, run-14
will show 0 cross-namespace bridges for most clicks because the corpus
and the entity-anchored citations are largely DISJOINT sets.

The resolver is plumbed correctly; whether it bridges depends on real
corpus overlap. For Phase A run-14 demo, this is honest data — the
contradictions tab covers the corpus-wide matrix, while clicking [N]
on a SURPASS trial citation correctly shows "0 directly linked
contradictions" + verified sentences citing it.

## Your job

Final verdict on M-3. GREEN / STILL-PARTIAL / DISAGREE.

Specifically:
- Is the identifier resolver implementation correct (DOI/PMID regex,
  bibIdentifiers integration with frame_coverage)?
- Is the run-14 honest assessment above acceptable? Or do you want
  more pre-Phase-A bridging (e.g., synthesizing entity-anchored
  citations into the corpus index at IR load time)?
- Any new issues introduced?

## Output

Write to `outputs/codex_findings/m3_v3_review/findings.md`:

```markdown
# Codex re-review of M-3 v3

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Identifier resolver assessment
Implementation correctness; any regex/coverage gaps.

## Run-14 bridge reality
Acceptable as Phase A scope, or does it need pre-load synthesis?

## New issues
none / list

## Final word
GREEN to lock M-3 and proceed to M-4 / STILL-PARTIAL with edits.
```

Be terse. Under 120 lines.
