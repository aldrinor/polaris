HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is embedded
verbatim below (§C). Review ONLY that diff.

# Codex brief review — I-cd-003 / GH#622: canonical-pin reconciliation (URGENT)

## §A — Context

`docs/canonical_pin.txt` pins the SHA256 of 10 canonical files (CLAUDE.md §3.1
step-0 boot ritual + `.claude/hooks/stop_hook_v3.py:_verify_canonical_pin`).
The pin records the SHA256 of each file's **HEAD blob** (LF) — confirmed: the
4 non-drifted entries match `git show HEAD:<f> | sha256sum` exactly.

#524 (this issue) — the pin has drifted: canonical files were legitimately
changed without updating the pin. Acceptance: pins reconciled; §3.1 verifier
green.

## §B — The drift (verified this session)

Per-file `git show HEAD:<f> | sha256sum` vs the pinned SHA — **6 of 10 drifted,
4 match**:

DRIFT: `docs/carney_delivery_plan_v6_2.md`, `architecture.md`,
`docs/task_acceptance_matrix.yaml`, `.codex/REVIEW_BRIEF_FORMAT.md`,
`.codex/AUDIT_CYCLE_PROTOCOL.md`, `CLAUDE.md`.
MATCH: `docs/blockers.md`, `docs/agent_architecture.md`,
`docs/substrate_audit_2026-05-01.md`, `.codex/codex_red_team_checklist.md`.

Empirical: `_verify_canonical_pin()` returns
`(False, 'HEAD SHA mismatch for docs/carney_delivery_plan_v6_2.md: pin says
3c77e65463ba, HEAD has 9471a3967fda')` — it fails at step 3 (pin==HEAD) on the
first file.

## §C — The fix (the complete diff under review)

`docs/canonical_pin.txt` was **regenerated deterministically from HEAD** — for
each of the 10 files, `git show "HEAD:<f>" | sha256sum`, written in the
original file order. No hand-transcription. Result: the 6 drifted SHAs updated
to their current HEAD blob SHA, the 4 matching lines byte-identical. Diff =
exactly 6 lines:

```diff
diff --git a/docs/canonical_pin.txt b/docs/canonical_pin.txt
--- a/docs/canonical_pin.txt
+++ b/docs/canonical_pin.txt
@@ -1,10 +1,10 @@
-3c77e65463bab9e41a7ad54d1bb79ef1b83ddc21b8c0c1599d38e2402738bc3a  docs/carney_delivery_plan_v6_2.md
-8e8e7e2fb9358f83b9c27257f51cd3d8e82dd693b5e5ae7ffd698c46c411a19f  architecture.md
+9471a3967fda558c4507fcac83dac8e317fb5c2bd2ad8013d9f70a6ae257f694  docs/carney_delivery_plan_v6_2.md
+e1ef87574abe3470108a687336c6208cc9f6818e9ce515fc4f88a25421648b2e  architecture.md
 5d97dddba498c4dd50550f29b46f22dc8b6d26cd10532caa4405a0229d770199  docs/blockers.md
-0124a6240fd9b943e88112d2093a2f06ab14e77b0c12cb0f3084e703790936e2  docs/task_acceptance_matrix.yaml
+911c53b0645d4fe07e46b88d8a28ce5c5f13ba3db91a638a78c3a97d07664109  docs/task_acceptance_matrix.yaml
 61764ac6cbae2f241207acc32ee508aa99f084d324f0978f2ef89fc055b02122  docs/agent_architecture.md
 0ba71ca0ed94aac749b02e668b72f86af7ebfda6ee058e4319cb5953d0014617  docs/substrate_audit_2026-05-01.md
 92d9e650daad50d69b418979593801aef756473f28173af2f5fff7c78bec787f  .codex/codex_red_team_checklist.md
-f6db0746c0312a10276c55b4cee2eaf2b7edc67155abe44b9fcd2ead7e4509ab  .codex/REVIEW_BRIEF_FORMAT.md
-b51789187d70d7677ab7dcde356c3d2b321b33375028e2ba403de54ea9587cac  .codex/AUDIT_CYCLE_PROTOCOL.md
-652da8119a163b8155f39b3dc5d7c1e98dacabf8d1196a6aa144dbbe7db2325e  CLAUDE.md
+8710f63f1bcf3f2e83339a24ae7e0b36a872678152a383f25fe5ada2c2bc0c52  .codex/REVIEW_BRIEF_FORMAT.md
+2ec2f10bb4726ff658dc1e89cf72c7c86f392838a76f98811b031def2edefa4c  .codex/AUDIT_CYCLE_PROTOCOL.md
+bf3809edab56fcefd6c574feebb5aeaff2fbf73c04534173081e6cc9b3a6b5cf  CLAUDE.md
```

Verified: after this change, every line's SHA == `git show HEAD:<f> |
sha256sum` for all 10. Post-commit, `_verify_canonical_pin` reads the new pin
from HEAD → step 3 (pin==HEAD) passes for all 10 → §3.1 step-0 green.

## §D — Scope boundary (a real finding, deliberately NOT bundled)

While verifying, I found a separate pre-existing defect and **filed it as
GH#658** (`I-cd-003-followup`) rather than fixing it here:

- `_verify_canonical_pin()` in `stop_hook_v3.py` is **defined but never
  called** — the runtime canonical-drift HARD STOP is not wired into the hook.
- Its step-5 working-tree check (`_file_sha256` raw bytes vs HEAD-blob LF)
  false-positives on `core.autocrlf=true` Windows for every CRLF-smudged
  canonical file.

This is NOT #524. #524 is the pin drift — a content mismatch fixed by a SHA
update. The hook-wiring + autocrlf-aware-comparison fix is a behavioral change
to the safety hook, deserves its own focused brief, and bundling it into a SHA
reconciliation would be scope creep. Confirm you agree the boundary is right.

## §E — Files I have ALSO checked and they are clean

- The 10 canonical files themselves — unchanged (this issue only re-pins them).
- `_verify_canonical_pin` step-3 logic — sound (parses pin from HEAD, compares
  to `_git_show_head_sha256`); the reconciled pin satisfies it.
- `.github/workflows/codex_verdict_check.yml` references `canonical_pin.txt`
  (passes it to a Codex check as a hash input) — consumes the file, not
  affected by the SHA values inside; no change needed.

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
