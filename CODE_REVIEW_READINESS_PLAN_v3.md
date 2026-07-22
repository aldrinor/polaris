# Deep Cove Research — Code Review Readiness Plan (v3)

**Goal:** make the code clean and professional enough to pass an independent Telus code review — **without ever changing the pipeline's score or its faithfulness behavior.**

**Date:** 2026-07-18 · **Status:** for owner approval (v3 — folds in two rounds of independent codex review)

**Version history:**
- v1 — first draft from a research+audit workflow.
- v2 — folded in codex round 1 (baseline first; "byte-identical" needs a real test; severity recalibrated; reorder).
- **v3 — folds in codex round 2:** a real baseline *manifest* + comparison protocol; config tests cover precedence/case/timing/types + **govern-and-own the keys before migrating**; graph removal gated on a full compatibility matrix + usage evidence + repeated replays; and the extra review axes become **scheduled, owned, gated deliverables** — with a **public-compatibility check before any rename or delete**.

---

## The one rule (never break this)

The running pipeline's **RACE score** and its **faithfulness behavior** must stay **exactly the same** through every change. No change may move a threshold, a model name, a temperature, or a verdict. If we cannot *prove* a change is safe, we do not ship it.

**Owners:** every workstream below has an **Owner** field. Where it says `Owner: TBD`, you assign it before that item starts. Nothing with `Owner: TBD` may begin.

---

## The good news: the code is better than it feels

- **96%** of functions are type-annotated. · **98.5%** of modules have a docstring. · **1,082 tests** already exist. · **Secrets are clean** (no keys in git; `.env` ignored). · The "borrowed" parts (STORM, FS-Researcher) are **our own rewrite from the papers, cited — not copied code** (a naming choice, not a legal problem).

→ The gap is **not substance**. It is **discipline a reviewer can see, plus a few unknowns we must turn into knowns.**

---

## The real problems (honest severity)

1. **HIGH — Tests not enforced.** 1,082 tests exist but never run in CI. No lint/type-check/`pyproject.toml`. 28 CI actions on moving tags (security weakness).
2. **HIGH — Settings scattered.** 1,707 `os.getenv` calls, ~923 settings, only 24 documented; model names/numbers hardcoded in 9+ files.
3. **HIGH — One real architecture mess:** a live 3-way fork (`graph.py`/`graph_v2`/`graph_v3`) chosen by env var. The single most dangerous thing.
4. **MEDIUM — Messy names (tidiness):** `honest_*`, `_v2`-no-`v1`, two apparently-dead files.
5. **MEDIUM — A checkpoint built but never turned on** → every restart re-runs 30–40 min generation.
6. **NARROW — Docs gaps only in the contract/API files** (~530 docstrings).

**Plus six unknowns a reviewer will probe** (not yet audited, see the "Scheduled deliverables" section): security/privacy, operations, public compatibility, test *quality*/flakiness, settings governance, reproducible builds.

---

## The plan — step by step

Referee for "did the pipeline change?": the acceptance harness (`acceptance_outline_agent.py`), governed by the **baseline manifest + comparison protocol** defined in Phase 0. The graph fork additionally needs repeated per-selector replays.

### Phase 0 — Build a real baseline, then only the truly-safe tidy-ups

**0A. The reproducible baseline (the foundation everything else is measured against).** `Owner: TBD`

*0A-1 — Record a baseline manifest* (`baseline/manifest.json`): git commit SHA; `requirements.lock` hash; Python version + OS; a full dump of every `PG_*` (and non-`PG_*`) env value in effect; the provider/model routing config; any seeds; the exact commands run; and the input fixtures used. This is the "what state produced this result" record.

*0A-2 — Run in an ISOLATED sandbox* (running the pipeline is **not** read-only — it writes files and calls providers, so we must isolate side effects): a dedicated scratch output dir; the GitHub backup daemon **paused** for the run; no writes to shared state; provider calls either recorded or run with the existing offline/deterministic acceptance path. Record every output artifact **and its SHA-256 hash**.

*0A-3 — Establish NON-flakiness* (a single green run is not a baseline): run the full test suite **and** the acceptance harness **N≥3 times**; record pass/fail, timing, and variance. Any test or score that isn't stable across repeats is marked **flaky** and quarantined into a tracked list — it does not count toward the baseline.

