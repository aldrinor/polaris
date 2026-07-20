# SYNTHESIS — outline-agent `search_more_evidence` "0 searches" investigation

Sources: instrumentation.md, thin_seed.md, gap_detection.md, global_gating.md, plus direct
re-read of `outline_agent.py` (fold-in seam) and `acceptance_outline_agent.py` (harness).

---

## 1. VERDICT

**The outline-agent search path is NOT broken and NOT disabled. The observed "0 searches" is a
TEST-PREMISE / detection artifact, not a code defect on the search seam.** Confidence: **HIGH
(~0.85)** that the search *mechanism* is intact and reachable; **HIGH (~0.85)** that the THIN
"0 searches" outcome is explained by the upstream gap-detector plus a non-deterministic seed,
not by a disabled/broken search tool.

Why the search path is genuinely live and correctly instrumented:

- **Registration is unconditional and reachable.** With the seat `PG_OUTLINE_AGENT=1` (set at
  `acceptance_outline_agent.py:33`), `search_more_evidence` is registered `core=True,
  requires_data=False` (`outline_agent.py:1115-1128`) and is **never** filtered out of the decide
  menu (`available_tools` filters only on `requires_data`; `get_decide_menu` never hides a core
  tool). No `PG_*` flag, no `requires_llm` check, and no client-availability gate can drop it once
  the seat is on (global_gating.md §1-3). The only global switch is the seat itself, and it is ON.

- **The harness's search counter is FAITHFUL — it does NOT rely on the broken proxy.** The harness
  counts searches by matching the disclosure prefix `search_more_evidence[` (harness lines
  113-115 THIN, 203-205 SATURATED). That disclosure is emitted at **`outline_agent.py:823`
  UNCONDITIONALLY on every real invocation** — it fires *before* the `success=n_kept>0` decision at
  835 and regardless of how many rows survive. So a search that fetched rows but kept none STILL
  increments the harness counter. The harness search count is therefore a true ATTEMPTED-call
  count, immune to the `new_evidence_count` proxy bug.

- **Therefore `search_more_evidence_calls == 0` in the harness means the tool was genuinely never
  dispatched** — not "dispatched but silently miscounted." This rules out the instrumentation
  artifact *for the search counter specifically.*

The `new_evidence_count` field IS a broken/ambiguous proxy (instrumentation.md): it is an
evidence-store size delta, reads 0 both when nothing was searched and when searches kept 0 rows,
and had a historic aliasing bug (now fixed). But the harness's **pass/fail gate does not depend on
that field** — it depends on the disclosure-derived `search_calls`. So the `new_evidence_count=0`
red herring must not be conflated with the search verdict.

**Net:** the true cause of "0 searches" on THIN is that the **gap detector upstream of search
never emitted a grounded deficiency to search for** (gap_detection.md), often compounded by the
**THIN premise not actually holding that run** (thin_seed.md). The search tool downstream is armed
and would fire if fed a gap. This is a *detection/premise* failure, not a *search* failure.

---

## 2. ROOT CAUSE (with file:line)

Two stacked causes, both upstream of the search tool:

**(A) PRIMARY — the checklist grounding gate is a literal substring match with no synonym/
entailment tolerance.** `_quote_is_grounded` at **`outline_agent.py:298-310`**, specifically
**line 310: `return q in question_norm`**. A candidate CV-safety deficiency is admitted only if the
model's quote is a case/whitespace-normalized **literal substring** of the question (≥2 words,
`_MIN_GROUNDING_QUOTE_WORDS` at line 286). Any paraphrase ("cardiac risk", "CV outcomes", "MACE",
"heart-related adverse events") fails the `in` test and is dropped at
**`outline_agent.py:1531-1534`**, so `new_todos` is empty and the checklist discloses
`"NONE (no grounded deficiencies)"` at **`outline_agent.py:1618`** — even when the gap is real.
The cautious "reply NONE if unsure" prompt (`outline_agent.py:1431-1449`) is a secondary suppressor
that can zero the candidate list before the gate even runs. With no admitted gap, the loop has
nothing to hand to `search_more_evidence`, so it correctly fires zero searches.

