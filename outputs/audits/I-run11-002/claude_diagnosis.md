# I-run11-002 (#1044) — §-1.1 line-by-line root-cause diagnosis

**Symptom (run 11, drb_72, `outputs/q1_run11/`):** the 4-role eval completed all 70 claims;
EVERY final verdict is `UNSUPPORTED` -> `coverage_fraction 0.0` -> release held
(`held_reasons = ['d8_unsupported_residual_below_coverage', 'd8_pending_rewrite']`),
`fabricated_occurrence_latched=False`.

**Diagnosis mode:** read-only. No code changed. One claim traced end-to-end from raw role
outputs to the final `UNSUPPORTED`, then generalized across all 70 with the run artifact.

---

## 0. Evidence base (what the run artifacts actually contain)

From `outputs/q1_run11/four_role_role_calls.jsonl` (247 records, 70 claims), counted
programmatically:

- records-per-claim: **54 claims with 4 records** (full Mirror->Sentinel->Judge), **15 with 2
  records** + **1 with 1 record** = **16 short-circuited at Mirror**.
- slug distribution: `z-ai/glm-5.1` 139 (Mirror, 2 passes/claim), `ibm-granite/granite-4.1-8b`
  54 (Sentinel), `qwen/qwen3.6-35b-a3b` 54 (Judge).
- across the **54 full-path** claims:
  - **Sentinel raw_text: `<score>yes</score>` on ALL 54** (uniform).
  - **Judge raw_text: `VERIFIED` on 51, `UNSUPPORTED` on 3.**

From `outputs/q1_run11/manifest.json`:
- `four_role_evaluation.release_allowed = False`, `coverage_fraction = 0.0`, all 70
  `final_verdicts = UNSUPPORTED`.
- `evaluator_gate_advisory.release_allowed = True`, `reasons` includes `judge_parse_failed`.
  **The advisory legacy gate did NOT hold the release.**

### Traced claim: `00-000-679379fc` (autor `polarization_evidence`)

Its 4 raw records (verbatim):

1. Mirror pass-1 (`z-ai/glm-5.1`):
   `Polarization evidence: <co>one noticeable change has been a "polarization" of the labor
   market, in which wage gains went disproportionately to those at the top and at the bottom of
   the income and skill distribution, not to those in the middle</co:autor_why_still_jobs>.`
   -> a valid `<co>...</co:autor_why_still_jobs>` span; `autor_why_still_jobs` is in the
   evidence pool. **Grounding SUCCEEDS.**
2. Mirror pass-2 (`z-ai/glm-5.1`): `{"classification": "Polarization"}` -> JSON with a
   `classification` key. **Parse SUCCEEDS.**
3. Sentinel (`ibm-granite/granite-4.1-8b`): `<score>yes</score>`.
4. Judge (`qwen/qwen3.6-35b-a3b`): `VERIFIED`.

The `<co>` span is a **verbatim quote of the evidence document** — this claim is genuinely
grounded. The Judge returned `VERIFIED`. Yet the final verdict is `UNSUPPORTED`. The trace
below shows exactly why.

---

## 1. root_cause

**This is LAYERED, not one bug. Three distinct populations.**

### L1 — DOMINANT (51 of 70): Sentinel is mis-served, then composition correctly fail-closes.

**Mechanism, pinned line-by-line:**

1. `sentinel_contract.py:72-74` defines the strict score envelope; `:51-53` maps the token:
   `_SCORE_TOKEN_YES = "yes"` -> `SentinelVerdict.UNGROUNDED`. So `<score>yes</score>`
   `fullmatch`es cleanly -> `SentinelResult(verdict=UNGROUNDED, parsed_ok=True)`
   (`parse_sentinel_score`, `sentinel_contract.py:94-105`). **This parse is correct per the
   contract.**
2. `judge_contract.py:42-59` `parse_judge_verdict`: `token = raw.strip()`; `"VERIFIED"` is in
   `JUDGE_CHOICES` (derived from the canonical `Verdict` Literal, `:24`) -> returns `VERIFIED`.
   **Bare `VERIFIED` parses cleanly. No exception.**
