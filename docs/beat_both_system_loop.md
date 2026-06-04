# POLARIS Beat-Both System Loop (all 5 golden DR questions)

**Status:** BINDING standing loop for the beat-both mission. Operator-authored 2026-06-04.
**Reminder mechanism:** `.claude/hooks/ultimate_goal_stop_reminder.py` (Stop hook) re-injects a
condensed form of this loop every time a turn would end while the mission is unfinished. Status is
tracked in `state/beat_both_status.json`.

**Mission:** a RELEASED POLARIS run on each of the 5 LOCKED golden DRB-EN questions that BEATS BOTH
ChatGPT and Gemini on §-1.1 line-by-line / claim-by-claim faithfulness. Not one question — all five.

The 5 LOCKED questions (`project_golden_dr_benchmark_questions_locked_2026_05_28`):
- `drb_72_ai_labor` (source-critical)
- `drb_75_metal_ions_cvd` (clinical)
- `drb_76_gut_microbiota_crc` (clinical)
- `drb_78_parkinsons_dbs` (clinical)
- `drb_90_adas_liability` (source-critical)
Report the clinical-3 and the overall-5 separately. Honest label: "citation-faithfulness stress
slice (3 clinical + 2 source-critical)", NOT "hardest".

---

## CROSS-CUTTING DISCIPLINE — runs through EVERY phase, IN PARALLEL (not after)

