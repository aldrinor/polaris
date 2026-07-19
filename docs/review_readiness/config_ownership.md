# Configuration ownership & precedence (Plan V4 1A / S1)

Closes the S1 governance gate: **100% of the 1,044 runtime config keys are classified, owned (by
category), and have a documented resolution precedence.** This is a DOC / METADATA deliverable only —
no runtime or `src/` change accompanies it.

- **Classification** (6 categories) is already established in
  [`config_governance.md`](config_governance.md) and the machine-readable inventory
  `baseline/config_keys_classified.json` (per key: read-sites, files, in-env, category, secret flag).
- **This file** adds the two missing columns for every key: **owner-role** and **precedence**, assigned
  by category/domain (not 1,044 hand-entries) so every key inherits an owner + precedence via its
  category.

## Roles (as Plan V4 defines them)
- **OWNER** = the **project owner** — *accountable*. Any change to an OWNER key requires the project
  owner's explicit sign-off before merge. These are the keys that can change *what model runs* or *how
  strict verification/faithfulness is*, i.e. the ones that can silently move the product's answers or
  its safety guarantees.
- **EXECUTOR** = **engineering** — *responsible*, operating under owner sign-off. Executor tunes these
  (thresholds, timeouts, concurrency, internal flags) behind a green characterization test; the owner
  retains sign-off on the migration but not on each numeric nudge.

## Precedence (resolution order — characterized in Phase 1B, referenced here)
Two mechanisms, both **case-sensitive** (exact `PG_*` key name; no case-folding), both reading the
**current** environment on every access:

1. **Registry-backed keys** (the 871-key `config_defaults.py` registry, read via
   `settings.resolve(key)`):
   `resolve(key)` returns `os.getenv(key, CONFIG_DEFAULTS[key])`, i.e.
   **process-env (`os.environ`) > `.env` (loaded into the process env at startup) > registry default
   literal**. Locked byte-identical to the original `os.getenv("PG_X", "<lit>")` by
   `tests/test_config_registry.py` (`resolve == os.getenv` for every key, unset and overridden).
2. **The 12 model keys** (`ModelSettings`, pydantic-settings): each field resolves via its
   **`validation_alias="PG_..."`** — same precedence (**process-env > `.env` > field default**),
   case-sensitive on the exact alias, snapshotting the environment at construction. Locked by
   `tests/test_settings_models.py`.
3. **Not-yet-registered keys** (secret-shaped tail, computed/multiline, conflicting-default) still read
   directly via `os.getenv(key, <lit>)` at their call site — **same precedence**
   (process-env > `.env` > call-site literal). The 20 conflicting-default keys are the one exception
   where the "default" is path-dependent until resolved — see
   [`config_conflicts.md`](config_conflicts.md).

**In every case the effective precedence is identical: process-env > `.env` > default.** The only
variation is *where the default lives* (registry / model field / call-site literal).

## Ownership table (category → owner-role → precedence)

Covers all 1,044 keys. Categories are from `config_keys_classified.json`; counts sum to 1,044.
A cross-cutting **faithfulness/verification override** row promotes any key whose name matches
`FAITH | NLI | ENTAIL | VERIF | CONTRADICT | SENTINEL | JUDGE` to **OWNER** even if its base category is
a tuning/flag/other key — because these keys move the frozen-faithfulness / verification guarantee. The
category rows below show counts **after** that override is applied, so every key appears exactly once.