**(B) SECONDARY / CONFOUND — the THIN premise is not established by the harness.** The seed is a
*live, unfiltered* retrieval seeded by an efficacy query (`acceptance_outline_agent.py:62-64`), and
the only guard is a row-COUNT check `< 3` (lines 65-67) — never a content check. SURPASS/tirzepatide
pages routinely also discuss CV outcomes, so on any given run the seed may already cover the
CV-safety facet, meaning the "uncovered gap" the test assumes **does not exist** and a *correct*
agent legitimately searches zero times (thin_seed.md §1-3). This makes THIN non-deterministic and,
on some runs, self-defeating independent of cause (A).

Note the exact `"NONE (no grounded deficiencies)"` string most precisely corresponds to the
prompt-suppression path (model emitted no line); a paraphrase that the *gate* dropped surfaces
instead as the `"dropped N ungrounded line(s)"` disclosure at `outline_agent.py:1607`
(gap_detection.md). Either way, no gap reaches search.

---

## 3. IS THE SATURATED NEGATIVE CONTROL VACUOUS?

**Partially, and in a way that matters.** SATURATED asserts `search_calls == 0` as a *pass*
condition (harness line 214, folded into `valid_negative_control` at 230). But given cause (A), the
checklist under-detects gaps **structurally** — it will emit `NONE` for a real gap phrased with
non-literal wording just as readily as for a genuinely saturated question. So SATURATED's
`zero_searches` can be satisfied by the **same failure mode** that (wrongly) makes THIN also read 0.

Crucially: **THIN and SATURATED both reading 0 searches is exactly the signature of a dead/over-
strict detector, not of a working discriminator.** A valid negative control must *distinguish* the
two arms; if the very mechanism under test (gap-detection → search) can be silently jammed and
produce `0` on both the should-search and should-not-search inputs, then `search_calls == 0` on
SATURATED proves nothing about the agent's ability to *correctly refrain* — it is consistent with
the agent being simply unable to ever search. **The control is therefore vacuous as currently
written**, because it shares a common-mode failure with the positive arm and does not assert the
positive arm actually exercised search.

The iter-2 hardening (require full loop ran, ≥3 sections, checklist_ran, finish_accepted; harness
226-230) fixes a *different* vacuity (the "loop never built / early-return" degenerate pass) and is
a real improvement — but it does **not** cure the common-mode issue: `checklist_ran=True` only
proves the checklist LLM call happened, not that it *would have flagged a gap if one existed*. To
de-vacuum the control you must couple the two arms: SATURATED is only meaningful if, on the **same
build**, THIN demonstrably fired ≥1 search. Absent that coupling, SATURATED=0 is not
interpretable.

---

## 4. EXACT MINIMAL FIX FOR THE HARNESS PORTABILITY BUG

Two independent defects in `acceptance_outline_agent.py`:
(a) hardcoded absolute output/env paths (`/workspace/outline_agent_wt/...`,
`/workspace/POLARIS/.env`) — the harness only runs on one machine;
(b) the semantic assertions (`valid_negative_control`, THIN's search/mutation checks) **never set
the process exit status** — `main()` writes JSON and returns; a semantic FAIL exits 0. Worse, exit
status is *coupled to* the result-file write only implicitly (an unwritable path raises and is the
*only* way the script fails loudly). Both must be fixed so exit status reflects the **semantic
verdict**, decoupled from where (or whether) the artifact is written.

### (a) Portable / configurable output path + env locations

Replace the hardcoded `sys.path`/`.env`/`out_path` literals with env-overridable defaults anchored
on the harness's own location.

**Edit 1 — near the top, replace lines 27-31:**

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/workspace/outline_agent_wt")

from dotenv import load_dotenv  # noqa: E402
load_dotenv("/workspace/POLARIS/.env", override=True)
```

with:

```python
_HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.environ.get("OUTLINE_AGENT_REPO_ROOT", os.path.dirname(_HARNESS_DIR))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _HARNESS_DIR)

# Output dir for the acceptance artifact (portable; overridable).
_RESULT_DIR = os.environ.get("OUTLINE_AGENT_RESULT_DIR", _HARNESS_DIR)

from dotenv import load_dotenv  # noqa: E402
_ENV_PATH = os.environ.get("OUTLINE_AGENT_DOTENV")
if _ENV_PATH:
    load_dotenv(_ENV_PATH, override=True)
