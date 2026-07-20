# Foundation lockdown — faith-off pipeline v1 (rollback point, 2026-07-20)

This is the frozen, proven, faith-OFF pipeline. If any future change regresses, roll back here.
Tag: `foundation-faithoff-v1`. Foundation commit: `15fcdda` (branch `gate-inversion`).

## Proven results (DeepResearch Bench task 72, single task)
- **RACE Overall = 0.4486** (Comp 0.4733 / Insight 0.4489 / IF 0.4455 / Read 0.3981) — judge openai/gpt-5.5. See `race_result.txt`.
- **FACT citation accuracy (valid_rate) = 1.0** — 11/11 judged citations supported. See `fact_result.txt`.
- The report scored is `report.md` (article_chars ~79k).

Reference points on the same box/judge: champion 0.4447; judge noise band ~0.43–0.45 across repeats; Fable-5's own report 0.5065.

## How it was produced
- **Compose (RACE report):** `scripts/run_raw_a.sh --out-dir outputs/faithoff_t72` — raw-A compose over the frozen corpus `data/cp4_corpus_s3gear_329.json`, GLM 5.2, faithfulness FULLY OFF (`PG_STRICT_VERIFY_OFF=1`).
- **RACE score:** `scripts/score_report_race.py --report <report.md> --task-id 72 --model-name faithoff_t72`.
- **FACT score:** `scripts/score_report_fact.sh <report.md> faithoff_t72_fact 72` (Jina scrape + openai/gpt-5.4-mini judge).

## The load-bearing finding (do NOT undo)
The post-report faithfulness verifier (`PG_STRICT_VERIFY` / entailment) is a **backfire**: it deletes ~half the composed sentences (mostly true, NEUTRAL-not-false) and cut RACE from ~0.45 to ~0.30. Turning it OFF gives BOTH higher RACE (0.4486) AND perfect citation accuracy (1.0). **Never re-enable a post-generation entailment/verifier as a quality lever.** The real remaining gap is citation *volume* (11 vs leaders' ~100+), which is an ADDITIVE improvement in outline/compose/fetch/search — never a deletion filter.

## Rollback
```
git checkout foundation-faithoff-v1        # or: git reset --hard foundation-faithoff-v1
```
See [../docs/PIPELINE_FOUNDATION.md] for the full foundation record.