| Category | Example keys | Count | Owner-role | Precedence | Notes |
|---|---|---:|---|---|---|
| **model-selection** | `PG_JUDGE_MODEL`, `PG_SENTINEL_MODEL`, `PG_EMBED_MODEL`, `PG_OUTLINER_AGENT_MODEL`, `PG_NLI_MODEL` | 35 | **OWNER** | 12 via `ModelSettings.validation_alias` (process-env > `.env` > field default); the rest via `resolve()`/`os.getenv` (process-env > `.env` > default). Case-sensitive. | The "one file controls every model" surface. Any model-slug/provider/role change = owner sign-off. |
| **secret** | `OPENROUTER_API_KEY`, `EXA_API_KEY`, `OPEN_PAGERANK_API_KEY`, `PG_CREDIBILITY_JUDGE_API_KEY` | 97 | **OWNER** | process-env > `.env` > default (empty-string defaults; `SecretStr` migration is a tracked, behavior-changing tail pass). Case-sensitive. | Credentials / `*_KEY` / `*_TOKEN`. Never plaintext in the report; owner-controlled. |
| **faithfulness/verification (override)** | `PG_FAITHFULNESS_NLI_THRESHOLD`, `PG_MIN_FAITHFULNESS`, `PG_STRICT_VERIFICATION`, `PG_ENTAILMENT_MODEL`, `PG_VERIFY_RELEVANCE_GATE` | 83 | **OWNER** | process-env > `.env` > default (registry `resolve()` or call-site literal). Case-sensitive. | Keys matching the faith/verify pattern **promoted out of** tuning-threshold (26), internal-flag (3), internal-other (54). These gate the frozen-faithfulness invariant — owner-accountable. `PG_FAITHFULNESS_NLI_THRESHOLD` is a known conflicting-default (0.65 vs 0.75). |
| **tuning-threshold** | `PG_ACADEMIC_GATE_THRESHOLD`, `PG_ACCESS_DENIAL_MAX_CHARS`, `PG_ACADEMIC_QUERY_CAP`, `PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS` | 346 | **EXECUTOR** (owner sign-off on migration) | process-env > `.env` > registry default via `resolve()` (or call-site literal for tail). Case-sensitive. | `MAX_/_CAP/_TIMEOUT/THRESHOLD/_K` numerics. 372 minus 26 promoted to the faith override. Engineering tunes behind char tests. |
| **internal-flag** | `PG_ACADEMIC_ONLY_GATE`, `PG_ADAPTIVE_SEARCH_ENABLED`, `PG_AGENTIC_SEARCH_ENABLED`, `PG_AMPLIFICATION_ENABLED` | 68 | **EXECUTOR** (owner sign-off on migration) | process-env > `.env` > default via `resolve()`/`os.getenv`. Case-sensitive. | `_ENABLED/_MODE/_GATE` booleans. 71 minus 3 promoted to the faith override. |
| **internal-other** | `PG_A1_BASKET_FALLBACK`, `PG_ABSTRACTIVE_WRITER`, `PG_ACADEMIC_CONCURRENCY`, `PG_ADAPTIVE_SCAFFOLD` | 380 | **EXECUTOR** (owner sign-off on migration) | process-env > `.env` > default via `resolve()`/`os.getenv`. Case-sensitive. | Long tail of `PG_*` control flags. 434 minus 54 promoted to the faith override. |
| **external/system** | `ANTIWORD_CMD`, `CHROMA_PERSIST_DIR`, `FFMPEG_PATH`, `OPENROUTER_BASE_URL`, `HOME`/`PATH` | 35 | **EXECUTOR** (owner sign-off on migration) | process-env > `.env` > default (kept as-is / thin wrapper; non-`PG_` convention vars left in their namespace). Case-sensitive. | Standard env + provider base URLs + tool paths. Not our namespace to rename. |
| **TOTAL** | | **1,044** | | | 215 OWNER (35 model + 97 secret + 83 faith override) / 829 EXECUTOR. |

### Owner-role rollup
- **OWNER (project owner, accountable): 215 keys** — 35 model-selection + 97 secret + 83
  faithfulness/verification-override.
- **EXECUTOR (engineering, owner sign-off): 829 keys** — 346 tuning-threshold + 68 internal-flag +
  380 internal-other + 35 external/system.
- **1,044 / 1,044 keys** have exactly one owner-role and a documented precedence.

## Domain-prefix view (cross-check)
| Domain prefix | Count | Owner-role (default) |
|---|---:|---|
| `PG_*` | 1,005 | per category above (model/secret/faith → OWNER; else EXECUTOR) |
| `OPENROUTER_*` | 7 | OWNER for `*_API_KEY` (secret); EXECUTOR for base-url/cost/flag settings |
| other / external (`OPENAI_*`, `HF_*`, tool paths, `HOME`, …) | 32 | EXECUTOR (external/system), OWNER only if secret-shaped |

## Gate status — MET
- **Classified:** 1,044 / 1,044 (6 categories, from `config_keys_classified.json`). ✅
- **Owned:** 1,044 / 1,044 assigned an owner-role by category/domain (215 OWNER / 829 EXECUTOR). ✅
- **Precedence documented:** every category maps to the resolution order **process-env > `.env` >
  default**, case-sensitive; the 12 model keys via `ModelSettings.validation_alias`; characterized and
  test-locked in Phase 1B (`test_config_registry.py`, `test_settings_models.py`). ✅

**S1 governance gate: MET.** No runtime / `src/` change — documentation and metadata only.
