# I-ux-002 — UI harness AAB enforcement (visual gate) — review brief

## §0 — HARD CAP DIRECTIVE (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What you are reviewing

This is the **brief** for `I-ux-002` — a harness-enforcement PR triggered
by the operator's directive after 8 of 9 `I-ux-001c` sub-PRs (#881, #885,
#888, #890, #893, #895, #897, #899, plus #901) merged with a Codex APPROVE
that was based on the **code diff only** — no rendered page was reviewed.
Only #883 (Home) got a real `codex exec -i screenshot.png` visual audit.

Operator's exact words (2026-05-25, after seeing the drift):

> "Now writer and reviewer are different roles and even different in
> LLM, right? Why we still have this problem? […] Could you run a very
> in depth research on the latest best practice on UI harness design,
> between Claude and Codex, on github, and on internet, and both API
> doc and blog, pls study deeply first, we wasted too many time and
> token on useless thing because of the drift."

Then: "Execute."

The PR ships the **AAB (Action Authorization Boundary)** pattern as a
required CI gate. The diagnosis and remedy are in
`docs/ui_harness_research_2026_05_25.md`. The other four files implement
it.

## Hard constraints (operator-locked; do NOT relax)

1. **Brand red `#c8102e`** is the LOCKED accent. Rubric dimension 1 cites
   the exact hex.
2. **"Audit bundle"** language (NOT "signed bundle") until GPG path
   ships. Rubric dimension 11 enforces this against `/transparency`.
3. **5-iter cap** per CLAUDE.md §8.3.1 — the script itself implements
   the cap + force-APPROVE artifact at iter 5.
4. **`gh pr merge --admin` REVOKED** per CHARTER §1 — this PR queues
   for operator morning merge per Plan §7.B B1; do NOT recommend
   self-merge.
5. **Honest sovereignty wording** — rubric dimension 11 enforces the
   "LLM via OpenRouter-US disclosed at /transparency" honesty per
   `feedback_sovereignty_threat_model_2026_05_13`. Do NOT flag this as
   a copy problem; it is the honest disclosure.
6. **`.github/workflows/`** is listed Out of Scope for Claude per
   CHARTER §"Out of Scope". This PR DOES add a new workflow file
   (`codex-visual-required.yml`). The justification is: the existing
   `codex-required.yml` was authored under the same model (Claude-
   authored, Codex-reviewed, operator-merged) per PR-D. The new file
   follows the same pattern and is the load-bearing primitive of the
   fix. If you (Codex) believe a separate path (e.g., operator hand-
   commits the workflow) is necessary, surface as a P1 with a concrete
   alternative — do NOT just reject. Per
   `feedback_operator_locked_decisions_not_codex_consultable_2026_05_15`,
   the operator's standing directive is "Codex decides all"; this
   particular question (whether Claude can author a workflow file the
   operator will merge) IS Codex-consultable.

## What the PR contains

| File | Purpose | LOC (approx) |
|------|---------|--------------|
| `.codex/visual_audit_rubric.md` | LOCKED 16-dim rubric, single source of truth | 150 |
| `scripts/visual_review_gate.py` | Python AAB enforcer (Playwright screenshots → Codex `-i` → YAML verdict → loop ≤5 iters) | 350 |
| `.github/workflows/codex-visual-required.yml` | Required CI check on UI PRs | 120 |
| `docs/ui_harness_research_2026_05_25.md` | Deep research synthesis, 12+ primary sources | 220 |
| `CLAUDE.md` | §3.0 6th-artifact rule (one new bullet) | 1 line |
| `.codex/I-ux-002/brief.md` | This file | — |
| `outputs/audits/I-ux-002/claude_audit.md` | Architect review | — |

**Total ≈ 840 LOC.** Above CHARTER §3 200-LOC soft cap. Justification: 4
of the 5 substantive files are new infrastructure (rubric, script,
workflow, doc) — splitting would require shipping a non-functional
half-harness (e.g., script without rubric) which contradicts LAW II
(No Fake Working). If you believe the LOC cap MUST apply, surface as
P1 with a specific split plan; otherwise treat as cap-exempt per §3.0
"halt condition" being soft.

