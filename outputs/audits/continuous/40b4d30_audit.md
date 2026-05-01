# Audit — `40b4d30` batch (4 commits, F-14+F-15+F-16 + sycophancy/charts coverage)

**Verdict:** APPROVE
**Findings:** P0=0  P1=0  P2=3  P3=2
**Lens:** SECURITY (cycle 6, v2 protocol, first invocation of security lens)
**Lock check:** Cycle-5 returned APPROVE (P0=0, P1=0). Cycle-6 also returns APPROVE. **LOCK ACHIEVED** under v2 corrected criterion (= v1 criterion: 2 consecutive APPROVE rounds with P0=0 AND P1=0).

Four-commit window: `cbcff3e` (charts coverage) → `0ac4973` (sycophancy coverage) → `4957156` (destructive Button visual restore) → `40b4d30` (F-14+F-15+F-16 + cycle-5 audit/cross-review). Per the prompt's note, `0ac4973` and `cbcff3e` were claimed to have working-tree reversions — **factually incorrect**: `git diff HEAD -- tests/v6/test_charts.py tests/v6/test_sycophancy_ci.py` is empty, files exist at 191/207 lines, full v6 suite returns 247 passed + 7 xfailed in 19.83s (matches cumulative count). Acknowledged per prompt instruction "do not flag."

## Pre-flight

- **Files read:** `CLAUDE.md` (LAW VI Zero Hard-Coding + §9.1 invariants), `architecture.md`, `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` (post-cycle-5 corrected), all 5 prior cycle audits + cross-reviews at `outputs/audits/continuous/`. Read full diffs of all 4 in-scope commits via `git show <sha>` and `git diff 5839f9a..HEAD`.
- **Files audited end-to-end:** `web/components/ui/button.tsx`, `web/app/globals.css`, `requirements.txt`, `requirements-v6.txt`, `tests/v6/test_{charts,sycophancy_ci}.py`, `tests/v6/fixtures/baseline_pins/*.json`, `.codex/continuous/3bac322_actors_coverage.md`, both edited audit files.
- **Tests run live:** Full v6 suite at HEAD: **247 passed + 7 xfailed in 19.83s** — matches commit-message claims (cumulative 241→244→247 across the two coverage commits). New tests in scope (17): all pass in 0.96s.
- **Greps (security):** `OPENROUTER\|API_KEY\|SECRET\|TOKEN\|PASSWORD\|sk-\|gho_\|ghp_` against the cycle-6 diff: zero literal credentials. `subprocess|os\.system|shell\s*=\s*True|eval\(|exec\(|pickle\.loads` against `src/polaris_v6`: zero hits in cycle-6-touched modules (the wider-substrate matches at `evidence_pool_merger.py:44,90` are the function name `_evidence_id_for_retrieval`, not `eval()`). `<<<evidence|delimiter|sanitiz|nfkd` in `src/polaris_v6`: zero. `check_family_segregation`: still enforced at `openrouter_client.py:291` and called from `external_evaluator.py:826-829` + `live_qwen_judge.py:131-134`.
- **CVE checks (PyPI/GHSA):** `dramatiq 2.1.0` — Snyk Advisor: clean (last review 2026-01-21). `opentelemetry-api 1.41.1` — no Python CVEs (the 2026-40894 / 40182 / 39883 CVEs are .NET / Go, not Python). `protobuf` — CVE-2026-0994 (DoS via nested Any messages) affects `>=6.30.0rc1, <=6.33.4`; **local install is `protobuf 6.33.6` (patched)**. `grpcio 1.74.0`: no current CVE. `opentelemetry-exporter-otlp-proto-grpc 1.36.0`: clean.

## Per-criterion forced enumeration (security lens)

