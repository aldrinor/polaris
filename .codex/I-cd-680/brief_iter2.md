# Codex review — I-cd-680 (iter 2 of 5)

HARD ITERATION CAP: 5. iter 2. Front-load findings. APPROVE iff zero P0 + zero P1.
Per merge protocol (.codex/I-cd-567/DECISION.md): final line must include MERGE AUTHORIZED if mergeable. Touches only src/polaris_v6/api/** + tests/** (not the operator-only exclusion list).

Canonical-diff-sha256: `9ab8e617f5589c906bd7d89defeb28aaf7d79e388945082896c3882c3340f026`.

## Iter-1 P1+P2 all fixed
- P1 release-gate bypass → load_evidence_contract_for_run now mirrors bundle.tar.gz: abort_*→422, not-is_dir→404, manifest release_allowed=False→422. New release-blocked 422 test.
- P1 missing-dir → is_dir()→404.
- P2 contradiction claims[]+evidence[] shape mapped.
- P2 import moved to module top.
- 48 tests pass.

## Review focus
1. Are both iter-1 P1s fully closed? Any remaining path where a non-shippable/abort/release-blocked real run yields a 200 EvidenceContract via /bundle, /followup, or /compare?
2. Any NEW P0/P1 from the gate additions.

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
