export const meta = {
  name: 'compose-throughput-forensics',
  description: 'Line-by-line Opus investigation of what ACTUALLY caps compose throughput. 8 hypothesis lenses, adversarial verification, Fable synthesis. Find every serialization bug, not just the one we already know.',
  phases: [
    { title: 'Read', detail: '8 Opus investigators, one per failure hypothesis, line-by-line' },
    { title: 'Refute', detail: 'adversarially attack each finding — default to REFUTED' },
    { title: 'Synthesize', detail: 'Fable: ranked list of what really caps throughput', model: 'fable' },
  ],
}

const CONTEXT = `
POLARIS COMPOSE — THE INVESTIGATION.

WHAT COMPOSE DOES: renders 346 baskets into a deep research report. Compose model = z-ai/glm-5.2 via
OpenRouter. Each rendered sentence is verified by an NLI entailment judge (also via OpenRouter, SAME
account). Goal: render ALL 346 baskets fast. Today it is far too slow.

WORKTREE (read here): /home/polaris/wt/compose   — also /workspace/POLARIS for reference
KEY FILES: src/polaris_graph/generator/abstractive_writer.py, generator/quantified_analysis.py,
  the NLI/entailment judge + provenance_generator, scripts/run_s5_i3.py, launch_compose_gear_*.sh

WHAT IS ALREADY KNOWN — DO NOT RE-FIND THIS, GO PAST IT:
Commit 0615bc5 fixed ONE serialization bug: _draft_passes_wrapper (abstractive_writer.py:661) was a
sync \`def\` called with NO \`await\` from the async coroutine _pre_pass_one_basket (:749), at two call
sites. It ran writer_verify_fn -> verify_sentence_provenance -> entailment_judge.judge() ->
_post_with_total_deadline -> fut.result(timeout=...) which BLOCKS THE CALLING THREAD — and the calling
thread was the asyncio event loop. So every NLI judge POST froze the whole compose loop and achieved
concurrency was 1, regardless of PG_ABSTRACTIVE_WRITER_CONCURRENCY=12 / PG_MAX_CONCURRENT_LLM=16.
Both call sites now \`await asyncio.to_thread(...)\`. Measured A/B: 2.06s -> 0.60s on 4 baskets.

THE OPERATOR'S QUESTION, AND THE POINT OF THIS INVESTIGATION:
"The 48-way parallelism was never real. One missing await is a suspiciously tidy explanation. What
ELSE is capping compose? Is the context too large? Not enough token budget? Crashes? Something else?"
Your job is to find the REMAINING throughput killers. Assume there are more. There usually are.

RULES OF EVIDENCE (this is the whole game):
- A finding is a MECHANISM at file:line, not a vibe. "Context might be big" is worthless.
  "prompt is built at :412 by concatenating all N basket digests with no cap, so a 346-basket run
  sends ~X tokens per call, and TTFT scales linearly with it" is a finding.
- READ THE ACTUAL CODE. Do not reason from the summary above. Open the files.
- Where you can, PROVE it — a tiny probe script in /tmp, a python -c, a log grep with counts.
  A measured number beats a code-reading every time.
- Report REAL output. If you find nothing in your lane, say "nothing found" — a clean lane is a
  useful result. Do NOT invent a finding to look productive.
- NEVER print the OpenRouter API key.
`

const FINDING_SCHEMA = {
  type: 'object',
  required: ['lane', 'findings'],
  properties: {
    lane: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'file_line', 'mechanism', 'throughput_impact', 'evidence'],
        properties: {
          title: { type: 'string' },
          file_line: { type: 'string', description: 'exact file:line' },
          mechanism: { type: 'string', description: 'HOW it costs throughput, concretely' },
          throughput_impact: { enum: ['CRITICAL_serializes', 'HIGH', 'MEDIUM', 'LOW'] },
          evidence: { type: 'string', description: 'the code you read / the number you measured / the log lines' },
          measured: { type: 'boolean', description: 'true only if you PROVED it by running something' },
          fix_sketch: { type: 'string' },
        },
      },
    },
    nothing_found: { type: 'boolean' },
    notes: { type: 'string' },
  },
}

const REFUTE_SCHEMA = {
  type: 'object',
  required: ['refuted', 'reason'],
  properties: {
    refuted: { type: 'boolean', description: 'TRUE if the finding does not hold up. Default to TRUE when uncertain.' },
    reason: { type: 'string' },
    real_impact: { type: 'string', description: 'if it survives: what does it ACTUALLY cost, quantified' },
  },
}

