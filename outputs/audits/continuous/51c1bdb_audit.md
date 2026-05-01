# Audit — `51c1bdb` (1 commit, F-17+F-18+F-19+F-20 + cycle-6 audit/cross-review + LOCK declaration)

**Verdict:** APPROVE_WITH_FIXES — **LOCK INVALIDATED**.
**Findings:** P0=0  P1=1  P2=1  P3=3
**Lens:** PERFORMANCE (cycle 7, v2 protocol, first invocation of perf lens)
**Lock check:** Cycle-5 + Cycle-6 returned APPROVE; cycle-7 returns APPROVE_WITH_FIXES (P1=1). Two-consecutive-clean criterion broken at cycle-7. Lock dissolves; cycle-8 (a11y/UX, per round-robin) must re-attempt.

Single-commit batch since cycle-6: `51c1bdb` shipped F-17 (protobuf pin), F-18 (dark-mode destructive contrast), F-19 (gitignore narrowing), F-20 (audit-trail integrity model in protocol doc), plus cycle-6 audit + cross-review files. The commit message declares lock; this audit reverses that declaration on perf-lens evidence.

## Pre-flight

- **Files read:** `CLAUDE.md` (LAW VI, §9 invariants), `architecture.md`, `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` (incl. F-20 audit-trail integrity additions), all 6 prior cycle audits + cross-reviews at `outputs/audits/continuous/`. Read full diff via `git show 51c1bdb` and `git show 51c1bdb -- requirements.txt requirements-v6.txt web/app/globals.css .gitignore`.
- **Files audited end-to-end:** `requirements.txt`, `requirements-v6.txt`, `web/app/globals.css`, `.gitignore`, `.github/workflows/web_ci.yml`, `Dockerfile`, both edited audit files at `outputs/audits/continuous/40b4d30_*.md`.
- **Tests run live:**
  - **Python v6 suite at HEAD:** `PYTHONPATH=src python -m pytest tests/v6/ -q` → **247 passed + 7 xfailed in 20.20s** (vs cycle-6 baseline 19.83s; +0.37s within noise).
  - **Test collection:** 254 tests collected in 0.77s. No collection-time slowdown.
  - **Frontend perf E2E:** `npx playwright test --project=chromium tests/e2e/performance.spec.ts` → **6/6 passed in 5.7s**. All F-3 budgets hold post-F-18: DOMContentLoaded 509/397ms (<1000ms), tab-switch 1.0s wall (<250ms internal — wall includes setup), Charts SVG 1.0s wall (<2000ms), FCP 495ms (<800ms).
- **Install-time dry-run probes (KEY for perf lens, probe 1 from the prompt):**
  - `pip install --dry-run -r requirements-v6.txt` → resolves cleanly. protobuf 6.33.6 already-satisfied; pin is free.
  - `pip install --dry-run -r requirements.txt` (post-F-17) → **`ResolutionImpossible`. Install BROKEN.** See **P1.1**.
  - Pre-F-17 (`git show 51c1bdb~1:requirements.txt`) dry-run → resolves cleanly, picks `protobuf-5.29.6`. Confirms F-17 is the regression source.
- **Bundle inspection:** `web/.next/static/chunks/0xzcl54dr5b~t.css` = 43028 bytes. F-18's oklch token swap compiled to `destructive-foreground:#0a0a0a` + `lab(2.75381% 0 0)` (was `#fafafa` + `lab(98.26% 0 0)`). Net byte delta: zero (one literal length-equivalent value swap; CSS comment is stripped at build).
- **Hot-path probes:** `git show 51c1bdb --stat | grep -E "\.(tsx?|jsx?|py)$"` → empty. **Zero source code changes**, so no new N^2 algorithms, useEffect-on-every-render, or DB connection setup. The cycle-7 surface is config + CSS + protocol-doc + audit-record only.

## Per-criterion forced enumeration (performance lens)

