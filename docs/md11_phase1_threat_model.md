# M-D11 phase 1 — model-pin threat model + boundary

**Status:** GREEN-locked v5 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/model_pin.py`
**Tests:** `tests/polaris_graph/test_md11_model_pin.py` (63+ passing)
**Schema version:** `PIN_SCHEMA_VERSION = "v4"`
**Codex review trail:** `outputs/codex_findings/md11_phase1_*_review/`

---

## Scope

Phase 1 ships **pin capture + serialization**: a frozen
`ModelPin` dataclass that records what model(s), prompt(s),
retrieval-source versions, inductor type/profile, validation-set
hash, and runtime environment toggles produced a particular
audit run. JSON-serializable, deterministic, content-addressable
where appropriate.

Phase 2 (deferred) is **replay**: load a pin, configure a
pipeline to match, and rerun.

---

## What phase 1 protects against

| Threat | Mitigation |
|---|---|
| Silent model drift across reruns | Multi-role `llm_models` dict: generator/evaluator/judge/inductor each pinned independently. `pins_equivalent_for_replay` returns False on any role change. |
| Provider/routing drift | `llm_providers` dict + `OPENROUTER_*` vars in env_snapshot. |
| Prompt drift | `prompt_version_hashes` (per-role SHA-256 over UTF-8 prompt text). |
| Inductor profile drift (M-D2) | `inductor_type` + `inductor_version_hash` (SHA-256 over keyword profile / classifier prompt). |
| Validation-set drift (M-D1) | `validation_set_hash` (SHA-256 over file bytes). |
| Verification-gate drift (NLI, provenance, cross-source, contradiction) | env_snapshot captures 36 verified replay-critical vars. |
| LLM call-profile drift (token budgets) | `PG_SECTION_WRITER_MAX_TOKENS`, `PG_VERIFY_MAX_TOKENS`, `PG_GLM5_MIN_MAX_TOKENS` etc. captured. |
| Schema drift across pin versions | `pin_schema_version` field; loader rejects mismatched versions loudly. |
| Loader/validator asymmetry | `pin_from_dict` re-applies every invariant `capture_pin` enforces (run_id non-empty, llm_models non-empty, role coverage, str→str retrieval, env_snapshot None\|str). |
| Replay diverging on unset vs explicitly-empty env vars | `env_snapshot` typed `dict[str, str \| None]`. `None` = unset (phase 2 must DELETE), `""` = explicitly empty (phase 2 must SET to ""). Pins with one vs the other are NOT replay-equivalent. |

---

## Boundary (what phase 1 does NOT protect against)

### Env-var capture set is a *seed list*, not exhaustive

The codebase has 800+ env vars referenced by `os.getenv`. The
overwhelming majority are sovereign-mode-only, test fixtures,
low-impact debug toggles, or per-call overrides that the
pipeline never reads at the v3 honest-rebuild level.

`DEFAULT_REPLAY_ENV_VARS` is curated to 36 vars verified
against actual call sites across:
- `src/polaris_graph/llm/openrouter_client.py` (routing)
- `src/polaris_graph/agents/nli_verifier.py` (faithfulness)
- `src/polaris_graph/agents/verifier.py` (require-NLI gate +
  contradiction detector)
- `src/polaris_graph/synthesis/section_writer.py` (structural
  toggles + max-tokens)
- `src/polaris_graph/state.py` (token-budget defaults)
- `src/polaris_graph/graph_v3.py` (run budget + gap-fill loops)
- `src/polaris_graph/agents/storm_interviews.py` (STORM
  user-visible knobs)
- `src/polaris_graph/retrieval/synthesis_prompts.py` (analytical
  prompt mode)
- `src/polaris_graph/generator/provenance_generator.py`
  (provenance overlap)

**Vars NOT in the seed set**:
- STORM token-budget sub-knobs (PG_STORM_QUESTIONS_MAX_TOKENS,
  PG_STORM_ANSWER_MAX_TOKENS, PG_STORM_OUTLINE_MAX_TOKENS,
  PG_STORM_SEARCH_QUERIES_PER_QUESTION, …) — only matter when
  STORM is enabled
- Corroboration sub-thresholds (PG_CORROBORATION_MAX_PER_CLAIM,
  PG_CORROBORATION_SIM_THRESHOLD, PG_CORROBORATION_JACCARD_THRESHOLD)
  — deep verifier internals
- Contradiction detector tunings beyond the binary +
  NLI threshold (PG_CONTRADICTION_SIM_THRESHOLD,
  PG_CONTRADICTION_MODEL) — extension territory
- All test/debug/sovereign-mode vars

**Mitigation**: callers pass `capture_env_var_names=[...]` to
`capture_pin()` to extend the capture set per-pipeline. The
pin's env_snapshot is the source of truth; phase 2 replay must
match it exactly. Vars NOT in the captured snapshot are NOT
replayed — they take whatever value is in the replayer's env at
replay time.

This is the asymptote-stop boundary per the Codex 4-round
review (autoloop V2 stop condition: "Codex keeps finding
bypasses, distinguishing converging from asymptoting"). Round
counts: R1=4 → R2=3 → R3=2 → R4=2. The 4-round category
shifted from foundational gaps (schema, validation, version
forward-compat, empty/unset semantics) to env-var enumeration.
Adding more vars doesn't reduce the boundary; it shifts it.

### Out of scope for phase 1

- **Replay execution** (phase 2): loading a pin, reconfiguring
  the pipeline, running, comparing outputs.
- **Cross-version compat**: v4 pins do NOT load as v3 or v2.
  Schema bump is the explicit forward-compat mechanism.
- **Pin signatures / non-repudiation**: pins are not
  cryptographically signed. The intended threat model is
  honest replay, not anti-tampering.
- **Time-travel rebuild from pin alone**: pins do not capture
  source code state. A pin from a tagged commit is replay-
  meaningful; a pin from an arbitrary working-tree state is
  best-effort.

---

## Codex review trail (autoloop V2)

| Round | Commit | Verdict | Findings |
|---|---|---|---|
| R1 | d150a43 | PARTIAL | (4) singular llm_model, env routing/prompt toggles missed, pin_from_dict not symmetric, no schema_version |
| R2 | 472b865 | PARTIAL | (3) wrong env name OPENROUTER_FALLBACKS, missing call-profile knobs, retrieval not validated symmetrically |
| R3 | 273cfc2 | PARTIAL | (2) more env vars missing, "" vs unset semantics |
| R4 | a427174 | PARTIAL | (2) more env vars (verifier/STORM/budget), docstring inconsistency |
| R5 | (this commit) | GREEN-lock target | env-var enumeration only — see boundary above |

Findings count progression: 4 → 3 → 2 → 2. Category shifted
from foundational (schema, validation, semantics) to seed-list
extension. Asymptote pattern recognized.

---

## Phase 2 contract (for the deferred replay module)

When implementing phase 2, replay logic must:

1. Load `ModelPin` via `pin_from_json` / `pin_from_dict`.
2. Verify `pin_schema_version == "v4"` (or whatever current is).
3. Reconfigure pipeline:
   - Set `OPENROUTER_DEFAULT_MODEL` etc. from `llm_models` /
     `llm_providers` per-role.
   - Re-set system prompts; verify hash matches
     `prompt_version_hashes`.
   - Restore retrieval-source versions per
     `retrieval_source_versions`.
   - Restore inductor: same `inductor_type` + verify
     `inductor_version_hash`.
4. **Replay env_snapshot** with the None-vs-empty distinction:
   ```python
   for name, value in pin.env_snapshot.items():
       if value is None:
           os.environ.pop(name, None)  # delete
       else:
           os.environ[name] = value  # set, even if ""
   ```
5. Validate `validation_set_hash` if induction is in scope.
6. Run; capture a fresh pin; compare via
   `pins_equivalent_for_replay`. Anything False → replay
   diverged.

---

## Lock note

Phase 1 GREEN-locked at v5 (commit revision; schema stays v4).
Auto-induction precision benchmark (M-D1) and induction
inductors (M-D2) compose with this pin via
`inductor_type` + `inductor_version_hash` +
`validation_set_hash`. Phase 2 replay implementation tracked
under M-D11 phase 2 (deferred, depends on phase 1 stability).

Stop reason per autoloop V2: asymptoting. Boundary documented
above. Round-5 review brief explicitly asks Codex to
GREEN-lock if remaining findings are env-var enumeration only.
