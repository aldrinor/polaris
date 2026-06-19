HARD ITERATION CAP: 3 per document (operator-set for this campaign). This is iter 1 of 3.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Do not pick bone from egg" — if a finding is not a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 3 returns REQUEST_CHANGES, the document is force-APPROVE on remaining non-P0/P1 findings.
- If you are holding back a P1 for a later round — DO NOT. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

3-PRONG SKEPTICISM CHECK ON YOUR OWN ADVICE (Claude is the final judge of your comments and WILL reject any that violate these): do NOT suggest anything that (1) RELAXES FAITHFULNESS (weakens strict_verify / NLI / 4-role / span-grounding, ships unverified-as-verified, makes a fail-closed path fail-open), (2) GRANDFATHERS / is OUTDATED (pre-2024 approach, old model), or (3) CHOKES THE NECK (adds a cap / floor / throttle / hard-filter / thinner — the banned filter-and-cap anti-pattern; the pipeline DNA is WEIGHT-AND-CONSOLIDATE). A timeout that is a hang-guard with a disclosed error row is NOT a neck-choke; a relevance/breadth cap IS.

FRONTIER-TECH MANDATE: judge against 2025-2026 frontier JSON-parsing / structured-output / provider-routing practice; reject any grandfathered pattern.

TASK: STATIC code review (do NOT run pytest, do NOT execute anything) of the diff at C:/POLARIS/.codex/iarch011_campaign/judge.patch for I-arch-011 bugs B12/B14/B01. Read that patch file and, if needed, src/polaris_graph/llm/entailment_judge.py and src/polaris_graph/retrieval/semantic_conflict_detector.py.

BUGS: bare json.loads(content) on both side judges (entailment_judge.py:695, semantic_conflict_detector.py:779) cannot parse a "garbled-200" (a valid JSON verdict object FOLLOWED by trailing reasoning text -> "Extra data: ..."), throwing away a salvageable verdict; and response_format:{type:json_object} on both calls makes the novita+gmicloud mirror hosts 404, collapsing the 4-host chain to 2.

FIX UNDER REVIEW: (a) a new _extract_first_json_object() using json.JSONDecoder().raw_decode to pull the FIRST COMPLETE balanced object that CARRIES the required "verdict" field (so a leading non-verdict scratchpad object cannot be mis-selected and downgrade a strict HOLD to a fail-open neutral); it RAISES when no verdict-bearing object exists. (b) removed response_format:{type:json_object} from both calls so all 4 providers route.

CHECK (faithfulness is the crux here): confirm fail-closed behavior is PRESERVED on empty/None/non-str/malformed/verdict-less content (must still RAISE into the SAME existing except-handlers: entailment -> drop sentinel; semantic_conflict -> strict HOLD / non-strict neutral, unchanged). Confirm the extractor cannot make invalid partial JSON pass. Confirm removing response_format does not itself create a NEW fail-open path. Flag the live-host risk (a reasoning model could now blank the content field) as P2/P3 if you see it, but it is a known wiring/preflight item.

OUTPUT SCHEMA (the FINAL line MUST be exactly "verdict: APPROVE" or "verdict: REQUEST_CHANGES"):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
