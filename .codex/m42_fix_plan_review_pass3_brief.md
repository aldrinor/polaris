You are Codex step 6 pass-3 of autoloop V2 — third pass on the
V25→V26 M-42 fix plan. Pass-2 was CONDITIONAL with 2 narrow
revisions required; pass-3 closes them.

## Pass-2 Codex verdict (what needed fixing)

1. **M-42b source-content contract**: pass-2 left "fetched source
   content" ambiguous. You required: name the exact data object/
   field the table builder reads (e.g. `EvidenceRow.source_content`,
   fetched abstract text, parsed HTML/PDF), and specify what
   happens when only title/snippet/statement is available.

2. **Mechanism preservation test**: the 6-test preservation suite
   in pass-2 missed an explicit test proving M-42c expansion
   doesn't create new under-framed mechanism claims.

## Pass-3 revisions

Read `outputs/audits/v25/fix_plan.md`. Two targeted edits:

1. M-42b now specifies:
   - Primary source: `EvidenceRow.direct_quote` (verbatim quote
     from fetched source, 200-1000 chars of abstract/methods/
     results populated by live_retriever).
   - Secondary: `statement` only for disambiguation.
   - Forbidden: prose from generated report sections.
   - Thin-content fallback: if `direct_quote` <100 chars OR no
     fetched content → row marked `extraction_ineligible=True`;
     options (a) fetch refresh via
     `live_retriever.refetch_for_extraction(url)`, or
     (b) skip the row.
   - Concrete regex patterns for N, baseline, comparator, dose,
     endpoint, timepoint, effect size.
   - LLM fallback only when deterministic extraction yields
     <2 rows OR all rows extraction-ineligible; LLM receives
     selected primary-trial `direct_quote`s, not generated prose.

2. Preservation suite now has 7 tests (was 6). New test:
   `test_mechanism_underframed_rate_below_v25` — scans V26
   Mechanism section for trial-name + mechanism-claim tokens
   without >=3 accompanying frame elements. Asserts V26 rate
   <= V25 rate (~55% ceiling, <40% target).

## What you need to verify

1. Is the `EvidenceRow.direct_quote` contract concrete enough to
   prevent fall-back to prose or snippet-only extraction?
2. Does the thin-content fallback policy (refetch or skip) make
   sense for the live_retriever architecture? Does
   `refetch_for_extraction` need to be stubbed as a new API or is
   it already derivable from existing live_retriever methods?
3. Is the mechanism-underframing preservation test concrete enough
   to fail fast when M-42c expansion goes wrong?

## What to NOT re-verify (already approved pass-2)

- M-42a (group-ref tightening): APPROVED
- M-42c upstream mechanism-evidence floor: APPROVED
- M-42d FDA/EMA/NICE preservation guard: APPROVED
- M-42e cap + T2 preservation: APPROVED
- Implementation order M-42e → a+b → c → d: APPROVED
- Structural depth coverage (table + timeline): APPROVED
  (per-trial subsections deferred to M-43)

## Deliverable

Write `outputs/audits/v25/codex_plan_review_pass3.md` with:
- Overall verdict: APPROVED / CONDITIONAL / REJECT
- Confirmation that each of the 2 pass-2 requirements is closed
- Any remaining blocker (ideally none)

Keep under 800 words. If APPROVED, implementation begins next
turn in the Codex-recommended order.
