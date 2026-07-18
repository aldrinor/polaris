# 0018. The moat: section/basket-modular depth rendered in parallel

Status: accepted

Date: 2026-07-11

## Context

GPT and Gemini deep-research write the whole report inside ONE context window, so their depth has a hard ceiling. POLARIS is section-modular with a knowledge base bigger than the context window, so report depth is the SUM over ALL baskets. This is the differentiator competitors cannot match — the moat.

The stall that exposed it was a SERIAL per-basket residual loop: 276 baskets times about 200 seconds each is roughly 15 hours, and the process was OOM-killed. The bottleneck was serial execution, not basket count. Fable's first proposed fix — "consolidate the 276 residual baskets into 8 or fewer summaries" — COLLAPSES depth, the exact opposite of the moat, and was vetoed; the operator noted Fable "did not look at the math" (`project_single_context_window_moat_parallel_compose_2026_07_11.md`).

## Decision

Report depth equals the sum over all baskets. Keep every basket and render them all in bounded PARALLEL: `asyncio.gather` over the serial per-basket loop, rate-limit-aware, with per-basket memory release, and verification batched on the box GPU. Never consolidate baskets away to escape a stall.

## Consequences

- The fix for a slow per-basket loop is parallelism and memory hygiene, never fewer baskets. Collapsing baskets throws away the one advantage competitors structurally cannot copy.
- Parallel rendering must respect provider rate limits and release per-basket memory, or it trades an OOM for a rate-limit failure.
- Because depth is additive over baskets, more retrieved corroboration directly buys more report depth — which is why the WEIGHT-and-CONSOLIDATE genome (ADR 0006) and this moat reinforce each other.
- Any proposal that reduces basket count to "simplify" or "speed up" composition is suspect; check the math before accepting it.
