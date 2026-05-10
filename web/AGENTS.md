<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

<!-- END:nextjs-agent-rules -->

<!-- BEGIN:polaris-evaluation-debug-standards-2026-05-09 -->

# STANDING EVALUATION & DEBUG STANDARDS (binding)

Per project `CLAUDE.md` §-1 (added 2026-05-09 per user directive).

## §-1.1 Line-by-line audit standard (clinical-safety-critical)

Every content/quality evaluation MUST be a **line-by-line, claim-by-claim, citation-by-citation, reasoning-step-by-reasoning-step** audit against the **actually-fetched source content** using the highest industrial benchmarks (PRISMA 2020, AMSTAR-2, GRADE per claim, ICMJE, ICH-GCP, Cochrane RoB 2 / ROBINS-I / QUADAS-2, jurisdiction-specific frameworks: FDA label, EMA SmPC, Health Canada PM, NICE TA, MHRA AR, TGA PI, PMDA review, NMPA labeling).

Both Claude AND Codex MUST run independent audits in parallel. Cross-review combines findings.

Per-claim verdict required: VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE — with the specific evidence span quote that supports the verdict.

**STRICTLY BANNED:** word counts, citation counts, unique-source counts, pattern presence ("does the report mention X?"), sample-based audits ("we audited 5 of 50 claims"), string-presence checks (PASS/FAIL on "does it cite [N]?"), metadata comparison ("ChatGPT has 27 contradictions, POLARIS has 3, so ChatGPT is better"), spot-checking, "looks coherent" assertions without reading every cited span.

**Why:** clinical context. Pattern-matching evaluation will miss real fabrications. Patients can be hurt by a wrong dose, wrong contraindication, wrong indication population that survived a metadata check. Length is liability, not advantage.

## §-1.2 Standard debug workflow (no §3.0 bypass)

Every task / bug / issue follows this sequence (§-1.2 governs _task-work_; the §3.1 boot ritual and §3.0 halt-marker checks always run first and can preempt this sequence):

1. **GitHub Issue FIRST** (first _task-work_ call). `gh issue create` BEFORE any branch, code, or brief. Title `I-<prefix>-NNN — <one-line summary>`; body has acceptance criteria.
2. **Comprehensive grep/scan adjacent files.** Before writing the brief, grep all call sites, consumers, downstream rule checks, tests. List them in the brief under "Files I have ALSO checked and they're clean: [...]".
3. **Smoke test offline** (single sentence/section), NOT a full sweep, before claiming the change works.
4. **Codex brief** with the iter-1 cap directive verbatim + adjacent-file scan results so Codex VERIFIES rather than discovers.
5. **Codex APPROVE → diff → Codex APPROVE on diff.** Goal: 1-2 iters per task, not 5. The 5-cap is a backstop, not a target.
6. **If a big bug surfaces and cannot be resolved in 5 iters, mark URGENT new GitHub Issue and resolve it FIRST.** Do not let cap-5 force-approve a real production blocker.
7. **Close the GitHub Issue when the PR merges.** Do not leave resolved issues open.

<!-- END:polaris-evaluation-debug-standards-2026-05-09 -->

<!-- BEGIN:polaris-restart-2026-05-05 -->

# POLARIS issue-driven workflow (mandatory)

Per project `CLAUDE.md` §3.0 + `state/polaris_restart/plan.md`:

- Every unit of work is a GitHub Issue from `state/polaris_restart/issue_breakdown.md`.
- Per-Issue 5-artifact triple required (brief + verdict + diff + audit + claude_audit). CI enforcement lands at PR-D; pre-PR-D, Codex review enforces.
- Per plan §7.A LOCKED A2 + §7.B LOCKED B1: Claude writes briefs + diffs; Codex reviews twice per Issue (brief + diff); CI required check `polaris/codex-required` gates GitHub auto-merge; user reads `git log` morning.
- **HARD ITERATION CAP: 5 per Codex review** (added 2026-05-06 per CLAUDE.md §8.3.1). If Codex has not APPROVE'd by iter 5, Claude force-APPROVE's and ships, capturing residual concerns as follow-up Issues. Every brief MUST include the verbatim cap directive (see CLAUDE.md §8.3.3 + `.codex/REVIEW_BRIEF_FORMAT.md` §0).
- **Resource discipline (CPU/RAM/GPU)** per CLAUDE.md §8.4 (added 2026-05-06): one `codex exec` at a time; kill leftover python/node/codex processes between iters; no heavy ML/CUDA processes in autonomous loops; track long-running dev servers and kill before next Issue; pre/post-task `Get-Process` inventory.
- `gh pr merge --admin` REVOKED from Claude.

Read project `CLAUDE.md` §3.0 + §10 boot ritual before any frontend work.

<!-- END:polaris-restart-2026-05-05 -->
