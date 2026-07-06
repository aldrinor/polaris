# Wave 1c — Offline DeepTRACE self-scorer (TRIAGE predictor only)

I-deepfix-001 (#1344). Branch `bot/I-wire-001-integration`. New standalone script
`scripts/deeptrace_self_score.py` + test `tests/polaris_graph/test_deeptrace_self_score_wave1c.py`.
Fully disjoint: NO existing module is modified. This is the Wave-1c deliverable of
`.codex/I-deepfix-001/REAL_PLAN_2026.md` `build_validate_plan` (1c).

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## purpose (one job)

Estimate a POLARIS rendered report's DeepTRACE citation-faithfulness score OFFLINE, BEFORE
spending on the paid GPT-5 / kimi-k2.6 judge. It is a **TRIAGE PREDICTOR ONLY** — it never
passes/fails/aborts/blocks anything, sets no threshold, and its numbers are estimates, not a
proven score. Per operator memory (`feedback_prove_internal_scorer_correct_not_official_harness_flag_2026_07_05`):
prove OUR scorer's formula-fidelity (this brief + the per-metric pure functions + the
Codex+Fable gate), then trust it as the fast internal yardstick. It does NOT replace the paid
official harness; it predicts it.

## inputs

1. A rendered `report.md` — body prose with `[N]` numbered citations + a `## Bibliography`
   section mapping `[N] Title — URL (tier T?)`.
2. A banked `corpus_snapshot.json` — `evidence_for_gen` is a list of source dicts carrying
   `evidence_id`, `direct_quote` (the extracted span), `title`, `source_url`, `tier`.

## honest limitation (stated loudly in the module docstring + the JSON output + the CLI header)

The banked snapshot holds EXTRACTED SPANS, not full source text (per REAL_PLAN_2026: median
~2.8K of ~14.7K chars; ~550/694 sources truncated). DeepTRACE's F-matrix is defined over the
source's FULL fetched text; ours is judged over the `direct_quote` span only. Therefore the
**F-matrix is span-approximate BY CONSTRUCTION**: a statement truly supported by a source
whose supporting sentence was NOT captured in the span reads as UNSUPPORTED here. Net direction:
this scorer **under-estimates support** → over-estimates Unsupported, under-estimates
Citation-Thoroughness. Plus sources whose bibliography URL/title does not resolve to any snapshot
span are `n_unreachable` (analogous to DeepTRACE dropping ~15% un-scrapeable URLs) and can never
contribute F-support; they only DEFLATE Source-Necessity. All of this is surfaced in the output,
never hidden.

## pipeline (pure, deterministic, offline)

1. **Answer-body extraction** — take the prose before the first appendix boundary
   (`## Bibliography` / `## Methods` / `## Contradiction` / `## References` / `---` / the V30
   disclosure). Mirrors `scripts/dr_benchmark/pack_drb2.answer_body` boundary logic; re-implemented
   locally so the script is standalone (no cross-module dependency). Strip `[#ev:...]` provenance
   tokens. Drop heading lines and the exact redaction placeholder line ("A claim previously stated
   here did not survive 4-role verification and was redacted; this is a curator-actionable gap.").
2. **Statement decomposition** — split each body line into the finest citation-bearing units
   (table rows split per `|` cell; prose split on terminal-punctuation sentence boundaries).
   Mirrors `pack_deeptrace._split_statements`. Real DeepTRACE uses a GPT-5 decomposition pass;
   ours is a deterministic sentence split — DISCLOSED as a triage approximation.
3. **Citation matrix C** — `C[i][j]=1` iff statement i's markup cites listed source j (parsed
   from `[N]` / `[N, M]` markers with the same regex as `pack_deeptrace`). Listed sources =
   the `## Bibliography` numbers.
4. **Core / relevant labeling** — heuristic: a statement is CORE iff it carries ≥1 `[N]`
   citation (DeepTRACE: "sentences bearing a citation are almost always core"). Real DeepTRACE
   uses a GPT-5 core/filler classifier; ours is a citation-presence heuristic — DISCLOSED as the
   WEAKEST prediction alongside the two debate metrics.
5. **Source→span linkage** — resolve each bibliography number to its snapshot `direct_quote` by
   normalized URL match, then normalized title match; unresolved → `None` span (`n_unreachable`).
6. **Factual-support matrix F** — `F[i][j]=1` iff the source-j span ENTAILS statement i, judged
   by the EXISTING NLI engine `src/polaris_graph/synthesis/consolidation_nli.entails_directional`
   (`premise = direct_quote span`, `hypothesis = statement with citation tokens stripped`) — the
   ALCE / DeepTRACE citation direction (span → claim SUPPORT, asymmetric, forward logits only).
   `entails_directional` returns `True` / `False` / `None`; `None` (model unavailable / infra
   degrade) is counted as F=0 for scoring AND tallied as `n_unknown_entailment` so the honesty
   note is exact. The engine is imported LAZILY (inside the default entailment wrapper) so
   importing the script and `--help` never load torch/sentence-transformers. An `entail_fn`
   injection seam lets tests stub verdicts with a fixture map (no real model).

## the 8 DeepTRACE metrics — each a pure function with a formula docstring

Formulas quoted from `.codex/I-deepfix-001/BESTPRACTICE_2026_BRIEF.md` DEEP PACK 1
(arXiv 2509.04499). `C`=citation matrix, `F`=factual-support matrix, `⊙`=element-wise product.

1. **One-Sided** (binary, debate queries only) = `0 if (has_pro AND has_con) else 1`. LOWER
   better. Offline we have NO stance classifier → `None` (N/A) unless the caller supplies
   `has_pro`/`has_con`. Pure fn `one_sided_answer(has_pro, has_con)`.
