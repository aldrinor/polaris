export const meta = {
  name: 'exhaustive-name-read-batched',
  description: 'Read every line of all 842 Python files at low concurrency (rate-limit safe) and flag every unprofessional/marketing/temporal name at the Telus bar',
  phases: [{ title: 'Read', detail: 'batched 5-at-a-time, resumable' }],
}

const REPO = '/home/polaris/wt/outline_agent'
const MANIFEST = `${REPO}/.name_shards.json`
const OUTDIR = '/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/name_findings'
const N = 72
const BATCH = 5

const prompt = (i) => `You are auditing source code for an INDEPENDENT external code review (client: Telus). Tools: Bash, Read.

STEP 0 — SKIP IF DONE. Run: test -s ${OUTDIR}/shard_${i}.tsv && echo DONE || echo TODO
If it prints DONE, this shard is already complete — reply exactly "shard ${i}: cached" and STOP. Do nothing else.

STEP 1 — get your file list: /opt/conda/bin/python -c "import json; print(chr(10).join(json.load(open('${MANIFEST}'))[${i}]))"
It prints lines "relpath:START-END" relative to ${REPO}.

STEP 2 — GENUINELY READ every assigned file/range line by line with the Read tool (offset/limit from START-END; use limit up to 2000 per call to minimize calls). Do NOT grep-and-skim — read the code.

STEP 3 — flag EVERY name (file/module, class, func/method, var, const, enum value) that looks UNPROFESSIONAL in an external review:
  - marketing/quality adjectives: honest, real, true, smart, magic, ultimate, enhanced, improved, robust, aggressive, killer, awesome, blazing, super, mega, best
  - temporal/version markers: v2/v3/v4, r2/r3, _new, _old, legacy, deprecated, next/nextgen, final(meaning 'this version'), fixed, temp, wip, draft, backup, orig, working, experimental, proto
  - jokes/informal/vague/slang: junk, garbage, hack, spy, stub(as a real name), yolo, stuff, misc, foo/bar, doit, thing, blah, landmine, nuke, magic-number-as-word, terse cryptic abbreviations
Judge at a STRICT bar: **when in doubt, mark RENAME.** Only KEEP-BUT-NOTED for unambiguously standard, descriptive, professional vocabulary or a REAL domain term genuinely implemented (finalize, proper_noun, evict_older_than, SmartArt only if it truly makes SmartArt).

STEP 4 — APPEND TAB-separated rows to ${OUTDIR}/shard_${i}.tsv (one per flagged name), using printf with real tabs:
  VERDICT<TAB>NAME<TAB>relpath:LINE<TAB>KIND<TAB>WHY<TAB>SUGGESTED_NAME
  VERDICT=RENAME or KEEP-NOTED; KIND=file/class/func/var/const/enum. If a file is fully clean, write: NONE<TAB>-<TAB>relpath<TAB>-<TAB>clean<TAB>-

Reply ONLY: "shard ${i}: <R> renames, <K> kept across <F> files".`

const idxs = Array.from({ length: N }, (_, i) => i)
const results = []
for (let b = 0; b < idxs.length; b += BATCH) {
  const batch = idxs.slice(b, b + BATCH)
  const r = await parallel(batch.map((i) => () =>
    agent(prompt(i), { label: `read:${i}`, phase: 'Read', model: 'sonnet' }).catch(() => `shard ${i}: FAILED`)
  ))
  results.push(...r)
  log(`batch ${b / BATCH + 1}/${Math.ceil(N / BATCH)} done`)
}
const failed = results.filter((r) => typeof r === 'string' && r.includes('FAILED'))
return { shards: N, failedCount: failed.length, failed }
