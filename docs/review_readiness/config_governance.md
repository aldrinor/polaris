# Configuration governance (Phase 1A)

The pipeline's configuration surface, inventoried from **every** `os.getenv` / `os.environ` read site
in the code (not just `.env`), classified, and with the migration approach. This is the "govern before
migrate" gate: nothing migrates into the typed settings layer until it appears here.

## The surface (measured)
- **1,644** distinct config keys read across `src/` + `scripts/` (2,592 read-sites).
- **1,044 runtime keys** (`src/polaris_graph`) — the governance + migration target:

| Category | Count | Meaning | Migration priority |
|---|---:|---|---|
| model-selection | 35 | model slug / provider / LLM role choice | **P1 — the single source of truth** |
| secret | 97 | `*_KEY` / `*_TOKEN` / credentials | P1 — `SecretStr`, never plaintext |
| internal-flag | 71 | `_ENABLED`/`_MODE`/`_GATE` booleans | P2 |
| tuning-threshold | 372 | `MAX_`/`_CAP`/`_TIMEOUT`/`THRESHOLD`/`_K` numerics | P2 |
| external/system | 35 | non-`PG_` standard env (HOME, PATH, provider base urls) | keep as-is / thin wrapper |
| internal-other | 434 | other `PG_*` control flags | P3 (long tail) |

- **600** keys are `scripts/`-only (dev tooling) — out of the runtime migration scope.
- **~1,198** keys are **code-default-only** (a literal default in the `os.getenv` call, not set in `.env`)
  → the migration MUST preserve each literal default exactly.

Machine-readable inventory: `baseline/config_keys_classified.json` (git-ignored; per key: read-sites,
files, in-env, category, secret flag).

## The hard rule (byte-identical by construction)
Every migrated key keeps its **exact `PG_*` name** and its **exact current default literal**. A
characterization test (Phase 1B) locks today's resolution behaviour — value, precedence, case,
coercion, malformed input, read-timing, runtime type — before any module migrates. Never change a
value in the same commit that moves it.

## Approach (given the 1,044-key scale)
A one-shot rewrite of 1,044 hardcoded reads is neither safe nor reviewable. The plan is:
1. **Establish the pattern + the model source of truth first** — build `src/polaris_graph/settings.py`
   (pydantic-settings, `env_prefix="PG_"`, `SecretStr` for secrets) and migrate the **35
   model-selection keys** so "one file controls every model," which was the headline requirement.
2. **Migrate module-by-module** thereafter (start `abstractive_writer.py`), each behind a
   characterization test + the acceptance harness, as a tracked, gated backlog.
3. **A CI grep** bans *new* `os.getenv(` outside `settings.py`, so the surface stops growing while the
   backlog drains.

Ownership: until per-key owners are assigned, the **project owner** is accountable for the model +
secret keys (P1); the executor (engineering) drains P2/P3 behind tests. No key migrates without a
green characterization test.
