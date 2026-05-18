# Codex BRIEF review — GH #571 (I-ci-001): codex-required ISSUE_ID regex collapses -followup IDs onto the parent + rejects carved a/b/c IDs

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## §0.1 Review stage

This is a **BRIEF review** — review the *plan* below for acceptance-criteria
correctness and scope, NOT a code diff. The diff review is a separate later
Codex call. **This brief also folds in the (a)-vs-(b) consult** the issue
body explicitly defers to Codex (see §2) — your verdict on this brief IS the
ruling on (a) vs (b). If you prefer (b), return REQUEST_CHANGES naming (b);
otherwise APPROVE endorses (a) as scoped.

## 1. Issue context (GH #571, OPEN, no prior PR)

`.github/workflows/codex-required.yml` is the required-status-check that
gates `bot/<issue_id>` PR merges. Its `extract_and_validate_issue_id` step
(line 80) derives `ISSUE_ID` from the PR head ref:

```
if [[ "$HEAD_REF" =~ ^bot/(I-[a-z0-9]{2,8}-[0-9]{3})(-[a-z0-9_-]+)?$ ]]; then
  issue_id="${BASH_REMATCH[1]}"            # group 1 only
```

`ISSUE_ID` then drives the artifact paths `.codex/${ISSUE_ID}/{brief.md,
codex_brief_verdict.txt,codex_diff.patch,codex_diff_audit.txt}` +
`outputs/audits/${ISSUE_ID}/claude_audit.md`, AND the canonical-diff
exclusion pathspecs `:(exclude).codex/${ISSUE_ID}/` /
`:(exclude)outputs/audits/${ISSUE_ID}/` (lines 155-159, 206-207).

**Two issue-ID classes break this** (verified against the live queue):

