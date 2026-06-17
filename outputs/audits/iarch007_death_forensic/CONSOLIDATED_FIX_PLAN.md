# I-arch-007 — CONSOLIDATED DEATH-FORENSIC FIX PLAN (GH #1264)

**One complete, surgical, faithfulness-NEUTRAL plan that BOTH Claude and Codex can sign.**
Date 2026-06-16. Anchor evidence: `outputs/audits/iarch007_death_forensic/q90_genstall_faulthandler.txt`.
Sources consolidated: `claude_modeA_genstall.md`, `claude_modeB_credhang.md`, `claude_modeC_gapabort.md`,
`codex_forensic.txt`, `research_trickle_cancellation.md`, `research_advisory_bound.md`.

---

## 0. The death taxonomy (5 runs, reconciled to 3 root mechanisms + 2 containment gaps)

| Run | Symptom | Root mechanism | This plan |
|---|---|---|---|
| Q90 (anchor) | generation-stall, faulthandler | advisory credibility pass wedged on serial entailment loop | **KEYSTONE (B)** |
| Q72, Q76 | "generation_in_progress, ~0 sockets, no log" | **SAME wedge as Q90** (MODE A ≡ MODE B) | KEYSTONE (B); MODE A folds in |
| Q78 | `abort_excessive_gap` | entailment judge bricked its shared client → mass fail-closed over-drop + wrong abort label | **MODE C** |
| (silent deaths) | no faulthandler / no manifest | Codex MODE 1 (trafilatura SIGSEGV) + MODE 2 (OOM/SIGKILL) — **unconfirmed from source** | **CONTAINMENT (§6)** |

**The single most important reconciliation (overturns the task's premise that MODE A and MODE B are
distinct deaths):** Claude's MODE-A forensic and Codex's Mode-3 forensic BOTH conclude the
"generation 0-socket stall" on Q72/Q76/Q90 is the **advisory credibility pass** wedged at the *exact*
faulthandler site — `entailment_judge.py:126 _post_with_total_deadline ← :430 judge ←
provenance_generator.py:2056 verify_sentence_provenance ← credibility_pass.py:236 _verify_member_in_isolation
← :304 _assemble_baskets ← :521 _run_chain ← :400 run_credibility_analysis` inside a `ThreadPoolExecutor`
worker; main thread idle in the asyncio loop. **There is no separate MODE-A bug.** The "0 sockets" is the
transient inter-call window created when `_post_with_total_deadline` force-closes the hung socket on its
150 s per-call deadline (`entailment_judge.py:129 client.close`) before the bounded retry reopens a fresh
one. The contract-slot stall wall (`PG_CONTRACT_SLOT_STALL_TIMEOUT_S`) and the openrouter provider-pin
read-timeout are the **WRONG site** — the outline LLM call completed and logged (anchor log lines 8-10),
and Stage-2 per-section generation (`multi_section_generator.py:6685`) was never entered (`run_status`
`sections_done/total/claims_total` all null; zero section-gen log lines). **Do NOT add a MODE-A fix at the
stall-timeout / provider-pin site — it would contradict the verified root cause.**

**The ONLY hard gates** (CLAUDE.md §-1.3): `strict_verify` + NLI entailment + 4-role D8 + span-grounding.
A fix is **faithfulness-neutral iff** it never changes those verdicts, their thresholds, the fail-closed
`('ENTAILED','judge_error:…')` sentinel, the 0.40 section floor, or the set of cited evidence shipped.
The advisory credibility pass is NOT a gate (`credibility_pass.py:6-8,215,333-335` — `basket_verdict` is a
pure LABEL; `_verify_member_in_isolation` is never re-run as a gate). Every fix below is argued and tested
against exactly these invariants.

---

## ITEM 1 (KEYSTONE) — MODE B(a): wall-clock bound on the advisory credibility pass
_(Codex P2: the bound stops the AWAIT from hanging the run; `to_thread` is not cancellable so the leaked nested `ssl.recv` worker persists until process teardown — fine for one-query-per-VM — and ITEM 1b is what makes the pass actually COMPLETE within the wall. "Bound" here = the run never hangs, not that the worker is killed.)_

**This is the tourniquet that stops Q72/Q76/Q90 (and absorbs MODE A). Ship first.**

### Root cause (verified, file:line)
`multi_section_generator.py:6643` offloads the advisory pass via
`await asyncio.to_thread(_credibility_pass.run_credibility_analysis, …)` with **no `asyncio.wait_for`**
wrapper — contrast the per-section runner at `multi_section_generator.py:203` which IS wrapped
(`await asyncio.wait_for(runner(plan), timeout=wall)`). Inside, `credibility_pass._assemble_baskets`
(`:280-323`) is a **plain serial nested for-loop** over every basket member (309 distinct keys / 310-777
rows in the dead runs), each calling `_verify_member_in_isolation` (`:304`) → the PRODUCTION
`verify_sentence_provenance` (injected at `:518-523`) → the binding `entailment_judge.judge`
(`provenance_generator.py:2056`). Each judge call is ~6-40 s healthy, up to the 150 s per-call deadline on
a trickle/empty-content hit. The per-call `PG_ENTAILMENT_TOTAL_S=150` deadline DOES fire (Q76 log:
`total_deadline_exceeded_150s`; anchor `ev_184` progression proves the loop advances) — the kill is the
**SUM** over the unbounded-COUNT serial pass, with **no pass-level wall-deadline**. O(N)·(up-to-150 s) ≫
run-wall → slow death in `generation_in_progress`, never reaching Stage-2.

### The change (surgical) — steps 1-3
In `multi_section_generator.py` at the `else: # "run"` branch (`:6632-6683`):

**Step 1.** Add an env knob (LAW VI), near the other PG_* reads:
   ```python
   _cred_pass_wall_s = float(os.getenv("PG_CREDIBILITY_PASS_WALL_S", "600"))
   ```
   The default bounds the DEATH (the run can no longer hang indefinitely); it does NOT promise the pass
   COMPLETES. See the sizing reality immediately below, then steps 2-3.

