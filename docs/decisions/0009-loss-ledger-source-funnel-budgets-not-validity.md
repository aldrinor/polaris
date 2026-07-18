# 0009. Separate operational budgets from evidence validity with a loss ledger and a source funnel

Status: accepted

Date: 2026-06-13

## Context

Codex's forensic review (MISS 2/3, `pipeline_redesign_master_plan.md` §2.2) found that the earliest and biggest source loss happens in `_rerank_and_reserve` enforcing a `fetch_cap` — it decides which URLs are never fetched by any tool at all. Those silent budget cuts were being treated as "irrelevant." But a budget skip is not a quality verdict: a URL dropped because the fetch budget ran out may be the best source for a claim.

The old retrieval output was one evidence row with a capped `direct_quote`, which threw away the full text and every fetch attempt.

## Decision

Keep real operational caps — fetch budget, provider page limits, timeouts, cost — but never let a source silently vanish. A URL that is not fetched stays a `SourceCandidate` with an explicit status (`not_fetched_budget`, `fetch_failed`, `blocked`, `metadata_only`, `fetched_fulltext`) and a loss-ledger row: `{source_id, stage, knob, score, reason, would_keep_as_low_weight, claims_affected}`.

Change the retrieval data model to a funnel: `SourceRecord` (full text plus every fetch attempt) → `SourceVersion` (preprint/journal/PDF/HTML twin) → `SourceSpan` (claim-specific windows derived later). Prompt windows stay small; stored content is full.

## Consequences

- Operational budgets and evidence validity are now cleanly separated. A source can be cut for cost while still being recorded as valid and re-includable, which is the honest reflection of what happened.
- The loss ledger makes every drop auditable and disclosable, and is the enforcement surface for ADR 0006's "no silent DROP" promise.
- Storing full text and all fetch attempts costs more storage but enables later re-derivation of spans, re-ranking, and resumption without re-fetching.
- Because content is stored full but prompted small, prompt budgets no longer force the corpus to be lossy.
