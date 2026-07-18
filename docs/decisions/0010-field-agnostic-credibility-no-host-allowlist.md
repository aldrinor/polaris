# 0010. Score credibility from computed field-agnostic signals, not a curated host allowlist

Status: accepted

Date: 2026-06-08

## Context

The tier classifier carried roughly 1,871 lines of curated biomedical host frozensets. That design returns UNKNOWN for any new field or region — Bank of Canada, a Japanese ministry — and needs a brand-new frozenset per domain. That per-domain curation IS the over-fit. Users ask across 10,000+ fields; the only domain signal that scales is the question itself. Operator directive (2026-06-08, `credibility_weighted_sourcing_redesign_plan_2026_06_07.md` §9): NO fixed domain rubrics.

## Decision

Replace the curated host frozensets with a continuous `authority_score` computed from field-agnostic signals:

- scholarly-graph authority (OpenAlex/Crossref `cited_by`, venue h-index, `is_core`, `is_retracted`),
- primary-vs-secondary via ROR institution type plus PSL government-suffix,
- structural junk detection (press-release / user-generated-content / self-published markers),
- independent-host CORROBORATION (Knowledge-Based Trust — the sovereign trust multiplier), and
- recency.

Use one generic adaptive credibility SKILL that reasons over the question (a hint, not a branch). No fixed clinical, economic, or qualitative rubrics. T1-T7 survives only as a clinical VIEW rendered from these primitives.

The anti-over-fit gate is a four-part contract, not a single grep: no host/suffix/platform literals in CODE (all as versioned data); a zero-host grep; a per-source `authority_confidence`; and adversarial thin-field fixtures.

## Consequences

- The pipeline is now domain-general: a credible source in an unlisted field gets a real score instead of UNKNOWN, without anyone writing a new frozenset.
- The four-part anti-over-fit contract must be enforced, or curated literals will creep back into code and quietly re-introduce the over-fit.
- The question is a weighting hint, never a hard branch, so the same code path serves every field.
- This generalizes the allowlist decision (ADR 0005): the clinical allowlist becomes one VIEW over the computed primitives, not the credibility model itself.