// Eight lenses. Each is blind to the others — that is the point.
const LANES = [
  {
    key: 'more-event-loop-blocks',
    prompt: `LANE: OTHER EVENT-LOOP BLOCKS. The 0615bc5 bug was a sync call blocking the event loop.
FIND EVERY OTHER INSTANCE OF THAT BUG CLASS. Systematically hunt, across the whole compose path, for:
  - sync def called without await from inside an async def
  - .result() / .wait() / fut.result(timeout=) on a future, called on the event loop thread
  - time.sleep() (not asyncio.sleep) anywhere in an async path
  - requests/httpx SYNC client calls inside async code
  - blocking file I/O or sqlite calls on the loop (checkpoint writes! ev_store reads!)
  - threading.Lock / RLock acquired on the loop thread and held across an I/O call
Grep hard: 'def _', 'async def', '.result(', 'time.sleep', 'requests.', 'httpx.Client'.
Cross-reference every sync function called from every async one. This is the highest-yield lane —
the bug class already proved itself once. PROVE any hit: show the async caller AND the sync callee.`,
  },
  {
    key: 'context-size',
    prompt: `LANE: CONTEXT / PROMPT SIZE (the operator explicitly asked about this).
Trace EXACTLY what goes into each compose LLM call. Is the prompt built by concatenating all basket
digests / all evidence / the whole outline into every call? Is there a cap? MEASURE the real prompt
token count for a realistic 346-basket run — actually build one and count (tiktoken or len//4).
Questions: does prompt size scale with corpus size (O(N) per call = O(N^2) total)? Is the same huge
context re-sent on every one of hundreds of calls with no caching? Does GLM-5.2 prompt-cache apply
and are we structuring the prompt to hit it (stable prefix first)? Big context = slow TTFT + high
cost + more 429 weight (rate limits are often TOKEN-based, not request-based — check that).`,
  },
  {
    key: 'token-budget-truncation',
    prompt: `LANE: TOKEN BUDGET / TRUNCATION / RETRY-ON-TRUNCATION (operator asked about this too).
Find max_tokens / max_output / context-cap settings on every compose + judge call. Are we starving
the model (too-low max_tokens -> truncated output -> the code retries or discards -> wasted calls)?
Known related bug in this repo: "un-starve to GLM-5.2 real 131072 cap" (commit ecda022) — so
starvation HAS happened here before. Check: is there a truncation-detect -> retry loop? How often
does it fire in the REAL logs? Every retry is a doubled call. Also: reasoning-token truncation on
GLM-5.2 (the outline wheel has a documented 'GLM-5.2 reasoning truncation' failure). Count real
occurrences in logs, do not speculate.`,
  },
  {
    key: 'crash-retry-resume',
    prompt: `LANE: CRASHES, RETRIES, RESUME THRASH (operator asked: "crash?").
Read the REAL run logs for the recent s5/compose runs (outputs/s5_*, logs/, ckpt dirs). Count:
crashes, restarts, exceptions, retry storms, and whether the SELF-RELAUNCH launcher
(launch_compose_gear_*.sh, 'self-relaunch launcher' per commit 4e0b1f9) is looping — re-doing work
it already did. Check the SHA-gated section-level RESUME (commit 4e0b1f9): does it actually skip
completed sections, or does it silently redo them? A resume that re-renders finished work is a 2x+
throughput loss and looks like 'slow' rather than 'broken'. Also check for the two root-owned runs
self-contending. QUANTIFY from real logs: how many baskets got rendered more than once?`,
  },
  {
    key: 'concurrency-knobs-inert',
    prompt: `LANE: DO THE CONCURRENCY KNOBS ACTUALLY BIND?
PG_ABSTRACTIVE_WRITER_CONCURRENCY, PG_MAX_CONCURRENT_LLM, PG_SIDE_JUDGE_MAX_CONCURRENCY (default 4).
For EACH: trace from the env read to the actual semaphore/gather that uses it. Prove whether it is
LIVE on the compose path or INERT. (Precedent: the side-judge knob was documented as non-binding on
the compose path but binding elsewhere — knobs in this repo lie.) Look for: a semaphore created but
never awaited; a gather() over a list of size 1; a nested semaphore where the inner one is tighter
and silently dominates; a global cap that undercuts the per-stage cap. Find the SMALLEST effective
cap in the chain — that is the real concurrency, and it is probably much lower than anyone thinks.`,
  },
  {
    key: 'sequential-seams',
    prompt: `LANE: SEQUENTIAL SEAMS / HIDDEN BARRIERS.
Compose renders 346 baskets across sections. Map the ACTUAL control flow: what is parallel and what
is a barrier? Look for: a per-section await that waits for ALL baskets before starting the next
section (so wall-clock = sum of slowest-per-section, not max); a for-loop with await inside (classic
accidental serialization — should be asyncio.gather); passes that run strictly in sequence
(draft -> verify -> dedup -> coherence) when they could pipeline; a single-threaded post-processing
pass over all output. Draw the real execution graph and identify where the parallelism actually
collapses to 1. Cite line numbers for every await-in-a-loop you find.`,
  },
  {
    key: 'judge-verifier-path',
    prompt: `LANE: THE NLI JUDGE / VERIFIER — the high-call-volume half.
Every rendered sentence gets NLI-verified, so the judge is called FAR more than the writer. Read the
judge path end to end: entailment_judge.judge(), _post_with_total_deadline, provenance_generator,
judge_verdict_cache. Questions: is the judge called per SENTENCE (N calls) when it could be batched
(1 call, N pairs)? Is judge_verdict_cache actually hit, or does a key mismatch make the hit rate ~0
(MEASURE the hit rate)? Is there a per-call deadline/timeout that is way too long (a 300s deadline on
a hung call holds a slot for 5 minutes)? Is the ThreadPool bounded far tighter than the writer?
Provider rotation / total-deadline retry: does a slow provider stall the pool? Batching the judge is
potentially a 10x+ win — check whether the API supports it and whether we use it.`,
  },
  {
    key: 'measure-it-live',
    prompt: `LANE: JUST MEASURE IT. Everyone else is reading code; you RUN it.
Do a REAL, INSTRUMENTED compose run on a small basket set in /home/polaris/wt/compose (foreground,
hard timeout, e.g. \`timeout 900 python ...\`; NEVER nohup+tail -f). Instrument to answer:
  - What is the ACHIEVED concurrency over time (how many LLM calls actually in flight)? Sample it.
  - Where does the wall-clock actually GO? Break it down: writer calls vs judge calls vs local CPU
    vs waiting on a lock vs retry/backoff sleep. A flame-ish breakdown beats any theory.
  - Is the event loop still ever starved post-fix? Run a heartbeat coroutine (sleep 0.01 in a loop)
    and log the max gap. Gap >> 0.01s = something is STILL blocking the loop.
  - Actual req/s hitting OpenRouter, and how many 429s come back.
CAVEAT: root-owned run_s5_i3.py (PID 966951) may be competing for the same OpenRouter account —
check \`ps -p 966951\` and if it is alive, SAY your numbers are contaminated. Report REAL numbers.`,
  },
]

