# I-run11-007 (#1051) — Claude architect audit

## Decision
Mirror "blanks" (drb_72 runs 14/15/16) are intermittent OpenRouter provider failures, NOT the model.
Fix = deterministic provider routing (most-stable+fastest, ranked fallback, exclude broken) + an
empty-response failover, because OpenRouter does not auto-advance on an empty 200.

## Evidence chain (whole-system, not a proxy)
- mirror_production_config_test.py: GLM-5.1 emits clean cited answers at the production config
  (reasoning ON, 16384) — blank=False on every provider.
- mirror_blank_reproduce.py: no blank across simple/hard claims × 16384/40000 budgets.
- mirror_provider_blank_test.py: all 6 forced providers (incl. degraded Phala/Together) returned
  content — the blank is intermittent.
- Research: OpenRouter `allow_fallbacks` fires on errors only, NOT on an empty 200 (provider-selection docs).

## Implementation review
- provider_routing.py loads config/settings/openrouter_provider_routing.yaml (ranked healthy `order`
  + `ignore` + provider_aliases), merges order+ignore+allow_fallbacks:False; degrades gracefully.
- verifier transport pins both reasoning + non-reasoning blocks; empty-retry adds the
  slug_for_provider(served) to `ignore` and a routed non-reasoning role gets 1+N attempts.
- generator: config-driven routing when no env/Path-B override.
- 654 role+benchmark tests green; new tests cover loader, block-build, display→slug mapping, and
  BOTH the reasoning + non-reasoning routed empty-retry failover.

## Codex gate
iter-1 REQUEST_CHANGES (1 P1: display-name vs slug in `ignore`) -> FIXED via provider_aliases +
slug_for_provider. iter-2 APPROVE (zero P0/P1; 2 P2s — stale ranker header comment + Sentinel-retry
test gap — BOTH addressed in the final commit).

## Verdict
APPROVE. Scope = OpenRouter benchmark/dev path; sovereign self-host failover is a GPU-gated follow-up.
Family-distinctness / served==pinned unaffected (routing changes the SERVER, not the model family).