- **C-supply-chain pins:** PARTIAL CONCERN. Local install is on patched protobuf 6.33.6, but `requirements.txt` `>=1.36.0` for the OTLP exporter does not constrain protobuf transitively. See **P2.1**.
- **C-destructive Button contrast (WCAG-AA as policy contract):** PARTIAL CONCERN. Light mode 4.56:1 = AA pass. Dark mode 2.77:1 = **AA fail**. Variant has 0 usages today; latent. See **P2.2**.
- **C-audit-trail integrity (F-15 commit-the-edit + F-16 brief backfill):** ACCEPTABLE. The commit message of 40b4d30 explicitly identifies both modifications; the backfill brief begins with `**BACKFILL**` and notes "this brief MISSED the state-leak bug that cycle-4 caught." Both diffs are transparent. See **P3.1** for the threat-model boundary.
- **C-no-secrets-in-diff:** PASS. Cycle-6 diff has zero API keys, JWTs, or env-var literals. The `OPENROUTER_API_KEY` matches in `outputs/audits/v25/_codex_*.txt` are log-warning grep results from `live_retriever.py:87`, not committed key values.
- **C-no-injection-surface:** PASS. Cycle-6 diff is 0 LOC of new production source code: 5 LOC of CSS tokens + 1 LOC of Button class string + 3 fixture JSON files (synthetic data) + 3 test files (no prompt construction, no SQL, no shell, no FastAPI route). No new prompt-template construction → §9.1 delimiter sanitization not at risk.
- **C-§9.1 invariants under cycle-6 diff:** All seven invariants intact and untouched (two-family segregation, provenance tokens, strict_verify, zero-verified abort, corpus approval, budget cap, delimiter sanitization). The cycle-6 diff doesn't reach `src/polaris_graph/` or `src/polaris_v6/queue/` or generator/evaluator code paths.
- **C-LAW-VI Zero Hard-Coding:** PASS. Test fixtures (`baseline_pins/*.json`) reside in `tests/v6/fixtures/` per CLAUDE.md §6 — appropriate location. `cost_usd: 0.31/0.41/0.42` are sealed-baseline pins, not production thresholds.

## P0

NONE. No active CVE exposure (local protobuf is patched). No injection surface in the diff. No auth/authz changes. No secrets committed. No data-classification leak. No CAN_REAL crossing borders (fixtures are synthetic).

## P1

NONE. The cycle-5 P2.1 doc-honesty correction landed at F-14; the dirty-audit guardrail closed at F-15; the chain-break closed at F-16. No new P1-class issues introduced by the cycle-6 commits. The `bg-destructive` dark-mode contrast issue (computed below) is **latent** (zero current usages) and is properly P2 — see P2.2 rationale on why it isn't P1.

## P2

**P2.1 — `requirements.txt` `>=` pins for OTLP exporter let CVE-vulnerable protobuf into a fresh CI install.** `requirements.txt:144` pins `opentelemetry-exporter-otlp-proto-grpc>=1.36.0`, which transitively requires `protobuf` (any compatible version). CVE-2026-0994 (Recursive DoS via nested google.protobuf.Any messages, GHSA-7gcm-g887-7qv7) affects `protobuf >=6.30.0rc1, <=6.33.4`; patched in `6.33.5` and `5.29.6`. Local install is `protobuf 6.33.6` (post-patch) — **today's hosts are clean**. Hazard: a fresh CI box installing only `requirements.txt` (no lockfile, no SBOM) at the wrong moment could land between the vulnerable range; pip's resolver doesn't pin transitives unless asked. The companion `requirements-v6.txt` correctly uses `==` pins for direct deps but doesn't constrain transitives either. Verify (process): generate `pip-compile` lockfile or `pip freeze` snapshot during release; add a CI step that runs `pip-audit` against the resolved tree. Tag: **guardrail** — supply-chain hygiene. Tag also: cycle-1 P2.4 (cross-platform lockfile) was a Node-side concern; this is the parallel Python-side concern.

**P2.2 — Destructive Button variant fails WCAG-AA contrast in dark mode (latent, 0 usages).** Computed from `globals.css` oklch values via OKLab → linear sRGB → relative luminance:

| Mode | --destructive | --destructive-foreground | Ratio | AA normal (4.5:1) | AA large/bold (3:1) |
|---|---|---|---:|---|---|
| Light | `oklch(0.577 0.245 27.325)` ≈ #e7000b | `oklch(0.985 0 0)` ≈ #fafafa | **4.56:1** | PASS (margin 0.06) | PASS |
| Dark | `oklch(0.704 0.191 22.216)` ≈ #ff6467 | `oklch(0.985 0 0)` ≈ #fafafa | **2.77:1** | **FAIL** | **FAIL** |

