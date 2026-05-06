# M-INT-8 v2 — Codex round-2 GREEN

## Codex verdict (verbatim)
> No review findings.
>
> The test correctly forces the real empty-report path
> (sentences_verified=0 → SlideDeckEmptyReportError → 422).
> All 4 v2 error-path tests verified.
>
> The cross-org MEDIUM is framed correctly as system-wide
> deferred, not specific to M-INT-8.
>
> 11/11 pytest pass.
>
> VERDICT: GREEN

## Round summary
- R1: MEDIUM (cross-org authz on run endpoints — system-wide)
       + LOW (test coverage gap on 422/500 paths)
- R2: GREEN (LOW closed; cross-org MEDIUM correctly deferred)

## Acceptance bar — ALL met
1. ✅ Imported (build_slide_deck, deck_to_dict, render_deck_html,
   SlideDeckError, SlideDeckEmptyReportError)
2. ✅ Invoked (two endpoints registered)
3. ✅ Run-log evidence (200/404/422/500 explicitly tested)
4. ✅ Rollback flag PG_USE_SLIDE_DECK_ENDPOINT=0 → 404
5. ✅ M-15b authn retrofit (require_authenticated_caller)
6. ✅ 422 for empty report (explicit test forces it)
7. ✅ 500 for IR load failure (explicit test forces it)
8. ✅ 500 for build failure (explicit test forces it)

## Cross-org follow-up (Phase F / M-PROD-1)
Codex confirmed the cross-org gap is system-wide:
> "the new slide-deck routes add authn only ... while existing
>  endpoints like get_run, get_report_markdown, get_audit_bundle,
>  and get_run_citation_health still have no run-level org check."

Tracked for Phase F / M-PROD-1 (SOC2 dry-run scope), requires:
- Adding org_id to RunSummary (registry schema migration)
- Updating 5+ run-level endpoints
- Backfilling org_id on existing artifacts

## Tests
- 11/11 M-INT-8 (Codex independently verified)
- 87/87 across slide_deck + inspector_router substrate

Branch: PL-honest-rebuild-phase-1
Commit: bd40be0

## Verdict
**GREEN — M-INT-8 LOCKED. Proceeding to M-INT-9.**
