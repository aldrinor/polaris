## Operator directive (2026-06-07) — drop the journal-only tunnel vision

> "I don't like this approach, as many things are not journal, but still credibility. Mainstream news, gov, some credible sites, why you have tendency to make yourself into tunnel view"

**Resolution:** journal-only is rejected. The source model must be a **domain-aware credibility model** (peer-reviewed journals + government statistics + working papers + reputable institutes + quality news), judged on claim-support — NOT a peer-reviewed-journal-purity filter.

### Investigation findings (2 parallel agents)
**Methodology (research):** a "distinct peer-reviewed journal COUNT" adequacy floor is the metadata-as-quality proxy banned by §-1.1; journal-only is methodologically wrong for economics/policy (Campbell Collaboration modifies the clinical hierarchy; grey-literature inclusion is expected; the Economic Report of the President is ~33% non-journal). Working papers (NBER/IZA), gov stats (BLS/OECD/Eurostat), reputable institutes are PRIMARY evidence in economics.

**Key catch (research):** the AEA Journal of Economic Perspectives (`10.1257/jep.*`) that fetched as 1 char is **publicly FREE** on aeaweb.org — the failure was **anti-bot blocking of legally-free content**, NOT a paywall. Silent capability downgrade.

**Code map (agent):**
- `JOURNAL_ONLY_BENCHMARK_SLUGS = frozenset({"drb_72_ai_labor"})` — `scripts/dr_benchmark/run_gate_b.py:827`; set via `apply_journal_only_for_slug` (:830-853), called :952.
- Source-filter `[journal_only] ... evidence_rows N->M citeable` — `scripts/run_honest_sweep_r3.py:3252`; predicate `is_citeable_journal` `src/polaris_graph/nodes/journal_only_filter.py:208-264`.
- Count floor `DEFAULT_MIN_DISTINCT_JOURNALS = 12` — `journal_only_filter.py:531`; `assess_journal_only_adequacy` :543-607; YAML override `config/scope_templates/workforce.yaml:109-112`.
- General adequacy (`adequacy=proceed`) computed first at `run_honest_sweep_r3.py:2773`; journal-only floor RE-overrides to abort at :3321-3338.
- FIX-JO rationale: drb_72 question text "only cites high-quality, English-language journal articles" → was read as a literal journal-only contract.

### Plan (Codex-gated)
- **FIX-CRED-01 (this issue #1146):** remove `drb_72_ai_labor` from `JOURNAL_ONLY_BENCHMARK_SLUGS` and retire the drb_72 journal-only override in `workforce.yaml` so the broad credibility-tier contract governs (general adequacy already = proceed). Faithfulness gates (strict_verify / 4-role D8 / provenance / two-family) UNCHANGED — journal-only was corpus composition, not a faithfulness gate.
- **FIX-FETCH-02 (sibling issue):** recover legally-free journal full text blocked by anti-bot (proper UA/headers) + Unpaywall→CORE→Semantic-Scholar legal OA fallback; record fetched version (working-paper vs version-of-record) for provenance honesty.
- Then operator-gated re-run → §-1.1 line-by-line audit → beat-both vs Q72 ChatGPT/Gemini.

Note: question text says "journal articles" — interpreted as "high-quality credible scholarly/authoritative sources," not literal journal-only, per operator directive + the fact a credible multi-source review scores higher on §-1.1 faithfulness than a thin 5-journal one. Codex to weigh.