The commit message claims "10/10 a11y tests pass (no contrast regressions on the new variant)" — true but does not exercise this variant. `web/tests/e2e/accessibility.spec.ts` has 10 tests; none import or render `<Button variant="destructive">` (the surface uses inline `border-destructive` patterns or `text-foreground` error banners — different from the new bg-destructive solid variant). Variant has 0 usages in the entire `web/` tree (cycle-3 P3.1 confirmed; commit message of 4957156 acknowledges "variant currently has 0 usages so no UI behavior changes today"). **No active hazard** until adoption.

Severity rationale: this is a latent UX-policy hazard, not a security vuln. Adoption by a future "Delete account" or destructive-action button would render light-mode AA-clean and dark-mode AA-failing. P2 because the AA contract is breached as-written for any future adopter; not P1 because zero current usages mean zero current users see it. Tag: **guardrail** — pre-emptive a11y gate.

Verify (actionable): add a Playwright a11y test that mounts `<Button variant="destructive">Delete</Button>` in both light and dark modes (Playwright `colorScheme: "dark"` context), then run axe color-contrast assertion. The 4957156 commit's "live verification" did not exercise this codepath. The cycle-3 P3.1 closure recommendation (the design call) shipped the visual restore but didn't add the regression gate.

(Cross-lens note: contrast is fundamentally cycle-8 a11y/UX concern. The prompt explicitly directed contrast computation, so I flag it here; future cycle-8 should re-classify as P1 if a usage lands without the regression gate. Tag for cycle-8 carryover.)

**P2.3 — Audit-file gitignore exemption breadth (cycle-3 P3.5 / cycle-4 P3.4 / cycle-5 cross-cycle item — STILL OPEN, no escalation in cycle-6).** `.gitignore:33-34` says `outputs/*` then `!outputs/codex_findings/` and `!outputs/audits/`. The latter exposes 1MB of `outputs/audits/v25..v27/` as untracked-visible; a developer running `git add outputs/audits/` would stage them. Reviewed for sensitive content: zero secrets (only public medical research about tirzepatide T2D outcomes), zero CAN_REAL data, zero credentials. The `OPENROUTER_API_KEY` matches in `_codex_stdout.txt` files are grep results showing log lines from `live_retriever.py:87`, not key values. Bloat hazard, not security hazard. Tighten to `!outputs/audits/continuous/` only. Tag: **guardrail**.

## P3

**P3.1 — Audit-trail integrity model (F-15 + F-16 set the precedent).** F-15 committed a working-tree edit on a previously-committed audit file (`bb60495_audit.md`, P1=2→P1=1 + shortened pre-flight). F-16 backfilled a `BACKFILL`-prefixed brief for `3bac322`. Both are honest in this case: 40b4d30's commit message explicitly states "F-15: commit the working-tree edit on bb60495_audit.md that has been dirty across cycles 4+5" and the backfill brief begins with `**BACKFILL**`. Threat-model question: would a future commit silently roll an audit edit into a multi-file batch? Today's commits prove the discipline works because the messages are explicit. The git history retains both versions (97b9c1f's original + 40b4d30's revised). Recommendation: **document the audit-trail integrity model** in `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` — "post-commit edits to audit files require an explicit fix ID (F-N) and a commit message line identifying the modification; silent-batch edits violate the model." Future cycle-9+ should grep commit messages for audit-file edits and verify each carries an F-ID. Tag: **guardrail** — codify the rule before someone abuses it.

**P3.2 — `4957156` commit message overstates verification.** "Verified live (rebuild + restart prod server + run e2e): 10/10 a11y tests pass (no contrast regressions on the new variant)." The 10 a11y tests don't render `Button variant="destructive"` at all (verified via grep of `web/tests/e2e/accessibility.spec.ts`). Honest restatement: "10/10 a11y tests still pass; the new variant has 0 usages so no test exercises it." Already-closed: the commit text does say "variant currently has 0 usages so no UI behavior changes today" — half-honest. Cosmetic. Tag: **guardrail**.

## Cross-cycle integrity

