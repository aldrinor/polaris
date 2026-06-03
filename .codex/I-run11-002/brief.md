# I-run11-002 (#1044) — Codex diff review brief (L1 + L2)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (return exactly this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## HARD CONSTRAINTS (operator-locked — NOT consultable)

1. **LOCK: Sentinel = `ibm-granite/granite-4.1-8b` at the benchmark stage.** No model-family swap. The 4-role architecture (`config/architecture/polaris_runtime_lock.yaml`) locks Sentinel to the granite family. The fix is **PROMPT + PARSER only**, no slug change.
2. **SAFETY (§-1.1, clinical-lethal):** do NOT flip the existing inverted polarity mapping, do NOT weaken `role_pipeline._compose_final_verdict`. `_compose_final_verdict` is BYTE-UNCHANGED. Fail-closed-on-malformed stays UNGROUNDED. A genuinely-ungrounded claim must still map UNGROUNDED -> UNSUPPORTED.
3. **Sovereign path unchanged:** the self-hosted `granite-guardian-4.1-8b` keeps the inverted `<guardian>` prompt + the `<score>yes|no</score>` parser (`parse_sentinel_score`, yes=risk=UNGROUNDED), byte-for-byte.

## Root cause (the EVIDENCE — verify, don't rediscover)

`outputs/audits/I-run11-002/claude_diagnosis.md` + `outputs/audits/I-run11-002/l1_groundedness_probe.md`:

- Run 11 (drb_72): all 70 final verdicts UNSUPPORTED -> coverage 0.0 -> release held.
- **L1 (dominant, 51/70):** the benchmark Sentinel = the GENERAL `ibm-granite/granite-4.1-8b` (NOT the task-trained Guardian). It IGNORES the inverted Guardian instruction and answers the NATURAL question, returning a uniform `<score>yes</score>` -> the contract inverts yes->UNGROUNDED -> every genuinely-grounded claim becomes UNGROUNDED -> composition correctly fail-closes VERIFIED->UNSUPPORTED. The Sentinel signal carried ZERO information.
- **Probe proof (16 live calls, n=1/cell, flip-proof criterion):** under `noninverted_direct`, `ibm-granite/granite-4.1-8b` returned `GROUNDED` on the verbatim-grounded fixture A AND `UNGROUNDED` on the on-topic-fabricated fixture B — it DISCRIMINATES. A polarity flip is explicitly REJECTED (false-accepts B; §-1.1 lethal). The fix is a non-inverted prompt + a direct parser, keeping the inverted Guardian path for the self-host model.
- **L2 (16/70):** Mirror pass-2 classification brittleness — already fixed + committed at `515bff50` (this PR is L1; L2 is in-branch).

## The fix (L1) — what the diff does

All in `src/polaris_graph/roles/`:

### 1. `sentinel_contract.py` — ADD `parse_sentinel_grounded_token` (NON-INVERTED parser)
- New SEPARATE contract over the non-inverted prompt's output. Direct polarity: standalone `GROUNDED` -> GROUNDED; standalone `UNGROUNDED` -> UNGROUNDED.
- **Word-boundary count** (`re.compile(r"\bgrounded\b", IGNORECASE|ASCII)` and `\bungrounded\b`), NOT substring. `\bgrounded\b` does NOT fire inside "ungrounded" (no left boundary), so a clean `UNGROUNDED` yields grounded_count=0 — the substring trap cannot register as "both present".
- **FAIL CLOSED** to `(UNGROUNDED, parsed_ok=False)` on: both tokens present, neither present, a token repeated (>1), non-string. NEVER a silent GROUNDED on bad input — identical safety property to `parse_sentinel_score`.
- `re.ASCII` reuses the inverted parser's homoglyph defense.
- **`parse_sentinel_score` (the inverted Guardian parser) is BYTE-UNCHANGED** (only a docstring note added).

### 2. `sentinel_adapter.py` — mode selection (LAW VI) + non-inverted prompt
- New `_NONINVERTED_BLOCK` = the EXACT wording the probe validated (`scripts/diagnostics/sentinel_groundedness_probe.py:_NONINVERTED_BLOCK`): "Answer with EXACTLY one word: GROUNDED or UNGROUNDED."
- New `sentinel_groundedness_mode()` resolves `PG_SENTINEL_GROUNDEDNESS_MODE` ("noninverted"|"guardian"). When unset/unrecognized, **DERIVES the default from `PG_FOUR_ROLE_TRANSPORT`**: `self_host` -> `guardian`; anything else (incl. the "openrouter" default) -> `noninverted`. This is the **runtime-desync guard**: the prompt can never silently desync from the served model. Lazy env read (mirrors `role_reasoning_enabled` / `four_role_transport_mode`).
- `build_sentinel_request(..., mode=None)` selects the FINAL user instruction: `guardian` -> `<guardian>` block; `noninverted` -> the one-word block. `mode=None` -> `sentinel_groundedness_mode()`.
- `run_sentinel(..., mode=None)` selects BOTH prompt AND parser off the SAME resolved mode so they always pair: `guardian` -> `parse_sentinel_score`; `noninverted` -> `parse_sentinel_grounded_token`.
- Fail-closed `BudgetExceededError` re-raise + broad-except UNGROUNDED record are UNCHANGED.