*0A-4 — Define the comparison protocol up front* (because LLM calls are non-deterministic, "same" must be defined, not assumed): declare the equivalence rule before any change — e.g. RACE score within a stated tolerance band over N repeats, identical faithfulness verdict sets on fixed inputs, and artifact-hash match for artifacts that are meant to be deterministic. Document explicitly what counts as a **regression** vs noise.

*0A-5 — Characterize all 3 graph selectors* now: record `v1`/`v2`/`v3` routing + behavior on the fixed inputs as **replay fixtures**, so later graph work has a real "before" for each selector.

**0B. Changes that touch NO importable runtime code (safe to ship immediately).** `Owner: TBD`
- **SHA-pin all 28 CI actions** to exact commit SHAs (safe; closes a supply-chain finding).
- **Fix third-party attribution** (licenses/notices) — `third_party/` is never imported → zero risk.
- **Add `pyproject.toml` + CI** (lint, type-check, tests) in **report-only mode** (shows results, blocks nothing).
- **Tidy the README/architecture doc.**

**Deferred out of Phase 0 (they only *looked* zero-risk):** deleting "dead" files and changing secret types — both wait until the baseline exists **and** the public-compatibility inventory (Phase 2 gate) clears them.

---

### Phase 1 — Central settings (governance first, then a full-behavior migration)

Build one typed `settings.py` — the **master control panel** you asked for. This is a **semantic redesign, not a copy-paste**, so it is gated:

**1A. Govern and own the keys BEFORE moving any of them.** `Owner: TBD`
- Classify **every one of the ~923 keys** (including any non-`PG_*` ones) as: **supported / internal / secret / deprecated / experimental**, with an **owner** per key and its **source precedence** documented. Acceptance gate: **100% of keys classified and owned** before a single key migrates. (A 923-line `.env.example` is an inventory; this makes it a contract.)

**1B. Full-behavior characterization tests (not just default values).** `Owner: TBD`
- For every key, lock today's behavior across the **whole matrix**: `{unset, empty, valid, malformed}` × `{default / .env / process-env / CLI precedence}` × `{key-case sensitivity}` × `{read timing: lazy vs import-time snapshot}` × `{runtime type: str / coerced int·float·bool / SecretStr wrapper}`. These characterization tests are the real "byte-identical" proof.

**1C. Migrate one module at a time.** `Owner: TBD`
- Each field's default = today's exact value; each env name preserved verbatim; `SecretStr` for keys (with call-sites updated to unwrap, since a wrapper is a runtime-type change). Run the acceptance harness after each module; any deviation from the 0A baseline → stop. **Never change a value in the same commit that moves it.** Highest-risk spots: `state.py` (114 reads) and the model resolver (a wrong slug trips a self-check guard).

---

### Phase 2 — Public-compatibility gate, THEN renames + delete + checkpoint

**2A. Public-compatibility inventory — runs BEFORE any rename or delete.** `Owner: TBD`
- Renaming or deleting is **reversible in git but NOT proven safe** by "zero static importers." Before touching any symbol/file, inventory: **dynamic imports** (`importlib`, `__import__`, `getattr` on modules, entry-points/plugins), **string-based references**, **saved-state references** (persisted objects that name module paths), and **external/public consumers**. A file or symbol is cleared for rename/delete **only** after this inventory shows nothing depends on its name. This is the acceptance gate for 2B/2C.

**2B. Rename messy names (only after 2A clears each).** `Owner: TBD`
- `honest_*` → plain names; drop `_v2` where there's no `v1`. **Rename code symbols and filenames only — never env-var text or stage-name strings** (those control the pipeline). One rename per commit; acceptance harness before/after each.

**2C. Delete the apparently-dead files (only after 2A clears them).** `Owner: TBD`

**2D. Turn on the generation checkpoint.** `Owner: TBD`
- Save **pre-check data only** (drafts, outline) — **never a verdict** — so faithfulness re-runs fully. **Gate the *write* behind the flag** so a normal run produces no new side effect and stays truly identical. Reload path must re-verify from scratch.

---

### Phase 3 — Docs, flakiness-gated required CI, then the graph fork (LAST)

**3A. Docs.** `Owner: TBD` — fill the ~530 docstrings (contract/API first) + ADRs. Pure text.