These are not optional cleanup-at-the-end; they happen alongside every run, audit, and fix. Skipping
them is a loop violation (operator flagged 2026-06-04: "you forget about github and doc update, and
file hygiene and management").

**A. GITHUB — issue-driven, in parallel (CLAUDE.md §-1.2, §3.0):**
- Every new issue/bug/fix opens a **GitHub Issue FIRST** (`gh issue create`, title `I-<prefix>-NNN —
  <summary>`, acceptance criteria in body) — before any branch, code, or brief.
- Work on a `bot/<issue>` branch; the fix carries the 5-artifact triple (`brief.md`,
  `codex_brief_verdict.txt` APPROVE, `codex_diff.patch` + canonical-diff-sha256 trailer,
  `codex_diff_audit.txt` APPROVE, `outputs/audits/<id>/claude_audit.md`).
- Codex is the only gate; PR queues for OPERATOR merge (Claude has NO merge authority). **Close the
  GitHub Issue when its PR merges.** Post findings/run results as issue comments as they land — keep
  GitHub current, not a morning data-dump.
- Do NOT mix unrelated concerns in one PR ("while we're at it" is banned); one issue = one branch =
  one PR. A canonical-diff-sha256 trailer must bind ONLY the code Codex actually reviewed.

**B. DOCS — updated in parallel with the code that changes them:**
- When the system changes, update the docs in the SAME cycle: `architecture.md` role/flow tables (if
  not canonical-pinned — pinned files need an operator-signed reconciliation, defer those),
  `docs/file_directory.md`, `docs/runbook.md` / `docs/carney_demo_runbook.md`, `logs/session_log.md`
  (§2.2 entry per action), `state/polaris_restart/iteration_trajectory.md` (every Codex iter),
  `state/beat_both_status.json` (per-question status), and the relevant memory under the
  per-project memory dir + its `MEMORY.md` index line.
- Docs lag is a loop violation. A reader of `git log` + the docs in the morning must see the whole
  trail without asking.

**C. FILE HYGIENE & MANAGEMENT (CLAUDE.md §4, §8.4):**
- snake_case names; right directory; one responsibility per file; no bloat / dumping-ground files.
- `git add` EXPLICIT paths (never `git add -u` / `.` — they choke on permission-denied codex tmp
  dirs and sweep junk); verify with `git show --stat` after every commit.
- Diagnostics/scratch/run artifacts stay gitignored (`.codex/<id>/` slim, `outputs/`, `state/`
  runtime); never commit secrets (`.env`, keys) or large caches.
- ONE heavy job at a time; before/after any heavy step list + kill orphan `codex/python/node`
  (§8.4); never two `codex exec` in parallel.
- Clean up temp dirs you create; keep the working tree tidy so branch/PR ops don't trip on cruft.

---

## PHASE 0 — RESEARCH-FIRST, NEVER GUESS (the gate on EVERY new issue)

For ANY new issue/bug/failure surfaced anywhere in the loop — a held run, a lost benchmark, a §-1.1
finding, a system bug — BEFORE writing a single line of fix:

1. **Research the LATEST + BEST + TOP solutions** for the specific failure class — on GitHub
   (issues, PRs, releases of the relevant libraries/frameworks) AND the wider internet (papers,
   engineering blogs, SOTA leaderboards). Use WebSearch + WebFetch. Examples of the failure class to
   search: "deep-research agent low coverage / release held", "long-form report claim faithfulness
   verification SOTA 2026", "RAG retrieval recall improvement", "citation grounding hallucination
   detection", "claim decomposition entailment". Cite what you find.
2. **Deeply review those solutions** — how are other people solving THIS, lately? What's the current
   best practice, and why? What did they try that failed?
3. **Deeply review OUR source code, line by line**, on the exact path that produced the issue
   (retrieval / generation / verification / scoring). Quote the real `file:line`.
4. **Deeply review OUR output content, line by line** — the actual produced report, the
   `four_role_claim_audit.json`, the fetched source spans, the scorer output. Read the real text,
   claim by claim, against the cited span — not metadata, not pattern presence (§-1.1).
5. **ONLY THEN design the fix**, grounded in (research ∧ our code ∧ our output). A hand-rolled
   A/B/C options list with no research and no line-by-line read is "blind, fucking around" — banned
   (`feedback_research_then_empirically_test_candidates_2026_06_03`).
6. **For any serious / architecture / safety / release-blocking choice: empirically bake off MULTIPLE
   candidate fixes on a REAL labeled test set** (§-1.1 ground truth, real claims+spans, deterministic
   corruptions for the negatives) and let recall/precision pick the winner. Evidence decides, never
   assertion. Prefer the Workflow engine for the research + bake-off.

Phase 0 is the no-guess gate. Skipping it (guessing a fix) is the failure this loop exists to prevent.

---

## PHASE 1 — WHOLE SYSTEM RUN (not a component)

Run the FULL pipeline on the question(s), the exact shipping path (`scripts.dr_benchmark.run_gate_b
--only <slug>` on the VM, 4-role transport). It must RELEASE a verified report (not hold / abort like
run-12 `abort_four_role_release_held`). Benchmark the TOOL, not a cheap component proxy
(`feedback_benchmark_the_tool_not_a_component_2026_05_28`).

- Watch the real stage progression: scope → retrieval → corpus gates → generation → 4-role verify →
  release. Confirm the verifier runs on ALL claims (not truncated by the seam timeout).
- Freshness gate: `docker inspect StartedAt`; trust run artifacts ONLY when mtime > StartedAt (run
  dir is reused). Never read a stale prior run's artifacts as if fresh.
- A component passing its unit tests is NOT a released system. Only a released whole-system run counts.

---

## PHASE 2 — WHOLE-REPORT AUDIT (§-1.1, line-by-line)

Audit the ENTIRE released report, claim by claim, against the FETCHED source spans:
- Per claim: VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE, with the cited span quote
  that supports the verdict. Cited span TEXT, not title/abstract; not metadata; not pattern presence.
- Apply the domain benchmark: clinical → PRISMA 2020 / AMSTAR-2 / GRADE per claim, ICH-GCP for trial
  methods, RoB 2 / ROBINS-I / QUADAS-2; source-critical → source provenance + attribution integrity.
- **Claude AND Codex run independent line-by-line audits in parallel**; cross-review combines findings.
- Banned: word/citation/source counts as quality, sample-based audits ("audited 5 of 50"),
  string-presence PASS/FAIL, metadata comparison. These are lethal in clinical context.

---

## PHASE 3 — WHOLE-SYSTEM BEAT-BOTH (head to head)

Score POLARIS's report AND ChatGPT's AND Gemini's on the SAME question with the SAME claim-by-claim,
evidence-locked scorer (`src/polaris_graph/benchmark/claim_audit_scorer.py`; substring-validated
span_quote). External reports: `outputs/dr_benchmark/external_outputs/{gpt_5_5_pro,gemini_3_1_pro}/
Q<NN>_*.md`.

- Beat-both = POLARIS has fewer UNSUPPORTED/FABRICATED claims AND higher faithful coverage than BOTH
  competitors on that question. Score all three IDENTICALLY (system-agnostic).
- Claude + Codex independent; reconcile to one verdict per question.
- A "win" is real only when (a) the run was RELEASED and (b) the benchmark was source-grounded
  claim-by-claim. Never claim beat-both on a held run or a metadata comparison.

---

## PHASE 4 — DIAGNOSE → FIX → SMOKE → RE-RUN (system, not just verifier)

If the system HOLDS (no release) or LOSES (doesn't beat both) on a question:
1. Diagnose the **system** cause across the whole pipeline — retrieval breadth/recall, generation
   grounding, coverage threshold, verification — NOT only the verifier. Read the run's stage logs +
   artifacts line-by-line to localize it.
2. Run **PHASE 0** on that cause (research-first, no-guess, line-by-line code + output).
3. Fix → **offline smoke** (single sentence/section, before any full sweep) → **Codex gate** (the
   only gate; §8.3.1 5-iter cap; a clinical-safety fail-OPEN in the verifier is the §-1.1 lethal
   exception — fix it, never force-approve) → **fresh whole-system re-run** (Phase 1).
4. A fix that helps one question MUST NOT regress the others — re-run the affected questions.

---

## PHASE 5 — COVER ALL 5 QUESTIONS

The mission is beat-both on ALL 5 golden questions, reported clinical-3 + overall-5. Cycle Phases
1–4 per question. Track per-question status in `state/beat_both_status.json`
(`{question: released|audited|beat_both|lost|held|blocked}`). The mission is complete only when all
5 are `beat_both` on a released, source-grounded run.

---

## STOP CONDITIONS (the ONLY legitimate reasons to end the loop)

- All 5 questions `beat_both` on released + source-grounded benchmarks → notify the operator.
- A real halt fired (a `state/halt_*` marker): canonical/CHARTER pin drift, VM down, Codex
  unavailable >1h, a NEW verifier safety fail-open that cannot be closed, spend ceiling crossed,
  same root cause failing 2+ cycles, network unusable >1h.
- The operator explicitly says stop.
- Legitimately WAITING on a long external run: set `state/beat_both_status.json.waiting_on` to the
  run id and schedule a wakeup — yielding to wait is allowed; abandoning the loop is not.

Self-initiated "natural cadence / good place to pause" stops are NOT legitimate (CLAUDE.md §8.3.10).

## GUARDRAILS (always on)

- Codex is the only review gate. GitHub + docs updated in parallel. File hygiene; one heavy job at a
  time; kill orphan codex/python (§8.4).
- Voters/arbiter + generator = OPEN-WEIGHT only, strongest LATEST frontier; no closed/old/weak/encoder
  models. Never lower the §-1.1 bar or the false-accept threshold.
- Only a RELEASED run + a real source-grounded per-claim benchmark = beat-both. No metadata audits.
- Claude has NO admin-merge authority; PRs queue for operator merge.