else:
    load_dotenv(override=True)  # walk up from CWD for a .env; no-op if none found
```

**Edit 2 — replace the `out_path` block at lines 280-283:**

```python
out_path = (
    "/workspace/outline_agent_wt/acceptance_result.json" if only is None
    else f"/workspace/outline_agent_wt/acceptance_result_{only}.json"
)
```

with:

```python
_basename = "acceptance_result.json" if only is None else f"acceptance_result_{only}.json"
out_path = os.path.join(_RESULT_DIR, _basename)
os.makedirs(_RESULT_DIR, exist_ok=True)
```

### (b) Exit status = semantic verdict, INDEPENDENT of the result-file write

Compute pass/fail from the returned dicts, write the artifact in a way whose failure is reported
but does **not** mask the semantic verdict, and `sys.exit(nonzero)` on semantic failure.

**Edit 3 — replace the tail of `main()` (lines 276-285) from the summary print onward:**

```python
print("\n" + "#" * 80)
print("ACCEPTANCE SUMMARY")
print("#" * 80)
print(json.dumps(result, indent=2, default=str))

# --- semantic verdict, computed BEFORE and INDEPENDENT of any file write ---
failures: list[str] = []
if "thin" in result:
    t = result["thin"]
    if not t.get("outline_mutated"):
        failures.append("THIN: outline did not mutate")
    if (t.get("search_more_evidence_calls") or 0) < 1:
        failures.append("THIN: search_more_evidence never fired")
if "saturated" in result:
    s = result["saturated"]
    if not s.get("full_loop_ran"):
        failures.append("SATURATED: full agent loop did not run (degenerate control)")
    if not s.get("valid_negative_control"):
        failures.append("SATURATED: not a valid negative control "
                        f"(search_calls={s.get('search_more_evidence_calls')})")

# Artifact write is best-effort telemetry: a write failure is reported loudly but does NOT
# change the semantic verdict (and a successful write does NOT launder a semantic FAIL).
try:
    os.makedirs(_RESULT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"[artifact] wrote {out_path}")
except OSError as exc:
    print(f"[artifact] WARNING: could not write {out_path}: {exc}", file=sys.stderr)

if failures:
    print("\nACCEPTANCE: FAIL", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)
