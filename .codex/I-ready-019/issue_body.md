## Context
Follow-up to #1100 (drb_72 fix campaign). The operator-authorized paid drb_72 re-run on `bot/I-ready-017-faithfulness` (2026-06-07) reached a terminal **`abort_corpus_inadequate`** — but NOT for a genuine corpus reason.

## Outcome (authoritative: this run's stdout log)
- `status=abort_corpus_inadequate`, ~$3, ~20 min, **no generation, no 4-role spend, no fabrication** (correct fail-closed).
- `[agentic] merged +41 evidence rows from +93 sources; adequacy=proceed uncovered=0` ← **general corpus was ADEQUATE.**
- `[journal_only] source-filter: evidence_rows 59 -> 11 citeable (48 non-journal excluded); classified_sources 247 -> 63`
- `[journal_only] adequacy floor FAILED: ['too_few_distinct_journals:5<12']`
- AEA Journal of Economic Perspectives PDFs (`aeaweb.org/articles/pdf/doi/10.1257/jep*`) returned **1 char** (paywall/anti-bot).

## Root cause
FIX-JO (#1144) applied `journal_only` to `drb_72_ai_labor` — an **economics/workforce** question whose primary evidence is NBER working papers, BLS/OECD data, and think-tank reports, NOT peer-reviewed journals. `journal_only` (a clinical-domain tool) excluded 48/59 sources and collapsed an otherwise-adequate corpus below the 12-distinct-journal floor. Compounded by paywalled-journal full-text fetch failure (AEA etc.). The #1100 campaign fixes (A3/SLOT/GLM/RENDER) are sound but never touched this layer.

Note: this also sits in tension with `state/q1_run_prep_one_go_ahead.md`, which lists `journal_only` as an **operator-controlled, optional** restriction ("do NOT self-set") — FIX-JO effectively baked it on for drb_72 in code.

## Fix options (to research + Codex-review; faithfulness-adjacent — do NOT self-decide)
- (a) Remove `drb_72_ai_labor` from `JOURNAL_ONLY_BENCHMARK_SLUGS` (journal_only is clinical; an economics question should not be journal-only).
- (b) Domain-aware journal_only adequacy floor (count working-paper series / government statistical sources toward adequacy for non-clinical domains; lower the distinct-journal floor).
- (c) Recover paywalled-journal full text via Unpaywall / CORE / OpenAlex green-OA so AEA-class journals yield content → more distinct journals.

## Acceptance
drb_72 produces a releasable report (or holds for a GENUINE corpus reason, not a journal_only artifact). §-1.1 line-by-line audit of the report is the real acceptance. MUST NOT weaken faithfulness gates (strict_verify / 4-role D8 / provenance / two-family).
