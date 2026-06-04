# MiniMax-M2 Sentinel certification evidence (I-run11-004 / #1046)

Codex diff-gate iter-2 P1-4: the production cert artifact. (outputs/ is gitignored, so the
evidence is copied here for the PR.) Source of truth: outputs/audits/I-run11-004/sentinel_certification.md
+ the per-model cache outputs/audits/I-run11-004/cache/certify_minimax_minimax-m2.jsonl (this file is the
CORRECT artifact — NOT sentinel_bakeoff_result.json, which holds the stale race-contaminated
glm_decomposition run with FA=3).

## Result (reliable 56-item fixture: 28 grounded + 28 fabricated across 5 error types)
- model: minimax/minimax-m2, claim-decomposition + span-coverage prompt (the certified GLM_PROMPT).
- coverage: 56/56 claims, 56 cached verdicts.
- FALSE_ACCEPTS on the 28 fabrications: **0** (NUMBER_SWAP 4 / ENTITY_SWAP 4 / NEGATION 4 / FABRICATED_ATTRIBUTION 5 / SCOPE_INFLATION 11 — all caught).
- over_flag: 3/28 = 0.107; grounded_recall 0.893.
- Codex independent APPROVE: .codex/I-run11-004/certification_verify_verdict.txt (labels_reliable=yes, zero_false_accept_sound=yes, n_adequate=yes, p0=[], p1=[]).

## Honest caveat
n=28 fabrications across 5 deterministic error types on drb_72 AI-labor spans; this certifies the
headline failure modes, not a full clinical statistical validation. The released run-13 report
audit vs ChatGPT/Gemini is the end-to-end §-1.1 test.