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
