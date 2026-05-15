# Codex review iter 2 — I-rdy-002 (#498): Phase 1 gap verification

**Type:** REVIEW, iter 2 of 5. Iter 1 = REQUEST_CHANGES (2 P1, 3 P2). All addressed.

## §0. Cap directive: front-load all findings. APPROVE iff zero P0 and zero P1.

## §1. Iter-1 findings and fixes applied to `.codex/I-rdy-002/verification_findings.md`
- **P1 rich-UI under-stated** → FIXED. Rich UI is now CONFIRMED-BROKEN with the code evidence: `bundle.py:45-64` `_GOLDEN_RUN_INDEX`, and `charts.py`/`followup.py`/`compare.py` all import + gate on it → any non-golden run 404s. No LLM needed.
- **P1 missed P0 register gaps** → FIXED. Added: canonical templates CONFIRMED-BROKEN (`web/app/page.tsx` uses housing/climate/defense/trade, missing policy/tech/due_diligence/custom); model/env stale-refs CONFIRMED present; coherent product journey CONFIRMED-BROKEN.
- **P2 F14 memory** → FIXED. Now states live path confirmed in-memory (`memory.py:18,22` WorkspaceMemoryStore; Chroma exists but not wired).
- **P2 worker document_ids wording** → FIXED. Now: payload reaches `request_payload`, the break is `actors.py` builds `q` without `document_ids`.
- **P2 GPG** → FIXED. Now: live tarball path appears wired; clean-machine verification unproven.

## §2. Verify `.codex/I-rdy-002/verification_findings.md`
1. All 5 iter-1 findings correctly addressed.
2. Verdicts now accurate against the repo.
3. No remaining P0/P1 gap omitted from the verification.

## §3. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
iter1_findings_addressed: yes | no | partial
residual: [...]
verdict_reasoning: <text>
```
