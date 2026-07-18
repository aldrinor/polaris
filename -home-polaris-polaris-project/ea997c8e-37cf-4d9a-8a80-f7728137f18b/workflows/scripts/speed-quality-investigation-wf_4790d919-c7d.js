export const meta = {
  name: 'speed-quality-investigation',
  description: 'Serious investigation: where does deep-run wall-time actually go, why does the 16-way compose deadlock at scale, and what speedups keep deep coverage + faithfulness. Ranked, quality-safe plan.',
  phases: [
    { title: 'Profile', detail: '4 parallel lenses: retrieval, compose-deadlock, whole-pipeline, quality-constraints' },
    { title: 'Stress-test', detail: 'adversarially verify each proposed speedup keeps coverage + faithfulness' },
    { title: 'Synthesize', detail: 'Fable: ranked safe speedup plan', model: 'fable' },
  ],
}

const CTX = `
POLARIS SPEED-VS-QUALITY INVESTIGATION. Established facts (measured today):
- A deep report render (route_all = 328 of 329 baskets) takes ~30+ min END-TO-END, and the AGENTIC
  RETRIEVAL phase (the react loop fetching URLs one turn at a time) dominates (~24 min); the COMPOSE
  phase is the smaller slice.
- We ported compose_fix's 16-way concurrency into outline_agent. The OFF-LOOP to_thread wrap is
  verdict-safe. But the aggressive PG_COMPOSE_BASKET_WORKERS + semaphore(48) DEADLOCKED at full
  328-basket scale: 19/20 threads stuck in futex_wait, 0 progress 8.8min, had to SIGKILL. The small
  verdict-identity A/B passed but never exercised full-scale concurrency.
- Also observed: the outline can DEGRADE to seed+partial under load (must stay cp4_used=agentic).

QUALITY INVARIANTS ANY SPEEDUP MUST KEEP (non-negotiable):
1. DEEP COVERAGE: render ~328/329 baskets (route_all). Do NOT speed up by dropping baskets/coverage.
2. FAITHFULNESS: strict_verify gate intact; kept/dropped NLI verdict set unchanged; no unverified/
   derived number renders via [CITE:ev_xxx]. Speed must be verdict-identical.
3. AGENTIC: cp4_used=agentic, never degrade-to-seed as a shortcut.
4. NO DEADLOCK: a speedup that can hang is not a speedup.

READ-ONLY: read code in /home/polaris/wt/outline_agent and /home/polaris/wt/compose_fix; run cheap
deterministic profiling; write findings ONLY to /home/polaris/polaris_project/speed_investigation.md.
Do NOT edit either worktree (a wheel is live in outline_agent). Source key for any measured run:
set -a; . /workspace/POLARIS/.env; set +a. Report REAL measured numbers; if you can't measure, say so.
`

const FIND = {
  type: 'object', required: ['lane', 'findings'],
  properties: {
    lane: { type: 'string' },
    findings: { type: 'array', items: {
      type: 'object', required: ['what', 'evidence', 'proposed_speedup', 'quality_risk'],
      properties: {
        what: { type: 'string', description: 'the bottleneck/mechanism at file:line or measured' },
        evidence: { type: 'string', description: 'REAL number or code cite, not a guess' },
        proposed_speedup: { type: 'string', description: 'the concrete change and its expected time saving' },
        est_saving: { type: 'string', description: 'rough wall-time saved' },
        quality_risk: { type: 'string', description: 'which of the 4 invariants it could threaten, and how to keep it safe' },
      } } },
  },
}
const VERDICT = {
  type: 'object', required: ['keeps_quality', 'reason'],
  properties: {
    keeps_quality: { type: 'boolean', description: 'does this speedup keep coverage+faithfulness+agentic+no-deadlock' },
    real_saving: { type: 'string' },
    reason: { type: 'string' },
  },
}