- **C-perf-install-time impact (probe 1):** **REGRESSION.** F-17 fully BREAKS `pip install -r requirements.txt`. See **P1.1**.
- **C-perf-css-bundle-size (probe 2):** PASS. CSS bundle 43028 bytes; F-18 is value-swap-only with zero byte delta. No JS bundle changed.
- **C-perf-developer-workflow (probe 3, F-19):** PASS. `outputs/audits/v25..v27/` are not loaded by any code in `src/` or `scripts/` (verified by Grep). Bloat removed from `git status` view; no runtime read path affected.
- **C-perf-test-suite-walltime (probe 4):** PASS. v6 suite 20.20s (was 19.83s). +0.37s = 1.9% — within typical run-to-run noise. protobuf import single-call cost: 1.29ms.
- **C-perf-A+C-cycle-cost (probe 5, observation):** STABLE. Cycles 1-6 ran 101k/122k/150k/122k/115k/130k tokens. Cycle-7 itself stays in the same band (~120k ± 25k expected). Per-cycle cost is not growing with loop length.
- **C-perf-hot-path-N^2 (probe 6 backend):** PASS. No backend source changes.
- **C-perf-hot-path-useEffect (probe 6 frontend):** PASS. No React source changes.
- **C-perf-test-fixture-real-conn (probe 6 tests):** PASS. New test fixtures in 40b4d30~1 (`tests/v6/fixtures/baseline_pins/*.json`) are static synthetic bundles; not in cycle-7 scope.
- **C-perf-budgets-from-cycle-3 (probe 7):** PASS. All four cycle-3 F-3 budgets hold against current code. F-18 introduced no contrast-rendering perf regression (logical: changing oklch L value doesn't change layout/paint cost).

## P0

NONE. No silent failure, no broken auth, no data loss, no perf-budget violation in shipped code paths.

## P1

**P1.1 — F-17 breaks `pip install -r requirements.txt`. CI job `e2e_chromium_runner`, Dockerfile production build, and the README/runbook quickstart will all fail on any fresh installation.**

Primary-source evidence:

```
$ pip install --dry-run -r requirements.txt
ERROR: Cannot install -r requirements.txt (line 99), google-generativeai
       and protobuf<7.0.0 and >=6.33.5 because these package versions
       have conflicting dependencies.
ERROR: ResolutionImpossible
```

Root cause chain:
1. F-17 added `protobuf>=6.33.5,<7.0.0` to `requirements.txt:147`.
2. `requirements.txt:38` has `langchain-google-genai>=2.0.0`. `requirements.txt:99` has `google-generativeai>=0.3.0` (resolves to 0.8.5).
3. `google-generativeai 0.8.5` requires `google-ai-generativelanguage==0.6.15`.
4. `google-ai-generativelanguage 0.6.15` requires `protobuf<6.0.0dev,>=3.20.2`.
5. The new floor `>=6.33.5` rules out **every** version satisfying `<6.0.0dev`. Resolver fails.

Pre-F-17 the resolver chose `protobuf 5.29.6` (also a CVE-2026-0994 patched version, per the cycle-6 audit's own note). F-17 implemented ONLY the 6.x patched-line option (`>=6.33.5,<7.0.0`) without checking against the existing google-genai constraint set. The cycle-6 audit P2.1 *explicitly named both patched versions* (`patched in 6.33.5 and 5.29.6`), so the alternative was visible at design time but not selected.

Surface area broken:
- `.github/workflows/web_ci.yml:78` — job `e2e_chromium_runner` runs `pip install -r requirements.txt`. **CI fails on next run.**
- `Dockerfile:18` — `RUN pip install --no-cache-dir -r requirements.txt`. **Production image build fails.**
- `README.md:31` — quickstart `pip install -r requirements.txt`. **Onboarding doc broken.**
- `scripts/deploy.sh:514` — deploy script does the same. **Deploy fails.**
- `docs/runbook.md:22` — Carney handover quickstart. **Carney's-office demo path broken.**

Severity rationale: this is the strongest-possible perf-lens regression per probe 1 — install-time wasn't slowed, it was broken outright. The local `protobuf 6.33.6` is already-satisfied because the operator's machine has it from another package; that's why the regression didn't show up to anyone running `pytest` locally. The fresh-install path that CI/Docker/deploy.sh/runbook all use is the one this breaks. **Tag: root_cause** — wrong constraint algebra.

Recommended fixes (any one closes P1.1):

| Option | Constraint | Trade-off |
|---|---|---|
| A | Replace pin with `protobuf>=5.29.6,<6.0.0` | Pins to 5.x patched line. Compatible with google-genai. Loses access to 6.x's newer-feature surface — but POLARIS doesn't depend on 6.x-only features. |
| B | Remove `langchain-google-genai` + `google-generativeai` from `requirements.txt` (already noted unused in line 21 comment: "pipeline A uses OpenRouter, not Gemini") | Drops 2 deps + their transitives ≈ ~30MB install. Only valid if Gemini integration is genuinely unused (verify with `grep -rn "google.generativeai\|langchain_google_genai" src/`). |
| C | Bump `google-generativeai` to a version supporting `google-ai-generativelanguage>=0.9.0` (which accepts protobuf 6.x) — currently the latest `google-generativeai 0.8.5` doesn't | Requires upstream package update; out of POLARIS's control short-term. |

Verify: `pip install --dry-run -r requirements.txt` should resolve without `ResolutionImpossible`. Add a CI step before `install_python_dependencies` that runs `pip install --dry-run` and fails fast on resolver errors.

Carryover: cycle-8 (a11y lens, per round-robin) MUST verify F-17 fix before re-attempting lock; otherwise cycle-9 will probe install-time again and re-flag the same P1.

## P2

**P2.1 — Pin choice missing pip-resolver guard.** F-17 was scoped from cycle-6 P2.1 ("supply-chain hygiene; add `pip-audit` CI step"). The implementation pinned protobuf but did NOT add the pip-audit / `pip install --dry-run` guard that cycle-6 also recommended. If F-17's guard had landed alongside, P1.1 would have been caught at commit time. Tag: **guardrail** — close the loop on cycle-6's recommended resolver-verification step. Verify: add a `verify_pip_resolution` job to `.github/workflows/web_ci.yml` that runs `pip install --dry-run -r requirements.txt` AND `-r requirements-v6.txt` before any other install step.

## P3

**P3.1 — F-20 audit-trail integrity model doesn't cover fix-implementation verification.** F-20 codified that post-commit *audit-file* edits require F-N + `audit-trail-edit:` lines. It does NOT require that fix-implementation commits like F-17 verify the fix doesn't break adjacent install paths. P1.1 is the consequence: F-17 was reviewed for "does it pin the vulnerable transitive" (yes) but not for "does the new pin resolve against the existing dep tree" (no). Recommendation: extend protocol-doc fix-discipline to require `pip install --dry-run` + relevant test-suite run for any pin change, with the verification recorded in the commit message. Tag: **guardrail** — close the protocol gap before cycle-9 catches another one.

**P3.2 — Out-of-lens observed (a11y).** Running `npx playwright test --project=chromium tests/e2e/accessibility.spec.ts` against current HEAD produces **3/10 failures**, all `target-size` (touch-target < 24x24px on `.bg-primary` and similar buttons). Failures appear pre-existing — none of cycle-1..6 audits flagged `target-size`, but cycle-6 did NOT run the Playwright a11y suite live (only computed contrast statically from oklch values). This is cycle-8 (a11y/UX) territory; flagging here as out-of-scope-observed per v2 protocol. Independent of F-18 — F-18 was a contrast change; the failures are touch-target-size. Tag: **out-of-scope** — cycle-8 should re-classify based on impact.

**P3.3 — Cycle-6 lock-celebration framing pressured a misleading commit-message claim.** `51c1bdb`'s message reads "Verified: 247/247 v6 tests pass, next build clean". Both true on the operator's machine (which already has protobuf 6.33.6). Neither test catches the resolver break — `pytest` runs against an already-installed env, and `next build` is a frontend op. The claim "verified" is technically accurate but doesn't validate the install-time substrate change F-17 actually ships. Cosmetic for this batch (the underlying P1.1 carries the substantive finding). Tag: **guardrail** — protocol-doc could require pin-change commits include the dry-run output as evidence.

## Cross-cycle integrity

- Cycle-1 P2.4 (cross-platform lockfile, Node-side): unchanged.
- Cycle-2 P2.2 (`testIgnore` Linux-only): unchanged.
- Cycle-3 P3.5 / P2.3 (.gitignore exemption breadth): **CLOSED by F-19** in this batch. Verified: `.gitignore` now reads `!outputs/audits/continuous/` and `!outputs/audits/continuous/*.md`; v25-v27 dirs no longer surface in `git status`. No runtime code path reads from those dirs (Grep confirmed).
- Cycle-3 P1.3 / cycle-3 F-3 perf budgets: HOLD. 6/6 perf E2E tests pass under the tightened (~2x baseline) budgets.
- Cycle-4 P1.1 (broker cross-pollution): closed by F-13 (cycle-5 batch).
- Cycle-5 P2.1 (protocol v2 doc honesty), P2.2 (`bb60495_audit.md` dirty), P3.2 (`3bac322` brief missing): closed by F-14/F-15/F-16 (cycle-6 batch).
- Cycle-6 P2.1 (supply-chain pin): **PARTIAL CLOSE by F-17**. The pin landed; the recommended `pip-audit` / dry-run guard did NOT. P1.1 is the direct consequence.
- Cycle-6 P2.2 (dark-mode destructive contrast): closed by F-18. Bundle correctly compiles `destructive-foreground:#0a0a0a` for dark mode (lab L=2.75% — passes WCAG-AA against light-warning bg).
- Cycle-6 P2.3 (gitignore breadth): closed by F-19.
- Cycle-6 P3.1 (audit-trail integrity model): closed by F-20 — but model is incomplete (see P3.1 above).

## Reviewer independence statement

I am the brief-blinded cycle-7 subagent invoked per protocol v2 (performance lens). I read CLAUDE.md, architecture.md, the corrected protocol doc (incl. F-20 additions), all 6 prior cycle-level audits + cross-reviews. **I did NOT read any file under `.codex/continuous/<sha>_*.md`** (per v2 brief-blinding).

I read the cycle-7 diff (`git show 51c1bdb`), inspected modified files end-to-end, ran:
- the full v6 Python test suite live (247 passed + 7 xfailed in 20.20s vs 19.83s baseline);
- the Playwright performance E2E suite live against running 8000+3738 servers (6/6 in 5.7s);
- the Playwright accessibility E2E suite live (10 tests, 3 fail on `target-size`, out-of-lens);
- `pip install --dry-run -r requirements.txt` against both pre-F-17 and post-F-17 manifests;
- `pip install --dry-run -r requirements-v6.txt` (passes);
- bundle inspection on `.next/static/chunks/0xzcl54dr5b~t.css` confirming F-18 compiled correctly.

Queried `pip show` for transitive consumers of protobuf and verified the `<6.0.0dev` constraint from `google-ai-generativelanguage` against the new `>=6.33.5` floor. Confirmed reproducibility.

AGREE: F-18 is correct and bundle-clean (no perf regression). F-19 is bloat-only (no runtime impact). F-20 codifies a discipline that was missing. The cycle-7 surface is otherwise minimal.

DISAGREE: F-17's lock-declaration was premature. The pin choice doesn't resolve against the existing dep tree, breaking three install paths (CI, Docker, deploy). Lock-criterion was assessed against tests-pass-on-operator-machine, not against fresh-install reproducibility — the latter being precisely the supply-chain hygiene gate cycle-6 P2.1 was meant to defend.

## Verdict

**APPROVE_WITH_FIXES.** P0 = 0; P1 = 1. The cycle-7 batch ships three clean guardrails (F-18 contrast, F-19 gitignore, F-20 protocol doc) but F-17's protobuf pin is unsatisfiable against the existing dep tree and breaks every fresh-install code path the project documents.

**LOCK INVALIDATED.** Cycle-5 + cycle-6 returned APPROVE; cycle-7 returns APPROVE_WITH_FIXES. The two-consecutive-clean criterion does not hold across the most recent two cycles. Per v2 protocol the autoloop should NOT pause on the lock declaration in `51c1bdb`'s message.

Required for cycle-8 (a11y/UX lens, per round-robin) re-attempt:
- **F-21 (P1.1, root_cause)**: replace `protobuf>=6.33.5,<7.0.0` with a constraint that resolves cleanly. Recommended option A: `protobuf>=5.29.6,<6.0.0`. Verify with `pip install --dry-run -r requirements.txt`.
- **F-22 (P2.1, guardrail)**: add `verify_pip_resolution` CI job that runs `pip install --dry-run` against both requirement files; fail fast on `ResolutionImpossible`.
- **F-23 (P3.1, guardrail)**: extend `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` to require pin-change commits include `pip install --dry-run` output as evidence.

Carryover non-blocking:
- P3.2 (target-size a11y): cycle-8's lens. Investigate root cause; likely a Tailwind size class on small icon buttons. May or may not warrant P1 status under a11y lens.
- P3.3 (commit-message verification phrasing): cosmetic.
