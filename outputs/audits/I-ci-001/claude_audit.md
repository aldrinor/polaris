# Claude architect audit — GH #571 (I-ci-001)

**Issue:** GH #571 (I-ci-001) — `codex-required` ISSUE_ID regex collapses
`-followup` issue IDs onto the parent and rejects carved `a/b/c` IDs.
**Acceptance:** path (a) — fix the gate's ISSUE_ID derivation to support
`-followup` and carved-letter suffixes as distinct issue IDs, with matching
`.codex/<id>/` dirs; Codex APPROVE.
**Branch:** `bot/I-ci-001` off `polaris` HEAD `a359df80`.
**Commit 1:** `74112202` — 2 files, +152/-4.
**Brief:** Codex brief review APPROVE iter 1 (0 P0/P1; 1 non-blocking P2 —
addressed, see §4).

## 1. Provenance

Not a recut — `bot/I-ci-001` is a fresh branch; no prior in-flight PR
exists for I-ci-001 (`gh pr list --search "I-ci-001 in:title"` returned
only unrelated `bot/I-lint-001` / `bot/I-sec-001-*` results). Loop
selected #571 per the Codex next-action consult
(`.codex/autonomous_overnight_loop/`): #571 was mis-grouped with #567 as
"operator-handoff" in the loop's exclusion list; it is in fact a normal
bounded CI-workflow code fix needing no GitHub-mechanics handoff.

## 2. The (a)-vs-(b) decision

The issue body deferred the (a)-regex-fix vs (b)-naming-convention choice
to Codex. The brief folded that consult in and recommended (a); Codex's
brief-review APPROVE is the binding ruling for (a). (a) makes the gate
*correct* for IDs already in the queue; (b) would leave the gate broken
and force a permanent mismatch between carved issues' GitHub titles
(`I-rdy-014a/b/c`) and their artifact dirs.

## 3. What shipped

`.github/workflows/codex-required.yml` — `extract_and_validate_issue_id`
arm-1 regex:

```
- ^bot/(I-[a-z0-9]{2,8}-[0-9]{3})(-[a-z0-9_-]+)?$
+ ^bot/(I-[a-z0-9]{2,8}-[0-9]{3}(-followup|[a-z])?)(-[a-z0-9_-]+)?$
```

The base-id capture group (group 1, the only group the code reads via
`BASH_REMATCH[1]`) now absorbs an optional `-followup` literal OR a single
bare carved letter. Plus comment-text updates (the new I-ci-001 paragraph;
extended GATE examples; the reject-arm `echo` schema string). New test
`tests/test_codex_required_issue_id_regex.py` extracts the live ERE from
the YAML and asserts the branch-name table.

## 4. Per-finding verification

- **VERIFIED — `-followup` no longer collapses.**
  `bot/I-rdy-019-followup-test-matrix` → `BASH_REMATCH[1]` =
  `I-rdy-019-followup` (was `I-rdy-019`, the parent #515's dir). The
  `-followup` literal is consumed by the nested `(-followup|[a-z])` inside
  group 1; the descriptive slug `-test-matrix` falls to group 3. Proven:
  the smoke script shows OLD → `I-rdy-019`, NEW → `I-rdy-019-followup`.
- **VERIFIED — carved IDs no longer rejected.** `bot/I-rdy-014a` →
  `I-rdy-014a`. OLD: regex no-match → catch-all `bot/*` reject arm →
  workflow `exit 1`. NEW: `[a-z]` consumes the bare `a`.
- **VERIFIED — `[a-z]` not `[a-c]` (resolves Codex brief P2).** Codex's
  brief-review P2 flagged that carved IDs beyond `c` exist in repo history
  (`I-arch-001d/e/f`, #466/#467/#468). The brief proposed `[a-c]` per the
  issue's literal acceptance text; the implementation widens to `[a-z]` —
  strictly more correct, zero ambiguity cost (the leading-dash, not the
  letter range, is the carved-vs-slug discriminator), and eliminates a
  future false-reject. This is the deliberate response to the P2, not a
  silent deviation from the approved brief.
- **VERIFIED — additive / zero regression.** Every pre-existing branch
  form resolves byte-identically OLD vs NEW: `(-followup|[a-z])?` matches
  empty whenever the next token starts with `-` (descriptive slug) or ends
  the ref. Smoke script's regression block confirms `I-ci-001`,
  `I-bug-079`, `I-f1-001-scope-discovery`, `I-hand-003-final`,
  `I-rdy-014-a` all unchanged. `bot/I-rdy-014-a` (dashed single-letter
  slug) still → `I-rdy-014`; `bot/I-rdy-014a` (bare) → `I-rdy-014a`.
- **VERIFIED — group renumbering inert.** The slug group shifts from
  group 2 to group 3; the bash code references only `BASH_REMATCH[1]`
  (line 81). No other group is read.
- **VERIFIED — downstream paths.** `.codex/${ISSUE_ID}/` artifact paths +
  the `:(exclude).codex/${ISSUE_ID}/` / `:(exclude)outputs/audits/${ISSUE_ID}/`
  canonical-diff pathspecs consume the full ID automatically — a
  `-followup`/carved PR creates `.codex/I-rdy-019-followup/` etc. and the
  gate excludes the correct dir. `scripts/ci/codex_artifact_gate.py` +
  `scripts/extract_codex_verdict.py` receive `ISSUE_ID` / read
  `.codex/<id>/`; they do not re-derive the ID from the branch — correct
  full ID in ⇒ correct behavior. Not modified.
- **VERIFIED — infra + reject arms untouched.** The `elif` infra-allowlist
  regex (line 85) and `else` non-bot arm are unchanged; no
  followup/carved infra branch exists.
- **Accepted residual (P3):** `-followup` *of a carved* issue
  (`bot/I-rdy-014a-followup`) parses to `I-rdy-014a` with `-followup` as a
  group-3 slug. This nesting does not exist in the queue; the issue names
  only the two flat classes; such a case falls back to the recut playbook.
  Documented in the brief §3.4.

## 5. Smoke

YAML valid (`yaml.safe_load`). Test file `ast.parse` clean.
`pytest tests/test_codex_required_issue_id_regex.py` — **25 passed** in
0.86s. Old-regex-fails proof: the smoke script confirms the OLD regex
yields `I-rdy-019` / `<no match>` for the followup + carved cases (the bug)
and the NEW regex yields the correct IDs — the LAW II
reproducible-failing-test-now-passes evidence. No `src/` runtime code
touched; no other suite in scope.

## 6. Codex iteration trail

- Brief: Codex brief review APPROVE iter 1 — 0 P0, 0 P1, 1 P2
  (non-blocking, addressed by the `[a-c]`→`[a-z]` widening),
  `convergence_call: accept_remaining`.

## 7. Verdict

Option (a) implemented surgically: one regex line + comment text in
`codex-required.yml`, one new extraction-based test. The `-followup`
collapse and carved-ID rejection are both fixed and proven; the
`[a-c]`→`[a-z]` widening resolves the sole Codex P2; zero regression on
every pre-existing branch form. Ready for Codex diff review.
