# RACE 4-dimension action plan (Sol + Fable + K3 + Claude, consolidated)

Champion: `k3_b1_run` (K3 generator + Batch-1 evidence substrate + route-all). RACE 3x-mean **0.5084**.
Per-dimension (task-72 judge weights in parentheses): Comprehensiveness 0.521 (0.29), Insight 0.524 (0.32),
Instruction-Following 0.499 (0.25), Readability 0.457 (0.14). Goal: lift ALL FOUR together, never trade one
for another. Every change is central-config-gated, defaults to today's behavior, and is measured on RACE
before the next lands.

## How RACE actually scores (verified in `third_party/deep_research_bench`)
- Comparative, not absolute: dimension score = target / (target + reference) (`deepresearch_bench_race.py:155`).
  We lose where the fixed reference report beats us.
- The judge reads BODY PROSE ONLY. A cleaner deletes the whole reference list and every inline `[N]` marker
  before judging (`prompt/clean_prompt.py`, verified on the cleaned champion artifact: zero markers, references
  gone, paragraph structure preserved). => Reference-list edits are ~zero for RACE (they help FACT only).
- Dimension weights are judge-assigned per task (`data/criteria_data/criteria.jsonl` id 72). Readability is our
  lowest score but the lowest weight (0.14) — it must rise as a co-benefit, not as the primary target.

## Rubric mass reachable by each joint lever (from the task-72 weights)
| Lever | Raw rubric mass | Dimensions |
|---|---|---|
| Cross-study / cross-industry synthesis | 0.190 | Insight + Comprehensiveness + Instruction-Following + Readability |
| Coverage spine (4IR + scope + AI/GenAI balance) | 0.115 | Insight + Comprehensiveness + Instruction-Following |
| Upstream journal/English source routing | 0.106 | Instruction-Following + Comprehensiveness |
| Paragraph/formatting render | 0.035 | Readability |

## Verified gaps in the current report
- Each section is one block up to 1,214 words; no paragraph breaks (renderer flattens with `" ".join` at
  `provenance_generator.py:5121`; whitespace collapse eats newlines at `:715`).
- Industries are named but never compared side by side; the reference has a dedicated cross-industry section.
- "Fourth Industrial Revolution" appears 4x in the introduction and 0x afterward — named, never threaded.
- Prose says "the working-paper version..." (`report.md:19`) and limitations admit "only 4% of sources are
  T1" (`report.md:39`) — both are judge-visible and hurt the "journal articles only" instruction.
- Corpus RQ is "Generative AI" but the task asks about "AI" broadly (`compose_summary.json`) — evidence
  over-centers recent LLM studies.
- One citation is Arabic-language; language metadata fails open (unknown treated as English).

## Action plan (shipped and RACE-measured one at a time)

### Step 1 — Structure-preserving render (safe enabler; ship first)
Capture the writer's semantic blocks BEFORE whitespace cleanup; sentence-split each block independently;
carry a `render_block_id` through `SentenceVerification` (must NOT affect the verdict); keep sentence-end
citation attachment; join sentences within a block by space and blocks by blank line; restrict whitespace
normalization to horizontal space only. Do NOT use the existing `PG_SECTION_STRUCTURE` prompt path alone —
its base/retry/user prompts still demand a single paragraph and conflict with it. Validate by replaying a
saved report through old vs new renderer: sentence text/order/citation ownership byte-identical, only grouping
changes. Small direct gain (~0.035); its real job is to unblock Step 2. Seams: `provenance_generator.py`
`:696/:715/:730/:5101/:5121`. Flag: render-blocks, default off.

### Step 2 — Typed cross-study comparison tables (largest lever: 0.190, all four dimensions)
Generalize the existing verified-prose-only table generator (`multi_section_generator.py:7170`, reuse-`[N]`-only
contract `:3524`) to a comparison matrix. Emit a row only when 3+ verified studies share a genuinely comparable
construct; each row keeps its own `[N]` sources; columns for context/industry, technology/use, outcome,
direction, horizon, study design, boundary condition; plus explanatory prose (agreement / contradiction /
why they coexist). Preserve every unique claim in the matrix or the narrative (claim-coverage checksum).
Never force incomparable metrics into one column. Needs Step 1. Flag: synthesis-matrix, default off.

### Step 3 — Coverage spine (0.115)
Give each required-coverage concept from the RQ contract one distinct analytical role, used consistently
(framing / mechanism / industry comparison / synthesis / implication), so the 4IR frame recurs instead of
appearing once, and broad AI is covered with Generative AI as a major case. Additive only; never drop or
rename existing sections; coverage routing stays on. Seams: constraint extractor required-coverage, clause
ledger (`planning/clause_ledger.py:487`), outline allocation, judged-RQ / corpus-RQ interface. Flag:
coverage-routing, default off.

### Step 4 — Upstream journal/English source routing + backfill (0.106; hardest, highest risk)
Route evidence toward peer-reviewed journal articles; where only a working paper exists, resolve the same
work's published version and RE-EXTRACT from it, then rerun strict verification (never swap on a title match —
`planning/citation_reanchor.py:90/:261` requires literal-span equivalence and its "primary" admits preprints).
Add real language detection (fix fail-open at `retrieval/rq_eligibility.py:153`). No-rollback gate: match or
exceed baseline unique-claim, industry, and mechanism coverage, else do not ship. Seams: constraint
extraction, retrieval projection (`planning/retrieval_projection.py:82`), quality eligibility
(`retrieval/quality_eligibility.py`), same-work identity, evidence selection. Flags: source-routing plus
existing gate/source-restriction, default off.

### Step 5 — Cross-section fact consolidation
Merge the same verified fact restated across sections into one statement that carries all corroborating `[N]`s;
preserve every distinct qualifier; reallocate freed words to synthesis (do not shorten the report). The
anti-restatement pass is skipped under the strict-off recipe (`multi_section_generator.py:11594`, flag exists).

### Step 6 — Limitations wording + bibliography (last)
Rewrite the limitations in scholarly language: keep the honest caveat, drop internal vocabulary (tier codes,
telemetry, pipeline) and the self-attack "only 4% are T1". This one helps RACE (judge-visible prose). The
bibliography cited-only / canonical-work render helps FACT only (references are stripped before RACE) — do it
for integrity, not for RACE. Flags: limitations-register, bibliography-usage, canonical-work-bibliography,
default off.

## Per-dimension coverage (all four rise; none traded)
- Insight (0.32): Steps 2, 3
- Comprehensiveness (0.29): held by route-all; raised by Steps 2, 3, 4
- Instruction-Following (0.25): Steps 4, 3, 6
- Readability (0.14): Steps 1, 2, 5

## Rejected traps
Delete/truncate content for shorter paragraphs; disable route-all or cap citations (load-bearing coverage);
enable `PG_SECTION_STRUCTURE` alone (conflicting prompts + renderer flatten); add bullets/tables/bold
mechanically; grow synthesis word count without typed comparisons; relabel working papers as journals or add
a sourcing-policy note; delete the limitations admission to hide it; edit the bibliography for RACE (stripped
before judging); redirect a claim to a published version without re-extracting and re-verifying; use "primary
source" as a proxy for "journal article"; leave strict verification off to protect coverage.

## Method for every step
Central-config-gated (default = today's behavior); implemented via the claude + Sol workflow with tests;
gated by Sol at max reasoning; measured 3x on RACE (judge noise about +-0.007; Instruction-Following alone
ranged 0.4943-0.5079 across the three champion draws); faithfulness engine untouched; GitHub and docs updated
per step. No overfitting, no hardcoding, no adjective naming (switches named by behavior).
