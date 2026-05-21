# Codex review — web/ pip-shim (unblocks the merge protocol)

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1. Final line MERGE AUTHORIZED if mergeable. Touches ONLY web/requirements*.txt (NOT .github/workflows — pushable by Claude's token).

Canonical-diff-sha256: `aed2618a0329b9ff2de001d33e85fdfb8104e17a65a8cc36e42f9f34dce1b4b4`.

## What + why
You designed this (Option C, merge_gate_decision_v2). web_ci.yml's verify_pip_resolution job runs pip dry-run from web/ (workflow-level default) but requirements.txt is at repo root → red on every src/polaris_v6 PR, blocking the merge protocol. The proper workflow fix is unpushable (no workflow scope on either token). This adds web/requirements.txt + web/requirements-v6.txt forwarding shims (`-r ../requirements.txt`) so the dry-run from web/ resolves the canonical root files.

## Review focus
1. Do the shims correctly forward (`-r ../requirements.txt` relative to web/ = repo root)? Confirms the pip dry-run will go green.
2. Any risk the shim is picked up unintentionally elsewhere (Docker build, real pip install)? (Dockerfile.v6 installs from requirements.lock per #623, not web/requirements.txt.)
3. Is the "remove once workflow fix lands" follow-up adequately noted in-file?
4. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: [...]
```