phase('Read')
// pipeline: each lane's findings get refuted as soon as that lane returns — no barrier
const perLane = await pipeline(
  LANES,
  lane => agent(`${CONTEXT}\n\n=== YOUR LANE ===\n${lane.prompt}`, {
    label: `read:${lane.key}`,
    phase: 'Read',
    schema: FINDING_SCHEMA,
  }),
  (res, lane) => {
    if (!res || res.nothing_found || !(res.findings ?? []).length) return []
    return parallel(
      res.findings.map(f => () =>
        agent(
          `${CONTEXT}

YOU ARE A REFUTER. An investigator claims the following caps compose throughput. Your job is to KILL
it. Open the real code and try to prove it WRONG. Default to refuted=true if you are uncertain — a
plausible-but-false finding sends the whole team down a dead end, which is worse than missing one.

CLAIM: ${f.title}
AT: ${f.file_line}
MECHANISM: ${f.mechanism}
CLAIMED IMPACT: ${f.throughput_impact}
THEIR EVIDENCE: ${f.evidence}
THEY ${f.measured ? 'MEASURED it' : 'DID NOT measure it — only read code'}

Attack it: Is that code path even reached at runtime? Is it already guarded/fixed elsewhere? Is the
impact real at 346-basket scale or negligible? Is it dominated by a bigger cost? If it survives,
quantify what it ACTUALLY costs.`,
          { label: `refute:${lane.key}`, phase: 'Refute', schema: REFUTE_SCHEMA },
        ).then(v => ({ ...f, lane: lane.key, verdict: v })),
      ),
    )
  },
)

const survivors = perLane
  .flat()
  .filter(Boolean)
  .filter(f => f.verdict && !f.verdict.refuted)

log(`survivors after refutation: ${survivors.length}`)

phase('Synthesize')
const synthesis = await agent(
  `${CONTEXT}

YOU ARE FABLE. Eight independent Opus investigators read the compose path line-by-line. Every finding
was then attacked by an adversarial refuter. These are the ones that SURVIVED:

${JSON.stringify(survivors, null, 2)}

Answer the operator's actual question: WHY IS COMPOSE SLOW, really?

1. RANK the surviving causes by real throughput cost at 346-basket scale. Put a number on each where
   you can. Be explicit about which are MEASURED and which are only code-read — the operator has
   already been burned once by a confident unmeasured thesis (the "429 is the ceiling" claim in the
   master brief, which was wrong because concurrency was actually 1).
2. Answer the operator's three named hypotheses directly and by name: is it CONTEXT TOO LARGE? is it
   TOKEN BUDGET? is it CRASHES? Yes or no, with evidence, for each.
3. THE ONE THING: if we fix exactly one thing tomorrow, what is it, and what is the expected speedup?
4. What is the honest expected wall-clock to render all 346 baskets after the top fix — and what does
   that estimate rest on?
5. What did we NOT establish? Name the gaps. An honest "we still cannot explain X" is required if
   true — do not close the loop with a story that merely sounds complete.`,
  { label: 'fable:why-is-compose-slow', phase: 'Synthesize', model: 'fable', effort: 'high' },
)

return { survivors_count: survivors.length, survivors, synthesis }
