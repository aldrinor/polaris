HARD ITERATION CAP: 3 per document (operator-set for this campaign). This is iter 1 of 3.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Do not pick bone from egg" — if a finding is not a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 3 returns REQUEST_CHANGES, the document is force-APPROVE on remaining non-P0/P1 findings.
- If you are holding back a P1 for a later round — DO NOT. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

3-PRONG SKEPTICISM CHECK ON YOUR OWN ADVICE (Claude is the final judge of your comments and WILL reject any that violate these): do NOT suggest anything that (1) RELAXES FAITHFULNESS (weakens strict_verify / NLI / 4-role / span-grounding, ships unverified-as-verified, makes a fail-closed path fail-open), (2) GRANDFATHERS / is OUTDATED (pre-2024 approach, old model), or (3) CHOKES THE NECK (adds a cap / floor / throttle / hard-filter / thinner — the banned filter-and-cap anti-pattern; the pipeline DNA is WEIGHT-AND-CONSOLIDATE). A timeout that is a hang-guard with a disclosed error row is NOT a neck-choke; a relevance/breadth cap IS.

FRONTIER-TECH MANDATE: judge against 2025-2026 frontier async/timeout practice; reject any grandfathered pattern.

TASK: STATIC code review (do NOT run pytest, do NOT execute anything) of the diff at C:/POLARIS/.codex/iarch011_campaign/distill.patch for I-arch-011 bug B19. Read that patch file and, if needed, the cited source in src/polaris_graph/generator/evidence_distiller.py.

BUG B19 (root cause of the B15 generator hang): the two distill_map LLM calls (call_type="distill_map") passed NO timeout=, so for reasoning-first deepseek-v4-pro the effective per-call bound resolved to ~6530s; a half-open SSE socket hung the asyncio loop until only the 10800s run-wall backstopped.

FIX UNDER REVIEW: (a) new env knob PG_DISTILL_MAP_CALL_WALL_S default 1800 (chosen ABOVE the 1475s observed healthy-call telemetry, well under the 10800s run-wall) passed as timeout to BOTH distill_map call sites; (b) PG_DISTILL_MAX_PARALLEL default raised 4->8; (c) the asyncio.gather over the map fan-out now uses return_exceptions=True + an isinstance(BaseException) guard so ONE timed-out source does not cancel the whole map — the timed-out source becomes a LOUD fail-closed coverage row (status=map_failed), never a silent drop.

CHECK: correctness; that a timeout yields a DISCLOSED coverage row (never unverified-as-verified, never a silent breadth drop); that no faithfulness gate is touched; that nothing here is a §-1.3 cap/floor/throttle (the wall is a hang-guard; the 4->8 raise widens fan-out). Flag any way the gather guard could still drop a source silently or the wall could truncate a HEALTHY call.

OUTPUT SCHEMA (the FINAL line MUST be exactly "verdict: APPROVE" or "verdict: REQUEST_CHANGES"):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