**3B. Flakiness policy BEFORE CI becomes required.** `Owner: TBD`
- Run the suite N times over several days; fix or quarantine flaky tests; define an explicit **non-flakiness bar**. CI flips from report-only to **required** **only after the suite is provably stable** — *not* after "one green run." Add dependency hash-pinning + license/secret scanning at this point.

**3C. The graph fork — the single most dangerous change, fully gated.** `Owner: TBD`
Nothing in `graph*.py` is deleted until **all** of these pass:
1. **Per-selector compatibility matrix** — behavior of `v1`/`v2`/`v3` on the 0A-5 fixtures, side by side.
2. **Real usage inventory** — grep prod configs, CI, scripts, and docs for `PG_GRAPH_VERSION` and any `v2`/`v3` use; confirm what is actually selected in practice.
3. **Saved-state migration fixtures** — prove persisted `ResearchStateV2` data still loads (or has a migration).
4. **Repeated equivalent replays per selector** — not one run; N repeats within the 0A-4 equivalence band.
5. **Explicit rollback + deprecation window** before any file is removed.
Its own separate, reviewed change.

---

## Scheduled deliverables — the six reviewer axes (owned, with acceptance gates)

Not questions — **work items**, each blocking a specific later step.

| # | Deliverable | Evidence / acceptance | Gates (blocks) | Owner |
|---|---|---|---|---|
| S1 | **Config governance** (classify+own 923 keys) | 100% keys classified + owned + precedence documented | Phase 1 migration | TBD |
| S2 | **Public-compatibility inventory** (dynamic imports, plugins, saved refs, external consumers) + supported-Python / install / state-migration / rollback doc | inventory complete; nothing depends on renamed names | Phase 2 rename/delete | TBD |
| S3 | **Test quality / flakiness policy** | suite stable across N runs; flaky list quarantined; bar defined | Phase 3 required-CI | TBD |
| S4 | **Security / privacy review** | threat-model doc (API auth, crawler SSRF, prompt-injection, PII, log redaction, checkpoint retention); no unresolved critical findings | before any external exposure | TBD |
| S5 | **Operational readiness** | checklist: timeouts, retries, rate/cost limits, monitoring, runbooks, recovery | before external exposure | TBD |
| S6 | **Reproducible build** | two independent builds hash-match; hash-pinned deps + locked env + documented build + SBOM | before "reproducible" is claimed to Telus | TBD |

---

## The safety rules (apply to every change)

1. **Baseline first** — no runtime change before the 0A manifest + comparison protocol + N-run non-flakiness baseline exist.
2. **Config = full-behavior proof.** Characterization tests cover value, precedence, case, coercion, malformed input, read-timing, and runtime type — not just the default. Keys are classified + owned before migration.
3. **No behavior change** in the same commit as a rename or a settings move.
4. **Renames/deletes are gated on the public-compatibility inventory (S2)** — "zero static importers" is not sufficient. Rename symbols/filenames only; never env text or stage-name strings.
5. **Checkpoint:** pre-check data only, never a verdict; the write is gated off by default so normal runs are identical.
6. **Acceptance harness before and after** every code-touching change; the graph fork additionally requires the full 3C gate (matrix + usage + migration + repeated replays + rollback).
7. **CI starts report-only, becomes required only after the flakiness bar (S3) is met** — not after one green run.
8. **Do not rename real domain terms** (SmartArt, deep_crawl, OpenAlex, PubMed, Semantic Scholar). Keep paper citations.

---

## What to show Telus first

1. The `pyproject.toml` + CI PR next to the **96% typing** number — quality now enforced, substance always there.
2. The strong fundamentals, honestly (98.5% module docs, real README, 1,082 tests, pinned deps, clean secrets).
3. The clean-room proof for STORM/FS-Researcher.
4. This plan + the baseline manifest — proof the rest is scoped, owned, gated, and ring-fenced from the score.

---

## Where we start

**Phase 0-A: the reproducible baseline** (manifest → isolated N-run → comparison protocol → 3-selector fixtures). It cannot change the pipeline, and every later "we did not move the score" claim depends on it.

**One-line summary for the boss:** *"The pipeline is sound and the fundamentals are real; what's missing is the enforcement, the tidiness, and a few proofs an outsider needs. We establish an evidence baseline first, then pay down each item behind an owned, gated guarantee that the score and faithfulness never move."*
