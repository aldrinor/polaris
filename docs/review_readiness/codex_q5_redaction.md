# Q5 — Secret redaction (defense-in-depth), codex-gated

**Decision:** SecretStr pass **skipped**; a lighter, centralized redaction helper added
instead (codex Q5 decision option (c)).

## Why not SecretStr
The S4 threat model established POLARIS does **not** log secret values today: API keys and
tokens are read from `os.environ` and passed straight into HTTP headers or subprocess
`env=` mappings; no code path serializes, `repr`s, or logs a config object carrying a
secret, and no exception message interpolates `os.environ`. Wrapping ~50–56 secret-shaped
config keys in pydantic `SecretStr` (with `.get_secret_value()` at every read) is invasive,
touches every secret call site, is behavior-adjacent, and buys little marginal safety given
the existing hygiene.

## What was added (purely additive — no existing file edited)
- `src/polaris_graph/util/__init__.py` — new utility package.
- `src/polaris_graph/util/secret_redaction.py` — a single, well-tested place to scrub
  secrets at **diagnostic OUTPUT boundaries** (a future "dump effective settings" command, a
  config `__repr__`, an error context that echoes the environment):
  - `redact(value)` — masks `Mapping` values whose **key** looks secret
    (`SECRET_KEY_RE` over word-bounded `KEY/TOKEN/SECRET/PASSWORD/PASSWD/CREDENTIAL/AUTH/
    AUTHORIZATION`), recurses into nested mappings/list/tuple, and masks inline
    `key=value` / `"key":"value"` / `Authorization: Bearer|Basic <tok>` shapes in free text.
    Word-bounding keeps hot config keys like `max_tokens` / `PG_*_MAX_TOKENS` (plural
    TOKENS) and words like `author` **unmasked** while still masking `AUTH_TOKEN` /
    `api_key` / `Authorization`.
  - `register_known_secret(value)` — opt-in registry to scrub a literal secret value from
    free text even when the surrounding key is unknown (min length 6; import side-effect
    free; never scans `os.environ` implicitly).
  - `safe_repr(obj)` — `repr`-style rendering of a config/dataclass/pydantic/namedtuple/
    mapping with secret-looking fields masked, safe to interpolate into a log/exception.
- `tests/test_secret_redaction.py` — 11 **canary** tests: a `CANARY` sentinel planted as a
  fake key/token is asserted to never survive a mapping dump / inline string / `safe_repr`;
  byte-identity is locked on non-secret data (redaction is identity when no secret-looking
  key is present); `max_tokens` / `PG_GRADE_MAX_TOKENS` are asserted **not** falsely
  redacted; overlap/partial-leak is covered.

## Scope contract (oracle byte-identical)
Nothing imports this module on any pipeline path (grep-confirmed: zero importers outside
the test). It is dormant defense-in-depth until a future diagnostic boundary opts in. It is
**never** to be called on pipeline data, evidence text, retrieval results, or report bytes.
Both absolute rules hold: (A) faithfulness behavior frozen; (B) the RACE score cannot move,
because the module is not wired into any scored path.

## Verification
- `canary_tests_pass` — `pytest tests/test_secret_redaction.py` → **11 passed**.
- `collection_ok` — full-suite collect: 16,749 tests collected; the collection errors that
  remain are **pre-existing baseline debt** (registry import-time validation; missing
  `src.phases` / `src.polaris_graph.wiki.mesh.cli.main` modules; playwright), unchanged by
  this additive change; the new test module collects and passes.
- `oracle` — the replay oracle failure observed in this worktree is a **pre-existing
  stale-cassette / cross-phase contamination** issue: it reproduces byte-identically with
  the Q5 files moved out of the tree, so it is orthogonal to Q5, which by construction
  cannot move the RACE score.
- **codex verdict: Q5-OK** — dormant, additive, tested, cannot affect pipeline behavior or
  RACE; the staging guard excludes the contaminated oracle files.

## Acceptance — codex DECISION Q5:A (high reasoning)

Codex accepted the redaction helper + non-vacuous canary tests as sufficient defense-in-depth, and
ruled that NO synthetic wired boundary is required. Rationale + what this acceptance records:
- **No secret-value sink exists today** (S4 threat model): production logging/diagnostics do not emit
  secret values (secrets only in Authorization headers, never logged; a dedicated commit secret-scanner
  exists). So `boundaries_wired = []` accurately represents the current architecture — it is **not** a gap.
- **The helper is verified** by a canary-secret test that is non-vacuous (it masks a recognizable canary
  and would leak if redaction were disabled).
- **The helper is the required mechanism** the moment a future config-dump / diagnostic payload /
  exception formatter / structured-log field that could carry a secret is introduced — Q5 must be
  revisited and the redactor wired at that new boundary then.
- The existing secret scanner + no-leak coverage remain in place.
- **SecretStr bulk conversion is deliberately NOT done** (codex Q5): invasive, no observed exposure.
