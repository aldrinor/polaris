export const meta = {
  name: 'exhaustive-name-read',
  description: 'Fan out ~72 agents to genuinely READ every line of all 842 Python files and flag every unprofessional/marketing/temporal name at the Telus external-review bar',
  phases: [
    { title: 'Read', detail: '72 agents read ~7k lines each, line by line' },
  ],
}

const REPO = '/home/polaris/wt/outline_agent'
const MANIFEST = `${REPO}/.name_shards.json`
const OUTDIR = '/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/name_findings'
const N = args && args.n ? args.n : 72

const idxs = Array.from({ length: N }, (_, i) => i)

const results = await parallel(idxs.map((i) => () =>
  agent(
    `You are auditing source code for an INDEPENDENT external code review (client: Telus). You have Bash, Read, Grep tools.

STEP 1 — get your file list. Run:
  /opt/conda/bin/python -c "import json; s=json.load(open('${MANIFEST}'))[${i}]; print(chr(10).join(s))"
That prints your assigned slice as lines of "relpath:START-END" (relative to ${REPO}).

STEP 2 — GENUINELY READ every one of your assigned files/ranges, line by line, using the Read tool with the given offset/limit. Do NOT grep-and-skim. Actually read the code so you catch names a keyword search would miss.

STEP 3 — flag EVERY name (module/file name, class, function/method, variable, constant, enum value) that would look UNPROFESSIONAL in an external code review. This includes:
  - marketing / quality adjectives: honest, real, true, smart, magic, ultimate, enhanced, improved, robust, proper(when boastful), aggressive, killer, awesome, blazing, super, mega, best, clean(when boastful)
  - temporal / version markers: v2/v3/v4, r2/r3, _new, _old, legacy, deprecated, next/nextgen, final(when it means 'this version'), fixed, temp, wip, draft, backup, orig, working, experimental, proto
  - jokes / informal / vague: hack, yolo, stuff, misc, foo, doit, thing, blah, magic numbers named as words
Judge at a STRICT bar: **when in doubt, mark RENAME, not KEEP.** Only mark KEEP for names that are unambiguously standard, descriptive, professional vocabulary or a real domain term (e.g. 'finalize', 'proper_noun', 'evict_older_than', a real product name like 'SmartArt' ONLY if the code truly implements it).

STEP 4 — WRITE your findings by APPENDING TAB-separated rows to ${OUTDIR}/shard_${i}.tsv, one row per flagged name:
  VERDICT<TAB>NAME<TAB>relpath:LINE<TAB>KIND<TAB>WHY_it_reads_unprofessional<TAB>SUGGESTED_professional_name
  (VERDICT = RENAME or KEEP-BUT-NOTED; KIND = file/class/func/var/const/enum)
Use a bash heredoc or printf with real tab characters. If a file range has NO issues, still write one row: NONE<TAB>-<TAB><relpath><TAB>-<TAB>clean<TAB>-.

Return ONLY a one-line summary: "shard ${i}: <R> renames, <K> kept-noted across <F> files".`,
    { label: `read:shard-${i}`, phase: 'Read' }
  ).catch(() => `shard ${i}: FAILED`)
))

const failed = results.filter((r) => typeof r === 'string' && r.includes('FAILED')).length
return { shards: N, failed, summaries: results }