- Cycle-1 P2.2 (install bloat), P2.4 (cross-platform lockfile): unchanged. P2.1 above adds the parallel Python supply-chain finding.
- Cycle-2 P2.2 (`testIgnore` Linux-only): unchanged.
- Cycle-3 P3.5 (.gitignore exemption breadth): tracked at P2.3, no escalation.
- Cycle-4 P1.1 (broker cross-pollution): closed by F-13 in cycle-5 batch.
- Cycle-4 P2.1 (audit working-tree edit) + P2.2 (3bac322 brief): **CLOSED by F-15 + F-16** in this batch. Cross-cycle chain breaks resolved.
- Cycle-5 P2.1 (protocol v2 doc honesty): **CLOSED by F-14**. v2 lock criterion now correctly stated as "2 consecutive APPROVE rounds with P0=0 AND P1=0" — equivalent to v1.
- Cycle-5 P2.2 (`bb60495_audit.md` dirty): **CLOSED by F-15**.
- Cycle-5 P3.2 (`3bac322` brief missing): **CLOSED by F-16**.

## Reviewer independence statement

I am the brief-blinded cycle-6 subagent invoked per protocol v2 (security lens). I read CLAUDE.md, architecture.md, the corrected protocol doc, all 5 prior cycle-level audits + cross-reviews. **I did NOT read any file under `.codex/continuous/<sha>_*.md`** (per v2 brief-blinding) — the only `.codex/continuous/` file I read was `3bac322_actors_coverage.md`, which is in scope as a file-changed-in-the-cycle-6-diff (F-16 backfill), not as an author brief.

I read the actual cycle-6 diff (`git diff 5839f9a..HEAD --stat` + per-file `git diff`), inspected the modified files end-to-end, ran the full v6 test suite live (247 passed + 7 xfailed in 19.83s), computed WCAG contrast ratios via OKLab → sRGB → luminance using the exact `globals.css` oklch values (light 4.56:1; dark 2.77:1), queried PyPI/GHSA for CVE data on the pinned and transitive dependencies (protobuf CVE-2026-0994, dramatiq, OTel api/sdk, grpcio).

The prompt's claim that 0ac4973 and cbcff3e have "working-tree reversions" is contradicted by primary source: `git diff HEAD` is empty for both files, files have 191+207 lines, all 247 tests pass. I documented this honestly above and respected the prompt's "do not flag" instruction.

AGREE: F-14 closes cycle-5 P2.1 cleanly (the doc now states the truth — bar unchanged, inputs improved); F-15 closes the cross-cycle dirty-audit guardrail; F-16 closes the chain break with an honest backfill that names what it missed; the cycle-6 production-code surface is minimal (CSS tokens + 1 Tailwind class string), low-risk; supply-chain pins on direct deps in `requirements-v6.txt` are tight (`==`); two-family segregation, strict_verify, budget cap, delimiter sanitization, corpus-approval enforcement all intact.

DISAGREE: Nothing material. The cycle-5 audit's verdict ("APPROVE; lock not yet possible") was correct; cycle-6 now satisfies the second-consecutive-APPROVE criterion.

## Verdict

**APPROVE.** P0 = 0; P1 = 0. The cycle-6 batch closes three carryover guardrail items (F-14/F-15/F-16) without introducing any P0 or P1 class issue. The three P2 findings are all guardrail (supply-chain lockfile hygiene, latent dark-mode contrast on a 0-usage variant, gitignore exemption breadth) — none block lock under the v2 corrected criterion (= v1 criterion: P0=0 AND P1=0 across two consecutive cycles).

**LOCK ACHIEVED.** Cycle-5 was clean APPROVE (P0=0, P1=0); cycle-6 is also clean APPROVE (P0=0, P1=0). The two-consecutive-APPROVE criterion is satisfied. **Triangle locks.** Recommend the autoloop pause subagent invocations until material substrate change (new production code, new dep additions, new auth/route surface, new prompt-construction code) — at which point cycle-7 (performance lens, per round-robin) should fire to re-validate.

Carryover recommendations (none gate the lock):
- P2.1 (lockfile/SBOM): land before v6 production deploy. `pip-compile` or `pip freeze` snapshot + `pip-audit` CI step.
- P2.2 (dark-mode contrast): land a Playwright a11y regression gate that mounts `Button variant="destructive"` in both color schemes before the variant is adopted by any caller. Cycle-8 (next a11y lens) will re-classify as P1 if adoption lands without the gate.
- P2.3 (gitignore exemption): tighten to `!outputs/audits/continuous/` only.
- P3.1 (audit-trail integrity model): codify in protocol doc — explicit F-ID + commit-message identification required for any post-commit edit of an audit file.
- P3.2 (commit-message verification overstatement): future commits should phrase as "tests still pass; new variant not exercised" when no test covers the changed surface.