print("\nACCEPTANCE: PASS")
```

(Then `asyncio.run(main())` remains; a semantic FAIL now yields a nonzero exit even when the
artifact wrote fine, and — conversely — a real exception still propagates per LAW II because it is
raised, not caught, above this block.)

**Why this satisfies the two requirements:** (a) no `/workspace/...` literal survives; every path
is derived from `__file__` and overridable by env. (b) `failures` is computed from in-memory
results before the write, the write is wrapped so its failure is non-fatal to the verdict, and
`sys.exit(1)` is driven solely by `failures` — pass/fail is now fully decoupled from whether the
JSON landed.

---

## 5. DESIGN — DETERMINISTIC REGRESSION ORACLE (record/replay + byte-diff)

### Problem the live harness cannot solve
The current harness calls `run_live_retrieval` (real Serper/Exa/fetch) and a live LLM at nonzero
temperature (0.2). Its inputs (web results), its model outputs, and therefore its outline are
**non-deterministic**. It cannot arbitrate a *byte-identical refactor* claim ("this refactor
changes no behavior") because two runs of even the unchanged code differ. It also has a
common-mode blind spot (§3). A refactor oracle needs the opposite property: **given identical
frozen inputs, the artifact must be byte-identical, and any diff is a real regression.**

### Architecture: three frozen layers + a byte-diff gate

**Layer 1 — Frozen provider I/O (record/replay).**
Introduce a seam interface for every non-deterministic boundary the agent touches:
- retrieval backend (`run_live_retrieval` / Serper / Exa search + URL fetch),
- the LLM client(s) (decide model, checklist model, code/outliner model, fold-in screen model),
- the clock / RNG / any UUID or evidence-id minting.

Wrap each behind a thin provider protocol with two implementations:
- **RecordProvider** — delegates to the real backend, and appends every `(request → response)`
  pair to a cassette keyed by a **canonical hash of the request** (method + normalized args +
  a monotonically-increasing call ordinal to disambiguate identical repeated requests).
- **ReplayProvider** — looks the request hash up in the cassette and returns the recorded
  response; a **miss is a hard error** (the refactor issued a request the recording never saw =
  behavior change), and an **unused cassette entry** at teardown is also a hard error (the refactor
  skipped a request = behavior change). This bidirectional strictness is what makes replay a
  *behavioral* oracle, not just a mock.

Cassettes are checked into the repo (e.g. `tests/cassettes/thin.jsonl`,
`saturated.jsonl`) and are the frozen ground truth. Recording is a deliberate, reviewed act
(`--record`), never automatic in CI.

**Layer 2 — Pinned determinism knobs.**
- LLM: **temperature=0, top_p=0, fixed seed** where the provider supports it; but do NOT trust
  sampling determinism — the cassette (Layer 1) is authoritative, so even a non-deterministic model
  is frozen by replay. Pin the exact **model id/version** (e.g. `claude-<dated-snapshot>`, never a
  moving alias) and record it in the cassette header so a model bump invalidates the cassette
  loudly rather than silently.
- Tooling: pin **browser/engine version, fetcher/parser (readability/trafilatura) version, and
  tokenizer version** in a `versions.lock` written into the cassette header. Replay asserts the
  running versions match the header; a mismatch fails closed (the extractor changing the bytes of a
  fetched page is exactly the kind of regression this must catch, so it must not be masked).
- Clock/RNG/ids: inject a fixed clock and a seeded RNG; make evidence-id minting a pure function of
  (ordinal, content-hash) so ids are reproducible. Freeze `PYTHONHASHSEED=0` and sort every
  set/dict before serialization.

**Layer 3 — Canonical artifact + byte-level diff gate.**
Define the oracle artifact as the **full agent trace**, not just the final outline:
- the ordered disclosure log (already emitted, e.g. `search_more_evidence[...]`, `checklist[...]`,
  `finish_outline ACCEPTED`),
- the gap ledger,
- the final outline plans with `ev_ids` per section,
- the evidence store (ids + content hashes, sorted).

Serialize this with a **canonical JSON writer** (sorted keys, fixed separators, `ensure_ascii`
fixed, floats quantized or forbidden, no wall-clock timestamps, no absolute paths). Strip/normalize
any residual nondeterminism (elapsed seconds → bucketed or dropped; absolute `/workspace` paths →
already fixed in §4). The oracle test:

1. runs the agent under ReplayProvider + pinned knobs,
2. canonical-serializes the trace to `artifact.json`,
3. **byte-compares** against the checked-in golden `artifact.golden.json`,
4. on any diff: print a unified diff of the canonical JSON and **fail** (exit 1).

Because inputs are frozen (Layer 1), knobs pinned (Layer 2), and serialization canonical (Layer 3),
a **byte-identical refactor produces a byte-identical artifact** — the diff gate is then a sound
arbiter: zero diff ⇒ behavior preserved; any diff ⇒ a precise, reviewable behavioral delta. This is
exactly the property the live harness lacks.

### Operating model
- **CI (default):** replay only, offline, no network, no API keys, deterministic, fast. The diff
  gate is the pass/fail.
- **Refresh (manual, reviewed):** `--record` re-derives cassettes + goldens against live backends;
  the resulting cassette/golden diff is reviewed like code. This is the *only* time nondeterminism
  enters, and it is gated by human review.
- **Relationship to the live harness:** keep the live harness as a separate, occasionally-run
  *integration/smoke* check (does the real stack still work end-to-end?), but make the **replay
  oracle** the gate for refactors and the regression signal in CI. The live harness answers "does
  reality still work"; the replay oracle answers "did this change alter behavior" — the two
  questions the current single harness conflates.

### What it fixes vs. the current harness
- Non-determinism → eliminated by frozen cassettes + canonical serialization.
- Common-mode vacuity (§3) → the cassette can be authored so the THIN replay *contains* a genuine
  CV-safety gap and the golden asserts ≥1 search fired; SATURATED's golden asserts zero — and both
  are byte-frozen, so the discriminator is proven, not assumed.
- Silent premise drift (thin_seed.md) → impossible; the seed is a fixed cassette, not a live query.
- Exit-status/portability coupling (§4) → the oracle's verdict is a pure byte-diff with a nonzero
  exit, independent of any `/workspace` path.
