# Codex Q6 — typed accessors for duplicated computed-defaults

**Status:** DONE (Phase ACC). 3 keys warranted a typed accessor; each migrated
byte-identically. Verify green; parity proven programmatically.

## The question (codex Q6)
The long-tail config migration (Phase 1C) moved 832 `os.getenv("PG_X", "<lit>")`
sites onto the central `resolve()` registry. `resolve()` deliberately owns only
keys whose default is a **single-line string literal** — one default per key. Codex
Q6 asked: for the remaining keys whose default is *computed* (not a plain string
literal) **and** duplicated across call sites, do any warrant a typed per-domain
accessor that owns the computed default once?

## Selection criterion
A key warrants an accessor iff BOTH hold:
1. Its default is **computed** — an arithmetic expression under a coercion
   (`int(...)`), or a module-local **named constant** (not a bare string literal
   `resolve()` could hold); and
2. That computed default is **duplicated** — the same value/const is read at 2+
   call sites (drift risk: one copy can silently diverge from the other).

A computed default read at a *single* site, or a named const defined in exactly
*one* module, has a single owner and no cross-copy drift risk — it does not
warrant centralizing and was left in place.

## What was found (investigation)
- **Named-const defaults defined in >1 module** (cross-module duplication) — the
  exact drift hazard:
  - `_DEFAULT_ENTAILMENT_MODEL = "z-ai/glm-5.2"` — defined verbatim in
    `entailment_judge.py:107` **and** `semantic_conflict_detector.py:80`, each
    feeding `os.environ.get("PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL)`.
    Two NLI paths; a drift in one copy would silently split the entailment model.
  - `DEFAULT_REDIS_URL = "redis://localhost:6379/0"` — defined verbatim in
    `broker.py:22` **and** `run_events.py:24`, each feeding
    `os.environ.get("POLARIS_V6_REDIS_URL", DEFAULT_REDIS_URL)`.
  - Every other named-const default (`DEFAULT_FLOOR_HIGH`, `DEFAULT_API_KEY_PREFIX`,
    `_DEFAULT_MODE`, `_UNPAYWALL_PLACEHOLDER_EMAIL`, `_DEFAULT_SIM_MEASURE`,
    `_DEFAULT_WHITELIST`, `DEFAULT_ACCOUNTS_PATH`, `DEFAULT_EGRESS_ALLOWLIST`,
    `DEFAULT_PUBKEY_PATH`, `_ROLE_HTTP_RETRY_MAX_DEFAULT`,
    `_DEFAULT_CONFLICT_MAX_TOKENS`, `_CITATION_NLI_PURITY_DEFAULT`, …) is defined
    in exactly **one** module → single owner → not warranted.
- **Arithmetic-expression defaults under `int()`**: the only one duplicated at 2+
  sites is `int(os.getenv("PG_MAX_DOCLING_PDF_BYTES", str(5 * 1024 * 1024)))` —
  `access_bypass.py:5781` **and** `:5950`. Other `int(os.getenv(...))` reads
  either default to a plain string literal (`"40"`, `"1024"`, …) or are read at a
  single site; and the multi-site *conflicting* int defaults (`"12"`/`"2"`,
  `"0.65"`/`"0.75"`, …) are tracked separately in
  [`config_conflicts.md`](config_conflicts.md) because they need a product decision
  on the single correct default, not an accessor.

## What was done (3 accessors, `src/polaris_graph/settings.py`)
Each owns its computed default once and is **byte-identical** to the call sites it
replaces — same env key, same default value, same coercion, same `os.getenv`
precedence (a fresh read of the CURRENT environment on every call, matching the
originals):

| Accessor | Env key | Default (owned once) | Replaced call sites |
|---|---|---|---|
| `get_entailment_model()` | `PG_ENTAILMENT_MODEL` | `"z-ai/glm-5.2"` | `entailment_judge.py`, `semantic_conflict_detector.py` |
| `get_max_docling_pdf_bytes()` | `PG_MAX_DOCLING_PDF_BYTES` | `int(str(5*1024*1024))` | `access_bypass.py` (×2) |
| `get_v6_redis_url()` | `POLARIS_V6_REDIS_URL` | `"redis://localhost:6379/0"` | `broker.py`, `run_events.py` |

`get_max_docling_pdf_bytes()` preserves the inline `int()` coercion exactly,
including raising `ValueError`/`TypeError` on a non-integer override (the call
sites already wrap these reads in `try/except (TypeError, ValueError)`).

## Verification
- **Parity harness** (unset + override + bad-int cases): each accessor returns
  identical output to its original `os.getenv`/`os.environ.get` expression;
  `get_max_docling_pdf_bytes()` raises `ValueError` on a non-integer override
  exactly as the inline `int()` did.
- **Characterization tests** `tests/test_settings_models.py` +
  `tests/test_config_registry.py` — 9/9 passing.
- All touched modules (`settings`, `entailment_judge`,
  `semantic_conflict_detector`, `broker`, `run_events`, `access_bypass`) import
  cleanly.

## Not done (out of scope for Q6, tracked elsewhere)
- Single-owner computed defaults (defined in one module) — left in place; no
  duplication, no drift risk.
- Conflicting multi-site defaults — [`config_conflicts.md`](config_conflicts.md);
  need a product decision before centralizing.
- The old module-local const definitions (`_DEFAULT_ENTAILMENT_MODEL` at
  `entailment_judge.py:107` / `semantic_conflict_detector.py:80`,
  `DEFAULT_REDIS_URL` at `broker.py:22` / `run_events.py:24`) remain as
  now-unreferenced literals; each is byte-identical to the accessor default, so
  leaving them is behavior-neutral. A follow-up may delete the dead copies once
  no other reader depends on them.
