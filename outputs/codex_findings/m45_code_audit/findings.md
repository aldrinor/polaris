# M-45 Code Audit Findings

Verdict: **do not sign off yet**. The strict quote contract is preserved and the builder sink/persistence path is mostly in place, but the diagnostic artifact does not satisfy the central acceptance requirement because it cannot report the backend(s) attempted or distinguish timeout/fallback behavior.

## Findings

1. **High - `refetch_diagnostics.json` cannot identify attempted backend(s), so it cannot drive the M-45 targeted branch.** In `refetch_for_extraction_with_diagnostics`, `method` is initialized to `"none"` and never updated after `_fetch_content` returns (`src/polaris_graph/retrieval/live_retriever.py:712`, `src/polaris_graph/retrieval/live_retriever.py:727`, `src/polaris_graph/retrieval/live_retriever.py:736`). `_fetch_content` does read `result.access_method` from AccessBypass, logs it, and then discards it before returning `(content, ok, title, body_type)` (`src/polaris_graph/retrieval/live_retriever.py:859`, `src/polaris_graph/retrieval/live_retriever.py:878`, `src/polaris_graph/retrieval/live_retriever.py:882`). This means the persisted artifact will show `method: "none"` for Crawl4AI/Jina/Firecrawl/direct/archive/proxy/Sci-Hub alike, and AccessBypass timeout collapses into whatever the naive fallback returns (`src/polaris_graph/retrieval/live_retriever.py:836`, `src/polaris_graph/retrieval/live_retriever.py:842`). The acceptance criterion explicitly requires attempted backend(s), character count, and eligibility; this implementation only gives character count and eligibility. It also cannot identify remaining URLs as `timeout`, even though timeout is named in the criterion.

2. **Medium - Thin primary rows with no refetchable URL are skipped without a diagnostic entry.** The builder only appends diagnostics inside the `if url:` branch (`src/polaris_graph/generator/multi_section_generator.py:1377`, `src/polaris_graph/generator/multi_section_generator.py:1379`, `src/polaris_graph/generator/multi_section_generator.py:1392`). If a matched primary row has `direct_quote` below 100 chars but lacks both `source_url` and `url`, it falls through to the strict skip at `src/polaris_graph/generator/multi_section_generator.py:1414` without any sink entry. That leaves a skipped primary row invisible in `refetch_diagnostics.json`; add a `missing_url`/`unrefetchable` diagnostic branch if the artifact is meant to cover every skipped primary row.

## Non-Blocking Checks

- Strict contract: I did not find a statement/prose extraction fallback reintroduced in the deterministic builder. Refetched text is only cached as `_m42b_refetched_quote` after `len(refetched) >= 100` (`src/polaris_graph/generator/multi_section_generator.py:1395`), and rows still skip when the final quote is below 100 chars (`src/polaris_graph/generator/multi_section_generator.py:1414`).
- Builder integration: when a URL refetch is attempted through the diagnostic path, the sink receives the diagnostic plus `anchor` and `evidence_id` (`src/polaris_graph/generator/multi_section_generator.py:1387`, `src/polaris_graph/generator/multi_section_generator.py:1390`, `src/polaris_graph/generator/multi_section_generator.py:1392`).
- Persistence: the sweep writes `refetch_diagnostics.json` unconditionally, including empty lists (`scripts/run_honest_sweep_r3.py:1080`, `scripts/run_honest_sweep_r3.py:1081`).

## Recommendation

Make backend/method reporting part of M-45, not a later refactor. The smallest acceptable fix is to have `_fetch_content` (or a diagnostic-only wrapper around it) return enough telemetry for the JSON: final winning `access_method`, whether AccessBypass was invoked, fallback method if used, and timeout/exception reason. Then add diagnostics for no-URL skipped primaries.

## Verification

Ran:

```text
python -m pytest tests/polaris_graph/test_m45_refetch_diagnostics.py -q
```

Result: **11 passed**. Pytest emitted a cache warning because `.pytest_cache` could not be written, but the tests completed successfully.
