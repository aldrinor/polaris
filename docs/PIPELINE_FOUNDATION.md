# Pipeline Foundation — stabilized main line (2026-07-20)

This is the secured, stabilized foundation the pipeline builds on going forward. After the
descriptive renames, the five foundation fixes, and the config consolidation, the raw-A pipeline
runs clean end-to-end and the champion result was replicated.

## Canonical branch and run command
- **Foundation branch:** `gate-inversion` (the real ~10,017-file tree; `main` is an empty,
  unrelated-history placeholder — do NOT target it).
- **One run command:** `scripts/run_raw_a.sh [--corpus PATH] [--rq-drb-task N] [--out-dir DIR]`.
  It captures every fragile knob (browser libs, `PG_LOOPBACK_MODE=0`, GPU reranker chunk,
  outline token budgets, keys via dotenv, interpreter `/home/polaris/pipeline-env/bin/python`).

## The replicated result (task 72, RACE, judge openai/gpt-5.5)
| Config | Overall | Comprehensiveness | Insight | IF | Readability | Sentences dropped |
|---|---|---|---|---|---|---|
| **Faithfulness OFF** (this foundation) | **0.4486** | 0.4733 | 0.4489 | 0.4455 | 0.3981 | 0 |
| Champion (faithfulness on) | 0.4447 | 0.4569 | 0.4293 | 0.4587 | 0.4310 | — |
| Fresh raw-A (faithfulness on) | 0.30 / 0.37 / 0.38 | — | — | — | — | ~half dropped |

Faithfulness OFF beats the old champion and far outscores the faithfulness-on runs — the
over-strict verifier was dropping ~half the (mostly true, NEUTRAL-not-false) synthesis, which is
what held the score down. The `RACE`-vs-`FACT` tradeoff (citation-support rate with faithfulness
off) is not yet measured — it needs a working-browser box to scrape the 147 cited sources.

## The five foundation fixes (all codex-sol(max) approved, on gate-inversion)
1. **Config consolidated** — `CONFIG-CONSOLIDATED`: settings.py + `resolve()` + 833 migrated
   sites; the 215-site tail codemod is byte-identical (`8264c3d`, `58e0809`).
2. **Checkpoints** — `CHECKPOINT-FIX-SOUND`: a resume reuses saved generation drafts and still
   re-runs every faithfulness gate (§-1.3 preserved) (`695951c`).
3. **Logging** — `LOGFIX-SOUND`: the compose path now wires the reasoning-trace sink; reasoning
   is no longer lost (`8d23105`).
4. **Faithfulness switch** — `ENTOFF-SOUND` + `FAITH-TRULY-OFF`: master `PG_STRICT_VERIFY_OFF`
   (default OFF, byte-identical unset) drops NOTHING when set; wired into `run_raw_a.sh`.
5. **Clean run command** — `RUNSCRIPT-SOUND`: `scripts/run_raw_a.sh`.

## Governance
All future work runs inside the govkit (`gov/` + `tools/` + `.githooks/pre-commit` +
`govkit_checks.yml`): descriptive naming, GitHub updated on every change, new settings through the
central config layer (never hardcoded), and every operator message linted.

## Honest owner-only remainders (NOT blockers on this foundation)
- **27 conflicting-default config keys** need a product decision (each has disagreeing literals).
- **12 credential keys** await a separate `SecretStr` pass.
- **The FACT/citation-support score** with faithfulness off is unmeasured (needs a working browser).
- **`main` branch**: empty + protected (1 review, admins included) + unrelated history — merging
  the foundation there needs an operator approval or a protection change. `gate-inversion` is the
  working foundation in the meantime.
