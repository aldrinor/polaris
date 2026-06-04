# Claude architect audit — I-run11-004 (certified MiniMax-M2 decomposition Sentinel + GLM-5.1 Mirror)

Reviewer: Claude (architect). Scope: implementation conformance to `.codex/I-run11-004/brief.md`
acceptance criteria + §-1.1 clinical-safety properties. Independent of the Codex diff gate
(`codex_diff_audit.txt`, APPROVE iter-6).

## 1. Operator-constraint conformance (HARD CONSTRAINTS)

- **Open-weight only**: generator deepseek-v4-pro, Mirror z-ai/glm-5.1, Sentinel minimax/minimax-m2,
  Judge qwen/qwen3.6-35b-a3b — all open-weight, no gpt/claude/gemini. VERIFIED against
  `config/architecture/polaris_runtime_lock.yaml` + `verify_lock.py` "Required roles" output.
- **Strongest latest frontier LLMs, NO encoders**: all four are current frontier LLMs; the prior
  encoder proposal (LettuceDetect-class) was abandoned per operator. VERIFIED — no encoder/
  small-model dependency in the role transports.
- **4 distinct lineages**: deepseek/glm/minimax/qwen — 4 distinct `_FAMILY_PREFIXES` families;
  `family_policy: all_distinct`; `check_family_segregation` raises on collision. VERIFIED.
- **Licenses**: MIT (deepseek/glm) + modified-mit (minimax — MIT + a large-product UI-attribution
  condition per HF MiniMaxAI/MiniMax-M2; non-binding for hosted-inference use) + Apache-2 (qwen) —
  all permissive open-weight. VERIFIED against the lock `license:` fields (Codex brief-gate P2).

## 2. Faithfulness-detector certification (the empirical bake-off, not a guess)

- Per the operator's "research SOTA + empirically test multiple candidates on a real labeled set"
  directive, the Sentinel was chosen by a deterministic-corruption bake-off, not by assertion.
- Test set `outputs/audits/I-run11-004/faithfulness_testset.json`: 28 grounded + 28 fabricated
  items across 5 error types (numeric swap, scope inflation, wrong attribution, negation flip,
  fabricated entity).
- MiniMax-M2 decomposition: **0 false-accepts on all 28 fabrications** (the lethal axis — a
  fabricated claim must NOT be released as GROUNDED), over-flag 0.107 on the 28 grounded.
- This is the §-1.1 ground-truth pass: a fabrication surviving the detector is the "lethal in
  clinical context" failure; the detector caught all 28.

## 3. §-1.1 clinical-safety: parser fail-closed (the lethal property)

`parse_sentinel_decomposition` (`sentinel_contract.py`) — claim-by-claim against the LOCKED mapping:

- Non-string / unparseable-JSON / non-dict / missing-verdict / off-enum verdict →
  UNGROUNDED parsed_ok=False. There is NO path that returns GROUNDED on bad input. VERIFIED by
  `test_decomposition_never_silently_grounded_anti_inversion` + `test_decomposition_non_string_fails_closed`.
- **Internally-contradictory veto** (the fail-open Codex iters 3-5 hunted): a "supported" verdict
  that simultaneously reports unsupported atoms is VETOED to UNGROUNDED. Keyed on KEY PRESENCE
  (`if "unsupported_atoms" in parsed:`) so a present bool/null/list/non-coercible coerces to
  count=None and vetoes; only an ABSENT key or a clean numeric/string zero stays GROUNDED.
  VERIFIED by the 12-case truth table (Codex re-ran it iter-6) +
  `test_decomposition_non_numeric_unsupported_atoms_vetoes_to_ungrounded` (true/false/null/[]/{}).
- Per-atom override: any atom `status=="unsupported"` or `supported is False` also vetoes.
- **Contract gate (Codex brief-gate iter-1 P1, NEW fail-open the diff gate missed):** a "supported"
  verdict that OMITS the decomposition — no non-empty `atoms` list (≥1 atom object), or no
  `unsupported_atoms` field — FAILS CLOSED to UNGROUNDED parsed_ok=False. A bare/truncated
  `{"verdict":"supported"}` did no per-atom work; trusting it would release a fabricated claim if the
  Judge verifies. Validated against the cert cache (all 25 real "supported" outputs carry both →
  0 false-drops); regression `test_decomposition_supported_without_full_contract_fails_closed`.

## 4. Composition fail-closed UNCHANGED (no silent widening)

`_compose_final_verdict` (`role_pipeline.py`) is byte-unchanged: Sentinel UNGROUNDED OR
parsed_ok=False downgrades a Judge VERIFIED/PARTIAL to UNSUPPORTED; FABRICATED/UNREACHABLE
preserved (never upgraded). VERIFIED — the new GROUNDED-returning decomposition parser did NOT
make composition blanket-pass; `test_noninverted_ungrounded_still_unsupported_false_accept_guard`
+ the decomposition equivalents hold. The detector swap changes WHICH claims the Sentinel grounds,
not the fail-closed gate downstream of it.

## 5. Timeout sizing (operator "full performance" directive)

- SEAM default 2400→7200s (the run-12 truncation root: only 50/87 claims checked before the seam
  cut). Per-call `PG_VERIFIER_LLM_TIMEOUT_SECONDS` 900s. Decomposition Sentinel reasoning ON +
  `max_tokens` floored ≥3000 (self-host `_build_body` + benchmark transport) so atomization is not
  truncated mid-JSON. VERIFIED in `openai_compatible_transport.py` + `openrouter_role_transport.py`.

## 6. Test + gate evidence

- `tests/roles tests/architecture tests/dr_benchmark` = 661 passed.
- `tests/roles/test_sentinel_contract.py` = 99 passed (incl. iter-5 regressions).
- Codex diff-gate iter-6: APPROVE, zero P0/P1/P2 (lethal fail-open closed; Codex independently ran
  the truth table + suite + re-verified composition).
- verify_lock.py: roles + code-defaults-match + canonical-pin-includes-this-file + committed = OK;
  tests_pass = CI-recorded.

## 7. Residual / flagged for operator

- **Lock + canonical_pin changed** (a canonical-pinned file): the lock SHA was reconciled to the
  LF blob (7f4be774) and committed. Per §3.1 step-0, canonical-pinned changes warrant operator
  awareness at merge — FLAGGED in the PR body.
- **Pre-existing (NOT this PR)**: the autoloop `_verify_canonical_pin` shows a HEAD/pin line-ending
  mismatch on 5 canonical files (architecture.md, task_acceptance_matrix.yaml, agent_architecture.md,
  REVIEW_BRIEF_FORMAT.md, CLAUDE.md) — none touched here; candidate follow-up Issue.
- **Self-host GPU**: Sentinel sized 8×H100 fp8 TP8 for ~229B MoE, PENDING #90 procurement; benchmark
  stage routes via OpenRouter (the demonstrated path).

## Verdict

Implementation conforms to the brief acceptance criteria and the §-1.1 clinical-safety properties.
The detector swap is empirically certified (0/28 false-accepts), the parser is fail-closed (lethal
fail-open closed + Codex-confirmed), composition is unchanged fail-closed, and the operator
open-weight/no-encoder/4-distinct constraints are met. **APPROVE for merge** (queued for operator;
Claude has no merge authority).
