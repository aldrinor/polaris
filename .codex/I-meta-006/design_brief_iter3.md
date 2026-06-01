HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Same bar every iter. Reserve P0/P1 for real design risks. DESIGN gate.
- Verdict APPROVE iff §-1.1-sound + buildable as specified.

REVIEW DISCIPLINE: design re-review after iter-2. Open at most this brief +
`src/polaris_graph/benchmark/claim_audit_scorer.py`. No repo-wide audit. Emit the schema.

# I-meta-006 — Cash-free benchmark scorer — DESIGN iter 3 (resolves iter-2 1 P1 + 2 P2)

The iter-2 design (atomic extraction; evidence-locked judge emitting a substring-validated
JudgeVerdict; most-specific-span; UNREACHABLE-in-denominator; RACE out; lane2 rubrics =
follow-up) stands. Three precise resolutions:

1. **(iter-2 P1 — lane2_pending vs PASS contradiction):** the scorecard NEVER calls
   `system_passes_question` while lane2 rubrics are absent. With rubrics PENDING it computes
   **lane1 only** via `lane1_faithfulness(rows)` and emits, per (system × question):
   `{lane1: {...}, lane2_pending: true, pass: null}` — NOT `passed: false`, NOT an empty
   rubric through the PASS rule (which would read coverage 0.00 as a real fail). `pass` is
   reserved (stays null) until the hash-pinned 5 gold rubrics land in a follow-up Issue; only
   THEN does the scorecard call `system_passes_question` and set a real boolean `pass`.
   Aggregation across questions reports the mean lane1 unsupported-or-worse rate +
   per-verdict counts; it carries a `lane2_pending: true` flag and makes NO PASS/“wins”
   claim while pending.
2. **(iter-2 P2-1 — metadata-only subtype):** add an EXPLICIT `metadata_only` value to
   `claim_audit_scorer.UnreachableSubtype` (additive: now `paywall | robots | fetch_failure |
   source_missing | metadata_only`). The `span_fetcher` returns UNREACHABLE(metadata_only)
   when ONLY a title/abstract/reference-metadata is available and the actual cited source
   text/span was not fetched — distinct from `fetch_failure` (request failed) and
   `source_missing` (citation unresolvable to any source). NEVER verify from metadata/abstract.
   (One-line additive Literal change; the existing 4 values + all current callers unaffected.)
3. **(iter-2 P2-2 — uncited/no-span severity):** EVERY atom — including uncited material
   atoms and atoms whose source is UNREACHABLE — is routed through the evidence-locked
   `judge`/severity-rater, which assigns the S0-S3 severity (decision-relevance) AND the
   verdict. For an uncited atom the judge is called with `fetched_span=None, citation_ref=None`
   → it cannot VERIFY, returns `severity` + `UNSUPPORTED` + `citation_id=null` +
   `audit_note="uncited material claim; no citation supplied"`. Severity is therefore always
   audit-assigned, never harness-invented. Pre-registered rule: an atom is a material
   candidate (S0-S2 eligible) by the audit’s decision-relevance judgement; S3 observe-only
   atoms are excluded from lane1 by the existing `claim_audit_scorer`.

## Unchanged from iter-2 (for context)
- Atomic extraction (injected atomizer, deterministic test fallback) across POLARIS tokens /
  academic author-year / numbered superscript; uncited atoms kept.
- Evidence-locked judge: JudgeVerdict {verdict, severity, span_quote, audit_note,
  unreachable_subtype}; harness validates span_quote ⊂ fetched_span for
  VERIFIED/PARTIAL/FABRICATED; canonical impl = Claude+Codex reconciled-audit adapter.
- span_fetcher returns the MOST SPECIFIC cited span per system; no broader-source fallback;
  POLARIS [#ev:] defines its span but confers NO auto-verification.
- Unresolved citation → UNREACHABLE(source_missing), kept in denominator.
- REUSE claim_audit_scorer (ClaimRow + lane1 + aggregate); DO NOT reuse beat_both_scorer;
  RACE → follow-up.
- Spend-free smoke: extraction (3 formats + uncited + compound→≥2 atoms); score_atoms with a
  FAKE judge+fetcher (VERIFIED needs real substring span_quote; fabricated quote rejected;
  uncited→UNSUPPORTED null + audit-assigned severity; unresolved→UNREACHABLE(source_missing)
  in denominator; metadata-only→UNREACHABLE(metadata_only)); aggregation lane1-only +
  lane2_pending + pass=null; assert no live client.

## Confirm
Are the three resolutions sufficient, and is the design now APPROVE-able to build?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