### Sizing reality — the wall-deadline stops the death but the SERIAL pass cannot complete in any sane wall (so §7 #1 is a PRECONDITION, not a follow-up)
**Do not claim "comfortably above a healthy pass" — the per-call×count math refutes it.** The pass is
SERIAL over the whole corpus: ~310 members (Q90) up to ~619 (Q72), each entailment call ~6-40 s healthy. A
*healthy* serial pass floor is 310×6 s ≈ 31 min; a realistic case is 619×40 s ≈ 6.9 h — already past the
~10800 s (3 h) run-wall. **There is NO `PG_CREDIBILITY_PASS_WALL_S` value that both lets a large-corpus
serial pass finish AND stays under the run-wall.** Consequence: with ITEM 1 alone, on every large-corpus
run the pass completes only a prefix of members and then degrades to `credibility_analysis = None` /
sources UNSCORED + disclosed gap. That is faithfulness-safe (the disclosure is honest and the binding gates
are untouched), but it means the credibility WEIGHTING (the "WEIGHT" half of §-1.3 weight-and-consolidate)
ships **silently degraded on every real run** until the pass is parallelized.

**Therefore §7 #1 (parallelize `_assemble_baskets` with bounded parallelism + deterministic reassembly) is
pulled INTO this batch as ITEM 1b — it is the only way the advisory pass produces real output within a sane
wall.** With ~8-16 bounded workers a 619-member pass at 40 s drops to ~26-52 min, which a
`PG_CREDIBILITY_PASS_WALL_S=600`-1800 wall can clear. ITEM 1 (the wall-deadline) remains the required
backstop; ITEM 1b is what makes the pass actually complete. Faithfulness-neutral: bounded parallelism over
INDEPENDENT per-member isolated verifies (each member's claim vs its OWN single span — `credibility_pass.py:302-306`)
with deterministic post-step reassembly in the original `sorted(clusters)` / member order changes only
WALL-CLOCK, never which verdict any member gets (`_verify_member_in_isolation` is pure per-member) and never
a binding gate. Mirror P2's existing concurrency shape (`credibility_skill.py:302`) — and, like the
strict_verify parallel path (`provenance_generator.py` `_verify_in_context`), each worker MUST run under a
copied `contextvars.copy_context()` AND reconcile run-scoped cost/budget + raw-IO/judge telemetry back to the
parent (Codex P2); otherwise the parallel advisory verifies silently lose the run's cost accounting and
judge-telemetry ticks (the FX-09 ContextVar). Bound via `PG_CREDIBILITY_PASS_MAX_INFLIGHT` (LAW VI).
**Test:** identical baskets (same `basket_verdict` per cluster, same member order) serial vs. parallel on a
fixed corpus; wall-clock strictly lower; gate verdicts unchanged; AND run-scoped cost + judge-telemetry
totals identical serial vs. parallel (no lost ticks).

**HARD ORDERING CONSTRAINT (Codex P2, iter-1):** ITEM 1b's parallel per-member verifies all call the
binding `entailment_judge` through the SHARED-SINGLETON client (`_get_judge()`). Running them concurrently
BEFORE ITEM 2a makes that client thread-safe/thread-local re-introduces the exact cross-thread
close/rebuild race ITEM 2 fixes (the `[X509]`/closed-client cascade). Therefore **ITEM 1b MUST NOT be
enabled until ITEM 2a (thread-safety / per-thread client) has landed** — 1b and 2a ship in the same
keystone batch and 1b's parallelism flag stays inert until 2a is present. This is reflected in §8 step 1.

**Step 2.** Wrap the existing offload (`:6643-6654`) in `asyncio.wait_for`:
   ```python
   credibility_analysis = await asyncio.wait_for(
       asyncio.to_thread(
           _credibility_pass.run_credibility_analysis,
           research_question, list(evidence_pool.values()),
           gov_suffixes=tuple(credibility_pass_gov_suffixes), domain=(domain or None),
           judge=credibility_pass_judge,
       ),
       timeout=_cred_pass_wall_s,
   )
   ```

**Step 3.** **Widen the existing degrade-except** at `:6655` from `except _credibility_pass.CredibilityPassError`
   to `except (asyncio.TimeoutError, _credibility_pass.CredibilityPassError) as _cred_exc:`. The body is
   UNCHANGED — it already does exactly the right thing: under always-release set
   `credibility_analysis = None` + emit the LOUD `_credibility_disclosed_gap`
   (`:6665-6675`); under always-release-OFF `raise` (byte-identical legacy). Update the disclosed-gap
   string to name the timeout cause when the exc is a `TimeoutError`. The `finally` cost-reconcile
   (`:6676-6683`) already runs on every exit path — leave it.

### Why faithfulness-NEUTRAL (proven against the 3 binding gates)
- The pass is ADVISORY by construction (`credibility_pass.py:6-8,215,333-335`; `basket_verdict` is a pure
  LABEL that "NEVER feeds is_verified / strict_verify").
- `credibility_analysis = None` is an ALREADY-supported shipping state: all four `apply_disclosure_to_svs`
  consumers are `is not None`-guarded (documented at `multi_section_generator.py:6610-6611`), so None →
  sources ship UNSCORED at neutral credibility weight ("weight don't filter") + a disclosed gap — the
  operator-locked B5/B7 "nothing shall hold the report" posture. This is gentler than, and identical in
  effect to, the existing `CredibilityPassError` degrade.
- `strict_verify`, NLI entailment, the 4-role D8 release policy, and span-grounding run on the actual
  generated sentences **independent of** `credibility_analysis`; their verdicts/thresholds never read the
  basket labels. A timeout forfeits only the advisory disclosure, never a gate verdict, never a cited-source
  drop.
- OFF-path / always-release-OFF is byte-identical (`raise` preserved).

### Honest caveat (state it, don't hand-wave — per research_advisory_bound.md §0)
`asyncio.wait_for` frees the *await* but does **not** reclaim the `to_thread` worker (`to_thread` is not
cancellable), so the worker + its leaked nested `ssl.recv` thread keep running after the timeout. For this
campaign's **one-query-per-VM** model, process teardown reaps them — acceptable. For a long-lived
`--threads 2` worker the leaks accrue across questions; that is precisely why ITEM 2 (the entailment-judge
transport fix) exists.

### Test that proves it
`tests/polaris_graph/test_credibility_pass_wall_deadline.py` (new):
- **Bound fires + degrades:** inject a `run_credibility_analysis` stub that `time.sleep`s past
  `PG_CREDIBILITY_PASS_WALL_S` (set to ~0.1 s); assert `generate_multi_section_report` RETURNS (does not
  hang), `credibility_analysis is None`, the disclosed-gap string is emitted, and the report body + section
  `verified_text` are byte-identical to a run with the credibility pass disabled (proves no gate moved).
- **OFF path byte-identical:** with always-release OFF, the same timeout re-raises (legacy).
- **Healthy pass unaffected:** a fast stub completes within budget → `credibility_analysis` populated,
  identical to today.
- **Gate-invariance:** assert `strict_verify`/NLI/D8 verdicts on a fixed corpus are identical with the
  pass timed-out vs. completed (the only delta is the advisory disclosure).

---

## ITEM 2 — MODE B(b) + MODE C UNIFIED: entailment-judge transport redesign (trickle-cancel + self-heal + thread-safety)

**Unify, do not stack.** Both forensics target the SAME shared-singleton hazard in
`entailment_judge.py`. A per-call/thread-local client largely subsumes the "rebuild the shared singleton"
path. Present ONE coherent transport redesign. **This file is the BINDING NLI gate's own code → highest
neutrality risk → the test must prove verdict-INVARIANCE, not just "no longer hangs."**

### The three coupled defects (verified)
1. **No self-heal on the generic branch (MODE C — the Q78 run-killer).** The only
   `self._client = self._build_client()` rebuild sites are the ctor (`:277`) and the `TimeoutError` branch
   (`:441`). The generic `except Exception` retry path (`:532-542`) and the `_RetryableJudgeError` path
   (`:514-531`) NEVER rebuild. So a client closed/poisoned on any non-`TimeoutError` branch is **terminal**:
   Q78 log shows 2866 consecutive `Cannot send a request, as the client has been closed` over 33 min, only
   21 judge calls ever succeeded → 177 sentences fail-closed-dropped → `abort_excessive_gap`. The drops were
   verifier-outage, NOT missing evidence (corpus: 556 sources, adequacy=proceed).
2. **Shared mutable singleton with a cross-thread close/rebuild race (MODE B + C).** `self._client` is
   read/written by all verifier worker threads with no lock; `_post_with_total_deadline` force-closes it
   (`:129`) from one worker while another may be mid-`post` → the `[X509] PEM lib (_ssl.c:4166)` TLS-state
   corruption at Q78 22:32:58 (httpx Discussion #1633: close-while-in-flight on a shared client is
   explicitly discouraged; httpcore #550: poisons the pool).
3. **`client.close()` does NOT interrupt the blocked `ssl.recv` (MODE B trickle-leak).** Research
   (`research_trickle_cancellation.md` §3a, primary sources): on Linux `close()` does not wake a C-level
   `recv` in another thread — only `socket.shutdown(SHUT_RDWR)` on the **underlying TCP fd** does. So each
   trickle timeout LEAKS its nested POST worker (anchor Thread A still in `ssl.recv` after the timeout path
   ran on Thread B).

### The change (tiered — ship 2a+2b now; 2c is a tracked follow-up)

**2a. Self-heal + thread-safety (MODE C — REQUIRED, ships with the keystone):**
- In `judge()`'s generic `except Exception` branch (`:532-542`) AND the `_RetryableJudgeError` branch
  (`:514-531`): when the exception indicates a closed/poisoned transport (`httpx` "client has been closed",
  `httpx.ClientState.CLOSED`, or an `SSL`/`X509`/`PEM` transport fault — matched on type/string, NOT a
  parse fault), rebuild `self._client = self._build_client()` BEFORE the retry, exactly as `:441` does.
- Eliminate the cross-thread race: give each verifier worker its **own** client via `threading.local()`
  (preferred — `research_trickle_cancellation.md` §2 endorses per-thread for the cancellation path), OR
  guard `self._client` read+rebuild+force-close with a `threading.Lock`. Per-thread is cleaner and also
  the substrate ITEM 2b needs.
- Defensive: at the top of the attempt loop / in `_post_with_total_deadline`, `if self._client.is_closed:
  rebuild` proactively.

**2b. Trickle-cancel that actually interrupts the recv (MODE B(b) — the `needs_research` item;
Tier 1 of `research_trickle_cancellation.md`):**
- Move the judge POST onto a **per-call / throwaway `httpx.Client`** (never the shared singleton), so
  killing its socket can never poison a shared pool or race a sibling (httpcore #550 / httpx #1633).
- Capture the underlying TCP socket via a **custom httpcore `network_backend`** (clean, maintainable —
  §3d-2) that stashes the `SSLSocket`/fd in a per-call registry; fall back to a pinned-version private-attr
  descent (`pool → HTTPConnection._connection → _network_stream → _sock`) **guarded with `getattr` +
  fail-loud log if the path is missing** (LAW II — never silently no-op).
- Arm an **absolute-deadline watchdog** (`threading.Timer`/daemon) at submit; on expiry call
  `raw_sock.shutdown(socket.SHUT_RDWR)` on the captured fd (NOT on the `SSLSocket` wrapper — CPython #124618
  corrupts TLS; §3c). The blocked `recv` wakes, the worker raises a connection error and exits, the
  throwaway connection+client are discarded (`response.close()`/`client.close()` AFTER recv returns, per
  httpx #2139). Disarm on normal completion.
- **STOP calling `client.close()` on the shared `_JUDGE_SINGLETON` as a cancellation mechanism** — it is
  both ineffective (§3a) and a sibling/pool hazard (§2). Keep `PG_ENTAILMENT_TOTAL_S` as the deadline source
  (LAW VI). On shutdown-cancel, return the SAME fail-closed `('ENTAILED','judge_error:…')` sentinel.

**Scope decision for THIS redeploy — ship 2a now; DEMOTE 2b to fast-follow with 2c.** Per ITEM 1's honest
caveat, the campaign runs ONE query per VM, so process teardown reaps the leaked nested `ssl.recv` worker
between questions — the trickle-leak does NOT compound on a one-query-per-VM run. ITEM 2b (the custom
httpcore `network_backend` + `shutdown(SHUT_RDWR)` watchdog) is, by the research's own words,
"best-effort / version-fragile / private-ish socket access" and is the HIGHEST-fragility change on the
binding-gate file. Bundling it into the keystone batch adds Codex-gate convergence risk for ZERO benefit on
this redeploy. So: **ITEM 2a (self-heal + thread-safety) is the only must-ship-now from this item** — it is
the Q78 run-killer. **ITEM 2b ships as a fast-follow alongside 2c**, gated, with the long-lived
`--threads 2` worker as its justification (where leaks DO accrue). It stays specced here in full so the
research isn't lost, but it is OUT of the keystone PR batch.

**2c. Process-isolated judge POST (Tier 3, FOLLOW-UP ISSUE — do NOT bolt on):** if the long-lived
`--threads 2` worker still accrues leaks under load, escalate the judge POST to a
`ProcessPoolExecutor`-with-SIGKILL. Larger change; track separately. (Tier 2 async-judge-caller is the
clean long-term design but is a bigger refactor — also a separate issue.)

### Why faithfulness-NEUTRAL
Transport/lifecycle/cancellation ONLY. The verdict logic, the verdict-validation
(`verdict not in {ENTAILED,NEUTRAL,CONTRADICTED}` at `:502`), and the terminal fail-closed
`('ENTAILED','judge_error:…')` sentinel (`:548-549`) are **byte-unchanged**. The ONLY behavioral delta is
that a dead/trickled verifier comes back to life or fails fast instead of silently failing every claim
closed for the rest of the run — **faithfulness is STRENGTHENED (fewer false drops), never relaxed**: a
claim a healthy judge would call NEUTRAL/CONTRADICTED still fails closed and drops; a claim it would call
ENTAILED is now correctly verified instead of spuriously `judge_error`-dropped.

### Test that proves it (verdict-INVARIANCE is the load-bearing test)
`tests/polaris_graph/test_entailment_judge_transport.py` (new) — all hit a stub HTTP server (no real
provider):
- **Verdict-invariance:** the SAME judge input → the SAME `(verdict, reason)` before and after the
  redesign, for ENTAILED / NEUTRAL / CONTRADICTED / bad-verdict / empty-content cases. The fail-closed
  sentinel string is asserted byte-for-byte.
- **Self-heal (MODE C):** simulate a closed/poisoned client on attempt 1 (raise "client has been closed");
  assert attempt 2 rebuilds and succeeds → no permanent brick. Assert the SAME corpus that produced Q78's
  177-drop now verifies the recoverable claims (the over-drop disappears) while genuinely-unsupported claims
  still drop.
- **Thread-safety:** N concurrent judge calls where one trips the force-close path; assert no sibling
  call sees a closed client and no `[X509]`/closed-client cascade.
- **Trickle-cancel (MODE B(b)):** a trickle stub (dribbles 1 byte every few seconds, never closes); assert
  the call returns within ~`PG_ENTAILMENT_TOTAL_S` (+margin), the worker thread is reaped (no leaked
  `ssl.recv` thread after the deadline — assert via `threading.enumerate()`), and the returned verdict is
  the fail-closed sentinel.

---

## ITEM 3 — MODE C(2): correct abort cause-attribution (gap-abort pre-empts verifier-degraded)

### Root cause (verified, file:line)
The pipeline HAS the right guard — `abort_verifier_degraded`, fired when
`judge_error_rate > PG_MAX_JUDGE_ERROR_RATE` (`run_honest_sweep_r3.py:9100,9197-9268`), with a correct
~99%-rate per-run denominator (`_record_judge_outcome` ticks `judge_error` on every call;
telemetry context at `:3918-3921`). But the `abort_excessive_gap` branch executes and `return summary` at
**`:8662`**, which is BEFORE the verifier-degraded computation+abort at `:9080-9268`. So the dead-verifier
Q78 run was mis-labeled a coverage gap and its report.md told the operator to "widen retrieval" — the
exactly-wrong remedy.

### The change (surgical — LABEL only)
In `run_honest_sweep_r3.py`, compute `judge_error_degraded` and emit `abort_verifier_degraded` BEFORE the
`abort_excessive_gap` branch's `return summary` at `:8662`. Cleanest: hoist the judge-error-rate
computation (`:9100-9117`) above the excessive-gap gate (`:8576-8662`); if `judge_error_rate > _max_jerr`,
set `status=abort_verifier_degraded`, write the terminal manifest, and `return` — so a bricked verifier
aborts with the TRUE cause and the misleading "widen retrieval" next-step is suppressed.

### Why faithfulness-NEUTRAL
Relabels the abort REASON only. Both `abort_excessive_gap` and `abort_verifier_degraded` are non-success
aborts (no report ships); no verdict, no threshold, no `judge_error` sentinel, no 0.40 floor moves. This is
what SHOULD have fired tonight — the guard and its denominator already exist and are correct; they were
merely pre-empted by the early return.

**Interaction with the existing always-release branch (Codex P2, iter-1) — document, do not change.** The
later verifier-degraded handling at `run_honest_sweep_r3.py:9233-9249` has LABEL-AND-CONTINUE semantics
under always-release (it annotates degraded-verifier without necessarily terminating). The hoisted gate in
this item is a TERMINAL relabel that fires only on the `abort_excessive_gap` path (which already
`return`s — no report ships either way), so it does NOT alter the label-and-continue success path: when the
run is NOT gap-aborting, control still reaches `:9233-9249` unchanged. The build MUST preserve that — the
hoist adds a terminal `abort_verifier_degraded` ONLY where `abort_excessive_gap` would otherwise have
returned a mis-labeled gap; it must not pre-empt or duplicate the `:9233-9249` always-release annotation on
the non-gap path. Test the non-gap path (below) to prove no regression there.

### What NOT to do (binding)
- Do NOT lower `PG_MIN_VERIFIED_SECTION_FRACTION`. **Floor-value note (Codex P2, iter-1):** the
  `run_honest_sweep_r3.py` CODE DEFAULT is `0.5`; the Gate-B benchmark slate FORCE-SETS
  `PG_MIN_VERIFIED_SECTION_FRACTION=0.4` (`run_gate_b.py`). The operative clinical-safety
  coverage-honesty floor on the benchmark path is therefore the **0.40 Gate-B slate value** — this plan
  does NOT lower it (or the 0.5 code default); references to "the 0.40 floor" mean the Gate-B slate value
  in force on the run path.
- Do NOT relax `PG_STRICT_VERIFY_ENTAILMENT=enforce` or soften the `judge_error:` fail-closed sentinel
  (that converts a dead verifier into silent fabrication-passing).
- Do NOT "widen retrieval" — the corpus was already rich; the bottleneck was the verifier (fixed by ITEM 2).
- The FDA-label/regulatory anti-bot shells (Q78 re3 L42/L58/L74, 41 fetch-degraded rows) ARE a genuine gap
  for the Regulatory slot → the floor correctly holds for those; fix via the cross-file A1/A15 re-fetch,
  NOT the floor (separate follow-up, not this plan).

### Test that proves it
`tests/polaris_graph/test_abort_attribution_ordering.py` (new): drive a run where
`judge_error_rate > PG_MAX_JUDGE_ERROR_RATE` AND `verified_sections < floor`; assert
`summary["status"] == "abort_verifier_degraded"` (NOT `abort_excessive_gap`) and the manifest carries the
verifier-degraded fields. Complement: judge healthy but a section genuinely below floor → still
`abort_excessive_gap` (no regression).

---

## ITEM 4 — SENTINEL DEPLOY: ship commit 376ac812 (PG_SENTINEL_TRANSPORT_DEGRADE) to all boxes

### What it is (verified)
Commit `376ac812` "I-arch-007: sentinel transport-fault degrade-and-continue (B5/B7 #1257)". A single
blank/non-JSON sentinel HTTP-200 raised `RoleTransportError` → propagated → `sweep_integration` tore down
the WHOLE D8 seam → coverage hardcoded 0.0 → `curator_gap` (the literal cause of old Q90 emptiness, ~177
claims). The fix marks ONLY that claim `sentinel-unavailable` (fail-closed UNGROUNDED, never GROUNDED) and
the D8 seam CONTINUES with real coverage. Gated `PG_SENTINEL_TRANSPORT_DEGRADE` (default-ON); OFF =
byte-identical legacy. Codex APPROVE 0 P0/P1; 33/33 sentinel tests pass.
Touches `src/polaris_graph/roles/sentinel_adapter.py` + `tests/polaris_graph/test_run11_010_degraders.py`.

### Why faithfulness-NEUTRAL
A transport fault on the SENTINEL fails CLOSED (UNGROUNDED, never GROUNDED) — it can never pass a fabrication
as grounded. It only prevents one transport blip from zeroing the whole D8 coverage. Faithfulness
STRENGTHENED.

### Explicit clarification the task demands
**`PG_PARALLEL_VERIFY=1` is NOT the fix for MODE B.** The faulthandler proves the hang is the ADVISORY
CREDIBILITY PASS's serial entailment loop (`credibility_pass._assemble_baskets`), NOT `strict_verify`'s
verifier pool. Parallelizing strict_verify would not touch the credibility-pass chokepoint and would not
stop Q72/Q76/Q90. (Parallelizing the credibility-pass per-member loop is a SEPARATE faithfulness-neutral
follow-up — see §7 — but it is not the keystone and not this item.)

### Action + test
Deploy: this commit is already on the branch; confirm it is present in the deploy checkout on each of the 5
boxes (`git log --oneline | grep 376ac812`) and that `PG_SENTINEL_TRANSPORT_DEGRADE` is ON in the run slate.
Test: the committed `test_run11_010_degraders.py` (33/33) is the proof; behavioral preflight asserts a
forced sentinel blank-200 → D8 seam continues with non-zero coverage (one claim UNGROUNDED), not a
curator_gap collapse.

---

## ITEM 5 — GENERATION CHECKPOINT: wire postgen_checkpoint.json so resume skips generation, re-runs verification only

### Confirmed state (this is the answer the task asks for)
The A12 `postgen_checkpoint.json` is **written but NOT consumed to skip generation**. Verified:
- Written at `run_honest_sweep_r3.py:8172` (`write_postgen_checkpoint`, `:2509`) right after generation,
  before verification. Payload is **DATA ONLY** (`raw_drafts` + identity hashes), verdict-free, with a
  fail-loud loader that rejects any leaked verdict key (`load_a12_checkpoint`, `:2601-2625`;
  `_A12_FORBIDDEN_VERDICT_KEYS`, `:2587-2598`).
- On `--resume` it is LOADED at `:4194` but the comment at `:5043-5046` is explicit: *"The re-entry above
  re-runs generation + EVERY gate on the reloaded corpus; the A12 payloads are verdict-free DATA"* — the
  payload is only **surfaced/logged** (`:5046-5058`), never used to bypass Stage-2 generation. **It needs
  wiring.**

### Why the wiring is safe (the `raw_draft` provenance check — BLOCKING, now resolved)
`raw_draft` is the **PRE-strict-verify** raw generator output, confirmed:
`multi_section_generator.py:2429` (`Returns (raw_draft, …)`), the dataclass field `:825-827` (`raw_draft`
is distinct from `verified_text`, which is "after strict_verify + citation resolution"), and `:3948`
(`raw_draft=raw`) vs `:3950` (`verified_text=verified_text`). Therefore reusing `raw_drafts` on resume
skips ONLY the generator LLM calls + the advisory credibility pass; **strict_verify, NLI, the 4-role D8
gate, and span-grounding all RE-RUN from scratch** on the reused drafts. This is faithfulness-neutral AND it
is precisely the Q78 over-drop experiment (re-verify the same drafts with a HEALTHY judge from ITEM 2).

### Re-entry-completeness PRECONDITION (Codex P1, iter-1 — resolved here, do NOT skip)
`raw_drafts` alone is NOT enough to re-enter the existing post-generation verification path losslessly.
The verification stage consumes per-section `SectionPlan` metadata + the per-section atom/claim catalogs
(which atoms/claims belong to each section, their evidence bindings) — NOT just the raw section text. The
current `postgen_checkpoint.json` payload (`write_postgen_checkpoint`, `:2509-2544`) stores ONLY
`raw_drafts` (section_id→text) + `evidence_ids`/hashes + model/env pins. So a resume that reconstructs
ONLY `raw_drafts` cannot deterministically re-enter strict_verify/NLI/D8 the way a fresh run does. The
fix MUST close that gap one of two ways (pick (a); (b) is the fallback):
**(a) — preferred: extend the DATA-ONLY postgen checkpoint** to also persist the verdict-FREE section
metadata the verification path needs — the per-section `SectionPlan` (section id/title/atom-id list) and
the per-section atom/claim catalog (atom→evidence-id/span bindings), all of which are PRE-verdict DATA
(no `is_verified`, no release_outcome — they remain subject to the `_A12_FORBIDDEN_VERDICT_KEYS` guard).
This keeps the checkpoint data-only and lets the resume re-enter losslessly. **(b) — fallback:**
deterministically RECOMPUTE that section/atom structure from the hash-checked `corpus_snapshot` +
`raw_drafts` BEFORE bypassing generation (same code path generation uses to build it, minus the LLM
draft call). Either way the structure is recomputed/loaded as verdict-free DATA, and every binding gate
still re-runs on it. If neither is feasible within the keystone batch, ITEM 5 is DEFERRED and Q78 simply
re-generates from `corpus_snapshot` like the other four (the postverify checkpoint is NOT usable — see note).

**Note — `postverify_checkpoint.json` is NOT usable for the Q78 over-drop re-verify (Codex P1, dual-agree
iter-1 — CORRECTED).** A SECOND data-only checkpoint exists (`write_postverify_checkpoint`, `:2547-2580`;
loaded `:4195` as `_a12_postverify_payload`) storing per-sentence `verification_details` ACCOUNTING
(kept/dropped/drop-reason) — but it is written **AFTER** strict_verify/NLI already ran. Reusing it re-enters
RIGHT AFTER verification and would **NOT** re-run the (now ITEM-2a-healed) entailment judge, so Q78's 177
`judge_error` fail-closed drops stay **baked in** — the exact opposite of the over-drop experiment.
**Therefore Q78 MUST use the COMPLETE postgen re-entry (ITEM 5a — re-runs strict_verify + NLI + D8 on the
reused `raw_drafts` with the healed judge), OR regenerate from `corpus_snapshot`.** The postverify path is
explicitly REJECTED for this experiment.

### The change (surgical, gated, fail-loud)
- New env gate `PG_RESUME_REUSE_POSTGEN` (LAW VI, default OFF → byte-identical today). When ON and
  `_a12_postgen_payload is not None` and its `evidence_id_hash` matches the reloaded corpus
  (`_a12_hash(sorted(evidence_ids))`) — else FAIL LOUD, never silently re-generate against a different
  corpus — reconstruct the section `raw_draft`s AND the verdict-free section/atom structure (per the
  re-entry-completeness precondition above: either loaded from the extended checkpoint (a) or recomputed
  from the hash-checked corpus (b)) and enter the verification stage directly, **skipping Stage-2
  generation AND the advisory credibility pass**.
- Re-run strict_verify + NLI + D8 on the reused drafts exactly as a fresh run does. The checkpoint's
  fail-loud verdict-key guard already makes "replay a stored decision" structurally impossible (§-1.3);
  the extended section/atom metadata stays subject to the SAME `_A12_FORBIDDEN_VERDICT_KEYS` guard.
- Keep the existing surface-log path; the only addition is the actual short-circuit behind the new gate.

### Why faithfulness-NEUTRAL
Skips only generation (raw LLM drafting) + the advisory credibility pass — NEITHER is a faithfulness gate.
Every binding gate re-runs on the reused drafts; the corpus-hash guard prevents reusing drafts against a
mismatched corpus; the verdict-key guard prevents replaying a decision. Output is identical to a fresh run
that happened to generate the same drafts, **except** the advisory credibility disclosure (a postgen-resume
skips the credibility pass — but a fresh large-corpus run would also degrade that disclosure to unscored per
ITEM 1's sizing reality, so the binding output is unchanged).

### Scope reality — only Q78 has a postgen checkpoint (this gates which runs ITEM 5 helps)
The credibility pass runs BEFORE Stage-2 generation (`:6643` vs `:6685`) and `write_postgen_checkpoint`
fires AFTER generation returns (`:8172`). **Q72/Q76/Q90 died INSIDE the credibility pass — pre-Stage-2,
pre-postgen-write — so they NEVER wrote a postgen checkpoint.** Only Q78 (which died at
`abort_excessive_gap`, after gen+verify completed) has one. So ITEM 5's wiring helps exactly ONE run: Q78,
the cents-cost over-drop re-verify experiment (re-verify the same drafts with the ITEM-2a healthy judge).
The other four must resume from `corpus_snapshot` and re-generate (ITEM 1 stops the re-wedge). This is
reflected in §8 step 5.

### Test that proves it
`tests/polaris_graph/test_resume_reuse_postgen.py` (new):
- **Skips generation:** with `PG_RESUME_REUSE_POSTGEN=1` and a postgen checkpoint present, assert ZERO
  generator section-LLM calls fire on resume (spy on the section LLM call) AND strict_verify/NLI/D8 DO fire
  (gate re-run preserved).
- **Corpus-hash mismatch fails loud:** a checkpoint whose `evidence_id_hash` ≠ the reloaded corpus → raises,
  never silently re-generates.
- **Re-entry completeness (Codex P1):** assert the verification stage re-entered from a reused checkpoint
  has the SAME per-section `SectionPlan` + atom/claim catalog it would have on a fresh run for the same
  drafts (loaded-or-recomputed), and produces strict_verify/NLI/D8 verdicts identical to a fresh run that
  generated those drafts — i.e. raw_drafts-only is provably insufficient and the metadata path is exercised.
- **Default OFF byte-identical:** gate unset → today's behavior (re-generate).

---

## ITEM 6 — CONTAINMENT (Codex MODE 1 + MODE 2): force subprocess containment + per-query memory isolation

**Codex independently raised these two death modes and could NOT root-cause them from source alone. A plan
both parties sign cannot drop them — fold them in as containment, flagged UNCONFIRMED pending external
traces.**

### MODE 1 — native libxml2 / trafilatura SIGSEGV (containment gap, not a confirmed active bypass)
Codex: all active `trafilatura.extract` call sites route through `safe_trafilatura_extract`
(`access_bypass.py:1950/2261/2607/2658`, `ingest.py:505/1571`, `live_retriever.py:1741-1742`,
`frame_fetcher.py:998-1001`). BUT the wrapper has an in-process path when `PG_TRAFILATURA_SUBPROCESS != "1"`
(`access_bypass.py:461-465`; docstring `:453-458` admits in-process SIGSEGV is uncatchable), and Gate-B only
**`setdefault`s** that env at `run_gate_b.py:1543` — so an existing override can leave containment OFF.
- **Change:** force `PG_TRAFILATURA_SUBPROCESS=1` for every benchmark run (set explicitly, not
  `setdefault`, in the Gate-B path / run slate). Also audit the readability-lxml fallback that still uses
  lxml after size-gating (`live_retriever.py:1713-1717`).
- **Faithfulness-NEUTRAL:** affects fetch robustness/yield only — never a gate verdict.
- **UNCONFIRMED:** needs the crashed-run stderr/faulthandler/dmesg + effective env (esp.
  `PG_TRAFILATURA_SUBPROCESS`) from the silent-death boxes to confirm this was the mechanism.
- **Test:** assert the effective env in a Gate-B benchmark run has `PG_TRAFILATURA_SUBPROCESS=1` (not merely
  defaulted); a fixture HTML that crashes in-process is contained to the subprocess (parent survives,
  fetch-degraded row emitted).

### MODE 2 — silent death / suspected OOM (containment gap, unconfirmed)
Codex: the Gate-B path enables faulthandler (`run_gate_b.py:2005-2008`), wraps query exceptions + writes
crash records (`:2252-2311`), and has terminal manifest backstops (`run_honest_sweep_r3.py:3755-3799`). A
truly silent death with NO faulthandler and NO manifest is consistent with SIGKILL/OOM-killer/external
termination (Python handlers/finalizers don't run). `os._exit` only in diagnostic scripts, not the Gate-B
path.
- **Change:** run each query in a parent-supervised subprocess/cgroup/VM with a memory limit; the parent
  writes a manifest on child rc -9 / OOM and captures stderr; cap fetch/browser/trafilatura child
  concurrency. (For this campaign's one-query-per-VM model, the VM IS the isolation boundary — ensure the
  supervisor records an OOM/SIGKILL exit as a loud `error_*` manifest rather than a silent gap.)
- **Faithfulness-NEUTRAL:** changes containment + failure REPORTING, not any gate verdict.
- **RULED OUT for tonight's 5 runs (box evidence gathered 2026-06-16 ~23:55Z):** all four reachable boxes
  show cgroup `oom_kill 0`, no `dmesg` OOM lines, and massive headroom (total 257–709 GB, free 48–218 GB).
  Q78 died with a clean `abort_excessive_gap` manifest (not a silent death). So OOM did NOT kill tonight's
  runs — this item is **precautionary hardening**, not the confirmed cause. (The "3-on-one-box OOM" was a
  prior incident; tonight is one-VM-per-query on huge boxes.) Keep it for robustness of the supervisor's
  OOM-reporting, ship it OUTSIDE the keystone batch.
- **Test:** simulate a child SIGKILL → parent writes an `error_*`/OOM manifest (not a silent missing
  manifest, not a mis-attributed gap).

---

## §7 — Follow-ups (tracked, explicitly NOT bolted onto this plan)

1. ~~Parallelize the credibility-pass per-member verify~~ — **PROMOTED to ITEM 1b in the keystone batch**
   (the sizing reality makes it a precondition, not a follow-up). Listed here only to mark the move.
2. **Chase the GLM-5.1 empty-content blank** (`Expecting value: line 1 column 1 (char 0)`) — the mirror
   returning empty 200s is the UPSTREAM cause of the deadline cascade. Fixing it makes each call fast; the
   wall-deadline (ITEM 1) remains the required backstop. Own issue.
3. **Tier 2 async judge caller** and **Tier 3 process-isolated judge POST** (ITEM 2c) — durable
   cancellation hardening for the long-lived `--threads 2` worker. Own issues.
4. **A1/A15 FDA-label / regulatory re-fetch** — un-shell the anti-bot regulatory sources so the Regulatory
   slot has real evidence (the genuine gap the 0.40 floor correctly holds for). Own issue.

---

## §8 — REDEPLOY SEQUENCE (keystone-first)

1. **Build, in this order (keystone-first). KEYSTONE BATCH = the runs cannot redeploy without these:**
   - ITEM 1 (credibility-pass wall-deadline) — the tourniquet.
   - ITEM 2a (entailment self-heal + thread-safety) — required with the keystone (the Q78 run-killer),
     **and a HARD PRECONDITION for ITEM 1b** (1b's parallel verifies share the singleton judge client; 2a
     must make it thread-safe/thread-local FIRST — Codex P2).
   - ITEM 1b (parallelize `_assemble_baskets`) — PRECONDITION for the pass to complete in any sane wall
     (per the sizing reality); without it the WEIGHT half ships unscored on every large-corpus run.
     **Enable 1b's parallelism flag only AFTER 2a is present** (ordering constraint above).
   - ITEM 3 (abort attribution ordering) — small LABEL fix.
   - ITEM 4 (confirm 376ac812 deployed + flag ON) — deploy-only, no new code.
   - ITEM 5 (postgen resume wiring, gated OFF by default).
   - ITEM 6 (force `PG_TRAFILATURA_SUBPROCESS=1` + OOM-reporting containment).
   **FAST-FOLLOW (separate batch, NOT the keystone): ITEM 2b (trickle-cancel transport) + 2c** — demoted
   per the ITEM-2 scope decision (one-query-per-VM teardown reaps the leak; 2b is the highest-fragility
   binding-gate change, no benefit this redeploy).
   File-collision note: ITEMs 1+1b share `multi_section_generator.py`/`credibility_pass.py`; ITEMs 2a (and
   later 2b) share `entailment_judge.py` → build each shared file SERIALLY in one lane; the
   non-colliding items (3, 5, 6) parallelize.
   **PR-split note (200-LOC §3.0 halt cap + the 2a-before-1b ordering constraint — Codex P1#2):** six items
   in ONE diff blows the 200-LOC cap. Split into bounded PRs, each its own Codex diff gate, in an order that
   NEVER enables 1b's parallel credibility verifies before 2a's thread-safe judge client exists:
   **PR-1 = ITEM 1 (wall-deadline) + ITEM 2a (entailment self-heal + thread-safe/thread-local client)** — the
   tourniquet + the safe client, the must-ship pair; **PR-2 = ITEM 1b (parallelize `_assemble_baskets`)** —
   now safe because 2a's thread-local client landed in PR-1; PR-3 = ITEM 3; PR-4 = ITEM 5; PR-5 = ITEM 6.
   ITEM 4 is deploy-only (no PR). 1b's `PG_CREDIBILITY_PASS_MAX_INFLIGHT` stays at 1 (serial) until PR-2.
   Build back-to-back; do not pause between merges (§8.2).
2. **Self-test:** run every new test above + the existing faithfulness-guard suite (must stay green).
3. **Codex diff gate per PR** (§-1.2 / §8.3.1 cap-5 brief, front-loaded). Faithfulness-neutrality of each
   item is the headline Codex must verify (esp. ITEM 2a — the binding judge — and ITEM 1b — basket parity).
4. **Behavioral preflight canary** before any paid redeploy: a 1-query run that exercises the credibility
   pass + a forced trickle/closed-client to prove the wall-deadline degrades, the parallel pass produces
   identical baskets, and the judge self-heals.
5. **Redeploy all 5 from the nearest checkpoint (per the ITEM-5 scope reality — only Q78 has a postgen
   checkpoint):**
   - **Q78** → re-VERIFY the same drafts with the ITEM-2a healthy judge. The checkpoint MUST re-run
     strict_verify/NLI/D8 (Codex P1#1): use `postgen_checkpoint.json` with `PG_RESUME_REUSE_POSTGEN=1` ONLY
     AFTER the ITEM-5a section/atom re-entry-metadata gap is closed (checkpoint-extended or recomputed).
     **`postverify_checkpoint.json` is REJECTED** — it is post-verification, so it would NOT re-run the
     healed judge and the 177 drops would stay baked in. **If ITEM 5a is not re-entry-complete in this batch,
     Q78 simply re-generates from `corpus_snapshot` like the other four** (ITEM 1+2a stop the re-wedge; the
     over-drop fix still applies on the fresh run). Either way this IS the over-drop experiment: the 177
     `judge_error` drops resolve into real ENTAILED/NEUTRAL verdicts, most sections clear the 0.40 Gate-B
     floor, and only genuinely shell-sourced regulatory slots stay gap-stubbed.
   - **Q72 / Q76 / Q90 / (the silent-death run)** → resume from `corpus_snapshot` → re-GENERATE + verify
     (they died inside the credibility pass, pre-postgen-write, so no postgen checkpoint exists). ITEM 1
     stops the re-wedge; ITEM 1b lets the pass complete.
   - One query per VM (sidesteps the multi-on-one-box OOM).
6. **Target: ONE completed run, §-1.1 line-by-line audited** (claim-by-claim against fetched span text) —
   the only acceptance signal. "Gates green" ≠ faithful; the audit on the REAL output is the gate.

---

## §9 — Faithfulness-neutrality summary (the signable invariant)

Every item touches ONLY: an advisory-stage wall-deadline (ITEM 1), bounded parallelism over INDEPENDENT
advisory per-member verifies with deterministic reassembly (ITEM 1b), transport/lifecycle/cancellation in
the judge (ITEM 2), an abort LABEL (ITEM 3), a D8-seam transport degrade that fails CLOSED (ITEM 4), a
generation+advisory-pass skip that re-runs all gates (ITEM 5), and process/parser containment + failure
reporting (ITEM 6). **NONE** changes `strict_verify`, the NLI entailment thresholds, the 4-role D8 verdicts,
span-grounding, the fail-closed `('ENTAILED','judge_error:…')` sentinel, or the section floor
(`PG_MIN_VERIFIED_SECTION_FRACTION` — code default 0.5, Gate-B slate force-set to 0.40; neither lowered).
Faithfulness is in several places STRENGTHENED (fewer false drops, no D8-seam zeroing) and **NEVER relaxed**.

---

## §10 — DUAL-AGREE VERDICT (Claude ∧ Codex)

**Codex dual-agree gate: `verdict: APPROVE` (iter-2, 0 P0, 0 P1).** Iter-1 raised 2 P1 (Q78 postverify
path; 1b-before-2a ordering) + 2 P2 — all addressed in this revision; iter-2 confirms.

**Codex P2 advisories — BINDING build-time requirements (fold into the keystone PRs, not blockers):**
1. **Wall ↔ inflight pinning:** set `PG_CREDIBILITY_PASS_WALL_S` together with `PG_CREDIBILITY_PASS_MAX_INFLIGHT`
   so a HEALTHY large-corpus pass completes within the wall (default 600 s + low inflight can still degrade a
   healthy pass to unscored). Size them as a pair in the run slate; document the chosen pair in §8.
2. **2b deferral is conditional:** deferring the trickle-cancel (2b) is valid ONLY because the one-query-per-VM
   teardown hard-reaps the stuck `recv` thread. Build-step: VERIFY the supervisor/VM actually reaps it (the
   leaked thread must not survive into the next query) before relying on the deferral; if a long-lived
   `--threads N` worker is ever used, 2b is REQUIRED.
3. **Recursive verdict-key guard (ITEM 5):** the postgen checkpoint's `_A12_FORBIDDEN_VERDICT_KEYS` guard is
   top-level only; the extended nested section/atom metadata MUST be validated RECURSIVELY (or fail-loud
   regenerate) so no verdict key leaks through a nested structure.

These are tuning/validation refinements, not gate changes — every item remains faithfulness-neutral.