3. `role_pipeline.py:_compose_final_verdict` (`:217-255`), step (2), `:245-251`:
   ```python
   sentinel_unsafe = sentinel_result is None or (
       sentinel_result.verdict == SentinelVerdict.UNGROUNDED
       or not sentinel_result.parsed_ok
   )
   if sentinel_unsafe:
       if raw_judge_verdict in _SENTINEL_OVERRIDE_DOWNGRADE_FROM:  # (VERIFIED, PARTIAL)
           return _VERDICT_UNSUPPORTED
   ```
   Sentinel == `UNGROUNDED` -> `sentinel_unsafe = True` -> Judge `VERIFIED` is in the
   downgrade set -> **return `UNSUPPORTED`.**

**So 51 all-roles-"approve" claims compose to `UNSUPPORTED` at `role_pipeline.py:250-251`.**

**But `role_pipeline.py:250` is NOT the bug — it is the fail-closed SAFETY property working as
designed.** The real defect is UPSTREAM: the Sentinel groundedness signal carries **zero
information** in this run. Proof, from the run data itself:
- All 54 Sentinel calls returned `<score>yes</score>` (uniform -> UNGROUNDED for every claim).
- The traced autor claim is a **verbatim quote of its evidence** (genuinely grounded), yet
  Sentinel said `yes` -> UNGROUNDED. A correct groundedness checker would return GROUNDED here.

**Why the Sentinel signal is non-discriminating — model substitution (the actual root cause):**
The benchmark route serves the Sentinel role with the **general `ibm-granite/granite-4.1-8b`**,
NOT the task-trained **granite-Guardian** the `yes=risk=UNGROUNDED` polarity was verified
against. This is explicit and intentional in the wiring:
- `openrouter_role_transport.py:14-19, 128-135, 151-155` (`_BENCHMARK_LINEUP_DEFAULT_SLUG`):
  Sentinel benchmark slug = `ibm-granite/granite-4.1-8b`; the docstring states the lock pins the
  self-host `granite-guardian-4.1-8b` (NOT on OpenRouter) and "only the GENERAL
  `ibm-granite/granite-4.1-8b` is, not the Guardian variant."
- `openrouter_role_transport.py:308` `_ROLE_REASONING_DEFAULT` sets `sentinel: False` (no
  reasoning), and `:452` gives it a 256-token budget — i.e. it is treated as a classifier, but
  the served model is a general instruct model with no Guardian groundedness training.
- The Sentinel request DOES send the `<guardian>groundedness</guardian>` block
  (`sentinel_adapter.py:39-44`) + the rendered evidence (`openai_compatible_transport.py`
  `_normalize_messages`/`_render_documents_message`). The general granite model returns a
  uniform `<score>yes</score>` regardless of grounding — it does not implement the Guardian
  yes=risk contract.

