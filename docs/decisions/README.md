# POLARIS Architecture Decision Records

This directory holds the Architecture Decision Records (ADRs) for POLARIS, in the
[Nygard format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
each file records one decision with its Context, Decision, and Consequences.

These 27 records were distilled from mined decision items across the project's
session logs, forensic docs, and operator directives. Duplicate findings of the same
decision were merged. Several records document a REVERSAL of an earlier rule (for
example the review-iteration cap and the unfrozen faithfulness engine); in those the
Context names the prior position, and the single "accepted" status reflects the
current, durable form. Themes marked in the taxonomy but not represented here
(UI/visual audit, security/threat modeling, delivery/compliance) had no mined
decision item and were deliberately not invented.

## Themes

| Code | Theme |
|---|---|
| RETR | Retrieval, weighting & source triage (WEIGHT-not-FILTER) |
| FAITH | Faithfulness engine & span grounding (runtime) |
| AUDIT | Line-by-line audit standard & the faithfulness ghost (grading discipline) |
| EVAL | Evaluation, benchmarking & beat-both scoring |
| ARCH | Pipeline architecture, depth & parallel composition (the moat) |
| MODEL | Model & token governance / sovereignty constraint |
| REVIEW | Codex/Fable review gate & issue-driven workflow |
| AUTO | Autonomous execution loop & no-pause discipline |
| DEBUG | Debugging & forensic monitoring methodology |
| OPS | Resource discipline, VM ops & infrastructure |
| COMMS | Operator communication & working norms |
| GOV | Governance cage, session protocol & state persistence |

## Index

| # | Title | Theme |
|---|---|---|
| [0001](0001-bookkeeping-in-code-not-in-the-llm.md) | Do provenance bookkeeping in code, not in the LLM | ARCH |
| [0002](0002-per-section-isolation-scoring-bakeoff.md) | Isolation-scoring: bake off each pipeline section on its own axis | EVAL |
| [0003](0003-compose-first-verify-per-sentence.md) | Compose the report first, verify per-sentence afterward | ARCH |
| [0004](0004-class-b-verify-then-organize-composition.md) | POLARIS is a Class-B verify-then-organize composition pipeline | ARCH |
| [0005](0005-allowlist-not-denylist-tier-promotion.md) | Promote source tiers by allowlist; default everything else to the safe tier | RETR |
| [0006](0006-weight-and-consolidate-not-filter-and-cap.md) | Pipeline DNA: WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP; faithfulness is the only hard gate | RETR |
| [0007](0007-basket-consolidation-merge-key-guard.md) | Consolidate into corroboration baskets; guard the merge key against false-merge | RETR |
| [0008](0008-junk-deletion-carveout-chrome-and-offtopic.md) | Junk-deletion carve-out: delete only chrome and confirmed off-topic sources, fail-open, disclosed | RETR |
| [0009](0009-loss-ledger-source-funnel-budgets-not-validity.md) | Separate operational budgets from evidence validity with a loss ledger and a source funnel | RETR |
| [0010](0010-field-agnostic-credibility-no-host-allowlist.md) | Score credibility from computed field-agnostic signals, not a curated host allowlist | RETR |
| [0011](0011-origin-cluster-weight-mass-not-count.md) | Aggregate corroboration by origin-cluster weight-mass, not source count | RETR |
| [0012](0012-always-release-with-labels-never-hold.md) | Always release with labels; the verifier never holds or aborts a report | FAITH |
| [0013](0013-line-by-line-audit-ghost-is-a-mindset.md) | Line-by-line audit standard; the faithfulness ghost is a mindset; re-audit after every lock | AUDIT |
| [0014](0014-faithfulness-gate-provenance-strict-verify-context-nli.md) | The faithfulness gate: provenance tokens, strict_verify, context-level NLI and numeric match (lexical overlap dropped) | FAITH |
| [0015](0015-faithfulness-engine-unfrozen-visible-quality.md) | The faithfulness engine is unfrozen: visible quality outranks invisible faithfulness | FAITH |
| [0016](0016-map-reduce-short-markers-deterministic-span-finder.md) | In map-reduce distillation, emit short markers and let a deterministic span-finder compute offsets | ARCH |
| [0017](0017-flag-gated-default-off-byte-identical-phasing.md) | Ship every new layer behind a flag, default-OFF byte-identical, fail-loud | REVIEW |
| [0018](0018-moat-parallel-basket-modular-depth.md) | The moat: section/basket-modular depth rendered in parallel | ARCH |
| [0019](0019-connected-hamster-wheels-outline-is-the-soul.md) | Report quality is a chain of connected hamster wheels; the outline is the soul | ARCH |
| [0020](0020-two-family-generator-evaluator-segregation.md) | Generator and evaluator must be different model families | MODEL |
| [0021](0021-model-and-token-budget-governance-sovereignty.md) | LLM model must match the signed lock; reasoning effort and token budgets always go MAX | MODEL |
| [0022](0022-standard-debug-workflow-issue-grep-smoke-review.md) | Standard debug workflow: GitHub Issue first, grep adjacent, smoke test, then review | DEBUG |
| [0023](0023-bounded-dual-model-review-gate-5-iter-cap.md) | Bounded dual-model review gate: Codex and Fable, hard 5-iteration cap, front-loaded findings | REVIEW |
| [0024](0024-governance-cage-no-admin-merge-structural-enforcement.md) | The governance cage: no admin-merge authority, sequential issues, structural CI enforcement | GOV |
| [0025](0025-autonomous-execution-no-self-stop-quota-tiering.md) | Autonomous execution discipline: no self-initiated stops, quota-aware model tiering | AUTO |
| [0026](0026-resume-from-closest-checkpoint.md) | Resume from the closest checkpoint after a downstream crash; never re-run fresh | OPS |
| [0027](0027-operator-is-blind-plain-simple-english.md) | The operator is blind: plain simple English in every message | COMMS |
