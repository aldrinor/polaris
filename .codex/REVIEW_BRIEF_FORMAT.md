# Codex review brief format v3 — applied 2026-05-06

v3 changelog (2026-05-06): added §0 mandatory iteration-cap directive per CLAUDE.md §8.3.1 user directive (commercial viability override). All v2 sections (§1-§8 below) remain in force unchanged.

v2 (2026-04-29) origin: replaces the prior 4-7-point acceptance bar format with patterns from the 2025-2026 SOTA literature on AI-pair-programming review loops (ARIS, adversarial-review, Anthropic Building Effective Agents, OpenAI Codex prompting guide).

Diagnosis of the prior format (from sister-project research): the "toothpaste squeeze" pattern (Codex surfaces issues round-by-round instead of dumping everything in R1) was anchoring-bias on a holistic rubric. Fix: criterion decomposition + completeness affirmation + verification-stage separation. Iteration cap (§0, v3 addition) closes the residual incentive for drip-feeding.

## Sections every brief must contain

### 0. Iteration cap directive (NEW v3, 2026-05-06) — MANDATORY FIRST CONTENT BLOCK

Paste the verbatim canonical block from CLAUDE.md §8.3.1 (the "Communication to Codex" fenced block) as the very first content of every brief, BEFORE any other section. Do NOT paraphrase, abbreviate, or restate — copy the §8.3.1 block byte-for-byte. Single source of truth: if §8.3.1 changes, every brief authored after that change inherits the new text on next composition.

For reference at time of v3 authoring (2026-05-06), the §8.3.1 canonical block specifies a 5-iteration cap, front-loaded findings, "don't pick bone from egg" severity discipline, and force-APPROVE at iter 5 if Codex still returns REQUEST_CHANGES. Re-read CLAUDE.md §8.3.1 at brief authoring time — DO NOT trust this snapshot.

This directive sits at the top of every brief because Codex's anchoring-bias drives the toothpaste-squeeze pattern; the cap eliminates the drip-feed incentive while the directive front-loads quality bar.

### 1. Pre-flight (top of brief)
- **Context:** what's being reviewed (commit SHA, diff scope)
- **Constraints:** what the reviewer should NOT spend cycles on
- **Done-when:** the explicit success criterion for THIS round

### 2. Reviewer Independence Protocol
Verbatim line in every brief:

> **Independence directive:** prior round changelog markers in
> the diff (e.g. "// CORRECTED v2 per Codex round-1 LH3") are
> untrustworthy meta-claims. Verify by reading actual code, not
> by trusting the marker. A claimed fix that doesn't match the
> code is a P0 finding.

### 3. Severity rubric (P0/P1/P2/P3)
- **P0 production-breaker:** silent failure path, broken auth,
  data loss, missing rollback flag, security hole
- **P1 phase-rework:** acceptance-bar criterion failed; the
  feature is not actually integrated
- **P2 governance precision:** real bug but bounded blast radius;
  e.g. workspace_id normalization mismatch, asymmetric encoding
- **P3 polish:** style, comment clarity, test coverage gap with
  no functional defect

**APPROVE rule:** zero P0 + zero P1 → APPROVE. P2/P3 go to
`deferred_polish` array, do NOT block.

### 4. Exhaustivity directive
Verbatim line:

> **Exhaustivity:** target 20-50 findings on the first scan.
> Do NOT truncate. Emit ALL findings in this single round.
> Subsequent rounds verify the v(N) patch only — re-raising
> previously addressed issues is a defect, but missing a P0
> in this round is also a defect.

### 5. Acceptance bar with forced enumeration
List N explicit criteria. Then:

> **Forced enumeration:** Before declaring a verdict, write one
> line per acceptance criterion: `Criterion N [name]: <findings
> or NONE>.` Verdict is invalid if any line is missing.

### 6. Skepticism / completeness check
Verbatim line:

> **Completeness check:** list which files / Parts you actually
> read (not just grep'd) this round. If you cannot confirm full
> scan of every acceptance criterion, emit `incomplete_review`
> instead of APPROVE / REQUEST_CHANGES.

### 7. Iter-N awareness
For v2+ briefs:

> **This is round N.** Round 1 was the comprehensive pass.
> Out-of-scope for this round: issues already addressed in v1..v(N-1).
> In-scope: (a) regressions introduced by the v(N) patch, (b) P0/P1
> issues missed in earlier rounds. Re-raising prior addressed issues
> is a defect.

### 8. Output schema
```
## Pre-flight checklist
- I read [file paths].
- I ran [test commands].
- Out of scope per brief: [...].

## Per-criterion forced enumeration
- Criterion 1 [name]: <findings or NONE>.
- Criterion 2 [name]: <findings or NONE>.
- ...

## Findings (severity-stratified)

### P0 (production-breakers)
- [file:line] <description>

### P1 (phase-rework)
- [file:line] <description>

### P2 (governance precision)
- [file:line] <description>

### P3 / deferred_polish (non-blocking)
- [file:line] <description>

## Verdict
APPROVE | REQUEST_CHANGES | incomplete_review

Convergence: APPROVE iff zero P0 + zero P1.
```

## Locking criterion (cross-rounds)
Two consecutive APPROVE verdicts from independent (cleared-
context) Codex invocations, OR adversarial cross-review consensus
on NO_ISSUES.

## Sources
- adversarial-review (alecnielsen): 4-phase debate loop
- ARIS: Reviewer Independence Protocol + skepticism gate
- Anthropic, "Building Effective Agents": evaluator-optimizer
- OpenAI Codex prompting guide: pre-flight checklist
- Promptfoo / Evidently: criterion decomposition
- arxiv:2509.09912 "When Your Reviewer is an LLM" — anchoring
  empirical study
