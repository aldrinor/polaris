# FOUNDATION (WAVE 0) — ADVERSARIAL STRESS BATTERY: SIGNED OFF

Branch: `bot/foundation-core`. Date: 2026-07-10 (I-fetch-lock).

The WAVE-0 foundation (RunConfig control surface + cp0..cp6 checkpoint
envelope, locked in `foundation_locked.md`) was put through a full adversarial
offline stress battery built to BREAK it, not to go green. **Every case held.
Zero breaks.**

- **Total cases: 23** (Front A = RunConfig resolver, 6 cases A1–A6; Front B =
  checkpoint envelope, 11 cases B1–B11; Front C = cross-module resume+adjust,
  6 cases C1–C6).
- **Result: hold=23, break=0, total=23. Exit code 0.**
- The battery's exit code is 0 iff break==0 — a non-zero exit is the honest
  sign-off signal that at least one invariant broke. It exited 0.

This is not the self-test slice. `foundation_selftest.py` proves the five
acceptance conditions on a hand-picked slice. This battery attacks the SAME two
modules across their WHOLE surface (all 38 knobs × all layers, every checkpoint
guard, the full resume+adjust contract) and several cases are deliberately
crafted to expose a gap. None did.

---

## 1. The passing iter — what we signed off

- **Commit `a60544a2`** — "foundation_stress A5: behavioral prompt-settability
  check (fix bad test case)" is HEAD of `bot/foundation-core` and the passing
  iter for the full 23/23 green.
- Harness landed at `2883da55` ("adversarial offline stress battery (A/B/C)"),
  hardened at `848867d4` (A5 — every registered knob prompt-settable) and
  `a60544a2` (A5 behavioral prompt-settability, the passing iter).

Re-run at sign-off time (pure logic — no network, no GPU, no LLM):

```
python scripts/foundation_stress.py --out .codex/I-fetch-lock/stress_out
...
SUMMARY hold=23 break=0 total=23
EXIT=0
```

- **Harness path:** `C:/POLARIS/scripts/foundation_stress.py`
- **Stress out dir:** `C:/POLARIS/.codex/I-fetch-lock/stress_out/`
  (`summary.json` — the machine verdict; `stress_run.log` — the full per-case
  transcript)

Every quote below is the harness's own machine-written evidence string,
verbatim from `stress_out/summary.json`.

---

## 2. The hardest cases — quoted verbatim

### (a) PRECEDENCE MATRIX — A4, the full 38-knob four-layer sweep

Not the single-knob ladder the self-test shows. A4 drives the WHOLE registry:
for every one of the 38 knobs it sets panel+prompt+env at once and asserts panel
wins; strips panel and asserts prompt beats env; strips prompt and asserts the
14 env-backed knobs resolve to env; strips everything and asserts the code
default returns with the code-default VALUE. 152 resolutions, zero mismatches.

> `matrix 38 knobs: panel-wins=38/38 prompt-wins=38/38 env-wins=14/14`
> `default=38/38 mismatches=none`

### (b) TAMPER DETECTION — B8 (index-sha) + B9 (hash chain)

A saved checkpoint is silently edited on disk after write, then loaded. The
index holds the OLD sha, so the load must refuse. Then a clean 3-link chain is
built, one middle link (cp1) is tampered on disk, and the chain validator must
catch it.

> **B8:** `tampered payload caught by index-sha=True :: resume: cp0 on-disk`
> `sha256 does not match the index rec`

> **B9:** `clean chain=['cp0', 'cp1', 'cp2'] valid=True; cp1 tamper`
> `caught=True :: chain: cp1 on-disk sha256 != index record — T`

A silent post-write edit cannot survive either the per-file index-sha guard or
the end-to-end hash chain.

### (c) RESUME-WITH-ADJUSTMENT — C6, the full cross-module contract

Save cp0..cp5, resume at cp3 with a legal downstream-only `tone` adjustment.
The resume must re-run only cp4..cp6, leave cp0..cp3 sha256 untouched,
supersede-not-delete the downstream checkpoints (archive + index record), and
the chain must still validate up to cp3.

> `resume cp3 rerun=('cp4', 'cp5', 'cp6'); upstream_untouched=True;`
> `downstream_superseded=True archived=2026-07-10T110613Z recorded=True;`
> `chain<=cp3 ok=True`

