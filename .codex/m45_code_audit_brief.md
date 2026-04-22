M-45 audit — fourth of 7 V28 bundle items.

## Commit

`6b2f9c9` (bundled with M-44 pass-2).

## Plan reference

`outputs/audits/v27/fix_plan_v28.md` M-45 (pass-2). Your verbatim
requirement (from V28 plan review pass-1):

> "Prior mechanism gap: M-42b refetch calls refetch_for_extraction(),
> but V27 still produced zero eligible rows. V28 will instrument per-
> URL refetch backend, returned length, content type, and extraction
> eligibility; if AccessBypass did not actually invoke Jina/Firecrawl
> in this path, wire those providers explicitly. If it did, improve
> extraction by using provider text that contains abstract/results
> windows and by passing _m42b_refetched_quote into the deterministic
> table/timeline builder only when it meets the strict quote contract."

Your verbatim acceptance criterion:

> "refetch_diagnostics.json records attempted backend(s), character
> count, and eligibility for every skipped primary row; at least 6
> pivotal rows become eligible, OR the diagnostic file identifies
> each remaining URL as paywall/thin/timeout with no contract
> reversal."

## What changed

`src/polaris_graph/retrieval/live_retriever.py`:
- New `refetch_for_extraction_with_diagnostics(url, max_chars)`
  returns (quote, diagnostics_dict) with 8-key schema: url,
  attempted, method, raw_char_count, body_type, eligible,
  failure_mode, exception_type.
- Existing `refetch_for_extraction` now a thin wrapper around the
  diagnostic variant (backwards-compatible).
- Failure modes: `empty_url`, `exception`, `fetch_failed`,
  `thin_content`, `paywall_shell` (tagged body type but not a
  fatal skip — abstract may still be ≥100 chars).

`src/polaris_graph/generator/multi_section_generator.py`:
- `build_trial_summary_and_timeline_from_evidence` accepts new
  `refetch_diagnostics_sink: list | None` kwarg. When provided,
  routes through the diagnostic variant and appends one entry per
  refetch attempt (with anchor + evidence_id extras).
- Builder-level exceptions in refetch also recorded as
  `failure_mode: builder_exception` with exception_type.
- `MultiSectionResult.refetch_diagnostics` field (list of dicts)
  for orchestrator persistence.

`scripts/run_honest_sweep_r3.py`:
- Writes `refetch_diagnostics.json` per sweep run (always,
  including when empty — so audits can tell "builder ran but no
  refetches needed" from "builder didn't run").
- Also writes `m44_primary_citation_telemetry.json`.

## What I did NOT do

- No explicit Jina/Firecrawl wiring. Per your plan language, this
  was contingent on diagnostics showing AccessBypass DIDN'T invoke
  them. Real diagnostics will come from the V28 sweep run. The
  targeted-fix branches in your plan (explicit wiring OR
  abstract/results-window extraction OR strict skip) become
  actionable once diagnostics data exists.
- `_fetch_content` doesn't return `method` — so the diagnostic
  reports `method: none` for all attempts currently. Documented
  in code comment; extending _fetch_content to return method would
  be a separate refactor.

Strict contract preserved throughout:
- No statement fallback (enforced from M-48 pass-2)
- No prose fallback (enforced from M-42a+b pass-2)
- No contract reversal on the ≥100 char quote rule

## Test coverage

`tests/polaris_graph/test_m45_refetch_diagnostics.py` — 11 tests:
- Schema validation (5 tests covering every failure_mode)
- Paywall-shell handling
- Backwards-compat on the 1-value variant
- Builder diagnostic sink (receives entry per refetch + exception
  handling + None-sink legacy path)

## What to audit

1. **Schema completeness**: 8-key schema covers every decision
   branch? Missing any failure mode?
2. **Strict contract**: eligible iff ≥100 chars post-provenance?
   No statement fallback re-introduced?
3. **Builder integration**: sink correctly populated with
   anchor + evidence_id extras?
4. **Acceptance criterion**: V28 sweep will produce
   refetch_diagnostics.json with per-URL eligibility; can you
   sign off on this as the diagnostic artifact per your pass-2
   language? Or do you want the explicit Jina/Firecrawl wiring
   preemptively even without V27 diagnostics to drive it?
5. **Method tagging**: `method: none` for all current calls
   (because _fetch_content doesn't return method) — acceptable
   as scope note, or blocker?

Write verdict to `outputs/codex_findings/m45_code_audit/findings.md`.
