# POLARIS Statistical Safety Contract v3.3 — Lock Manifest

**Status**: Methodology-locked pre-registration draft.

**Lock date**: 2026-05-27

**Lock verdict source**: `codex_review_trail/05_v3_3_final_lock_verdict.txt`
("Lock v3.3 as pre-registration draft" — Codex round-3 final, all 10 items ✓ closed)

## Authorship

Paired-LLM authorship, no external statistician:
- Claude (Opus 4.7): drafted v3.0 architecture + applied Codex review findings across v3.1/v3.2/v3.3
- Codex (gpt-5.5): design-partner reviewer with deep statistical research; identified architectural gaps and mechanical errors across 4 review rounds (deep-dialogue + design-partner + 3 round-N audits)

Per operator directive 2026-05-27:
> "Codex 5.5 + Claude 4.7 with max reasoning power + super deep research skill on CLI beat 99.999% statisticians in the world... combine effort between Codex 5.5 + Claude 4.7 with max reasoning power, to work it out, stop asking me to reach out another person to help"

## Lock procedure (§11)

1. [x] Codex final verdict: lock as pre-registration draft
2. [x] Hash-pin commit in `state/polaris_statistical_contract/v3_3/`
3. [ ] **Operator sign-off** (pending — surface for review)
4. [ ] **Notarized timestamp** (post-operator-signoff)

## Next operational step

After operator sign-off:
- v3.4 = post-Phase-0a numerical specification (raw n per stratum, ICC ceiling escalation result, BH/BY validity-path choice, coefficient choice per §7.2 missingness audit)
- v3.4 lock procedure: same as v3.3
- THEN Phase 0b labeling begins (per the contract's pre-registration rules — must be hash-pinned before outcomes seen)

## Files

- `contract.md` — the v3.3 contract (locked methodology, deferred numerics)
- `contract.sha256` — SHA256 hash-pin of contract.md
- `codex_review_trail/` — the 6-file dialogue and review trail
- `codex_review_trail.sha256` — SHA256 hash-pin of the trail files
- `LOCK_MANIFEST.md` — this file
