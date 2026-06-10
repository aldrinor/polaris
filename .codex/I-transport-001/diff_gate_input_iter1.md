HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex review brief — I-transport-001 (#1191)

**Title:** bounded retry on empty-response / mid-stream-disconnect across generation + 4-role seam + NLI judge + breadth-probe (faithfulness-safe)

## 0. Pre-flight (context / scope / done-when)

- **Context:** This brief reviews the DIFF for I-transport-001. The diff adds bounded retries at FIVE transport sites so that a SINGLE transient provider fault (mid-stream `httpx.RemoteProtocolError`, structurally-empty HTTP 200 `{"choices":[]}`, single-backend HTTP-5xx in the breadth probe) is retried instead of crashing/holding a whole question. It is purely ADDITIVE: after retries exhaust, every terminal path stays exactly as fail-closed as today.
- **Diff scope:** 5 production files + 1 new hermetic test file + 1 docstring update. NO faithfulness-gate logic change, NO provider-config/env change in this diff, NO `requirements.txt` change.
- **Constraints (do NOT spend cycles on):** the provider env slate (`OPENROUTER_PROVIDER_ORDER`, `allow_fallbacks`, token caps) is FAILURE_AUDIT §4.2 run-config handled in a SEPARATE issue — NOT in this diff. Required-entity retrieval (§4.3) is a SEPARATE issue. drb_76 content-gap and drb_90 are out of scope. Do not re-litigate the §-1.1 audit verdict (it is the root-cause input, below).
- **Done-when (this round):** zero NOVEL P0, zero continuing P0, zero P1 against the acceptance criteria in §4. The single load-bearing safety property to verify: **every one of the five sites still fails CLOSED after retries exhaust** (status=error / release HELD / judge_error-sentinel-drop), and the NLI sentinel is NOT flipped ENTAILED→NEUTRAL standalone (§5).

**Independence directive:** prior-round changelog markers in the diff (e.g. "// fixed per Codex round-1") are untrustworthy meta-claims. Verify by reading the actual code, not by trusting the marker. A claimed fix that does not match the code is a P0 finding.

**Exhaustivity:** target all real findings in this single round. Do NOT truncate, do NOT drip-feed. Re-raising a previously-addressed issue in a later round is a defect; missing a P0 now is also a defect.

---

## 1. CLAIMS LEDGER — every change claim → proof file:line → status

`status` legend: **live** = the current on-disk code I verified by reading this session (the pre-change baseline the diff modifies); **staged** = the change this diff introduces (to be verified in the patch). All `live` line numbers below were read and confirmed this session against the working tree on branch `bot/I-ready-017-faithfulness`.

| # | Change claim | Proof anchor (file:line) — VERIFIED live this session | status |
|---|---|---|---|
| C1 | Generation retry except clause does NOT currently catch mid-stream disconnect | `openrouter_client.py:1975` — `except (httpx.TimeoutException, httpx.ConnectError) as exc:` (no `RemoteProtocolError`/`TransportError`) | live |
| C2 | Add `httpx.RemoteProtocolError` (≥) to that except so a mid-stream incomplete-chunked-read retries | `openrouter_client.py:1975` (edit target) | staged |
| C3 | Retry loop is `for attempt in range(MAX_RETRIES + 1)`; `MAX_RETRIES=2`, `RETRY_BACKOFF_BASE=2.0` → 3 attempts | `openrouter_client.py:1764`, `:792`, `:793` | live |
| C4 | After exhaustion the loop re-raises (`else: raise last_error`) — terminal stays fail-closed (status=error) | `openrouter_client.py:1999-2001` | live |
| C5 | Empty-choices detection sits OUTSIDE the retry loop (after for/else), raises `ValueError`, zero retries | `openrouter_client.py:2005-2024` (`choices = data.get("choices", [])`; `if not choices:` … `raise ValueError`) | live |
| C6 | Move/duplicate `not choices` detection INSIDE the `try` (after `data` assigned) and raise a RETRYABLE `RuntimeError` so existing RuntimeError retry re-issues | inside try after `:1817` (non-stream `data = resp.json()`) / after `:1784` (stream); reuse retry at `:1959` | staged |
| C7 | Existing error-key-absent retryable path must stay intact: `{"error",…,"choices":[]}` already raises retryable RuntimeError | `openrouter_client.py:1819-1836` (`if data.get("error") and not data.get("choices"): … raise RuntimeError(...)`) | live (must remain) |
| C8 | Stream branch synthesizes non-empty `choices` so `:2007` fires only for the non-stream error-key-absent `{"choices":[]}` shape | `openrouter_client.py:1784-1797` (stream builds `data={"choices":[{...}]}`) | live |
| C9 | Seam `_parse_openrouter_response` raises PLAIN `RoleTransportError` for `{"choices":[]}` — NOT caught by `except BlankVerdictError` → release HELD, no failover | `openrouter_role_transport.py:652-656` raise; not-caught at `:904` | live |
| C10 | FIX: raise `BlankVerdictError` for empty-choices (OR add `except RoleTransportError` alongside `:904`) → routed into existing effort-ladder + provider-exclusion failover | `openrouter_role_transport.py:653-656` (edit) → failover at `:902-973` | staged |
| C11 | Existing recoverable blank-content path + provider-exclusion failover is intact (the path the fix reuses) | `openrouter_role_transport.py:688-697` (BlankVerdictError raise), `:902-973` (failover: `slug_for_provider`, `ignore` list, effort step-down, `raise` only when ladder exhausted) | live (reused) |
| C12 | Seam transport retries already exist via `PG_ROLE_TRANSPORT_RETRIES` (default 2) — fix must not regress them | `openrouter_role_transport.py:795` | live (must remain) |
| C13 | NLI judge `_EntailmentJudge.judge` has NO retry; post/json/choices/bad-verdict swallowed by broad except → returns `("ENTAILED","judge_error:…")` | `entailment_judge.py:142-287`; `:206` post, `:215` json, `:266` choices, `:270-273` bad-verdict, `:281-287` broad except | live |
| C14 | Add bounded same-provider retry (new env `PG_ENTAILMENT_RETRIES` default 2, LAW VI) around post+parse+choices+bad-verdict | `entailment_judge.py:205-287` (edit) | staged |
| C15 | `BudgetExceededError` re-raise MUST stay FIRST/outside the retry | `entailment_judge.py:277-280` | live (must remain) |
| C16 | On exhaustion KEEP the existing `("ENTAILED","judge_error: …")` sentinel — do NOT flip to NEUTRAL standalone | `entailment_judge.py:287` (return) | staged-invariant |
| C17 | Consumer A (clinical strict_verify) fails CLOSED on `reason.startswith("judge_error:")` (prefix-only) in enforce | `clinical_generator/strict_verify.py:295-301` | live |
| C18 | Consumer B (provenance) sets `judge_error_flag` only when `verdict=='ENTAILED' AND reason.startswith('judge_error:')` — a NEUTRAL flip bypasses this | `provenance_generator.py:1795-1796` and `:1899-1900`; consumed → drop at `:1946-1958` (+ `judge_error=` field at `:1967`) | live |
| C19 | Update the `judge` docstring (no longer "fail-open … intentional"; now retry-then-fail-closed-at-consumer) | `entailment_judge.py:146-147` | staged |
| C20 | Breadth probe issues ONE Serper + ONE `_s2_bulk_search`; an S2 HTTP-500 → 0 S2 URLs → 29<100 floor → `GateError`, no retry | `super_heavy_preflight.py:361-372` (`_default_breadth_probe`) | live |
| C21 | FIX: wrap Serper+S2 union in a bounded retry (2-3 attempts, short backoff); re-issue S2 on 5xx/timeout before unioning; fail-closed only if floor still unmet | `super_heavy_preflight.py:361-372` (edit) | staged |
| C22 | Fail-closed terminal of the probe is `GateError` at the floor check — must remain after retries exhaust | `super_heavy_preflight.py:572-578` (and the probe-failure wrapper at `:563-571`) | live (must remain) |
| C23 | New hermetic offline test file (monkeypatch httpx; no live calls; no ambient keys) covering transient-then-success + all-blank-terminal for all three LLM seams + the probe | `tests/polaris_graph/test_transport_retry_resilience.py` — confirmed ABSENT this session (Glob: no files found) | staged (new) |

**Files I have ALSO checked and they're clean / consistent with the above:**
- `openrouter_client.py` retry-loop except ladder `:1839` (asyncio.TimeoutError), `:1855` (HTTPStatusError: 402/429/404/5xx), `:1959` (RuntimeError), `:1975` (Timeout/Connect) — verified the RemoteProtocolError add (C2) lands in the right tuple and the empty-choices RuntimeError (C6) correctly reuses the `:1959` branch.
- `openrouter_role_transport.py:902-973` failover block — verified `slug_for_provider`, `ignore`-list provider exclusion, effort-ladder step-down, and `raise` only on ladder exhaustion are the EXACT machinery C10 reuses.
- `provenance_generator.py:1512` (`judge_error_flag = False` init), `:1946-1958` (enforce→DROP, warn→log), `:1967` (`judge_error=` surfaced) — the full consumer path that the §5 DIVERGENCE protects.
- `clinical_generator/strict_verify.py:287-301` — `_entailment_mode()` gate + prefix-only `judge_error:` fail-closed.

---

## 2. Root cause (beatboth8 audit, ZERO faithfulness defects)

Source of truth: **`outputs/audits/beatboth8/FAILURE_AUDIT.md`** (full §-1.1 line-by-line forensic audit of the 5-question beatboth8 run; all quotes verbatim from per-run logs/manifests; no metadata/pattern/count proxies).

**Verdict (audit §1):** the beatboth8 run was NOT beat-both — four of five questions failed to release and the fifth was mid-retrieval — **but ZERO of the failures are faithfulness failures.** No run shipped a fabricated, mis-cited, or unsupported claim. Every failure is upstream of, or at, the release gate, and the gates behaved fail-closed exactly as designed. The four terminal failures classify as: two provider-flakiness retry GAPS (drb_72, drb_75), one genuine content-coverage HOLD (drb_76, out of scope here), one over-strict single-shot discovery gate (drb_78).

Concretely (audit §3, all CONFIRMED against code):
- **drb_72** — a mid-stream `httpx.RemoteProtocolError` on a generator SSE call matched NO `except` clause (`RemoteProtocolError` is a sibling, not a subclass, of `TimeoutException`/`ConnectError`) → propagated uncaught, ZERO retries → `status=error_unexpected`.
- **drb_75** — an OpenRouter verifier-role call returned a structurally-empty HTTP 200 (`choices:[]`, `model=None`); the no-choices case raised a PLAIN `RoleTransportError` (not the retryable `BlankVerdictError`) → not caught at `:904`, no provider failover → release HELD at coverage 0.000.
- **drb_78** — the super-heavy pre-spend breadth probe ran ONE fixed query; S2 returned HTTP 500 (0 URLs) → 29<100 floor → `GateError`, ZERO retry of the transient backend → aborted before spend.

**Faithfulness confirmation (audit §3 close):** in enforce mode the NLI sentinel ALREADY drops, so no fabrication ships; none of the gaps cause a fabricated claim to be released — all are crash/HELD (fail-closed) or over-drop. **The fix is therefore purely RESILIENCE: convert transient single-fault crashes/holds into a retry, while keeping every terminal path fail-closed.**

---

## 3. The FIVE retry sites (exact file:line + faithfulness-safety argument)

All five are ADDITIVE; the TERMINAL behavior after retries exhaust is UNCHANGED (still fail-closed). Spec verbatim from `outputs/audits/beatboth8/FAILURE_AUDIT.md` §4.1.

### Site 1 — generation mid-stream disconnect — `openrouter_client.py:1975` (FIXES drb_72)
- **Live baseline:** `:1975 except (httpx.TimeoutException, httpx.ConnectError) as exc:`. A mid-stream incomplete-chunked-read raises `httpx.RemoteProtocolError`, a sibling (not subclass) of those two → matches no clause → uncaught.
- **Change:** add the specific `httpx.RemoteProtocolError` (and optionally `httpx.ReadError`) to the tuple. If broadening to the `httpx.TransportError` parent instead, ensure the already-handled `TimeoutException`/`ConnectError` subclasses still behave (order/precedence preserved). The disconnect raised in `_accumulate_sse` aiter_lines (`:1330`) propagates through `asyncio.wait_for` (`:1780`) to the loop; the retry re-POSTs from the top of the for-body.
- **Faithfulness-safety:** after `MAX_RETRIES` the error STILL re-raises (`:1999-2001` else→raise) → `status=error` stays fail-closed. No new claim ships; a persistent disconnect aborts exactly as today.

### Site 2 — generation empty-choices — `openrouter_client.py:2006-2024` (moved INSIDE loop)
- **Live baseline:** `choices = data.get("choices", [])`; `if not choices: raise ValueError(...)` — sits AFTER the `break` (`:1837`) and the for/else `raise last_error` (`:1999-2001`), i.e. OUTSIDE the retry loop → zero retries on the first empty 200.
- **Change:** move/duplicate the `not choices` detection INSIDE the `try` (after `data` is assigned: `:1817` non-stream / `:1784` stream) and raise a RETRYABLE `RuntimeError` so the EXISTING RuntimeError retry (`:1959`) re-issues. After `MAX_RETRIES` the RuntimeError re-raises (still fail-closed).
- **Scope guard (must preserve):** the STREAM branch synthesizes non-empty `choices` at `:1784-1797`, so `:2007` fires only for the NON-STREAM error-key-absent `{"choices":[]}` shape. The error-KEY-present case (`{"error":…,"choices":[]}`) already raises a retryable `RuntimeError` at `:1819-1836` — that path MUST stay intact (do not double-raise or shadow it).
- **Faithfulness-safety:** terminal = re-raised RuntimeError → `status=error`. No empty/blank completion is ever consumed as content; a persistent empty-200 aborts.

### Site 3 — seam no-choices — `openrouter_role_transport.py:653-656` (FIXES drb_75)
- **Live baseline:** `_parse_openrouter_response` raises plain `RoleTransportError("OpenRouter response carried no choices …")` for `{"choices":[]}`. The `complete()` loop only catches `except BlankVerdictError` (`:904`) → the plain `RoleTransportError` is NOT caught → release HELD, coverage 0.000, NO provider failover.
- **Change:** raise `BlankVerdictError` for the empty-choices case (so the EXISTING effort-ladder + provider-exclusion failover at `:902-973` handles it: exclude the blanking provider via `slug_for_provider`/`ignore`, step effort down, advance to next healthy provider — OpenRouter does NOT auto-advance on an empty 200), OR add `except RoleTransportError` alongside `:904` routed into the SAME failover path.
- **Faithfulness-safety:** the gate is still fail-closed — HELD is reached only AFTER the ladder/providers exhaust (`:973`/`:1008` raise). A fake verdict is never synthesized; the only change is "try the next healthy provider before holding," not "release on a blank." Must NOT regress the existing `PG_ROLE_TRANSPORT_RETRIES` (`:795`) or BlankVerdictError-content path (`:688-697`).

### Site 4 — NLI judge — `entailment_judge.py:205-287` (stops drb_72-class OVER-DROP)
- **Live baseline:** `_EntailmentJudge.judge` has NO retry. `post` (`:206`), `json` (`:215`), `choices` access (`:266`), and a bad/unparseable verdict (`:270-273`) are all swallowed by the broad `except Exception` (`:281-287`) → returns `("ENTAILED", "judge_error: …")`. `BudgetExceededError` is correctly re-raised first (`:277-280`).
- **Change:** add a bounded SAME-provider retry loop (new env `PG_ENTAILMENT_RETRIES`, default 2 — LAW VI, no hardcoding) around post+json+choices+bad-verdict. **MUST keep** the `BudgetExceededError` re-raise (`:277-280`) FIRST/outside the retry. On exhaustion KEEP the existing `('ENTAILED','judge_error: …')` sentinel.
- **Faithfulness-safety:** both live consumers already FAIL CLOSED on this sentinel — `clinical_generator/strict_verify.py:295-301` keys on the `judge_error:` PREFIX alone (drops in enforce); `provenance_generator.py:1795-1796` + `:1899-1900` set `judge_error_flag` on `verdict=='ENTAILED' AND reason.startswith('judge_error:')`, consumed → DROP at `:1946-1958`. Retry is the load-bearing improvement: it stops a single transient judge fault from OVER-DROPPING a salvageable verdict (drb_72-class coverage collapse) — WITHOUT loosening the gate. Docstring `:146-147` must be updated (no longer "fail-open … intentional"; now retry-then-fail-closed-at-consumer). **See §5 DIVERGENCE — the sentinel must stay ENTAILED+prefix.**

### Site 5 — discovery breadth-probe — `super_heavy_preflight.py:361-372` (FIXES drb_78)
- **Live baseline:** `_default_breadth_probe` issues exactly one `_serper_search` + one `_s2_bulk_search` for the fixed query, unions URLs, returns the count. No retry; an S2 HTTP-500 contributes 0 URLs → 29<100 floor → `GateError` at `:572-578`.
- **Change:** wrap the Serper+S2 union in a bounded retry (2-3 attempts, short backoff); on a 5xx/timeout from `_s2_bulk_search`, re-issue that backend before unioning. Fail-closed (`GateError`) only if the 100-URL floor is STILL unmet after retries.
- **Faithfulness-safety:** this is a PRE-SPEND anti-throttle gate; the legitimate fail-closed (`GateError` at `:572-578`, plus the probe-exception wrapper at `:563-571`) MUST still fire when the floor is genuinely unmet after retries. The change only prevents a single transient S2 500 under 3×-parallel load from aborting a fundable run; it never widens the corpus floor or weakens the throttle check.

---

## 4. Acceptance criteria

**Forced enumeration:** before declaring a verdict, write one line per criterion: `Criterion N [name]: <findings or NONE>.` A verdict is invalid if any line is missing.

- **AC1 — Site 1 add is correct & scoped.** `:1975` now catches `httpx.RemoteProtocolError` (and any added subclass) AND still catches `TimeoutException`/`ConnectError`; if `TransportError` parent is used, no previously-handled subclass changes behavior. After `MAX_RETRIES` it re-raises (`status=error`).
- **AC2 — Site 2 in-loop + retryable + scoped.** Empty-choices detection runs INSIDE the `try`, raises a retryable `RuntimeError` reusing `:1959`; the `:1819-1836` error-key retryable path is intact; the stream-synthesized-choices invariant (`:1784-1797`) is unbroken; terminal re-raises after `MAX_RETRIES`.
- **AC3 — Site 3 routed into failover, HELD only on exhaustion.** Empty-choices now reaches the `:902-973` provider-exclusion/effort-ladder failover (either via `BlankVerdictError` or an added `except RoleTransportError`); release is HELD only after the ladder/providers exhaust; `PG_ROLE_TRANSPORT_RETRIES` and the BlankVerdictError-content path are not regressed; no fake verdict is ever produced.
- **AC4 — Site 4 bounded retry, budget-safe, sentinel preserved.** `PG_ENTAILMENT_RETRIES` (default 2, env-driven — LAW VI) bounds the retry; `BudgetExceededError` re-raise stays first/outside; on exhaustion the return is exactly `('ENTAILED','judge_error: …')`; docstring `:146-147` updated.
- **AC5 — Site 5 bounded probe retry, gate preserved.** `_default_breadth_probe` retries 2-3× with backoff, re-issues S2 on 5xx/timeout; `GateError` still fires when the floor is unmet after retries; no change to `_PREFLIGHT_MIN_BREADTH`.
- **AC6 — No faithfulness-gate relaxation anywhere.** No edit to `strict_verify` / `provenance_generator` entailment-drop logic; NO NEUTRAL-sentinel flip (§5); the persistent-outage posture (all-drop → `abort_no_verified_sections`, CLAUDE.md §9.3) is preserved as the CORRECT clinical fail-closed outcome.
- **AC7 — LAW VI / no-hardcoding.** New retry bounds come from env (`PG_ENTAILMENT_RETRIES`; probe attempt count likewise env-driven or reuses an existing knob), not magic numbers in `src/`.
- **AC8 — Hermetic test file present & correct.** `tests/polaris_graph/test_transport_retry_resilience.py` exists and covers, for generation + seam + judge: (a) one transient `httpx.RemoteProtocolError` then success → verdict returned; (b) one empty `{"choices":[]}` then success → verdict returned; (c) all-blank → terminal fail-closed (generation `status=error` after `MAX_RETRIES`; seam HELD after ladder; judge returns the `judge_error:` sentinel which the consumer drops). Tests monkeypatch the httpx client — NO live calls, NO ambient `FIRECRAWL`/`OPENROUTER` keys leaking. Any EXISTING test asserting these paths return WITHOUT a preceding retry is updated to expect N retries first.
- **AC9 — Diff hygiene / scope.** ≤200-LOC PR cap respected (or an exemption noted); no provider-config/env-slate change in this diff; no `requirements.txt` change; no unrelated "while we're at it" edits.

**Completeness check:** list which files you actually READ (not just grep'd) this round. If you cannot confirm a full scan of every acceptance criterion, emit `incomplete_review` instead of APPROVE / REQUEST_CHANGES.

---

## 5. DIVERGENCE FLAG for Codex — the NLI sentinel (do NOT flip ENTAILED→NEUTRAL standalone)

This is the single highest-risk way to get Site 4 "right-looking but lethally wrong."

**Do NOT, as a standalone change, flip the judge sentinel from `('ENTAILED','judge_error:…')` to `('NEUTRAL','judge_error:…')`.** The provenance consumer at `provenance_generator.py:1795-1796` (and the local-window re-judge at `:1899-1900`) sets `judge_error_flag = True` ONLY when `verdict == 'ENTAILED' AND reason.startswith('judge_error:')`. A bare flip to NEUTRAL:
1. silently BYPASSES that `verdict=='ENTAILED'` detection → `judge_error_flag` is never set → the `judge_error=` field surfaced at `:1967` and consumed at `:1946-1958` is lost (the credibility-disclosure layer goes blind), and
2. routes the sentence into the generic `NEUTRAL/CONTRADICTED` drop branch instead — which LOOKS like a drop but changes WHICH disclosure metadata is attached.

`clinical_generator/strict_verify.py:295-301` keys on the PREFIX alone and is safe under either verdict — but `provenance_generator.py` is NOT. So a NEUTRAL flip is only safe if paired with COORDINATED edits at `provenance_generator.py:1795` and `:1899` to `reason.startswith('judge_error:')` ALONE (verdict-agnostic). **Recommendation for THIS diff: keep ENTAILED+prefix (the existing contract), add retry only.** If Codex believes a NEUTRAL flip is warranted as defense-in-depth for a future verdict-only consumer, flag it — but it belongs in a SEPARATE coordinated issue, not silently in this transport-retry diff.

---

## 6. NON-GOALS (verbatim, enforce as scope guard)

- NO faithfulness-gate relaxation.
- NO NEUTRAL-sentinel flip (see §5).
- NO provider-config / env-slate changes in this diff (FAILURE_AUDIT §4.2 run-config is handled separately).
- A persistent outage → all-drop → `abort_no_verified_sections` is the CORRECT clinical posture, **not** a regression. Any finding that frames the fail-closed terminal as a bug is itself out-of-scope.

---

## 7. Output schema (§8.3.9 — REQUIRED; loose verdict prose is rejected)

Emit the per-criterion forced enumeration (AC1–AC9, one line each), then the findings stratified P0/P1/P2/P3, then this machine-parseable block as the FINAL content. The CI gate parses the LAST `verdict:` line.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

**APPROVE rule:** zero NOVEL p0 AND zero continuing p0 AND zero p1. P2/P3 are non-blocking (deferred follow-up).


---

## DIFF UNDER REVIEW (review against the brief's acceptance criteria; this is iter 1 of 5)

```diff
diff --git a/scripts/dr_benchmark/super_heavy_preflight.py b/scripts/dr_benchmark/super_heavy_preflight.py
index 1dc1e076..56efc7b7 100644
--- a/scripts/dr_benchmark/super_heavy_preflight.py
+++ b/scripts/dr_benchmark/super_heavy_preflight.py
@@ -53,11 +53,15 @@ when called. Importing this module opens no socket.
 """
 from __future__ import annotations
 
+import logging
 import os
+import time
 from typing import Awaitable, Callable, Mapping
 
 from scripts.dr_benchmark.pathB_run_gate import GateError, behavioral_canary
 
+logger = logging.getLogger(__name__)
+
 # The credibility-redesign master flag. The credibility judge LLM only fires in production when this is
 # active (run_honest_sweep_r3.py:4711), so its slug is probed only then — probe-alive must match the
 # run's real activation, never fail-closed on a model the run will not call.
@@ -74,6 +78,15 @@ _CREDIBILITY_OFF_TOKENS = ("", "0", "false", "off", "no")
 # UNCALIBRATED offline — may need tuning against the first real wide run (see I-preflight-002 caveats).
 _PREFLIGHT_MIN_BREADTH = int(os.getenv("PG_PREFLIGHT_MIN_BREADTH", "100"))
 
+# I-transport-001 (#1191) Site 5 (FIXES drb_78; LAW VI — env-overridable): the breadth probe
+# re-issues BOTH discovery backends up to this many EXTRA times before failing closed, so a single
+# transient S2 HTTP-500 / timeout (which `_s2_bulk_search` swallows to an empty list -> 0 S2 URLs ->
+# union below the 100 floor -> GateError, with zero retry) does not abort a fundable pre-spend gate.
+# Default 2 => up to 3 total attempts. 0 disables the retry (single attempt, the pre-#1191 behavior).
+_BREADTH_PROBE_RETRIES = int(os.getenv("PG_BREADTH_PROBE_RETRIES", "2"))
+# Short fixed backoff (seconds) between breadth-probe attempts. Env-overridable per LAW VI.
+_BREADTH_PROBE_RETRY_BACKOFF_S = float(os.getenv("PG_BREADTH_PROBE_RETRY_BACKOFF_S", "1.0"))
+
 # I-preflight-002 (#1169) STORM-FIRED floor (LAW VI, env-overridable). The cheap STORM probe requests
 # target_count=2 personas; require at least this many to fire. Default 2 — the probe is intentionally
 # cheap (the breadth probe is the real wide-run signal), so the STORM floor only proves the
@@ -360,15 +373,34 @@ def _default_breadth_probe() -> int:
     # wide; it does not assert the run's actual question yields this many — that is the run's own corpus).
     query = "metformin efficacy in type 2 diabetes"
 
+    # I-transport-001 (#1191) Site 5 (FIXES drb_78): bounded retry around the Serper+S2 union.
+    # `_serper_search` / `_s2_bulk_search` SWALLOW transient HTTP 5xx / timeouts internally and
+    # return an empty list (live_retriever.py:410-431), so the retry trigger is "union still below
+    # the floor," not an exception — re-issue BOTH backends each attempt so a transient S2 500
+    # (0 S2 URLs on one attempt) is recovered on the next. The unique-URL set is PERSISTENT across
+    # attempts (a partial result from a flaky attempt is never discarded). Break early once the
+    # floor is met (no wasted calls). The caller's `_PREFLIGHT_MIN_BREADTH` floor check remains the
+    # fail-closed terminal — this only prevents a single transient backend blip from aborting a
+    # fundable run; it never widens the corpus floor.
     urls: set[str] = set()
-    for hit in _serper_search(query, num=max_serper):
-        u = hit.get("url", "")
-        if u:
-            urls.add(u)
-    for hit in _s2_bulk_search(query, limit=max_s2):
-        u = hit.get("url", "")
-        if u:
-            urls.add(u)
+    for attempt in range(_BREADTH_PROBE_RETRIES + 1):
+        for hit in _serper_search(query, num=max_serper):
+            u = hit.get("url", "")
+            if u:
+                urls.add(u)
+        for hit in _s2_bulk_search(query, limit=max_s2):
+            u = hit.get("url", "")
+            if u:
+                urls.add(u)
+        if len(urls) >= _PREFLIGHT_MIN_BREADTH:
+            break
+        if attempt < _BREADTH_PROBE_RETRIES:
+            logger.warning(
+                "[super_heavy_preflight] breadth probe union=%d < floor=%d after attempt %d/%d "
+                "(likely a transient discovery-backend blip) — re-issuing both backends.",
+                len(urls), _PREFLIGHT_MIN_BREADTH, attempt + 1, _BREADTH_PROBE_RETRIES + 1,
+            )
+            time.sleep(_BREADTH_PROBE_RETRY_BACKOFF_S)
     return len(urls)
 
 
diff --git a/src/polaris_graph/llm/entailment_judge.py b/src/polaris_graph/llm/entailment_judge.py
index e2ea84dc..20d50ae4 100644
--- a/src/polaris_graph/llm/entailment_judge.py
+++ b/src/polaris_graph/llm/entailment_judge.py
@@ -77,6 +77,26 @@ logger = logging.getLogger(__name__)
 
 _DEFAULT_ENTAILMENT_MODEL = "google/gemma-4-31b-it"
 _ENTAILMENT_TIMEOUT_S = 30.0
+# I-transport-001 (#1191) Site 4 (LAW VI — no magic numbers): bounded SAME-provider retry count
+# for a single judge call. A transient transport/parse/empty-choices fault on the entailment judge
+# previously fell straight through to the fail-open ('ENTAILED','judge_error:…') sentinel, which the
+# consumers DROP in enforce mode — an OVER-DROP of a salvageable verdict (the drb_72-class coverage
+# collapse). Retry the POST+parse this many extra times before emitting the sentinel; default 2
+# (=> up to 3 total attempts). 0 disables the retry (single attempt, the pre-#1191 behavior).
+_DEFAULT_ENTAILMENT_RETRIES = 2
+# Short fixed backoff between judge retries (seconds). Env-overridable per LAW VI.
+_DEFAULT_ENTAILMENT_RETRY_BACKOFF_S = 0.5
+
+
+class _RetryableJudgeError(Exception):
+    """I-transport-001 (#1191) Site 4: a transient/recoverable judge fault that should trigger a
+    bounded SAME-provider retry. Carries the human-readable `reason` used for the terminal
+    ('ENTAILED','judge_error: <reason>') sentinel so a bad-verdict's `bad_verdict=<v>` detail is
+    preserved across retries instead of being collapsed into a generic exception type name."""
+
+    def __init__(self, reason: str) -> None:
+        super().__init__(reason)
+        self.reason = reason
 _ENTAILMENT_PROMPT = """You are a strict entailment judge. You will be given a SPAN of source text and a SENTENCE that cites that span. Decide whether the SPAN entails the SENTENCE.
 
 Rules:
@@ -143,17 +163,28 @@ class _EntailmentJudge:
         """Return (verdict, reason).
 
         verdict is one of "ENTAILED", "NEUTRAL", "CONTRADICTED".
-        On API/parse failure returns ("ENTAILED", "judge_error: ...") —
-        fail-open so a transient OpenRouter outage does not nuke a run.
+
+        I-transport-001 (#1191) Site 4: a transient transport/parse/empty-choices/bad-verdict
+        fault is now RETRIED on the same provider up to `PG_ENTAILMENT_RETRIES` extra times
+        (default 2 => 3 total attempts; env-driven per LAW VI) before the method emits the
+        ('ENTAILED', 'judge_error: ...') sentinel on exhaustion. This is NOT a fail-OPEN: both
+        consumers FAIL CLOSED on that sentinel — `clinical_generator/strict_verify.py:295-301`
+        keys on the `judge_error:` PREFIX alone (drops in enforce); `provenance_generator.py:1795`
+        sets `judge_error_flag` on `verdict=='ENTAILED' AND reason.startswith('judge_error:')`
+        (consumed -> drop). The sentinel stays EXACTLY ('ENTAILED', 'judge_error: ...') so that
+        detection is preserved (do NOT flip to NEUTRAL standalone — that bypasses the
+        provenance detection at :1795). The retry's only effect is to stop a SINGLE transient
+        judge fault from OVER-DROPPING a salvageable verdict (the drb_72-class coverage collapse),
+        without loosening the binding faithfulness gate.
 
         I-bug-100: after each successful httpx call this method records
         the call cost via openrouter_client's module-level helpers
         (`_add_run_cost`, `check_run_budget`, `_COST_LEDGER_PATH`) so
         judge spend is visible to the per-run budget cap and the cost
         ledger. `BudgetExceededError` is explicitly re-raised before
-        the broad `except Exception` fail-open handler so a cap breach
-        aborts the sweep cleanly instead of being masked as a transient
-        judge error.
+        the broad retry/fail-closed handler so a cap breach aborts the
+        sweep cleanly instead of being masked as a transient judge error
+        or being retried.
         """
         prompt = _ENTAILMENT_PROMPT.format(span=span, sentence=sentence)
         started = time.monotonic()
@@ -200,91 +231,128 @@ class _EntailmentJudge:
             except Exception:  # noqa: BLE001
                 pass
 
-        data = None  # I-obs-001 #1141 AC3: bound before the try so the fail-open capture can prefer
-        # the served response (post ok, parse/verdict failed) over the exception string.
-        try:
-            response = self._client.post(
-                self._endpoint,
-                headers={
-                    "Authorization": f"Bearer {self._api_key}",
-                    "Content-Type": "application/json",
-                },
-                json=json_body,
-            )
-            response.raise_for_status()
-            data = response.json()
-
-            # I-safety-002b (#925): Path-B gate capture. The entailment judge is the
-            # evaluator-family LLM call that bypasses OpenRouterClient (direct httpx),
-            # so without capturing here the gate's two-family completeness check would
-            # be a silent no-op. Best-effort + gate-flagged; lazy import keeps off-mode
-            # import cost zero. `data` is the genuinely-served non-stream JSON.
+        # I-transport-001 (#1191) Site 4: bounded SAME-provider retry around post+parse+budget+
+        # verdict (LAW VI — env-driven bounds). A single transient transport/parse/empty-choices/
+        # bad-verdict fault now RETRIES instead of immediately fail-closing the verdict (which the
+        # consumers DROP -> over-drop of a salvageable verdict, the drb_72-class coverage collapse).
+        _retries = max(0, int(os.environ.get("PG_ENTAILMENT_RETRIES", _DEFAULT_ENTAILMENT_RETRIES)))
+        _backoff = max(
+            0.0,
+            float(os.environ.get(
+                "PG_ENTAILMENT_RETRY_BACKOFF_S", _DEFAULT_ENTAILMENT_RETRY_BACKOFF_S
+            )),
+        )
+        data = None  # I-obs-001 #1141 AC3: bound before the loop so the terminal judge_error
+        # capture can prefer the served response (post ok, parse/verdict failed) over the exc string.
+        last_reason = ""
+        for attempt in range(_retries + 1):
+            data = None  # reset per attempt so a later attempt's terminal capture is not stale.
             try:
-                from src.polaris_graph.benchmark import pathB_capture as _pathb
-                if _pathb.is_active():
-                    _pathb.capture_llm_call(
-                        role="evaluator",
-                        messages=[{"role": "user", "content": prompt}],
-                        raw_response=data,
-                    )
-            except Exception:  # noqa: BLE001 — capture must never break the judge
-                pass
-
-            # I-bug-100: cost recording. Reads + records BEFORE verdict
-            # parse so a cap breach aborts the sweep regardless of
-            # downstream parse outcome.
-            usage = data.get("usage", {}) or {}
-            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
-            output_tokens = int(usage.get("completion_tokens", 0) or 0)
-            api_cost = float(usage.get("cost", 0) or 0)
-            actual_cost = api_cost or _orc._impute_cost_from_tokens(
-                self._model, input_tokens, output_tokens, 0,
-            )
-            # I-bug-100 iter-1 diff P2 fix: when the entire usage block
-            # is absent, both api_cost and the imputed value are 0, which
-            # silently bypasses the budget guard. Fall back to a
-            # conservative estimate based on typical judge-call shape
-            # (~500 prompt + ~100 completion tokens) priced at Opus-tier
-            # so the budget cap is preserved on degraded responses.
-            if actual_cost == 0 and not usage:
-                actual_cost = _orc._impute_cost_from_tokens(
-                    self._model, 500, 100, 0,
+                response = self._client.post(
+                    self._endpoint,
+                    headers={
+                        "Authorization": f"Bearer {self._api_key}",
+                        "Content-Type": "application/json",
+                    },
+                    json=json_body,
                 )
-            _orc._add_run_cost(actual_cost)
-            duration_ms = (time.monotonic() - started) * 1000.0
-            try:
-                _append_judge_ledger_entry(
-                    input_tokens=input_tokens,
-                    output_tokens=output_tokens,
-                    duration_ms=duration_ms,
-                    actual_cost=actual_cost,
+                response.raise_for_status()
+                data = response.json()
+
+                # I-safety-002b (#925): Path-B gate capture. The entailment judge is the
+                # evaluator-family LLM call that bypasses OpenRouterClient (direct httpx),
+                # so without capturing here the gate's two-family completeness check would
+                # be a silent no-op. Best-effort + gate-flagged; lazy import keeps off-mode
+                # import cost zero. `data` is the genuinely-served non-stream JSON.
+                try:
+                    from src.polaris_graph.benchmark import pathB_capture as _pathb
+                    if _pathb.is_active():
+                        _pathb.capture_llm_call(
+                            role="evaluator",
+                            messages=[{"role": "user", "content": prompt}],
+                            raw_response=data,
+                        )
+                except Exception:  # noqa: BLE001 — capture must never break the judge
+                    pass
+
+                # I-bug-100: cost recording. Reads + records BEFORE verdict
+                # parse so a cap breach aborts the sweep regardless of
+                # downstream parse outcome. Each real POST (incl. a retried one) bills its OWN
+                # tokens — correct, real money was spent — so this runs inside the loop per attempt.
+                usage = data.get("usage", {}) or {}
+                input_tokens = int(usage.get("prompt_tokens", 0) or 0)
+                output_tokens = int(usage.get("completion_tokens", 0) or 0)
+                api_cost = float(usage.get("cost", 0) or 0)
+                actual_cost = api_cost or _orc._impute_cost_from_tokens(
+                    self._model, input_tokens, output_tokens, 0,
                 )
-            except Exception as exc:  # noqa: BLE001 — ledger IO is non-critical
-                logger.warning("entailment ledger write failed: %s", exc)
-            _orc.check_run_budget(0)  # raises BudgetExceededError if cap breached
-
-            content = data["choices"][0]["message"]["content"]
-            parsed = json.loads(content)
-            verdict = str(parsed.get("verdict", "")).upper().strip()
-            reason = str(parsed.get("reason", ""))
-            if verdict not in ("ENTAILED", "NEUTRAL", "CONTRADICTED"):
-                # Bad verdict = a failed verification → ONE judge_error record, not ok (gate iter-1 P1).
-                _emit_raw_io("judge_error", data)
-                return "ENTAILED", f"judge_error: bad_verdict={verdict!r}"
-            # Validated verdict → the ONE success raw-IO record, AFTER parse (gate iter-1 P1).
-            _emit_raw_io("ok", data, duration_ms=(time.monotonic() - started) * 1000.0)
-            return verdict, reason
-        except _orc.BudgetExceededError:
-            # I-bug-100: do NOT fail-open on cap breach. Propagate so
-            # the sweep aborts with a clear cause.
-            raise
-        except Exception as exc:  # noqa: BLE001 — fail-open by design
-            logger.warning("entailment judge error: %s", exc)
-            # Fail-OPEN judge_error (the drb_72-class signal): prefer the bound served data (parse
-            # failure on a real response) over the exc string. ONE judge_error record — no preceding
-            # "ok" was emitted because the success capture now lives AFTER verdict validation.
-            _emit_raw_io("judge_error", data if data is not None else {"error": str(exc)})
-            return "ENTAILED", f"judge_error: {type(exc).__name__}"
+                # I-bug-100 iter-1 diff P2 fix: when the entire usage block
+                # is absent, both api_cost and the imputed value are 0, which
+                # silently bypasses the budget guard. Fall back to a
+                # conservative estimate based on typical judge-call shape
+                # (~500 prompt + ~100 completion tokens) priced at Opus-tier
+                # so the budget cap is preserved on degraded responses.
+                if actual_cost == 0 and not usage:
+                    actual_cost = _orc._impute_cost_from_tokens(
+                        self._model, 500, 100, 0,
+                    )
+                _orc._add_run_cost(actual_cost)
+                duration_ms = (time.monotonic() - started) * 1000.0
+                try:
+                    _append_judge_ledger_entry(
+                        input_tokens=input_tokens,
+                        output_tokens=output_tokens,
+                        duration_ms=duration_ms,
+                        actual_cost=actual_cost,
+                    )
+                except Exception as exc:  # noqa: BLE001 — ledger IO is non-critical
+                    logger.warning("entailment ledger write failed: %s", exc)
+                _orc.check_run_budget(0)  # raises BudgetExceededError if cap breached
+
+                content = data["choices"][0]["message"]["content"]
+                parsed = json.loads(content)
+                verdict = str(parsed.get("verdict", "")).upper().strip()
+                reason = str(parsed.get("reason", ""))
+                if verdict not in ("ENTAILED", "NEUTRAL", "CONTRADICTED"):
+                    # Bad verdict = a recoverable failed verification: raise the RETRYABLE error so a
+                    # transient garbled verdict re-issues. The reason (with bad_verdict=<v>) is
+                    # preserved for the terminal sentinel on exhaustion.
+                    raise _RetryableJudgeError(f"bad_verdict={verdict!r}")
+                # Validated verdict → the ONE success raw-IO record, AFTER parse (gate iter-1 P1).
+                _emit_raw_io("ok", data, duration_ms=(time.monotonic() - started) * 1000.0)
+                return verdict, reason
+            except _orc.BudgetExceededError:
+                # I-bug-100: do NOT fail-open OR retry on cap breach. Propagate immediately so the
+                # sweep aborts with a clear cause (this except MUST stay FIRST/outside the retry).
+                raise
+            except _RetryableJudgeError as exc:
+                last_reason = exc.reason
+                if attempt < _retries:
+                    logger.warning(
+                        "entailment judge bad verdict (attempt %d/%d): %s — retrying.",
+                        attempt + 1, _retries + 1, exc.reason,
+                    )
+                    time.sleep(_backoff)
+                    continue
+                break
+            except Exception as exc:  # noqa: BLE001 — transient transport/parse fault: retry then fail-closed
+                last_reason = type(exc).__name__
+                if attempt < _retries:
+                    logger.warning(
+                        "entailment judge error (attempt %d/%d): %s — retrying.",
+                        attempt + 1, _retries + 1, exc,
+                    )
+                    time.sleep(_backoff)
+                    continue
+                logger.warning("entailment judge error (final): %s", exc)
+                break
+
+        # Retries exhausted: emit EXACTLY ONE terminal judge_error record (no per-attempt emits) and
+        # return the fail-CLOSED-at-consumer sentinel. Prefer the bound served data (a parse/verdict
+        # failure on a real response) over a bare error string. The sentinel stays ENTAILED+prefix so
+        # both consumers DROP it (see method docstring + §5 DIVERGENCE in the brief).
+        _emit_raw_io("judge_error", data if data is not None else {"error": last_reason})
+        return "ENTAILED", f"judge_error: {last_reason}"
 
 
 def _append_judge_ledger_entry(
diff --git a/src/polaris_graph/llm/openrouter_client.py b/src/polaris_graph/llm/openrouter_client.py
index 085d7d7e..1eaa04c4 100644
--- a/src/polaris_graph/llm/openrouter_client.py
+++ b/src/polaris_graph/llm/openrouter_client.py
@@ -1834,6 +1834,35 @@ class OpenRouterClient:
                             f"Provider error (code={err.get('code', '?')}): "
                             f"{err.get('message', str(err))[:200]}"
                         )
+                    # I-transport-001 (#1191) Site 2 (FIXES drb_72-class): a structurally-empty
+                    # HTTP 200 ({"choices": []} with NO error key) was previously detected only
+                    # AFTER the for/else (the post-loop SF-16 block below) and raised a NON-retryable
+                    # ValueError — ZERO retries on the first empty 200. Move the detection INSIDE the
+                    # try so a transient empty 200 reuses the EXISTING retryable RuntimeError branch
+                    # (~:1959) and re-POSTs. This runs ONLY on the non-stream path (the stream branch
+                    # synthesizes a non-empty `choices` at :1784-1797, so {"choices":[]} can only
+                    # reach here non-streamed); it is placed AFTER the error-key check above so the
+                    # {"error":…,"choices":[]} path keeps its own retryable RuntimeError and is not
+                    # shadowed. After MAX_RETRIES the RuntimeError re-raises (status=error stays
+                    # fail-closed) — no empty/blank completion is ever consumed as content.
+                    if not data.get("choices"):
+                        # I-obs-001 #1141 AC3: emit the empty-choices forensic capture here (mirrors
+                        # the post-loop block) so the retry path does not silently drop the signal.
+                        _io_sink = current_raw_io_sink()
+                        if _io_sink is not None:
+                            try:
+                                _io_sink.record(
+                                    call_id=uuid.uuid4().hex, call_type=call_type,
+                                    role=_pathb_capture.current_llm_role(),
+                                    request={**body, "messages": sanitized_messages},
+                                    raw_response=data, duration_ms=None, status="empty_choices",
+                                )
+                            except Exception:  # noqa: BLE001
+                                pass
+                        raise RuntimeError(
+                            f"API returned no choices in response for {call_type} "
+                            f"(model={data.get('model', '?')}) — empty HTTP 200"
+                        )
                 break
 
             except asyncio.TimeoutError:
@@ -1972,7 +2001,20 @@ class OpenRouterClient:
                 self.usage.total_errors += 1
                 raise
 
-            except (httpx.TimeoutException, httpx.ConnectError) as exc:
+            except (
+                httpx.TimeoutException,
+                httpx.ConnectError,
+                # I-transport-001 (#1191) Site 1 (FIXES drb_72): a mid-stream
+                # incomplete-chunked-read raises httpx.RemoteProtocolError — a SIBLING (not a
+                # subclass) of TimeoutException/ConnectError, so the prior 2-class tuple matched
+                # NO clause and the disconnect propagated uncaught with ZERO retries
+                # (status=error_unexpected). Add the SPECIFIC RemoteProtocolError (+ ReadError for
+                # a truncated body read) — NOT the broad httpx.TransportError parent, which would
+                # also swallow ProxyError/UnsupportedProtocol/DecodingError. After MAX_RETRIES the
+                # error STILL re-raises via the for/else below (status=error stays fail-closed).
+                httpx.RemoteProtocolError,
+                httpx.ReadError,
+            ) as exc:
                 last_error = exc
                 # FIX-052B: DNS failures get longer backoff (outages last 10-60s)
                 is_dns_failure = "getaddrinfo" in str(exc).lower()
@@ -2002,7 +2044,13 @@ class OpenRouterClient:
 
         duration_ms = (time.monotonic() - start) * 1000
 
-        # SF-16: Check for empty choices before indexing
+        # SF-16: Check for empty choices before indexing.
+        # I-transport-001 (#1191) Site 2: the PRIMARY empty-choices detection now lives INSIDE
+        # the retry loop (raises a retryable RuntimeError so a transient empty 200 re-POSTs). This
+        # post-loop block is kept as a fail-closed BACKSTOP — it stays a ValueError (a non-retryable
+        # terminal) for any non-stream empty-200 that reaches here through a future code path; the
+        # in-loop check makes it dead for the current non-stream flow but its removal would weaken
+        # the defense if the break/assignment order ever changes.
         choices = data.get("choices", [])
         if not choices:
             self.usage.total_errors += 1
diff --git a/src/polaris_graph/roles/openrouter_role_transport.py b/src/polaris_graph/roles/openrouter_role_transport.py
index 43bfd289..67c7ca72 100644
--- a/src/polaris_graph/roles/openrouter_role_transport.py
+++ b/src/polaris_graph/roles/openrouter_role_transport.py
@@ -651,7 +651,18 @@ def _parse_openrouter_response(raw: dict) -> tuple[object, str | None, dict | No
     """
     choices = raw.get("choices")
     if not choices:
-        raise RoleTransportError(
+        # I-transport-001 (#1191) Site 3 (FIXES drb_75): a structurally-empty HTTP 200
+        # ({"choices": []}, model=None) previously raised a PLAIN RoleTransportError, which the
+        # complete() loop does NOT catch (it only catches BlankVerdictError at :904) -> release
+        # HELD at coverage 0.000 with NO provider failover (OpenRouter does not auto-advance off
+        # an empty 200). Raise the RECOVERABLE BlankVerdictError instead so the SAME effort-ladder
+        # + provider-exclusion failover that already handles a blank-content 200 (:902-973) excludes
+        # the blanking provider and advances to the next healthy one. This is scoped to the
+        # empty-choices case ONLY — the non-dict-choice / non-dict-message guards below KEEP their
+        # plain RoleTransportError (a malformed shape is a genuine fail-loud, not a provider blip).
+        # The gate stays fail-closed: HELD is reached only AFTER the ladder/providers exhaust
+        # (:973/:1008 raise); no fake verdict is ever synthesized.
+        raise BlankVerdictError(
             f"OpenRouter response carried no choices (model={raw.get('model')!r})"
         )
     first_choice = choices[0]
diff --git a/tests/polaris_graph/roles/__init__.py b/tests/polaris_graph/roles/__init__.py
new file mode 100644
index 00000000..e69de29b
diff --git a/tests/polaris_graph/test_transport_retry_resilience.py b/tests/polaris_graph/test_transport_retry_resilience.py
new file mode 100644
index 00000000..e8bde711
--- /dev/null
+++ b/tests/polaris_graph/test_transport_retry_resilience.py
@@ -0,0 +1,502 @@
+"""I-transport-001 (#1191) — bounded-retry transport resilience (faithfulness-safe).
+
+HERMETIC / OFFLINE: every test monkeypatches the httpx client (generation + NLI judge) or injects an
+``httpx.MockTransport`` (4-role seam). NO socket is opened, NO live LLM is called, and NO ambient
+``OPENROUTER_*`` / ``FIRECRAWL_*`` / ``SEMANTIC_SCHOLAR_*`` / ``SERPER_*`` keys leak into a probe — the
+relevant env is set to a fixed test value or deleted per test.
+
+Covers, for the three LLM transport seams (generation, 4-role verifier seam, NLI entailment judge):
+  (a) ONE transient ``httpx.RemoteProtocolError`` (mid-stream incomplete-chunked-read) then success
+      -> the verdict/response is returned (the fault was retried, not propagated).
+  (b) ONE structurally-empty ``{"choices": []}`` HTTP 200 then success -> the verdict is returned.
+  (c) ALL attempts fault -> the TERMINAL stays fail-CLOSED:
+        - generation: re-raises after ``MAX_RETRIES`` (the caller maps this to ``status=error``);
+        - seam: ``BlankVerdictError`` propagates (release HELD) after the effort ladder exhausts;
+        - judge: returns the EXACT ``("ENTAILED", "judge_error: ...")`` sentinel, which the
+          consumer (``strict_verify`` enforce mode) DROPS — fail-closed, not fail-open.
+
+NON-GOAL: no faithfulness-gate relaxation, no NEUTRAL-sentinel flip. The judge sentinel staying
+``ENTAILED`` + ``judge_error:`` prefix is the load-bearing contract both consumers fail-closed on.
+"""
+
+from __future__ import annotations
+
+import asyncio
+import json
+
+import httpx
+import pytest
+
+from datetime import datetime, timezone
+
+from src.polaris_graph.clinical_retrieval.evidence_pool import (
+    AdequacyVerdict,
+    EvidencePool,
+    Source,
+    SourceTier,
+)
+from src.polaris_graph.llm import entailment_judge, openrouter_client
+from src.polaris_graph.roles import openrouter_role_transport as ort
+from src.polaris_graph.roles.openrouter_role_transport import (
+    BlankVerdictError,
+    OpenRouterRoleTransport,
+)
+from src.polaris_graph.roles.role_transport import RoleRequest
+
+# --------------------------------------------------------------------------------------------- env
+
+
+@pytest.fixture(autouse=True)
+def _hermetic_env(monkeypatch):
+    """Fix the OpenRouter key to a test value and DELETE every ambient backend key so no probe can
+    reach a live endpoint even if a stub is missed. Keep retries fast (no real sleep)."""
+    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
+    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
+    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")
+    # Zero backoffs so the bounded retries do not actually sleep in the suite.
+    monkeypatch.setenv("PG_ENTAILMENT_RETRY_BACKOFF_S", "0")
+    for _k in (
+        "OPENROUTER_BASE_URL",
+        "FIRECRAWL_API_KEY",
+        "SEMANTIC_SCHOLAR_API_KEY",
+        "SERPER_API_KEY",
+        "PG_PROVIDER_BLANK_RETRIES",
+    ):
+        monkeypatch.delenv(_k, raising=False)
+    yield
+
+
+@pytest.fixture(autouse=True)
+def _reset_run_cost():
+    openrouter_client.reset_run_cost()
+    yield
+    openrouter_client.reset_run_cost()
+
+
+# ===================================================================== SEAM 1 — GENERATION (_call_impl)
+
+
+_GEN_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
+
+
+def _empty_choices_response() -> httpx.Response:
+    """A structurally-empty HTTP 200 ({"choices": []}, no error key) — the drb_72-class empty 200."""
+    return httpx.Response(
+        200, json={"choices": [], "model": "deepseek/deepseek-v4-pro"}, request=_GEN_REQUEST,
+    )
+
+
+def _ok_generation_response() -> httpx.Response:
+    return httpx.Response(
+        200,
+        json={
+            "choices": [{"message": {"content": "the answer"}}],
+            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
+            "model": "deepseek/deepseek-v4-pro",
+        },
+        request=_GEN_REQUEST,
+    )
+
+
+def _make_generation_client(monkeypatch, post_side_effects):
+    """Build an OpenRouterClient whose ``_client.post`` returns/raises the queued side effects in
+    order. ``response_format=json_object`` + ``reasoning_enabled=False`` forces the NON-STREAM path,
+    which posts via ``self._client.post`` (a single mockable coroutine)."""
+    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
+    calls = {"n": 0}
+
+    async def _fake_post(*args, **kwargs):
+        i = calls["n"]
+        calls["n"] += 1
+        effect = post_side_effects[min(i, len(post_side_effects) - 1)]
+        if isinstance(effect, Exception):
+            raise effect
+        return effect
+
+    monkeypatch.setattr(client._client, "post", _fake_post)
+    # No real backoff sleeps.
+    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
+    return client, calls
+
+
+async def _noop_async_sleep(*_a, **_k):
+    return None
+
+
+def _run_generation(client):
+    return asyncio.run(
+        client._call_impl(
+            messages=[{"role": "user", "content": "q"}],
+            call_type="section",
+            reasoning_enabled=False,
+            response_format={"type": "json_object"},
+        )
+    )
+
+
+def test_generation_remote_protocol_error_then_success(monkeypatch):
+    """(a) ONE mid-stream httpx.RemoteProtocolError then a valid 200 -> the response is returned
+    (Site 1: RemoteProtocolError is now in the retry tuple at openrouter_client.py:1975)."""
+    client, calls = _make_generation_client(
+        monkeypatch,
+        [httpx.RemoteProtocolError("peer closed connection mid-stream"), _ok_generation_response()],
+    )
+    resp = _run_generation(client)
+    assert resp.content == "the answer"
+    assert calls["n"] == 2  # one failed attempt + one success
+
+
+def test_generation_empty_choices_then_success(monkeypatch):
+    """(b) ONE empty {"choices": []} 200 then a valid 200 -> the response is returned
+    (Site 2: empty-choices now raises a RETRYABLE RuntimeError INSIDE the loop)."""
+    client, calls = _make_generation_client(
+        monkeypatch,
+        [_empty_choices_response(), _ok_generation_response()],
+    )
+    resp = _run_generation(client)
+    assert resp.content == "the answer"
+    assert calls["n"] == 2
+
+
+def test_generation_all_remote_protocol_error_fails_closed(monkeypatch):
+    """(c) EVERY attempt raises RemoteProtocolError -> after MAX_RETRIES the error re-raises
+    (the caller maps an exception to status=error — fail-closed). Asserts MAX_RETRIES+1 attempts."""
+    client, calls = _make_generation_client(
+        monkeypatch,
+        [httpx.RemoteProtocolError("persistent mid-stream disconnect")],
+    )
+    with pytest.raises(httpx.RemoteProtocolError):
+        _run_generation(client)
+    assert calls["n"] == openrouter_client.MAX_RETRIES + 1
+
+
+def test_generation_all_empty_choices_fails_closed(monkeypatch):
+    """(c) EVERY attempt returns an empty 200 -> the retryable RuntimeError re-raises after
+    MAX_RETRIES (status=error). No empty completion is ever consumed as content."""
+    client, calls = _make_generation_client(monkeypatch, [_empty_choices_response()])
+    with pytest.raises(RuntimeError):
+        _run_generation(client)
+    assert calls["n"] == openrouter_client.MAX_RETRIES + 1
+
+
+# ===================================================================== SEAM 2 — 4-ROLE VERIFIER SEAM
+
+
+def _judge_request() -> RoleRequest:
+    """A JUDGE role request — the Judge is an effort-reasoning role, so complete() uses the effort
+    ladder (multi-attempt) which is exactly the provider-exclusion/step-down failover Site 3 reuses."""
+    return RoleRequest(role="judge", model_slug="qwen/qwen3.6-35b-a3b", prompt="decide", params={})
+
+
+def _seam_transport(handler) -> OpenRouterRoleTransport:
+    return OpenRouterRoleTransport(httpx.Client(transport=httpx.MockTransport(handler)))
+
+
+def _seam_ok_payload() -> dict:
+    return {
+        "model": "qwen/qwen3.6-35b-a3b",
+        "provider": "DeepInfra",
+        "choices": [{"message": {"role": "assistant", "content": "VERIFIED"}}],
+        "usage": {"prompt_tokens": 11, "completion_tokens": 5},
+    }
+
+
+def _seam_empty_payload() -> dict:
+    # The drb_75 shape: a structurally-empty HTTP 200, model=None, choices=[].
+    return {"model": None, "provider": "DeepInfra", "choices": []}
+
+
+@pytest.fixture(autouse=True)
+def _pin_effort_ladder(monkeypatch):
+    """Pin the effort ladder to a deterministic 3-entry tuple so the seam attempt count is stable
+    regardless of ambient PG_FOUR_ROLE_EFFORT_LADDER (the module value is read at import)."""
+    monkeypatch.setattr(ort, "_VERIFIER_EFFORT_LADDER", ("xhigh", "low", None))
+    yield
+
+
+def test_seam_remote_protocol_error_then_success(monkeypatch):
+    """(a) The seam already retries transport faults via PG_ROLE_TRANSPORT_RETRIES (:828-849); this
+    is a REGRESSION GUARD that a transient RemoteProtocolError on the POST is retried, not a new
+    Site-3 behavior. ONE RemoteProtocolError then a valid 200 -> the verdict is returned."""
+    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "2")
+    state = {"n": 0}
+
+    def handler(request: httpx.Request) -> httpx.Response:
+        state["n"] += 1
+        if state["n"] == 1:
+            raise httpx.RemoteProtocolError("peer closed mid-stream")
+        return httpx.Response(200, json=_seam_ok_payload())
+
+    resp = _seam_transport(handler).complete(_judge_request())
+    assert resp.raw_text == "VERIFIED"
+    assert state["n"] == 2
+
+
+def test_seam_empty_choices_then_success(monkeypatch):
+    """(b) Site 3 (FIXES drb_75): ONE structurally-empty {"choices": []} 200 then a valid 200 ->
+    the empty 200 now raises a RECOVERABLE BlankVerdictError routed into the effort-ladder +
+    provider-exclusion failover, which advances to the next attempt and returns the verdict.
+
+    Also asserts the drb_75 MECHANISM: the blanking provider ("DeepInfra" -> slug "deepinfra") is
+    added to body['provider']['ignore'] BEFORE the retry, so OpenRouter advances to the next healthy
+    provider (it does NOT auto-advance off an empty 200)."""
+    state = {"n": 0, "bodies": []}
+
+    def handler(request: httpx.Request) -> httpx.Response:
+        state["n"] += 1
+        state["bodies"].append(json.loads(request.content.decode("utf-8")))
+        if state["n"] == 1:
+            return httpx.Response(200, json=_seam_empty_payload())
+        return httpx.Response(200, json=_seam_ok_payload())
+
+    resp = _seam_transport(handler).complete(_judge_request())
+    assert resp.raw_text == "VERIFIED"
+    assert state["n"] == 2  # the empty 200 was retried (not HELD immediately)
+    # The blanking provider was excluded on the RETRY request (provider-exclusion failover, :960-964).
+    retry_provider_block = state["bodies"][1].get("provider", {})
+    assert "deepinfra" in retry_provider_block.get("ignore", [])
+
+
+def test_seam_all_empty_choices_held_after_ladder(monkeypatch):
+    """(c) EVERY attempt returns an empty 200 -> BlankVerdictError propagates (release HELD) only
+    AFTER the full effort ladder exhausts. No fake verdict is ever synthesized."""
+    state = {"n": 0}
+
+    def handler(request: httpx.Request) -> httpx.Response:
+        state["n"] += 1
+        return httpx.Response(200, json=_seam_empty_payload())
+
+    with pytest.raises(BlankVerdictError):
+        _seam_transport(handler).complete(_judge_request())
+    # One attempt per ladder entry (the pinned 3-entry ladder) — HELD only on exhaustion.
+    assert state["n"] == len(ort._VERIFIER_EFFORT_LADDER)
+
+
+# ===================================================================== SEAM 3 — NLI ENTAILMENT JUDGE
+
+
+@pytest.fixture(autouse=True)
+def _reset_judge_singleton():
+    entailment_judge._JUDGE_SINGLETON = None
+    yield
+    entailment_judge._JUDGE_SINGLETON = None
+
+
+class _FakeJudgeClient:
+    """A stub httpx.Client for the NLI judge: returns/raises queued side effects per .post()."""
+
+    def __init__(self, side_effects):
+        self._side_effects = side_effects
+        self.n = 0
+
+    def post(self, *args, **kwargs):
+        i = self.n
+        self.n += 1
+        effect = self._side_effects[min(i, len(self._side_effects) - 1)]
+        if isinstance(effect, Exception):
+            raise effect
+        return effect
+
+
+def _single_span_pool(full_text: str) -> EvidencePool:
+    """A minimal one-source EvidencePool (pattern from test_strict_verify_entailment.py) whose
+    full_text is the cited span, so a `[#ev:src-1:0-<len>]` token validates and checks (a)-(e) pass,
+    letting verify_sentence reach the entailment judge."""
+    src = Source(
+        url="https://www.urncst.org/article",
+        domain="urncst.org",
+        tier=SourceTier.T1,
+        title="Source",
+        snippet="snippet text",
+        full_text=full_text,
+        full_text_available=True,
+        source_id="src-1",
+    )
+    return EvidencePool(
+        decision_id="dec-transport-001",
+        sources=[src],
+        adequacy=AdequacyVerdict(
+            is_adequate=True,
+            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
+            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
+        ),
+        retrieval_started_at_utc=datetime.now(timezone.utc),
+        retrieval_finished_at_utc=datetime.now(timezone.utc),
+        latency_ms=0,
+        cost_usd=0.0,
+    )
+
+
+_JUDGE_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
+
+
+def _judge_http_response(payload: dict) -> httpx.Response:
+    return httpx.Response(200, json=payload, request=_JUDGE_REQUEST)
+
+
+def _judge_ok_payload(verdict: str = "ENTAILED") -> dict:
+    return {
+        "choices": [{"message": {"content": json.dumps({"verdict": verdict, "reason": "ok"})}}],
+        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
+    }
+
+
+def _make_judge(monkeypatch, side_effects) -> entailment_judge._EntailmentJudge:
+    monkeypatch.setattr(entailment_judge.time, "sleep", lambda *_a, **_k: None)
+    judge = entailment_judge._EntailmentJudge()
+    judge._client = _FakeJudgeClient(side_effects)
+    return judge
+
+
+def test_judge_remote_protocol_error_then_success(monkeypatch):
+    """(a) Site 4: ONE httpx.RemoteProtocolError on the judge POST then a valid 200 -> the real
+    verdict is returned (the transient fault was retried, NOT collapsed to the judge_error sentinel)."""
+    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
+    judge = _make_judge(
+        monkeypatch,
+        [httpx.RemoteProtocolError("mid-stream disconnect"), _judge_http_response(_judge_ok_payload())],
+    )
+    verdict, reason = judge.judge("a sentence", "a span")
+    assert verdict == "ENTAILED"
+    assert not reason.startswith("judge_error:")
+    assert judge._client.n == 2
+
+
+def test_judge_empty_choices_then_success(monkeypatch):
+    """(b) Site 4: ONE empty {"choices": []} 200 then a valid 200 -> the verdict is returned
+    (the empty 200 raises inside the loop and is retried)."""
+    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
+    judge = _make_judge(
+        monkeypatch,
+        [_judge_http_response({"choices": []}), _judge_http_response(_judge_ok_payload())],
+    )
+    verdict, reason = judge.judge("a sentence", "a span")
+    assert verdict == "ENTAILED"
+    assert not reason.startswith("judge_error:")
+    assert judge._client.n == 2
+
+
+def test_judge_all_fault_returns_failclosed_sentinel_consumer_drops(monkeypatch):
+    """(c) Site 4: EVERY attempt raises -> the EXACT ('ENTAILED', 'judge_error: ...') sentinel is
+    returned after PG_ENTAILMENT_RETRIES, and the consumer (strict_verify enforce) DROPS it.
+
+    This is the load-bearing faithfulness property: the sentinel stays ENTAILED+prefix so BOTH
+    consumers fail CLOSED (NOT a NEUTRAL flip, which would bypass provenance detection)."""
+    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
+    judge = _make_judge(monkeypatch, [httpx.RemoteProtocolError("persistent disconnect")])
+    verdict, reason = judge.judge("a sentence", "a span")
+
+    # The sentinel contract: ENTAILED verdict + judge_error: prefix (do NOT flip to NEUTRAL).
+    assert verdict == "ENTAILED"
+    assert reason.startswith("judge_error:")
+    # PG_ENTAILMENT_RETRIES=2 => 3 total attempts before the sentinel.
+    assert judge._client.n == 3
+
+    # The consumer fails CLOSED on this sentinel. Drive the REAL strict_verify enforce-mode path
+    # end-to-end through verify_sentence (the only place that calls _get_judge().judge): a sentence
+    # whose mechanical checks (a)-(e) PASS but the entailment judge returns the judge_error sentinel
+    # must be DROPPED (returns not-verified, reason=entailment_judge_error_fail_closed). This proves
+    # the retry-then-exhaust path remains fail-CLOSED, not fail-open.
+    from src.polaris_graph.clinical_generator import strict_verify as sv
+
+    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
+    monkeypatch.setattr(sv, "_get_judge", lambda: judge)
+    judge._client = _FakeJudgeClient([httpx.RemoteProtocolError("persistent disconnect")])
+
+    full_text = "metformin reduced HbA1c in adults with type 2 diabetes mellitus"
+    pool = _single_span_pool(full_text)
+    # The sentence shares >=2 content words with the span and carries a valid provenance token, so
+    # checks (a)-(e) pass and control reaches the entailment judge (which returns the sentinel).
+    sentence = (
+        f"metformin reduced HbA1c in type 2 diabetes [#ev:src-1:0-{len(full_text)}]."
+    )
+    ok, detail = sv.verify_sentence(sentence, pool)
+    assert ok is False
+    assert detail == "entailment_judge_error_fail_closed"
+
+
+def test_judge_budget_exceeded_propagates_not_retried(monkeypatch):
+    """Site 4 invariant: BudgetExceededError must propagate IMMEDIATELY (first/outside the retry) —
+    a cap breach is never masked as a transient judge error nor retried."""
+    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
+    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.0001)
+    # A valid 200 whose cost (0.001) breaches the 0.0001 cap on the FIRST attempt.
+    payload = {
+        "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
+        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001},
+    }
+    judge = _make_judge(monkeypatch, [_judge_http_response(payload)])
+    # NOTE: the cap breach must abort on the FIRST POST, before any retry.
+    with pytest.raises(openrouter_client.BudgetExceededError):
+        judge.judge("a sentence", "a span")
+    # Exactly ONE POST — the breach aborts before any retry.
+    assert judge._client.n == 1
+
+
+# ============================================================ SITE 5 — DISCOVERY BREADTH PROBE (drb_78)
+
+
+def test_breadth_probe_transient_s2_500_then_recovers(monkeypatch):
+    """(b for Site 5; FIXES drb_78): a transient S2 HTTP-500 (which _s2_bulk_search SWALLOWS to an
+    empty list) yields 0 S2 URLs on attempt 1 -> union below the 100 floor -> the bounded retry
+    re-issues BOTH backends; on attempt 2 S2 recovers and the union crosses the floor. Proves the
+    PG_BREADTH_PROBE_RETRIES path (the production discovery functions are faked — NO network)."""
+    import src.polaris_graph.retrieval.live_retriever as lr
+    import scripts.dr_benchmark.super_heavy_preflight as m
+
+    monkeypatch.setenv("PG_BREADTH_PROBE_RETRIES", "2")
+    monkeypatch.setenv("PG_BREADTH_PROBE_RETRY_BACKOFF_S", "0")
+    monkeypatch.setenv("PG_SWEEP_MAX_SERPER", "100")
+    monkeypatch.setenv("PG_SWEEP_MAX_S2", "100")
+
+    s2_calls = {"n": 0}
+
+    def _fake_serper(query, num=10, api_calls=None):
+        return [{"url": f"https://serper/{i}"} for i in range(60)]
+
+    def _fake_s2(query, limit=20):
+        s2_calls["n"] += 1
+        if s2_calls["n"] == 1:
+            return []  # transient S2 HTTP-500 -> swallowed to [] (live_retriever.py:410-421)
+        return [{"url": f"https://s2/{i}"} for i in range(90)]
+
+    monkeypatch.setattr(lr, "_serper_search", _fake_serper)
+    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2)
+
+    n = m._default_breadth_probe()
+    # Attempt 1: 60 serper + 0 S2 = 60 (< 100 floor) -> retry. Attempt 2: +90 unique S2 = 150.
+    assert n == 150
+    assert s2_calls["n"] == 2  # S2 was re-issued after the transient blip
+
+
+def test_breadth_probe_persistent_s2_failure_stays_below_floor(monkeypatch):
+    """(c for Site 5): a PERSISTENT S2 failure (always []) means the union never crosses the floor
+    even after all retries -> the probe returns the genuinely-low count, so the caller's
+    _PREFLIGHT_MIN_BREADTH floor check still fails CLOSED (GateError). The retry never widens the
+    floor; it only recovers a transient blip."""
+    import src.polaris_graph.retrieval.live_retriever as lr
+    import scripts.dr_benchmark.super_heavy_preflight as m
+
+    monkeypatch.setenv("PG_BREADTH_PROBE_RETRIES", "2")
+    monkeypatch.setenv("PG_BREADTH_PROBE_RETRY_BACKOFF_S", "0")
+    monkeypatch.setenv("PG_SWEEP_MAX_SERPER", "100")
+    monkeypatch.setenv("PG_SWEEP_MAX_S2", "100")
+
+    serper_calls = {"n": 0}
+
+    def _fake_serper(query, num=10, api_calls=None):
+        serper_calls["n"] += 1
+        return [{"url": f"https://serper/{i}"} for i in range(30)]  # only 30 < 100 floor
+
+    def _fake_s2_dead(query, limit=20):
+        return []  # persistent S2 outage
+
+    monkeypatch.setattr(lr, "_serper_search", _fake_serper)
+    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2_dead)
+
+    n = m._default_breadth_probe()
+    # Union stays at 30 (< 100 floor) on every attempt -> probe returns the honest low count.
+    assert n == 30
+    # All attempts were exhausted (1 + PG_BREADTH_PROBE_RETRIES) because the floor was never met.
+    assert serper_calls["n"] == 3
+    assert n < m._PREFLIGHT_MIN_BREADTH  # the caller's floor check will fail CLOSED on this

```

---

## FINAL INSTRUCTION

Review the DIFF above against the acceptance criteria AC1-AC9 in the brief's §4. Run the forced per-criterion enumeration (one line per AC1-AC9), then findings stratified P0/P1/P2/P3, then emit ONLY the §8.3.9 YAML schema as the FINAL content of your response:

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

The CI gate parses the LAST `verdict:` line. APPROVE iff zero NOVEL p0 AND zero continuing p0 AND zero p1.