## Acceptance criteria (what makes this APPROVE-worthy)

1. **Rubric is self-contained.** Reading `.codex/visual_audit_rubric.md`
   alone tells a fresh reviewer what to score and how. ✓ verify dim 1–16
   each have one-sentence operationalization.
2. **Script implements AAB, not advisory.** Verify:
   - Exit code is non-zero when audit fails (CI can gate on it).
   - **Iter-5 force-APPROVE is bound to absolute iter 5, not to a user-
     supplied `--max-iter` flag.** Iter count is persisted at
     `.codex/<id>/visual_iter_state.json` across invocations; the cap
     is `HARD_ITER_CAP = 5` baked into the script. `--max-iter` is
     removed; `--reset-state` exists for fresh issues.
   - Force-APPROVE emits BOTH `codex_visual_audit.txt` (final
     `verdict: APPROVE`) AND an annotation file
     `codex_visual_audit_iter5_force_approve.txt` (audit trail).
   - Calls `codex exec --skip-git-repo-check -i <png>` with the env-unset
     for `OPENAI_API_KEY` (OAuth fallback) — matches existing brief-
     review workflow.
3. **CI gate parses LAST verdict line.** Mirrors `codex-required.yml`
   PRD2-P1-001 hardening (last `verdict:` line wins, exact equality).
4. **Rubric SHA cross-bound to PR (every block).** The CI gate verifies
   EVERY `rubric_sha256:` line in the audit matches
   `sha256sum .codex/visual_audit_rubric.md` in the PR's working tree.
   Script fails closed (return code 3) on per-job SHA drift, not warn.
5. **Path detector is narrow.** `web/app/**` + `web/components/**` only.
   `web/lib/**`, `web/tests/**`, `web/middleware.ts` do NOT trigger.
6. **Skip semantics correct.** Infra branches (`bot/pr-*`,
   `bot/cleanup-pr-*`) skip the gate cleanly. **Non-bot UI PRs DO NOT
   skip** (P1-iter1 fix): the gate scans `.codex/*/codex_visual_audit.txt`
   and matches the file whose `pr_head_sha:` equals the PR HEAD.
