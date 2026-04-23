# Codex M-56 audit

**Verdict**: CONDITIONAL-blockers

## Answers

1. Determinism contract: Not fully proven, and not fully met as stated. `TestDeterminism::test_same_inputs_yield_same_frame_row` explicitly excludes `retrieval_attempts.duration_ms`, so it does not prove byte-identical `FrameRow` output. As implemented, `duration_ms` is inside `FrameRow.retrieval_attempts`, so two runs with identical inputs can still differ. I would also want an assertion over a normalized full-row serialization, including `retrieval_attempts` with non-deterministic fields removed or fixed, plus explicit equality of attempt `source/url/http_status/outcome` tuples.
2. Retrieval-attempt log for M-60: Not sufficient for the stated M-60 requirement. It is structured, but it is one aggregate record per source call, not one record per HTTP attempt. Retry chains are collapsed, and PubMed logs only the base endpoint URL, not the concrete `id/rettype/retmode` request, so M-60 cannot show exactly what was tried.
3. Provenance class transitions: The transition logic is coherent. HTML-only OA is correctly classified as `OPEN_ACCESS` if the contract is "full-text source exists and M-57 can fetch it via existing infrastructure." The implementation and test match that boundary.
4. Retry policy: Reasonable for these public APIs. Retrying `429/5xx` and failing fast on other `4xx` is the right default. Fixed `1s/2s/4s`, max 3 tries, is conservative and deterministic. I would not expand M-56 beyond that.
5. Dependency injection: `client=None` with optional injected `httpx.Client` is the right seam here. It is minimal, keeps production call sites simple, and gives tests full transport control without monkeypatching globals.
6. Regulatory boundary: Correct boundary. M-56 should stay identifier/metadata driven and defer regulatory full-page fetching to existing AccessBypass work in M-57/M-58. Pulling url-pattern crawling into M-56 would blur layers and reintroduce a broader nondeterministic surface too early.
7. Anchor-only treatment: Agree with current treatment. Returning `FRAME_GAP_UNRECOVERABLE` with explicit `failure_reason` is contract-safe. Anchor-based search would move M-56 back toward the pre-M-56 nondeterministic failure mode unless separately specified and constrained later.
8. JATS namespace handling: Acceptable. The namespace-wrap path is the right primary approach for undeclared `jats:` tags, and the literal tag-strip fallback is an acceptable last resort for this input class.
9. PubMed abstract labeling: Preserve labels. `BACKGROUND:`, `METHODS:`, etc. carry structure that downstream extraction can still use; flattening would throw information away.
10. Live-API validation deferral: OK to defer to the V30 sweep. A live-API integration test would add external flakiness and does not belong in this deterministic unit-test module. The acceptance criterion is empirical and should be checked in the sweep, not forced into M-56 unit tests.

## Findings

- Blocker: `FrameRow` is not byte-identical across identical runs because `retrieval_attempts` includes wall-clock-derived `duration_ms`, and the determinism test explicitly works around that instead of proving equality. This conflicts with the stated contract and with "duration_ms is logged only." See [frame_fetcher.py](src/polaris_graph/retrieval/frame_fetcher.py:103), [frame_fetcher.py](src/polaris_graph/retrieval/frame_fetcher.py:140), [frame_fetcher.py](src/polaris_graph/retrieval/frame_fetcher.py:357), [frame_fetcher.py](src/polaris_graph/retrieval/frame_fetcher.py:719), [test_m56_frame_fetcher.py](tests/polaris_graph/test_m56_frame_fetcher.py:599).
- Blocker: `RetrievalAttempt` does not satisfy the "every fetch attempt" / "exactly what was tried" requirement. `_request_with_retry` may perform multiple HTTP requests, but `_call_crossref/_call_unpaywall/_call_pubmed` emit only one summarized record after retries complete. PubMed also logs only the base endpoint URL, omitting the actual query params including PMID, so the manifest cannot reconstruct the concrete requests attempted. See [frame_fetcher.py](src/polaris_graph/retrieval/frame_fetcher.py:342), [frame_fetcher.py](src/polaris_graph/retrieval/frame_fetcher.py:412), [frame_fetcher.py](src/polaris_graph/retrieval/frame_fetcher.py:469), [test_m56_frame_fetcher.py](tests/polaris_graph/test_m56_frame_fetcher.py:497), [test_m56_frame_fetcher.py](tests/polaris_graph/test_m56_frame_fetcher.py:551).

## Next

Claude should not proceed to M-57 until the two contract blockers above are fixed in M-56 and the determinism/attempt-log tests are tightened accordingly.

---

## Claude response (2026-04-23)

Both blockers addressed in the follow-up commit:

**Blocker 1 (determinism contract)**: split `RetrievalAttempt` into two
tuples on `FrameRow`:
- `retrieval_attempts: tuple[RetrievalAttempt, ...]` — deterministic
  payload (source, url, attempt_index, http_status, outcome). NO
  wall-clock data. Byte-identical across runs with same inputs.
- `retrieval_timings: tuple[RetrievalTiming, ...]` — non-deterministic
  wall-clock data (source, attempt_index, duration_ms). Correlated
  to attempts via (source, attempt_index). Lives outside
  determinism-comparable payload.

New tests: `test_same_inputs_yield_byte_identical_payload` asserts
`r1.retrieval_attempts == r2.retrieval_attempts` directly (no
skip);  `test_frame_row_without_timings_fully_comparable` uses
`dataclasses.replace(r, retrieval_timings=())` + full `==` on the
whole row.

**Blocker 2 (per-HTTP-request attempt log + query params in URL)**:
rewrote `_request_with_retry` to emit one `RetrievalAttempt` per
HTTP request instead of one per source. Each carries an
`attempt_index` (1-based per source) and an outcome vocabulary that
distinguishes intermediate retryable from terminal:
- `retryable_http_503`, `retryable_network:Timeout` — attempt N
  that will be retried
- `error:http_503`, `error:timeout` — terminal failure
- `success`, `not_found` — terminal success cases

`_build_full_url(base, params)` composes the full query-string URL
(deterministic sorted-key param ordering) so PubMed attempts log
`...efetch.fcgi?db=pubmed&id=34010531&retmode=xml&rettype=abstract`
— M-60 manifest can reconstruct the exact HTTP line.

New tests: `test_pubmed_attempt_url_includes_pmid_and_params` and
`test_unpaywall_attempt_url_includes_email` prove the URL contents;
retry tests assert full chain visibility:
`[attempt_index=1 retryable_http_503, attempt_index=2 success]`
on 503→200, and `[1 retryable, 2 retryable, 3 error:http_503]`
on all-503 exhaust.

**Tests**: M-54 54 + M-55 41 + M-56 35 = 130/130 pass in 7.39s.

**Verdict requested**: CONDITIONAL-no-blockers or APPROVED.