**Polarity ambiguity (stated honestly, not resolved — both indict Sentinel):** uniform-`yes`
cannot distinguish (a) the model literally following the inverted instruction ("respond yes if
the claim is NOT grounded") and judging everything ungrounded, from (b) the model ignoring the
counterintuitive inversion, answering the natural "is it grounded? yes," which the contract then
inverts to UNGROUNDED. Both fit the data; both mean the as-wired benchmark Sentinel is broken
for grounded claims. The fix must be robust to both (see §3).

**Confirmation that the contract + composition are correct (not the bug):** the unit-test
fixtures feed `<score>no</score>` through the SAME parser + composition and produce GROUNDED ->
VERIFIED (e.g. `tests/roles/test_role_pipeline.py:44`,
`tests/roles/test_openai_compatible_transport.py:237`, prior mocked run artifacts under
`codex_008budget_tmp/test_grounded_verified_claim_r0/`). The pipeline discriminates correctly
under a discriminating Sentinel; it is uniform-`yes` ONLY on the live general-granite run. This
pins root cause to the model substitution, not the composition code.

### L2 — SECONDARY (16 of 70): Mirror pass-2 parse/prompt brittleness -> fail-closed UNSUPPORTED.

For these 16, **Mirror pass-1 grounding SUCCEEDED** (a valid `<co>` span exists) — only the
pass-2 classification JSON failed. Classified the 16 pass-2 bodies programmatically:
- 5x code-fence-wrapped JSON (` ```json {...} ` ) -> `json.loads(raw_text)` raises ->
  `MirrorParseError` (`mirror_adapter.py:193-198`).
- 1x non-JSON, 1x garbage tokens -> `MirrorParseError`.
- the rest: valid JSON but the **top-level `classification` key is absent** —
  `{"answer": ...}`, `{"category": ...}`, `{"label","confidence","rationale"}`,
  `{"domain","subdomain","topic",...}`, a nested `classification` object, `{}` ->
  `MirrorParseError` (`mirror_adapter.py:199-203`).

`run_claim_pipeline` (`role_pipeline.py:301-307`) catches `MirrorParseError` (with
`MirrorCitationError`/`MirrorBindingError`) -> `mirror_failed_closed = True` ->
`_compose_final_verdict` step (1) (`:236-238`) -> **`UNSUPPORTED`, Sentinel + Judge never run**
(hence 2 records, not 4). This is the documented `#1028` fail-closed-per-claim path — also
correct fail-closed behavior, but it is firing on **recoverable** formatting noise from a
reasoning-first model (GLM-5.1) that grounded the claim fine in pass-1.

### L3 — CORRECT (3 of 70): Judge genuinely returned `UNSUPPORTED`.

3 full-path claims had Judge `UNSUPPORTED`. With Sentinel UNGROUNDED, step (2)'s preserve
branch (`role_pipeline.py:252`) keeps `UNSUPPORTED`. Even with a fixed Sentinel, step (3)
(`:254-255`) would return the Judge's `UNSUPPORTED`. **Not a bug — correct.**

### Coverage -> held chain (correct consequence, NOT an independent bug).

`sweep_integration.py:534-535`: `internal_ledger.covered_element_ids` is credited **only when
`result.final_verdict == "VERIFIED"`**. Zero VERIFIED finals -> numerator empty ->
`CoverageLedger.fraction()` (`release_policy.py:120-124`) = `0 / required` = **0.0**.
`apply_d8_release_policy` (`release_policy.py:241-242`) appends
`d8_unsupported_residual_below_coverage` because `0.0 < coverage_threshold`; first-pass
`needs_rewrite` for the material UNSUPPORTED rows (`:213-217`) adds `d8_pending_rewrite`
(`:296-297`). So coverage 0.0 + both held_reasons are the **correct downstream consequence** of
70 UNSUPPORTED finals, exactly matching the manifest. Fix the verdicts upstream and this chain
clears itself; it is not separately defective.

---

## 2. ONE bug or layered?

**LAYERED.**
- **L1 (51, dominant):** Sentinel role mis-served — benchmark routes the groundedness check to
  the GENERAL `ibm-granite/granite-4.1-8b`, not granite-Guardian; it emits a uniform,
  non-discriminating `<score>yes</score>` -> UNGROUNDED on every claim, including verbatim-quoted
  (genuinely grounded) ones. Composition then correctly fail-closes VERIFIED -> UNSUPPORTED.
- **L2 (16):** Mirror pass-2 JSON parse + prompt brittleness — code-fences / wrong schema keys
  from a reasoning-first model trip `MirrorParseError` even though pass-1 grounding succeeded.
- **L3 (3):** correct (genuine Judge UNSUPPORTED).
- **Coverage 0.0 / held:** correct consequence of the above, not an independent bug.

**Judge-parse hypothesis: REFUTED.** The task framing pushed "does the Judge parser accept bare
`VERIFIED`?" — it does. `parse_judge_verdict` (`judge_contract.py:52-59`) exact-matches
`raw.strip()` against `JUDGE_CHOICES`; `"VERIFIED"` is a member -> returns `VERIFIED` with no
exception. The 4-role Judge never raised `JudgeEnumError` in this run; `judge_result` was never
None on the full path. The `judge_parse_failed` reason comes from a **different, advisory,
LEGACY component**: `evaluator/evaluator_gate.py:155-160`, which inspects a structured
`judge_result` object with `.parse_ok` / `.verdicts` attributes (the R5-era evaluator), NOT the
4-role `judge_adapter`'s bare-string verdict. The manifest confirms
`evaluator_gate_advisory.release_allowed = True` — that gate is advisory metadata and did NOT
hold the release. The binding decision is `four_role_evaluation` (D8), driven entirely by the
composed verdicts above. **`judge_parse_failed` is a red herring for this symptom.**

---

## 3. the_fix (minimal correct changes; diagnosis-only recommendation)

**DO NOT touch `_compose_final_verdict`.** Downgrading VERIFIED -> UNSUPPORTED when the
groundedness checker says UNGROUNDED IS the fail-closed safety property (§-1.1, clinically
lethal to weaken). Any change that makes composition ignore Sentinel UNGROUNDED is a
false-accept regression. The bug is upstream of composition, in the Sentinel signal and the
Mirror pass-2 parse.

### L1 fix (dominant — make the Sentinel signal discriminating). Primary:
The benchmark Sentinel must emit a signal that actually distinguishes grounded from ungrounded.
Two acceptable forms (LAW VI env-gated, in `openrouter_role_transport.py` lineup +
`sentinel_adapter.py`):
1. **Route Sentinel to a real groundedness/NLI classifier** (the actual granite-Guardian when
   reachable, or an equivalent faithfulness model available on the benchmark route), OR
2. **If the general granite stays, replace the inverted-instruction guardian prompt**
   (`sentinel_adapter.py:_GUARDIAN_BLOCK`, the "respond yes if NOT grounded" inversion) with a
   **direct, un-inverted question** ("Is the claim fully supported by the documents? Answer
   grounded/ungrounded"), and **empirically pin the polarity against fixtures** (grounded and
   ungrounded controls) BEFORE trusting it. The contract's `yes=UNGROUNDED` mapping must only be
   kept if the served model is verified to honor it.

Composition stays byte-for-byte unchanged. The fix is "give the gate a real groundedness
detector," not "make the gate trust a broken one."

### L2 fix (16 — harden Mirror pass-2 parse + tighten the pass-2 prompt). Both, honestly:
- **Parser hardening (`mirror_adapter._parse_pass2`):** strip a leading/trailing
  ```` ```json ```` / ```` ``` ```` code fence before `json.loads`, and accept a **nested
  `classification` object** (not only a top-level string) — recovers the 5 fence cases + the
  nested-object case **while still raising `MirrorParseError` on a genuinely-missing
  `classification` and on non-JSON/garbage** (do NOT relax the missing-key guard — that is the
  fail-closed property).
- **Prompt tightening (`mirror_adapter.build_mirror_pass2_request`):** the current prompt
  ("Classify the bound pass-1 artifact and return JSON.") is too vague — the model answered
  `{"answer":...}` / `{"label":...}` / `{"category":...}` (a different schema). Specify the
  exact required key (`classification`, string) and forbid code fences. **Honest scope:**
  parser-hardening alone does NOT fix the wrong-schema cases; the prompt must be tightened too.
- Note: pass-1 grounding already SUCCEEDED for all 16, so this is purely recovering the label
  step; it does not touch the grounding-integrity guard.

### L3 / coverage: no change. Both are correct; they clear once L1+L2 land.

---

## 4. false_accept_guard (clinical-safety critical — how the fix keeps genuine UNSUPPORTED failing closed)

- **Composition untouched:** the `UNGROUNDED -> downgrade VERIFIED/PARTIAL -> UNSUPPORTED` rule
  (`role_pipeline.py:245-251`) and the "never upgrade FABRICATED/UNREACHABLE/UNSUPPORTED"
  preserve branch (`:252`) remain exactly as-is. A genuinely-ungrounded claim whose (fixed)
  Sentinel correctly returns UNGROUNDED STILL composes to UNSUPPORTED. The fix makes the Sentinel
  signal TRUE, not permissive — it does not add any path that turns UNGROUNDED into VERIFIED.
- **L1 fix gives MORE information, not a looser gate:** today Sentinel says UNGROUNDED for
  everything (over-blocking, zero discrimination). A working groundedness detector will say
  GROUNDED for genuinely-grounded claims AND UNGROUNDED for genuinely-ungrounded ones — the
  latter still fail closed. Polarity must be empirically pinned on both a grounded and an
  ungrounded control before the contract's `yes=UNGROUNDED` mapping is trusted, precisely so the
  fix cannot silently flip everything to pass.
- **L2 fix preserves Mirror fail-closed:** the missing-`classification` and non-JSON branches of
  `_parse_pass2` still raise `MirrorParseError` -> UNSUPPORTED. Only deterministic, lossless
  reformatting (fence strip, nested-object read) is recovered — never a fabricated classification.
- **Mirror grounding guard untouched:** `MirrorCitationError` (no bound `<co>` span) ->
  UNSUPPORTED (`mirror_adapter.py:247-253`, `role_pipeline.py:236-238`) is unchanged; a claim
  with no grounded citation can still never reach VERIFIED.

---

## 5. smoke_plan (exact tests proving the fix — positives AND the fail-closed negatives)

Run against the per-claim pipeline with an injected transport (no spend), then a single live
polarity probe for fix-validation. Negatives are mandatory — they prove the fix did not just
flip everything to pass.

1. **Grounded -> VERIFIED (positive):** Mirror valid `<co>` span + parseable pass-2
   `{"classification": "..."}` + (fixed) Sentinel `GROUNDED` (`<score>no</score>` under the
   current contract, or the un-inverted equivalent) + Judge `VERIFIED` -> `final_verdict ==
   VERIFIED`; ledger credits the element; coverage > 0.
2. **Genuinely-ungrounded -> STILL UNSUPPORTED (THE guard test):** same Mirror/Judge but
   Sentinel `UNGROUNDED` -> `final_verdict == UNSUPPORTED`. Proves composition still fail-closes
   and the fix did not blanket-pass.
3. **Judge NOT-VERIFIED, Sentinel grounded -> preserved:** Sentinel `GROUNDED` + Judge
   `UNSUPPORTED` -> `final_verdict == UNSUPPORTED` (step (3) returns the Judge verdict).
4. **Mirror no-valid-citation -> UNSUPPORTED:** pass-1 emits no bound `<co>` span ->
   `MirrorCitationError` -> short-circuit -> `UNSUPPORTED` (Sentinel/Judge never run).
5. **Mirror pass-2 genuine garbage / non-JSON -> STILL MirrorParseError -> UNSUPPORTED:** proves
   L2 hardening did NOT over-recover (the missing-`classification` / non-JSON fail-closed path
   survives).
6. **L2 recovery positive:** pass-2 body ```` ```json {"classification":"X"} ``` ```` and a
   nested `{"classification": {...}}` -> parse SUCCEEDS (no `MirrorParseError`); claim proceeds
   to Sentinel/Judge.
7. **Live polarity probe (fix-validation, not a blocker):** one grounded control + one ungrounded
   control through the live (fixed) Sentinel route; assert the grounded control returns GROUNDED
   and the ungrounded control returns UNGROUNDED — pinning the served model's polarity before
   trusting the mapping.

Existing fixtures already cover the mock-transport positive/negative composition
(`tests/roles/test_role_pipeline.py`, `tests/roles/test_openai_compatible_transport.py`) — the
new tests add the L2 parse cases + the live polarity probe.

---

## Confidence

**High.** The trace is grounded entirely in the run artifacts (verbatim role outputs, per-claim
record counts, manifest fields) cross-checked against the source line-by-line. The discriminating
fact — a verbatim-grounded claim getting Sentinel `<score>yes</score>` -> UNGROUNDED, uniform
across all 54 full-path claims, while the SAME parser+composition return GROUNDED->VERIFIED under
`<score>no</score>` fixtures — pins L1 to the live Sentinel model substitution, not the
composition code. L2's 16 short-circuits are confirmed by re-parsing the pass-2 bodies. The
`judge_parse_failed` refutation is confirmed by the manifest (advisory gate
`release_allowed=True`) + the bare-`VERIFIED` exact-match parser. The one acknowledged residual
uncertainty (instruction-following vs instruction-ignoring polarity) does not change the verdict
or the fix — both indict the Sentinel and both are covered by the empirical polarity-pin step.
