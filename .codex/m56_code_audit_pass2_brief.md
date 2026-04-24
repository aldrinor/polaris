M-56 code audit pass 2 — verify blocker fix.

**Skip git status.** Focus only on the two files below.

## Context

Your pass-1 verdict was CONDITIONAL-blockers with two blockers:
1. `FrameRow` not byte-identical because `duration_ms` inside
   `retrieval_attempts`.
2. Retrieval log collapsed retries into one summary per source;
   PubMed URL missing query params.

Claude committed the fix in `a8279ff`. findings.md at
`outputs/codex_findings/m56_code_audit/findings.md` has been
updated in-place with a "Claude response" section describing the
resolution.

## What to verify

Files (commit `a8279ff`):

1. `src/polaris_graph/retrieval/frame_fetcher.py` — M-56 with
   blocker fixes.
2. `tests/polaris_graph/test_m56_frame_fetcher.py` — 35 tests
   (was 32; +3 new).

Check:

1. **Blocker 1 resolution** — `FrameRow` now has
   `retrieval_attempts: tuple[RetrievalAttempt, ...]` AND separate
   `retrieval_timings: tuple[RetrievalTiming, ...]`. `RetrievalAttempt`
   has NO duration_ms field. Determinism test asserts direct
   equality: `r1.retrieval_attempts == r2.retrieval_attempts`.
   Does this satisfy the byte-identical contract?

2. **Blocker 2 resolution** —
   - `_request_with_retry` now emits ONE RetrievalAttempt per HTTP
     request with `attempt_index` (1-based) and refined outcome
     vocabulary (`retryable_*` for intermediate, `error:*` for
     terminal). Retry chain visible.
   - `_build_full_url` composes URLs with query params for logging.
     PubMed logs now include `id=X&db=pubmed&retmode=xml&rettype=abstract`.
     Unpaywall logs include `email=`.
   - Tests prove both: `test_pubmed_attempt_url_includes_pmid_and_params`,
     `test_unpaywall_attempt_url_includes_email`,
     `test_exhausted_retries_emits_error_outcome` (asserts
     `attempt_index=[1,2,3]`, `outcomes=[retryable_http_503,
     retryable_http_503, error:http_503]`).
   Does this satisfy "every HTTP attempt visible"?

3. **Regression check** — tests still 130/130 (was 127; +3 new
   M-56 tests).

## Output

Write verdict to
`outputs/codex_findings/m56_code_audit/pass2_findings.md`.

Format:
```markdown
# Codex M-56 audit — pass 2

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Blocker 1 — determinism
<resolution verified / still open>

## Blocker 2 — per-attempt log + URL query params
<resolution verified / still open>

## Residual concerns (if any)
<mediums/nits/new items>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-57
(planner frame-slot integration).
```

Keep under 80 lines. Pass-2 scope is narrow — just verify the two
blocker fixes. Do not re-raise previously approved items.
