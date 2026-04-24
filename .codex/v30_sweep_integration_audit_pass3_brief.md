V30 sweep integration audit — pass 3.

**Skip git status.** Two files only.

## Context

Pass-2 verdict: CONDITIONAL-blockers. You surfaced two concrete
false-pass paths in `_entity_cited_in_legacy()`: shared url_pattern
domains + DOI superstrings.

Commit `8453dc3` tightens:
- New `_word_bounded_search(needle, haystack)` with
  `(?<!\w)needle(?!\w)` lookaround + regex cache.
- DOI / anchor / label_name all use word-bounded matching.
- URL-pattern in bibliography: must co-occur with label_name or
  anchor in biblio entry's title/name.
- Label_name in report: requires url_pattern or anchor on the
  SAME REPORT LINE.
- Fallback: label-alone only when entity has no url_pattern
  AND no anchor (statute-only rare case).

Three new adversarial tests:
- test_shared_url_pattern_does_not_false_pass (Mounjaro vs
  Zepbound with shared accessdata.fda.gov)
- test_doi_superstring_does_not_false_pass
- test_surpass_1_vs_surpass_10_disambiguation

Regression: 316/316 pass (M-54..M-62 + 20 integration).

## What to verify

Files (commit `8453dc3`):

1. `src/polaris_graph/v30_sweep_integration.py` —
   `_word_bounded_search` + tightened `_entity_cited_in_legacy`.
2. `tests/polaris_graph/test_v30_sweep_integration.py` —
   20 integration tests.

## Questions

1. **Pass-2 blocker fixed**: verify both exploits closed in the
   new code path.
2. **Word-boundary correctness**: the lookaround pattern is
   `(?<!\w)needle(?!\w)`. Any edge case (unicode, punctuation
   with re.escape) I missed?
3. **Line-granular co-occurrence for label+url**: is line-
   granular the right scope, or should it be sentence/paragraph?
   Line-granular works for the Mounjaro/Zepbound case because
   the report would naturally put each on its own line. But
   what if a multi-line paragraph discusses both?
4. **Bibliography url_pattern + label disambiguator**: new
   code requires biblio entry's title or name to echo the
   entity's label_name or anchor. Is that the right
   disambiguator, or would checking biblio.url match against
   entity.url_pattern be sufficient with word boundaries?
5. **Statute-only fallback**: when entity has no url_pattern
   AND no anchor, label_name alone is accepted as citation.
   For the policy slug, statute entities actually have
   url_pattern AND anchor — so the fallback is rarely hit.
   When would it actually fire?
6. **Third-round adversarial attempts** (xhigh budget):
   - Can I construct a report that false-passes the new
     tightened check?
   - Any false-NEGATIVE where a real citation would fail the
     check? (e.g. label_name appearing across a line break
     with url_pattern on the next line — would that correctly
     fail under the conservative "same line" rule?)
   - Regex cache: any thread-safety concern at sweep scale?
     (Probably not for serial sweep, but worth noting.)

## Output

Write to
`outputs/codex_findings/v30_sweep_integration_audit/pass3_findings.md`.

Format:
```markdown
# Codex V30 sweep integration audit — pass 3

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-2 blockers resolved
<verified / still open>

## Third-round adversarial attempts
<list each>

## Residual concerns
<anything>

## Next
On APPROVED / CONDITIONAL-no-blockers: sweep integration is
ready for live-run exercise (task #28 proceeds to actual
V30 sweep launch with PG_V30_ENABLED=1).
```

Keep under 80 lines. Full xhigh. This should converge.
