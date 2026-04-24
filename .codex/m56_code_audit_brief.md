M-56 code audit — tight.

**Skip git status.** Loopback/audit/ deletions remain from prior
cleanup; unrelated to M-56. Read only the two files below.

## Scope

Commit `b0bb89c`. Two files:

1. `src/polaris_graph/retrieval/frame_fetcher.py` (~470 lines) —
   M-56 deterministic retriever. New module in the retrieval/
   subpackage alongside existing live_retriever.py.
2. `tests/polaris_graph/test_m56_frame_fetcher.py` (~570 lines) —
   32 tests in 11 classes. All tests use httpx.MockTransport;
   no network calls.

Do not re-read the V30 plan or prior findings.

## Your pass-1 revision to verify

You required (M-56): "**root_cause_approved**. Correct earliest
preventable stage for retrieval non-determinism. Keep it
contract-driven; do not move it ahead of M-54/M-55."

You also required (M-60, propagated to M-56 because M-60 consumes
M-56 output): "**structured failure metadata and retrieval-attempt
details**, not just a human sentence."

Look at `RetrievalAttempt` + `FrameRow.retrieval_attempts`: does
that satisfy your M-60 structured-metadata requirement?

## Questions

1. **Determinism contract**: "same (binding, upstream state) →
   byte-identical FrameRow payload". Retry backoff is fixed 1s/2s/4s
   (no jitter). No wall-clock in payload (duration_ms is logged
   only). Sort order explicit. Does the test
   `TestDeterminism::test_same_inputs_yield_same_frame_row` prove
   this? What else would you want asserted?
2. **Retrieval-attempt log for M-60 manifest**: every fetch
   attempt (success or failure) produces a `RetrievalAttempt(source,
   url, http_status, duration_ms, outcome)`. Sufficient structured
   metadata for M-60 manifest to explain exactly what was tried?
3. **Provenance class transitions**: OA PDF OR HTML URL →
   OPEN_ACCESS; no OA + CrossRef abstract → ABSTRACT_ONLY; no OA
   + no CR abstract + PubMed abstract → ABSTRACT_ONLY; metadata
   only (no abstract, no OA) → METADATA_ONLY; all fail →
   FRAME_GAP_UNRECOVERABLE. Is HTML-only OA correctly classified
   as OPEN_ACCESS? (Codex-rev indirect concern: the M-57 content
   fetcher should be able to handle HTML landings via existing
   AccessBypass.)
4. **Retry policy**: 429, 500, 502, 503, 504 retry; other 4xx
   fail immediately. Fixed 1s/2s/4s backoff (deterministic). Max
   3 attempts per URL. Appropriate for CrossRef / Unpaywall /
   PubMed rate limits?
5. **Dependency injection for testability**:
   `fetch_frame_entity(binding, *, client=None)` accepts an
   optional httpx.Client. Production callers pass None
   (module creates per-call client). Tests pass
   MockTransport-backed client. Agree this is the right DI surface,
   or do you want a different seam?
6. **Regulatory entities (url_pattern primary)**: current M-56
   emits `METADATA_ONLY` with url as locator, no network calls.
   Full-content fetch of regulatory pages (FDA, EMA, NICE, HC)
   deferred to existing POLARIS AccessBypass infrastructure,
   typically invoked at M-57 or M-58. Correct boundary, or should
   M-56 also handle url-pattern fetching?
7. **Anchor-only entities**: V30 plan notes SURPASS-CVOT may
   not have a DOI yet (unpublished). Currently anchor-only
   bindings emit FRAME_GAP_UNRECOVERABLE without any network call.
   failure_reason explicit. Agree with this treatment, or should
   M-56 attempt anchor-based search (falling back to keyword
   retrieval) for this edge case?
8. **JATS namespace handling**: CrossRef abstracts carry
   `<jats:p>` etc. without declared namespace. `_strip_jats_tags`
   wraps with a root element declaring the namespace so ET
   parses. Fallback path strips `<...>` literally if that fails.
   Acceptable?
9. **PubMed abstract labeling**: labeled AbstractText (BACKGROUND,
   METHODS, etc.) are preserved as "LABEL: text" concatenations.
   Agree, or do you want unlabeled flatten?
10. **Acceptance criterion from V30 plan**: "≥8 of 11
    pivotal-trial primaries land with provenance_class ∈
    {open_access, abstract_only}". M-56 ships WITHOUT running
    against the live APIs — that validation lives in a full-scale
    V30 sweep. Are you OK with deferring empirical validation to
    the sweep, or do you want a live-API integration test now?

## Output

Write to `outputs/codex_findings/m56_code_audit/findings.md`.

Format:
```markdown
# Codex M-56 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Determinism contract: ...
2. Retrieval-attempt log for M-60: ...
3. Provenance class transitions: ...
4. Retry policy: ...
5. Dependency injection: ...
6. Regulatory boundary: ...
7. Anchor-only treatment: ...
8. JATS namespace handling: ...
9. PubMed abstract labeling: ...
10. Live-API validation deferral: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-57
(planner frame-slot integration).
```

Keep findings.md under 150 lines.