And the paired negative — an out-of-scope (upstream) breadth adjustment at the
same resume point is fail-loud rejected (C2):

> `query_count adjust @cp3 refused=True :: resume --adjust: knob 'query_count'`
> `cannot be adjusted when resuming a`

### (d) INJECTION HANDLING — B1 + B2 + B11, forbidden-verdict smuggling

The data-only guarantee under attack: a caller tries to inject a faithfulness
verdict into a data-only checkpoint. Top-level key, deep-nested key, and a
hand-crafted well-formed envelope that skipped `save` — all three must be
refused, on BOTH the save path and the load path, recursively at every nesting
depth.

> **B1 (top level, SAVE):** `top-level verdict key refused=True :: checkpoint`
> `payload at cp3.payload contains FORBIDDEN verdict key(s) ['`

> **B2 (nested deep, SAVE):** `nested verdict key refused=True :: checkpoint`
> `payload at cp3.payload.baskets[0].meta contains FORBIDDEN v`

> **B11 (load-side, envelope that bypassed save):** `load-side verdict guard`
> `fired=True :: checkpoint payload at cp0.payload.section.nested contai`

A stored decision can never be smuggled in and replayed. A resume always re-runs
the real faithfulness gate from reloaded data (§-1.3 data-only, LAW II
fail-loud). The prompt-parse side of injection is covered too: A5 proves every
knob is settable from a crafted prompt directive with a verbatim span, so a
parsed value is always a real span match, never an invented number.

### (e) VOLUME — A5, every one of 38 knobs on both surfaces, behaviorally

The whole-surface volume sweep. A5 does not sample. For each of the 38
registered knobs it crafts an explicit prompt directive, parses it, and asserts
the parsed value carries a verbatim span AND wins resolution as `source=prompt`;
and independently asserts a type-valid panel override resolves as
`source=panel`. Every knob, both surfaces, zero gaps.

> `both-surface coverage panel=38/38 prompt(BEHAVIORAL)=38/38`
> `NOT_PROMPT_SETTABLE=[]`

Paired with A4's 152-resolution matrix, the full 38-knob surface is exercised at
volume with no hand-picked slice and no un-settable knob.

---

## 3. The remaining cases (all HOLD)

- **A1** four-layer precedence, panel wins, prompt span verbatim.
- **A2** `adjust` layer outranks panel.
- **A3** prompt beats env beats default, per-layer isolation.
- **A6** malformed int coercion is fail-loud (`'abc'`, `'3.5'` both raise);
  disclosed OBSERVATION: a negative int is accepted (resolver contracts
  type-only, no lower-bound guard — an honest gap surfaced in evidence, not a
  break of the guaranteed contract).
- **B3** byte-identical save/read round-trip (926B, re-serialize == on-disk).
- **B4** `schema_version=999` refused on load (stale-shape pin).
- **B5** stage/filename mismatch refused (cp0 envelope in cp1's file).
- **B6** GATE0 question_sha identity: golden #75 loads, golden #76 refused.
- **B7** flag_slate divergence (0 != 1) refused on load.
- **B10** resume resolver: present cp resolves, absent cp refused.
- **C1** adjustment validity matrix: `query_count@cp3=False`, `tone@cp3=True`,
  `query_count@cp0=True`, `section_concurrency@cp5=False`.
- **C3** valid downstream `tone` adjustment resolves via the adjust layer.
- **C4** config_sha deterministic AND sensitive to a one-knob change.
- **C5** adjust beats a pre-existing panel value through the resume path.

---

## 4. How to re-prove it (offline, no spend)

```
python scripts/foundation_stress.py --out <any_out_dir>
```

Pure logic — no network, GPU, or LLM. Prints one `CASE <id> <verdict> :: <evidence>`
line per case, writes `<out_dir>/summary.json`, prints
`SUMMARY hold=<H> break=<B> total=<N>`, and exits 0 iff break==0. At sign-off it
printed `SUMMARY hold=23 break=0 total=23` and exited 0.

Faithfulness engine: untouched. No claim gate was relaxed, moved, or replayed.
The verdict-key guard (B1/B2/B11) is the structural reason a resume can never
replay a stored decision — it always re-runs the real gate from reloaded data.
