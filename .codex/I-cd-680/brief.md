# Codex review — I-cd-680 real-run resolution for follow-up + compare

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. No drip-feeding. Same bar regardless of iter.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Per the operator-directed merge protocol (.codex/I-cd-567/DECISION.md): if this diff is mergeable, your final line must include `MERGE AUTHORIZED`. Preconditions Claude will independently verify before merging: codex-required CI green, canonical-diff SHA matches the PR diff, decision posted verbatim. #680 touches only src/polaris_v6/api/** + tests/** — NOT the operator-only exclusion list, so Claude may execute the merge if you authorize.

Canonical-diff-sha256: `f45725b069432f7ba90bb4c7c0cb85b63068190b67e6755d879e0e91730af855`. 6 files.

## What this implements (your Option B scope decision)

followup.py + compare.py were fixture-locked (_GOLDEN_RUN_INDEX) → real runs 404. Now they resolve real run_id → artifact_dir via run_store and build a typed EvidenceContract from the slice-chain (the proven bundle.tar.gz path). No fabricated source-doc offsets; full EvidenceContract capability deferred to #710.

- NEW `artifact_to_evidence_contract.py`: build_evidence_contract_from_artifact() reuses build_slice_chain. SourceSpan.span_start=0, span_end=len(span_text) — the truthful self-offset of the recorded evidence text (rich source-document offsets deferred to #710; NOT fabricated).
- `bundle.py`: shared load_evidence_contract_for_run() (golden fixture OR real run); get_bundle returns real-run EvidenceContract (was 404→tar.gz pointer); 404 unknown/not-completed/missing-artifacts; 422 sovereignty-emptied.
- `followup.py` + `compare.py`: use the shared resolver.
- Tests: 4 builder unit tests + updated bundle real-run test + existing followup/compare/slice-chain suites = 47 pass.

## Review focus (be adversarial)

1. **Honesty of span_start=0/span_end=len** — is this acceptable per your "no fabricated char offsets" rule, given it's the truthful self-offset of the recorded span text (not a claimed offset into the original source body)? Or is it misleading and should the deferred capability be required now?
2. **Resolver correctness** — does load_evidence_contract_for_run handle all run states (unknown→404, queued/running→404, completed-no-artifact→404, completed-valid→200, sovereignty-emptied→422)?
3. **import-inside-function** of build_evidence_contract_from_artifact in bundle.py — intentional (avoid heavy import at module load); any circular-import or correctness risk?
4. **Did removing _GOLDEN_RUN_INDEX/_FIXTURE_DIR imports from followup.py + compare.py** break anything (they're still defined in bundle.py for the resolver)?
5. Any NOVEL P0/P1.

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
