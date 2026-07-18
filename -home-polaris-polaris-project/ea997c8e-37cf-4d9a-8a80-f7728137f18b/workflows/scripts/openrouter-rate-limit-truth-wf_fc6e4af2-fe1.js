export const meta = {
  name: 'openrouter-rate-limit-truth',
  description: 'Establish the REAL OpenRouter rate limit for this account, empirically — and decide whether it is actually the binding constraint on compose now that the event-loop block is fixed.',
  phases: [
    { title: 'Recon', detail: 'find the key + what the account is actually entitled to' },
    { title: 'Probe', detail: 'measure the real limit empirically' },
    { title: 'Verdict', detail: 'Fable: is the 429 the binding constraint or not', model: 'fable' },
  ],
}

const RULES = `
POLARIS context: compose renders 346 baskets via OpenRouter (compose model = z-ai/glm-5.2, plus an
NLI verifier judge that shares the SAME OpenRouter account). Repo: /workspace/POLARIS (readable),
compose worktree: /home/polaris/wt/compose (writable).

THE DISPUTE YOU ARE SETTLING:
- Claim A (original Fable, baked into OVERNIGHT_MASTER_BRIEF.md:9): "compose is already ~48-way
  parallel; the real ceiling is the OpenRouter 429 rate limit."
- Claim B (later Fable gate, commit 0615bc5, backed by an A/B measurement): the ceiling was a
  missing await — _draft_passes_wrapper (generator/abstractive_writer.py:661) is a sync def that was
  called with NO await from the async coroutine _pre_pass_one_basket (:749), blocking the event loop
  on every NLI POST. True verify concurrency was 1. Measured 2.06s serialized -> 0.60s parallel.
  Under Claim B, the 429 could NOT have been binding pre-fix (you cannot rate-limit 1 in-flight req).

SECURITY: the OpenRouter API key is a secret. NEVER print it, never echo it, never paste it into
your result. Refer to it only as $OPENROUTER_API_KEY. Redact it if it appears in any output.

HONESTY: report REAL measured numbers. If you cannot measure something, say so. Do not estimate a
rate limit and present it as measured.
`

const RECON_SCHEMA = {
  type: 'object',
  required: ['key_found', 'account_facts', 'evidence_of_429'],
  properties: {
    key_found: { type: 'boolean' },
    key_location: { type: 'string', description: 'where the key is configured (path/env var NAME only, never the value)' },
    account_facts: {
      type: 'object',
      description: 'from GET https://openrouter.ai/api/v1/key',
      properties: {
        is_free_tier: { type: 'boolean' },
        credits_remaining: { type: 'string' },
        rate_limit_requests: { type: 'string' },
        rate_limit_interval: { type: 'string' },
        raw_response: { type: 'string', description: 'the JSON, KEY REDACTED' },
      },
    },
    evidence_of_429: {
      type: 'object',
      description: 'what the REAL logs say — how often did we actually get 429d',
      properties: {
        count: { type: 'string' },
        logs_searched: { type: 'string' },
        retry_after_values: { type: 'string' },
        sample_lines: { type: 'string' },
      },
    },
    configured_concurrency: {
      type: 'object',
      description: 'the knobs as they are ACTUALLY set: PG_ABSTRACTIVE_WRITER_CONCURRENCY, PG_MAX_CONCURRENT_LLM, PG_SIDE_JUDGE_MAX_CONCURRENCY — value + where set',
    },
  },
}

