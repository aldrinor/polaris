# Claude architect audit — I-f5-008

**Issue:** F5 latency at 50/100/200/500 sentences
**Branch:** bot/I-f5-008
**Canonical-diff-sha256:** c6c6a5a13c2b276e803d1588f5aafaeaf4129486da530d2832544f26d695074d
**Brief verdict:** APPROVE iter 1
**Diff verdict:** APPROVE iter 1 (1 P2 cosmetic; non-blocking)

## Substrate honesty
- New stress route at `/sentence_hover_test/stress?n={N}` produces synthetic VerifiedReports of N kept sentences for performance measurement only. Demo-only path; not part of production.
- Latency measurement uses `performance.now()` inside `page.evaluate`, MutationObserver-driven Sheet wait.
- Iter-1 P2 (visibility-vs-attachment): captured for I-f5-008a if real visibility-window measurement becomes important; today the DOM-attachment timing is the right proxy for React commit.

## Bundled CLAUDE.md §8.3.10
- Doc change shipped same-PR per user directive 2026-05-07: stops decided by Codex/halt/user, not Claude. Five forbidden self-initiated stop framings codified.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 172 net (incl. CLAUDE.md addition). Under 200.

## Verdict
APPROVE.