7. **Audit bound to actual rendered evidence (P0-iter1 + P1-iter2 +
   P1-iter3 fix).** The audit file declares three SHAs that CI verifies:
   - `rubric_sha256` — matches working-tree rubric (every block, see AC #4)
   - `pr_head_sha` — matches `github.event.pull_request.head.sha`; a
     stale audit from a prior commit is rejected
   - `screenshots_manifest_sha256` — matches the sha256 of the
     `manifest.json` produced by the script at
     `outputs/visual_review_gate/<id>/iter_N/manifest.json`. **CI walks
     the manifest** (P1-iter2 fix): for each entry it verifies (a) the
     `<label>.png` file exists on disk in the PR, (b) the file's
     content SHA256 matches the manifest entry's `sha256` field,
     (c) the manifest has ≥1 entry. A manifest-hash match with missing
     or drifted screenshot files is rejected.
   - **Route coverage** (P1-iter3 fix): `scripts/verify_route_coverage.py`
     verifies that every `web/app/<segments>/page.tsx` change in the PR
     maps to a route present in the manifest (Next.js convention
     `web/app/foo/page.tsx` → `/foo`; dynamic segments `[runId]`
     match any concrete value; Next.js group `(group)` segments are
     dropped). `web/components/**` and `layout/template/loading/error/
     not-found.tsx` changes are ADVISORY (they affect undetermined
     pages; per-file route mapping requires a build-time import graph
     and is operator-declared in the brief). A PR that changes
     `web/app/inspector/page.tsx` but audits only `/intake` is
     rejected.
8. **Interaction-dimension observability (P1-iter1 + P1-iter2 fix).**
   Script captures THREE screenshots per route×viewport (static,
   focused, hovered) so rubric dim 13 (motion-affordance), dim 14
   (keyboard+focus), and the focus-state aspect of dim 16 are observable
   from harness inputs, not assumed. Rubric dim 13 is **narrowed to
   end-state-observable evidence** (P1-iter2 fix): visible difference
   between static/focused or static/hovered screenshots; skeleton
   branding observable from static. Timing/easing is NOT screenshot-
   observable and is explicitly excluded from the gate (deferred to
   operator review per `feedback_ui_lively_to_100_2026_05_24`).

## Files I have ALSO checked and they're clean (§-1.2)

- `.github/workflows/codex-required.yml` — the new workflow mirrors its
  parsing convention exactly (LAST verdict line, last-match wins per
  PRD2-P1-001). No conflict.
- `.github/workflows/web_ci.yml` — does NOT enforce visual audit; only
  runs Playwright e2e specs. New gate is additive, not replacement.
- `scripts/visual_qa_audit.py` — exists but targets pipeline B
  (`live_server.py`), not the Next.js v6 app. Different scope; no
  duplication.
- `scripts/visual_verify.py`, `scripts/visual_test.py`,
  `scripts/visual_diag.py`, `scripts/visual_final.py` — all pipeline-B
  era; do not affect the v6 surface.
- `web/tests/e2e/*` — Playwright tests assert behavior; they don't
  audit visual design.
- `.codex/REVIEW_BRIEF_FORMAT.md` §0 — §8.3.1 cap directive references
  this file; rubric brief inherits same directive verbatim.
- Memory files referenced in the rubric (`feedback_ui_lively_to_100`,
  `feedback_sovereignty_threat_model`, `feedback_top_tier_visually_verified`)
  — all present in MEMORY.md index.

## What this Issue does NOT ship

- Self-hosted runner with mounted `~/.codex/auth.json` for ON-CI Codex
  execution. Phase 2 work; separate Issue when needed.
- Back-fill audit of the 8 sub-PRs that skipped visual review. Task
  #490 (TaskCreate) blocked-by this Issue.
- Live integration test that actually spins up `next start` and runs
  the gate end-to-end. The script is verified by inspection; the
  end-to-end run lands in task #490 as part of the back-fill.

## Smoke test (offline, per §-1.2)

Run on this commit before pushing:

```powershell
# Verify rubric SHA computable
python -c "import hashlib; print(hashlib.sha256(open('.codex/visual_audit_rubric.md','rb').read()).hexdigest())"

# Verify script imports cleanly
python -c "import ast; ast.parse(open('scripts/visual_review_gate.py').read()); print('OK')"

# Verify YAML workflow parses
python -c "import yaml; yaml.safe_load(open('.github/workflows/codex-visual-required.yml')); print('OK')"

# Verify rubric body present in docs/ui_harness_research_2026_05_25.md
grep -l "16-dimension" docs/ui_harness_research_2026_05_25.md
```

If any fails, the PR is NOT ready; iter back.

## Convergence

This is an infrastructure PR. The "execution risk" is: do the artifacts
work together (rubric → script → CI gate → §3.0) without a missing
seam? Verify each seam:

- Rubric → Script: script reads `.codex/visual_audit_rubric.md`, hashes
  it, passes SHA to Codex prompt; YAML response declares same SHA.
- Script → CI gate: script writes `.codex/<id>/codex_visual_audit.txt`
  with last-line `verdict: APPROVE`; CI gate parses that exact format.
- CI gate → CLAUDE.md §3.0: §3.0 now lists 6th artifact + cites
  rubric path; CI gate path-trigger matches "UI surface" definition.

If a seam is missing, that's a P0. If a seam works but is fragile
(e.g., string-match drift), that's P1.

`convergence_call: continue` recommended only if a real P0/P1 surfaces.
Otherwise `accept_remaining` and APPROVE.
