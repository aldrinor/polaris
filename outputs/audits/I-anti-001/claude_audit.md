# Claude architect audit — I-anti-001

## Issue scope
Paired-prompt corpus reaches 20 entries with neutral / leading / opposite-frame triples (4-framing tuple per existing schema).

## What landed
- tests/v6/fixtures/sycophancy_v1/paired_prompts.json: syc_defense_001 anchor refreshed to current "achieved 2% NATO target in 2026"; 9 new entries appended (NORAD, Paris, emissions cap, immigration target, dental, MAID, productivity, UNDRIP, Arctic defense).
- tests/v6/test_paired_prompts_corpus.py: 3 new corpus tests (≥20 entries, all-Pydantic-validate, 8-domain coverage + defense anchor current).

## Architectural alignment
- Plan §4.9 anti-sycophancy substrate; unblocks I-anti-002 stance-delta computation.
- §9.4 hygiene clean. CHARTER §3 LOC: 155 net.

## Iteration history
- Brief 5 iters: P1 entry arithmetic (3 vs 11 baseline) + P1 schema validation gap + P1 stale defense anchor (DND announcement March 2026 changed Canada's 2% status).
- Diff APPROVE iter 1.

## Verdict
Ready to merge. 19/19 tests pass (3 new + 16 existing). Codex brief APPROVE iter 5; Codex diff APPROVE iter 1.