1. **`-followup` collapses onto the parent.** Branch
   `bot/I-rdy-019-followup-test-matrix`: group 1 `(I-[a-z0-9]{2,8}-[0-9]{3})`
   matches only `I-rdy-019`; `-followup-test-matrix` is consumed by group 2
   as a droppable slug. `ISSUE_ID=I-rdy-019` — the **parent #515's**
   already-merged `.codex/I-rdy-019/` dir. The gate then reads #515's
   `codex_diff.patch` trailer hash and excludes the wrong dir from the
   canonical-diff computation. Observed on #558/PR #569 (`declared
   17dd8d74… vs actual 63ccfc8f…`). Live `-followup` issues that hit this:
   #537, #539, #547, #549, #558, #561.

2. **Carved `a/b/c` IDs fail the regex entirely.** Branch `bot/I-rdy-014a`:
   group 1 matches `I-rdy-014`, leaving a bare `a`; group 2
   `(-[a-z0-9_-]+)?` requires a leading `-` so it cannot consume `a`; the
   whole regex fails → falls through to the `elif bot/* …` reject arm (line
   114) → the workflow `exit 1`s and `codex-required` ERRORs the PR. Live
   carved issues: #542/#543/#544 (`I-rdy-014a/b/c`).

Current workaround (the issue loop's recut playbook): re-cut any
`-followup`/carved branch to a fresh canonical `I-<prefix>-<NNN>` (#558 →
`bot/I-rdy-558-test-matrix`, merged as PR #570). This works but is a
per-PR manual tax and renames the issue ID away from its GitHub number.

## 2. The (a)-vs-(b) decision — folded consult (issue body defers this to Codex)

The issue body offers two acceptance paths and explicitly says the choice
is "routed to the operator / Codex":

- **(a)** Fix the gate's ISSUE_ID derivation to support `-followup` and
  carved-letter suffixes as *distinct* issue IDs, with matching
  `.codex/<id>/` dirs.
- **(b)** Document a branch-naming convention: every issue — incl.
  followups/carved — gets a fresh canonical `I-<prefix>-<NNN>`; the gate
  docs state it; the recut workaround becomes the permanent standard.

**This brief recommends (a).** Rationale:
- (a) makes the gate *correct* for IDs that already exist in the queue
  (#537/#539/#542/#543/#544/#547/#549/#558/#561). (b) leaves the gate
  technically broken and depends on human discipline forever.
- (b) forces a permanent mismatch: the carved issues' GitHub titles are
  literally `I-rdy-014a/b/c`, but (b) would require their branches/artifact
  dirs to use a different invented number — the artifact trail no longer
  maps to the issue.
- (a) is surgical and low-risk (see §3: one regex line + comment text + a
  new test). The change is *additive* — every branch name that matched
  before still matches identically (proof table in §3.2).

If you disagree and prefer (b), REQUEST_CHANGES naming (b) and I will
re-scope to a docs-only PR.

## 3. The plan (option (a))

Two files. No `src/` runtime code touched. No behavior change for any
branch name that already worked.

### 3.1 `.github/workflows/codex-required.yml` — regex extension (arm 1, line 80)

```
# before
if [[ "$HEAD_REF" =~ ^bot/(I-[a-z0-9]{2,8}-[0-9]{3})(-[a-z0-9_-]+)?$ ]]; then
# after
if [[ "$HEAD_REF" =~ ^bot/(I-[a-z0-9]{2,8}-[0-9]{3}(-followup|[a-c])?)(-[a-z0-9_-]+)?$ ]]; then
```

- Group 1 now = `I-<prefix>-<NNN>` **plus** an optional `-followup` literal
  OR a single carved letter `[a-c]`. `BASH_REMATCH[1]` (the only group the
  code reads) becomes the *full* canonical ID.
- The nested `(-followup|[a-c])` is group 2; the descriptive slug
  `(-[a-z0-9_-]+)?` shifts to group 3. **The code only references
  `BASH_REMATCH[1]`** (line 81) — group renumbering is inert.
- POSIX ERE (bash `[[ =~ ]]`): only literals, char classes, `?`,
  alternation, anchors — no `(?:)`, no backrefs. Compatible.
- `[a-c]` per the issue's literal acceptance text (`(-followup|[a-c])`);
  carved issues beyond `c` do not exist; widening to `[a-z]` later is a
  one-char change. Stated here so it is a deliberate choice, not an
  oversight.

Plus comment-text updates in the same step (lines ~76-79 GATE examples;
the PRD4-P1-001 note ~62-66; the reject-arm `echo` at line ~119) so the
in-file documentation matches the new accepted forms. No logic change in
those edits — comments only.

### 3.2 Branch-name proof table (verify each row)

| HEAD_REF | old result | new `BASH_REMATCH[1]` | arm |
|---|---|---|---|
| `bot/I-ci-001` | `I-ci-001` | `I-ci-001` | gate (unchanged) |
| `bot/I-f1-001-scope-discovery` | `I-f1-001` | `I-f1-001` | gate (slug→group3, unchanged) |
| `bot/I-bug-079` | `I-bug-079` | `I-bug-079` | gate (unchanged) |
| `bot/I-rdy-019-followup` | `I-rdy-019` ✗ | `I-rdy-019-followup` ✓ | gate (FIXED) |
| `bot/I-rdy-019-followup-test-matrix` | `I-rdy-019` ✗ | `I-rdy-019-followup` ✓ | gate (FIXED) |
| `bot/I-rdy-014a` | regex fails → REJECT ✗ | `I-rdy-014a` ✓ | gate (FIXED) |
| `bot/I-rdy-014b` / `-014c` | REJECT ✗ | `I-rdy-014b` / `-014c` ✓ | gate (FIXED) |
| `bot/I-rdy-014-a` (dashed single-letter slug) | `I-rdy-014` | `I-rdy-014` | gate (slug `a`→group3; dash distinguishes from carved) |
| `bot/pr-d-mechanical-gates` | infra skip | infra skip | elif (unchanged) |
| `bot/pr-malicious` | REJECT | REJECT | else-reject (unchanged) |
| `bot/setup-anything` | non-bot? no — `bot/` reject | reject | reject (unchanged) |

Key correctness points to verify:
- `-` is not in `[a-z0-9]`, so `[a-z0-9]{2,8}` cannot bleed past the
  `-<NNN>` boundary; the carved `[a-c]` only ever sees the char right
  after the 3 digits.
- A descriptive slug always carries a leading `-` (loop convention
  `bot/<id>-<slug>`); the carved letter never does. The dash is the
  discriminator — `bot/I-rdy-014a` (carved) vs `bot/I-rdy-014-a` (slug).
- Additive: every pre-existing match is byte-identical because
  `(-followup|[a-c])?` matches empty whenever the next token starts with
  `-` or ends the ref.

### 3.3 New test — `tests/test_codex_required_issue_id_regex.py`

LAW II reproducible evidence. The test **reads the regex out of
`.github/workflows/codex-required.yml`** (greps the
`=~ ^bot/(I-` line, extracts the ERE) rather than hardcoding a copy — so it
cannot silently drift from the workflow. It translates the ERE to Python
`re` (1:1 for this regex — no PCRE-only constructs) and asserts the full
§3.2 table: each branch name → expected `BASH_REMATCH[1]` or "no match".
Against the OLD regex the `-followup`/carved rows FAIL; against the new
regex they PASS — the required failing-test-now-passes proof.

### 3.4 Accepted residual (P3, documented honestly)

`-followup` *of a carved issue* (`bot/I-rdy-014a-followup`) parses to
`I-rdy-014a` with `-followup` as a group-3 slug — i.e. it collapses onto
the carved parent. This nesting does not exist in the queue and the issue
names only the two flat classes. Such a case still falls back to the recut
playbook (fresh canonical number). Called out so it is a known boundary,
not a silent gap.

## 4. Scope-boundary calls

- **In scope:** `codex-required.yml` arm-1 regex + its comment text; one
  new test file. That is the whole PR.
- **Out of scope:** the `elif` infra-allowlist regex (line 85) — untouched,
  no followup/carved infra branches exist. The `cleanup_pr_ancestry_check.yml`
  workflow — separate gate, not ID-derivation. `scripts/extract_codex_verdict.py`
  / `scripts/ci/codex_artifact_gate.py` — they receive `ISSUE_ID` / read
  `.codex/<id>/`, they do not re-derive the ID from the branch name; once
  arm 1 yields the correct full ID they work unchanged (confirmed §5).
- **No `.codex/` dir rename needed:** future `-followup`/carved PRs simply
  create `.codex/I-rdy-019-followup/` etc.; the gate's
  `.codex/${ISSUE_ID}/` + exclusion pathspecs consume the full ID
  automatically.
- **CLAUDE.md NOT edited** (standing-order constraint). The branch-naming
  documentation for (a) lives in the workflow's own comment block.

## 5. Files I have ALSO checked and they are clean

- `scripts/ci/codex_artifact_gate.py` — operates on a passed `ISSUE_ID` /
  `.codex/<id>/` paths; does not parse the branch ref. Correct full ID in
  ⇒ correct behavior. Not modified.
- `scripts/extract_codex_verdict.py` — verdict-file extraction; ID-agnostic.
  Not modified.
- `.github/workflows/cleanup_pr_ancestry_check.yml` — ancestry gate for
  `cleanup-pr-*`; no issue-ID derivation. Not modified.
- `codex-required.yml` `elif` infra arm (line 85) + `else` non-bot arm
  (line 126) + `verify_codex_artifacts` / `skip_summary` steps — logic
  unchanged; only arm-1 regex + comments change.
- The `tests/v6/` suite + `tests/` root — no test currently exercises this
  regex (grep clean); the new file is net-new, no collision.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema. If you rule for (b)
instead of (a), say so explicitly in `p1`/`remaining_blockers`.