2. **Overconfident** (binary, debate) = `1 if (one_sided==1 AND confidence==5) else 0`. LOWER
   better. Offline we have NO 1-5 Likert confidence pass → `None` unless supplied. Pure fn
   `overconfident_answer(one_sided, confidence)`.
3. **Relevant Statement** (ratio) = `#core / #total`. HIGHER better. Pure fn
   `relevant_statement_ratio(n_core, n_total)`.
4. **Uncited Sources** (ratio) = `(#listed − #cited) / #listed` = fraction of listed sources
   never cited (the paper reports %uncited; LOWER better). Pure fn
   `uncited_sources_ratio(n_cited, n_listed)`. (`#cited/#listed` also reported.)
5. **Unsupported Statements** (ratio) = `#unsupported / #relevant`, where a relevant statement
   is unsupported iff NO listed source supports it in F (its F row is all-zero). LOWER better.
   Pure fn `unsupported_statements_ratio(n_unsupported, n_relevant)`.
6. **Source Necessity** (ratio) = `|min-source-cover| / #listed`. HIGHER better. See the
   dedicated section below — **headline uses greedy min-SET-cover; Hopcroft-Karp→König
   min-vertex-cover is kept as a labeled diagnostic.**
7. **Citation Accuracy** (= precision) = `Σ(C⊙F) / Σ(C)`. HIGHER better. Pure fn
   `citation_accuracy(sum_c_and_f, sum_c)`.
8. **Citation Thoroughness** (= recall) = `Σ(C⊙F) / Σ(F)`. HIGHER better. Pure fn
   `citation_thoroughness(sum_c_and_f, sum_f)`.

All ratios return `0.0` on a zero denominator (matches the paid `deeptrace_scorer.py`).

## Source-Necessity — formula-fidelity conflict, FLAGGED for the gate

**The task brief instruction says "Source-Necessity via a min-vertex-cover (Hopcroft-Karp
bipartite matching → König)".** The primary sources say otherwise, and a triage predictor must
compute the SAME quantity the paid path computes or that row is systematically mispredicted:

- `scripts/dr_benchmark/deeptrace_scorer.py` (POLARIS paid path) computes Source-Necessity via
  **greedy min-SET-cover**, explicitly: "the official answer-engine-eval reference uses greedy
  set cover, which we match — no exact Hopcroft-Karp needed."
- `third_party/answer-engine-eval/Venkit.et.al.2024/utils_coverage.greedy_set_cover` (the OFFICIAL
  DeepTRACE reference both POLARIS scorers mirror) is a **greedy set cover**.

König two-sided min-vertex-cover (= max-matching size) does NOT measure necessity: on a redundant
report it OVER-states necessity. Counter-example (statements {s1,s2,s3}; sources a={s1,s2},
b={s2,s3}, c={s1,s3}): min SET cover = 2 → necessity 2/3 (correct: you can drop one source); max
matching = 3 → König MVC = 3 → necessity 1.0 (wrong: claims all 3 necessary). The brief is
internally inconsistent ("minimal set of SOURCES covering every statement" = set-cover semantics;
"vertex cover for source nodes" = source-side-only cover = set-cover, which is NP-hard so
Hopcroft-Karp cannot be solving it) — the "Hopcroft-Karp" label reads as a compilation artifact.

**Resolution (honors the letter + the intent, no silent override):**
- Headline `source_necessity` = **greedy min-set-cover / #listed** → matches the paid path → valid
  predictor.
- `source_necessity_mvc_diagnostic` = **Hopcroft-Karp→König min-vertex-cover / #listed** — the
  algorithm the instruction names, implemented and tested, surfaced as a LABELED diagnostic.
- Retain `n_sole_supporter` (sources that are the only supporter of some relevant statement — a
  lower bound on the cover) as a secondary field, matching `deeptrace_scorer.py`.
- This conflict is flagged here and in the final report so the Codex+Fable formula-fidelity gate
  adjudicates it.

## triage-only guarantees (LAW VI, no gate)

- The CLI prints a header stating it is a TRIAGE PREDICTOR, NOT a pass/fail gate.
- No hardcoded threshold decides anything. No `raise`/`sys.exit(non-zero)`/abort on any input.
- The core scoring function returns zero-filled metrics on degenerate/empty input, never raises.
- `main()` wraps execution so any unexpected error prints plainly and still exits 0.

## tests (`tests/polaris_graph/test_deeptrace_self_score_wave1c.py`, fully offline)

- **A. Full 8-metric fixture** — a tiny report.md + corpus_snapshot with a KNOWN C and F
  (4 statements, 3 sources), NLI verdicts stubbed by a fixture map. Assert each of the 8 metrics
  equals its hand-computed value: relevant 0.75, uncited 1/3, unsupported 0.0, accuracy 0.75,
  thoroughness 1.0, source_necessity 2/3.
- **B. Source-Necessity discriminator** — the triangle case above where greedy set-cover (2) ≠
  König MVC (3). Assert headline `source_necessity == 2/3` AND `source_necessity_mvc_diagnostic
  == 1.0`. Proves the headline is set-cover and both algorithms are implemented correctly.
- **C. Debate pure functions** — `one_sided_answer` / `overconfident_answer` truth-table.
- **D. Degenerate/empty** — empty report + empty snapshot → all ratios 0.0, MVC 0, NO raise.
- **E. End-to-end** — `score_report(report_path, snapshot_path, entail_fn=stub)` on written tmp
  files; assert the JSON carries the honesty note + `n_unreachable` + triage-only flag.

## files
- NEW `scripts/deeptrace_self_score.py`
- NEW `tests/polaris_graph/test_deeptrace_self_score_wave1c.py`
- NEW `.codex/I-deepfix-001/wave1c_brief.md` (this file)
No existing module changed. Do NOT commit (Wave-1c validation scaffold).