const LANES = [
  { key: 'retrieval', prompt: `LANE: RETRIEVAL — the dominant ~24-min cost. Read the agentic outline's react/retrieval loop (search_more_evidence, fetch_url, live_retriever, the react turn loop in outline_agent.py). Determine WHY it's slow: sequential per-turn URL fetches? no fetch concurrency? redundant re-fetches? per-turn LLM decide latency? too many turns for 328 baskets? Measure fetch count / turn count if you can. Propose speedups that KEEP evidence quality: parallel/batched fetching, a fetch cache, capping turns without losing coverage, prefetch. For each, state the quality risk (must not drop coverage or fabricate).` },
  { key: 'deadlock', prompt: `LANE: COMPOSE DEADLOCK ROOT-CAUSE. The 16-way port deadlocked at 328-basket scale (19/20 threads futex_wait). Read the ported code in outline_agent multi_section_generator.py (PG_COMPOSE_BASKET_WORKERS basket-workers + off-loop to_thread) and compose_fix's original. Find the ACTUAL lock: is a shared semaphore (judge slot / LLM semaphore / get_semaphore) acquired ACROSS the off-loop thread boundary, or re-entrantly, causing a thread-pool ⨯ semaphore deadlock? Why did compose_fix gate parallel-verify OFF by default? Give the safe subset that CANNOT deadlock (likely off-loop-only, or basket-workers with a non-shared/timeout-guarded semaphore) and the exact fix.` },
  { key: 'pipeline', prompt: `LANE: WHOLE-PIPELINE PROFILE. Break the end-to-end deep run into phases (retrieval, outline build, credibility pass, compose draft, strict_verify, dedup/consolidate, RACE score) and estimate each phase's wall-time share from the real logs (outputs/_16way_run.log, step*_compose.log). Which phase is the biggest lever AFTER retrieval? Is the 41% sentence-drop rate causing wasted compute (drafting sentences that get dropped)? Rank the phases by time and by speedup-leverage.` },
  { key: 'quality-guard', prompt: `LANE: QUALITY-CONSTRAINT AUDIT. For EACH speedup idea likely to come up (parallel retrieval, fetch cache, turn cap, off-loop-only compose, basket-worker sharding, lower verify concurrency, batched judge), enumerate exactly which of the 4 invariants (deep coverage / faithfulness verdict-identity / cp4_used=agentic / no-deadlock) it threatens and the concrete guard that keeps it safe. Flag any 'speedup' that only works by quietly dropping baskets, weakening the verify gate, or degrading to seed — those are DISQUALIFIED.` },
]

phase('Profile')
const perLane = await pipeline(
  LANES,
  lane => agent(`${CTX}\n\n=== YOUR LANE ===\n${lane.prompt}`, { label: `probe:${lane.key}`, phase: 'Profile', schema: FIND }),
  (res, lane) => {
    if (!res || !(res.findings || []).length) return []
    return parallel(res.findings.map(f => () =>
      agent(`${CTX}\n\nADVERSARIALLY VERIFY this proposed speedup. Does it REALLY save meaningful wall-time AND keep ALL 4 quality invariants (deep coverage, faithfulness verdict-identity, cp4_used=agentic, no-deadlock)? Default to keeps_quality=FALSE if it risks any invariant or the saving is marginal.\n\nSPEEDUP: ${f.proposed_speedup}\nCLAIMED SAVING: ${f.est_saving}\nSTATED RISK: ${f.quality_risk}\nEVIDENCE: ${f.evidence}`,
        { label: `verify:${lane.key}`, phase: 'Stress-test', schema: VERDICT })
        .then(v => ({ ...f, lane: lane.key, verdict: v }))))
  },
)
const survivors = perLane.flat().filter(Boolean).filter(f => f.verdict && f.verdict.keeps_quality)

phase('Synthesize')
const plan = await agent(
  `${CTX}\n\nYOU ARE FABLE. Synthesize the RANKED, QUALITY-SAFE speedup plan from the speedups that
survived adversarial quality-verification:\n${JSON.stringify(survivors, null, 2)}\n
Deliver: (1) the end-to-end time breakdown and the single biggest honest lever. (2) A RANKED plan —
what to do first for the most wall-time saved while keeping ALL 4 invariants, with the guard for each.
(3) The compose-deadlock: the exact safe fix (and confirm the off-loop-only fallback is deadlock-free
+ verdict-identical). (4) An honest ceiling: after the safe speedups, roughly how fast can a deep
328-basket faithful run get, and what CANNOT be sped up without sacrificing quality. Do not propose
anything that drops coverage, weakens faithfulness, or degrades to seed — those are off the table.`,
  { label: 'fable:speedup-plan', phase: 'Synthesize', model: 'fable', effort: 'high' },
)

log(`SPEED INVESTIGATION: ${survivors.length} quality-safe speedups survived`)
return { survivors, plan }