### 3. `role_pipeline.py` — UNCHANGED
- `run_sentinel(recording, ...)` call site at `:311` is byte-unchanged (no mode arg -> resolves from env). `_compose_final_verdict` is byte-unchanged. The DEFAULT for the OpenRouter/benchmark Sentinel is `noninverted`.

## Locked-architecture substitution note

| | benchmark (OpenRouter, DEFAULT) | sovereign (self_host) |
|---|---|---|
| Sentinel model | `ibm-granite/granite-4.1-8b` (general) — LOCK kept, NO swap | `ibm-granite/granite-guardian-4.1-8b` (self-host) |
| prompt | `_NONINVERTED_BLOCK` (one word) | `_GUARDIAN_BLOCK` (inverted, byte-unchanged) |
| parser | `parse_sentinel_grounded_token` | `parse_sentinel_score` (yes=risk, byte-unchanged) |
| groundedness mode | `noninverted` (default; `PG_FOUR_ROLE_TRANSPORT=openrouter`/unset) | `guardian` (auto when `PG_FOUR_ROLE_TRANSPORT=self_host`) |

The sovereign inverted Guardian path is intact: same prompt, same parser, same yes=risk polarity — selected automatically on the self_host transport (no extra env) and explicitly via `PG_SENTINEL_GROUNDEDNESS_MODE=guardian`. The composition downgrade is untouched, so a genuinely-ungrounded claim still composes to UNSUPPORTED on BOTH paths.

## Files changed (also-checked-clean scan)

Production:
- `src/polaris_graph/roles/sentinel_contract.py` — add `parse_sentinel_grounded_token`; `parse_sentinel_score` unchanged.
- `src/polaris_graph/roles/sentinel_adapter.py` — add mode + non-inverted prompt; route prompt+parser; guardian path unchanged.
- `src/polaris_graph/roles/role_pipeline.py` — **NOT changed** (composition byte-unchanged; verified by grep).
- `scripts/dr_benchmark/gate_a_dry_run.py` — its Sentinel lethal-polarity fixture now pins `mode="guardian"` (it exercises the inverted Guardian contract; an explicit pin keeps the check faithful).
- `scripts/dr_benchmark/offline_e2e.py` — the `PerClaimFakeRoleTransport` fake now emits the mode-correct Sentinel output (`<score>no</score>` for guardian, `GROUNDED` for non-inverted).

Tests:
- `tests/roles/test_sentinel_contract.py` — new non-inverted parser tests (grounded/ungrounded/garbage/both/neither/repeated/non-string/`<score>`-tag -> fail closed; anti-inversion).
- `tests/roles/test_sentinel_adapter.py` — existing guardian tests pin `mode="guardian"`; new non-inverted adapter tests (build emits non-inverted block; grounded/ungrounded/garbage/both/`<score>`-tag/transport-error); mode-resolver tests (default noninverted; self_host->guardian; explicit override; unrecognized fallback; run_sentinel env-mode when arg None).
- `tests/roles/test_role_pipeline.py`, `test_sweep_integration.py`, `test_seam_parallel.py`, `test_four_role_budget_cap.py`, `tests/dr_benchmark/test_gate_b_seam.py` — their mock transports emit mode-correct Sentinel output (detect `<guardian>` in the request). New role_pipeline tests: non-inverted grounded->VERIFIED (run-11 fix), the §-1.1 false-accept guard (non-inverted UNGROUNDED still -> UNSUPPORTED), preserve-worse-Judge, guardian-env still composes, self_host-transport routes guardian end-to-end.

**Files I have ALSO checked and they're clean (no other Sentinel `<score>` fake / no other `run_sentinel` caller / no other guardian-block assumption):** grep of `src/**/*.py` for `run_sentinel|parse_sentinel_score|build_sentinel_request|_GUARDIAN_BLOCK` -> only `role_pipeline.py:311` (mode=None, correct) and the adapter/contract. grep of `tests/ scripts/ src/` for `score>` outside the handled files -> empty. `scripts/diagnostics/sentinel_groundedness_probe.py` imports `_GUARDIAN_BLOCK`/`build_sentinel_request` but sets `request.messages` directly, so it is unaffected.

## Tests run

`C:/Python313/python.exe -m pytest tests/roles/ tests/dr_benchmark/ -q` -> **593 passed, 0 failed.** No assertions relaxed. The §-1.1 false-accept guard is asserted explicitly (`test_noninverted_ungrounded_still_unsupported_false_accept_guard`).

## False-accept guard (how genuine UNSUPPORTED still fails closed)

- Composition untouched: UNGROUNDED/parsed_ok=False -> downgrade VERIFIED/PARTIAL -> UNSUPPORTED; FABRICATED/UNREACHABLE/UNSUPPORTED preserved. Asserted on the non-inverted path.
- The new parser gives MORE information (GROUNDED for genuinely-grounded, UNGROUNDED for genuinely-ungrounded), not a looser gate. It is NOT a polarity flip.
- Both/neither/repeated/garbage/non-string/`<score>`-tag-under-non-inverted-prompt -> fail closed to UNGROUNDED, never a silent GROUNDED.
