HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Same bar every iter. Reserve P0/P1 for real design risks.
- If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- DESIGN gate. Verdict APPROVE iff §-1.1-sound + buildable as specified.

REVIEW DISCIPLINE: design re-review after iter-1 rulings. Open at most this brief +
`src/polaris_graph/benchmark/claim_audit_scorer.py`. No repo-wide audit. Emit the schema.

# I-meta-006 — Cash-free benchmark scorer (FACT claim-by-claim) — DESIGN iter 2

All 5 iter-1 P1 + 3 P2 adopted; RACE scoped out; lane2 rubrics treated as a blocker.

## Revised design (cash-free harness; verdict/fetch/atomize INJECTED, faked in tests)

1. **Atomic extraction — NEW `report_claim_extractor.py`** (iter-1 P1-2): `extract_atoms(
   report_text, system, references, *, atomizer) -> list[ExtractedAtom{atom_id, text,
   citation_refs:[CitationRef], is_material_candidate}]`.
   - `atomizer(sentence) -> list[str]` is INJECTED (real atomizer in the paid run; tests pass
     a deterministic conservative clause-splitter). Compound sentences -> separate factual
     atoms so the denominator is not methodology-dependent.
   - Citation mapping per system: POLARIS reuses `split_into_sentences` +
     `parse_provenance_tokens` ([#ev:] -> the EXACT cited span; [N] -> bibliography); ChatGPT/
     Gemini map "(Author, Year)" / numbered-superscript keys against the report's references
     list. An atom with NO citation is KEPT (scored uncited, iter-1 P2-1).
   - Deterministic given the injected atomizer; cash-free.

2. **Evidence-locked judge — NEW `fact_scorer.py`** (iter-1 P1-1, P1-3, P1-4, rulings q1/q3):
   `score_atoms(atoms, *, span_fetcher, judge) -> list[ClaimRow]`.
   - `span_fetcher(citation_ref, system) -> FetchedSpan | UnreachableReason`: returns the MOST
     SPECIFIC cited text the system supplied (POLARIS [#ev:] -> that exact direct_quote span;
     competitor -> the cited source located as specifically as resolvable). NO broader-source
     fallback (a bad POLARIS span must NOT pass because the source supports the claim
     elsewhere). Fetch failure / paywall / robots / source-missing / metadata-or-abstract-only
     -> the matching UNREACHABLE subtype (iter-1 P2-3) — NEVER verify from title/abstract.
   - `judge(atom_text, fetched_span, citation_ref) -> JudgeVerdict{verdict, severity, span_quote,
     audit_note, unreachable_subtype}` is INJECTED and EVIDENCE-LOCKED. The strongest impl is
     the **Claude+Codex reconciled-audit adapter** (a bare verdict-only LLM judge is NOT
     §-1.1-sufficient, ruling q1). The judge reads the FETCHED span (not metadata).
   - The harness VALIDATES the JudgeVerdict before building a ClaimRow (iter-1 P1-1): for
     VERIFIED/PARTIAL/FABRICATED the `span_quote` MUST be a literal substring of `fetched_span`
     (else the row is rejected/raised — the judge cannot fabricate a supporting quote);
     UNSUPPORTED+cited requires an `audit_note`; UNREACHABLE requires a subtype. severity in
     S0-S3 (iter-1 P1-3). Emits the EXISTING `ClaimRow` (reuse its `__post_init__` invariants).
   - Severity is pre-registered + audit-assigned (part of JudgeVerdict); the harness does not
     invent it. Uncited MATERIAL atom -> UNSUPPORTED, citation_id=null (iter-1 P2-1).
     Unresolved author-year/reference -> UNREACHABLE(source_missing), kept in the denominator
     (iter-1 P2-2, ruling q2).
   - Identical path for every system (ruling q3): each is judged against ITS most-specific
     emitted cited span; POLARIS [#ev:] is used for extraction AND defines the span, but
     confers NO auto-verification.

3. **Scorecard — NEW `benchmark_scorecard.py`**: for the 5 Qs x 3 systems, extract ->
   score_atoms -> `claim_audit_scorer.aggregate` (REUSE lane1 + the PASS rule). Report
   clinical-3 (#75/#76/#78) AND overall-5 SEPARATELY (locked label). Honest framing:
   per-claim-traceable, NOT a one-number "wins" headline.
   **Lane2 (coverage) is GATED on the 5 gold rubrics**, which do NOT exist yet (iter-1 P1-5,
   ruling q5): authoring + §-1.1 verification + hash-pin is a SEPARATE follow-up Issue. This
   issue builds the lane2 PLUMBING (RubricElement already exists) but the scorecard reports
   **lane1 FACT faithfulness now**, and lane2 only once the hash-pinned rubrics land. The
   scorecard surfaces "lane2_pending: rubrics not authored" explicitly (no silent zero).

4. **Run wiring `scripts/dr_benchmark/run_scorecard.py`**: ingest the stored competitor
   reports + a POLARIS run's report+bibliography, run with the REAL fetcher+judge (the only
   billed step, operator-gated). Cash-free with injected fakes.

5. **REUSE:** `claim_audit_scorer` (ClaimRow + lane1 + aggregate), `ledger_schema`,
   `split_into_sentences`/`parse_provenance_tokens`, stored reports, locked Qs. **DO NOT
   reuse** `beat_both_scorer` (§-1.1-banned). **RACE** out -> follow-up Issue (ruling q4).

## Spend-free smoke (the GREEN bar)
- Atomic extraction for all 3 citation formats (POLARIS tokens, academic author-year, numbered
  superscript), incl. an uncited atom kept + a compound sentence -> >=2 atoms.
- `score_atoms` with a FAKE judge+fetcher: VERIFIED needs a real substring span_quote;
  a FABRICATED span_quote NOT in the fetched text is REJECTED; uncited material -> UNSUPPORTED
  null; unresolved citation -> UNREACHABLE(source_missing) and stays in the denominator;
  metadata-only -> UNREACHABLE (not VERIFIED).
- Aggregation reuses claim_audit_scorer; clinical-3 vs overall-5 split; lane2_pending surfaced.
- Assert NO live client; deterministic given the injected fakes.

## Confirm / rule
- Is the evidence-locked judge contract (JudgeVerdict + substring-validated span_quote +
  severity + the reconciled-audit adapter as the canonical impl) now §-1.1-sufficient?
- Is treating lane2 gold-rubric authoring as a separate hash-pinned follow-up (scorecard
  reports lane1 now, lane2_pending surfaced) the right scope, or must rubric authoring block
  this issue entirely?
- Any remaining path to a rigged/auto-pass result or a non-identical cross-system protocol?

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