const PROBE_SCHEMA = {
  type: 'object',
  required: ['probed', 'measured'],
  properties: {
    probed: { type: 'boolean' },
    method: { type: 'string' },
    measured: {
      type: 'object',
      description: 'REAL numbers from a real probe',
      properties: {
        headers_seen: { type: 'string', description: 'X-RateLimit-* headers verbatim' },
        max_sustained_concurrency: { type: 'string' },
        first_429_at: { type: 'string', description: 'at what concurrency / req-per-sec did 429 first appear' },
        throughput_req_per_s: { type: 'string' },
        latency_p50_p95: { type: 'string' },
      },
    },
    contention_note: { type: 'string', description: 'was a root-owned run_s5_i3.py (PID 966951) competing for the same account during the probe? If so the numbers are DIRTY — say so.' },
    raw_output: { type: 'string' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['binding_constraint', 'claim_a_or_b', 'reasoning', 'recommended_settings'],
  properties: {
    binding_constraint: { type: 'string', description: 'what ACTUALLY caps compose throughput right now, post-fix' },
    claim_a_or_b: { enum: ['A_rate_limit', 'B_event_loop', 'BOTH_IN_SEQUENCE', 'NEITHER', 'INSUFFICIENT_EVIDENCE'] },
    reasoning: { type: 'string' },
    is_429_binding_now: { type: 'boolean' },
    headroom: { type: 'string', description: 'how much faster can compose go before the rate limit actually bites' },
    recommended_settings: {
      type: 'object',
      description: 'concrete env values: PG_ABSTRACTIVE_WRITER_CONCURRENCY, PG_MAX_CONCURRENT_LLM, PG_SIDE_JUDGE_MAX_CONCURRENCY, backoff params',
    },
    time_to_render_346: { type: 'string', description: 'estimated wall-clock to render all 346 baskets at the recommended settings, and what that estimate rests on' },
    caveats: { type: 'array', items: { type: 'string' } },
  },
}

phase('Recon')
const recon = await agent(
  `${RULES}

YOU ARE RECON. Establish what this OpenRouter account is ACTUALLY entitled to. Do not guess.

1. Find how the OpenRouter key is configured (env var, .env, config/settings/*). Report the LOCATION
   and the VARIABLE NAME only — never the value.
2. Query the account's own limits — OpenRouter exposes this directly:
     curl -s https://openrouter.ai/api/v1/key -H "Authorization: Bearer $OPENROUTER_API_KEY"
   That returns is_free_tier, usage, limit, and a rate_limit {requests, interval} object.
   REDACT the key from anything you paste back.
3. Find the REAL 429 evidence in the logs. Search /workspace/POLARIS/logs, /home/polaris/wt/compose,
   and any s5/compose run logs for "429", "rate limit", "Retry-After". How MANY, how OFTEN, and what
   Retry-After values came back? A 429 that happened 15 times over an hour is a very different
   animal from one that happens on every other call.
4. Report the three concurrency knobs as ACTUALLY SET (not their defaults in code): 
   PG_ABSTRACTIVE_WRITER_CONCURRENCY, PG_MAX_CONCURRENT_LLM, PG_SIDE_JUDGE_MAX_CONCURRENCY.`,
  { label: 'recon:account+429-logs', phase: 'Recon', schema: RECON_SCHEMA },
)

phase('Probe')
const probe = await agent(
  `${RULES}

YOU ARE THE PROBE. Measure the REAL rate limit empirically. Recon found:
${JSON.stringify(recon, null, 2)}

Write a small standalone probe script (put it in /tmp, NOT in a worktree) that sends real requests to
OpenRouter for the compose model and RAMPS concurrency (e.g. 1, 2, 4, 8, 16, 32) with tiny cheap
prompts (max_tokens ~8 — you are measuring the rate limiter, not paying for generation).

CAPTURE:
- the X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset response headers VERBATIM
  (this is the single most direct answer to "what is the rate limit" — read them, do not infer)
- the concurrency / req-per-sec at which 429 FIRST appears
- the Retry-After value the 429 actually carries
- sustained throughput (req/s) and latency p50/p95

CRITICAL — CONTENTION: a root-owned run_s5_i3.py (PID 966951) may still be hitting the SAME account.
Check with \`ps -p 966951\`. If it is running, your numbers are CONTAMINATED — you are measuring the
limit MINUS whatever it is consuming. Report that loudly in contention_note rather than presenting a
dirty number as clean. Keep total spend trivial; this is a rate-limit probe, not a load test.`,
  { label: 'probe:empirical-limit', phase: 'Probe', schema: PROBE_SCHEMA },
)

phase('Verdict')
const verdict = await agent(
  `${RULES}

YOU ARE FABLE, THE INDEPENDENT GATE. Settle the dispute with the evidence below. You did not write
any of this code and you have no stake in either claim being right.

RECON (what the account is entitled to + what the logs really show):
${JSON.stringify(recon, null, 2)}

PROBE (what we actually measured):
${JSON.stringify(probe, null, 2)}

ANSWER, precisely:
1. What is the REAL OpenRouter rate limit for this account? (number + interval, from the headers/API,
   not inferred.)
2. Post-fix, is the 429 the BINDING constraint on compose, or is it not? Be specific about the
   arithmetic: at the configured concurrency, how many req/s does compose actually generate, and how
   does that compare to the measured limit?
3. Was Claim A right, Claim B right, or were both right in sequence (A describes the wall we had not
   yet reached because B was capping us at 1)?
4. If the probe was contaminated by the root-owned job, say the evidence is INSUFFICIENT rather than
   guessing. An honest "we could not measure this cleanly, kill PID 966951 and re-run" is a better
   answer than a confident wrong one.
5. Concrete recommended settings, and an estimated wall-clock to render all 346 baskets — with the
   assumption that estimate rests on made explicit.`,
  { label: 'fable:rate-limit-verdict', phase: 'Verdict', model: 'fable', schema: VERDICT_SCHEMA, effort: 'high' },
)

log(`VERDICT: ${verdict?.claim_a_or_b} | 429 binding now: ${verdict?.is_429_binding_now} | ${verdict?.binding_constraint?.slice(0, 100)}`)

return { recon, probe, verdict }
