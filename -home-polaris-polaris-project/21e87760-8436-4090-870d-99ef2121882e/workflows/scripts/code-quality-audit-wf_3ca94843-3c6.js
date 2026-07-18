export const meta = {
  name: 'code-quality-audit',
  description: 'Research 2026 best practices + audit our pipeline codebase across 6 axes; produce a Telus-review-ready remediation plan',
  phases: [
    { title: 'Research', detail: '2026 best practice per axis (web)' },
    { title: 'Audit', detail: 'quantify violations in our repo per axis' },
    { title: 'Synthesize', detail: 'prioritized phased remediation plan' },
  ],
}

const REPO = '/home/polaris/wt/outline_agent'

const AXES = [
  {
    key: 'resumability',
    title: 'Stage checkpointing / resumability',
    research: `Research the CURRENT (2025-2026) industry best practice for CHECKPOINTING and RESUMABILITY in long-running, multi-stage Python ML / data / LLM pipelines. Cover: idempotent stages; content-addressed / hashed artifacts; checkpoint-and-resume patterns; how mature frameworks do it (Metaflow, Prefect, Dagster, Ray, Temporal, dbt) AND how to do it well WITHOUT adopting a heavy framework (plain JSON/parquet checkpoints keyed by input hash, a resume flag, a manifest). What does "good" look like: granularity, where to store, how to detect staleness, how to make a stage skippable. Be concrete, name tools/patterns, keep it current.`,
    auditHints: `Our pipeline entry is scripts/run_honest_sweep_r3.py -> run_one_query, then src/polaris_graph/generator/multi_section_generator.py. Some checkpoints already exist. Investigate with Bash/Grep/Read in ${REPO}:
  grep -rn "checkpoint\\|_snapshot\\|resume\\|PG_E2E_RESUME" scripts/ src/polaris_graph | grep -iE "json|checkpoint|snapshot|resume" | head -60
  ls scripts/*.py ; grep -rn "def run_one_query\\|def run_\\|stage\\|phase" scripts/run_honest_sweep_r3.py | head
Identify the DISTINCT pipeline stages (gate -> retrieval -> compose -> verify/dedup -> render -> score) and for EACH stage state whether a resumable checkpoint exists (e.g. postgen_checkpoint.json, postverify_checkpoint.json, corpus_snapshot.json) or NOT. Quantify: how many stages can resume vs must re-run from zero.`,
  },
  {
    key: 'config',
    title: 'Config centralization / hardcoded values',
    research: `Research the CURRENT (2025-2026) best practice for CONFIGURATION MANAGEMENT in production Python (esp. ML/LLM systems). Cover: 12-factor config; a single typed source of truth (pydantic-settings / BaseSettings, dynaconf, hydra/OmegaConf); env layering (defaults -> .env -> environment -> CLI); SEPARATING secrets from config; typed validation; how to avoid scattered os.getenv() calls and magic literals; how to centralize MODEL CHOICE and thresholds so one file controls the system. Concrete tools + patterns, current.`,
    auditHints: `Audit ${REPO} for hardcoded values and scattered config. Use Bash/Grep:
  grep -rn "os.getenv\\|os.environ" src/polaris_graph | wc -l ; grep -rhoE "os.getenv\\(\\"[A-Z_]+\\"" src/polaris_graph | sort | uniq -c | sort -rn | head -40
  grep -rnE "moonshotai|z-ai|zai|glm-|glm5|claude-[a-z0-9]|gpt-[0-9]|openai/|anthropic/|model\\s*=\\s*\\"" src/polaris_graph | head -50
  grep -rnE "= [0-9]{2,}([^0-9]|$)|temperature\\s*=|max_tokens\\s*=|threshold\\s*=|0\\.[0-9]+" src/polaris_graph/generator | head -40
Is there a CENTRAL config module (search for settings.py, config.py, pydantic BaseSettings)? Count distinct PG_* env vars. Report: how many getenv call-sites, how many hardcoded model refs, whether a master .env / typed config exists, worst offenders with file:line.`,
  },
  {
    key: 'naming',
    title: 'Naming discipline (no marketing adjectives)',
    research: `Research CURRENT (2025-2026) professional naming conventions for a serious production codebase. Specifically: why marketing/temporal adjectives in file and symbol names are a code smell (honest, final, real, true, smart, magic, new, old, v2/v3, r2/r3, sweep, ultimate). What the accepted conventions are (PEP 8, Google Python style, "name by what it IS/DOES not by a quality claim or a version"), how mature teams handle versioned modules (avoid _v2 suffixes; use packages/interfaces), and a concrete renaming discipline. Cite style guides.`,
    auditHints: `Audit ${REPO} for adjective / version-suffix naming. Use Bash:
  find . -name "*.py" | grep -iE "honest|final|real|true|smart|magic|_v[0-9]|_r[0-9]|sweep|ultimate|new_|old_|clean_|deep_" | head -40
  grep -rnE "def (get_?)?(honest|final|real|true|smart|magic|ultimate|clean)_|_final\\b|_honest\\b|_v[0-9]\\b|_r[0-9]\\b" src/polaris_graph | head -40
List the worst-offending filenames and symbols (e.g. run_honest_sweep_r3.py). Quantify: how many files and how many symbols carry adjective/version names. Give the 15 worst with suggested serious names.`,
  },
  {
    key: 'devendoring',
    title: 'De-vendoring external component names',
    research: `Research CURRENT (2025-2026) best practice for INCORPORATING third-party / open-source components into a proprietary codebase: how to properly VENDOR or ADAPT external code (LICENSE + NOTICE files, attribution, an adapter/anti-corruption layer so external names don't leak into YOUR public API), clean-room renaming of internal identifiers, and how to do this WITHOUT violating open-source licenses (MIT/Apache/BSD attribution requirements). Distinguish "rename internal identifiers for cohesion" (fine) from "strip required attribution" (not fine). Concrete guidance.`,
    auditHints: `Audit ${REPO} for external-origin names leaking into our code. Use Bash:
  grep -rniE "fs.?researcher|storm|deepresearch.?bench|semantic.?scholar|openalex" src/polaris_graph | head -40
  ls third_party 2>/dev/null; find . -iname "LICENSE*" -o -iname "NOTICE*" | head
  grep -rniE "adapted from|based on|forked from|copied from|vendored" src/polaris_graph | head
Report: which external names appear in OUR module/class/function names vs merely as integration targets, where attribution/LICENSE files exist, and which identifiers should be renamed to our own identity (with a mapping) while preserving required license attribution.`,
  },
  {
    key: 'documentation',
    title: 'Documentation coverage & control',
    research: `Research CURRENT (2025-2026) documentation standards for a serious production Python codebase that must pass an EXTERNAL code review: module + function docstrings (PEP 257 / Google or NumPy style), README, ARCHITECTURE.md, Architecture Decision Records (ADRs), API reference generation (mkdocs/Sphinx/pdoc), docstring coverage tooling (interrogate, pydocstyle), inline rationale comments vs noise. What minimum doc set an external reviewer expects. Concrete + current.`,
    auditHints: `Audit ${REPO} for documentation coverage. Use Bash:
  find . -name "*.py" -path "*polaris_graph*" | wc -l
  grep -rn "def \\|class " src/polaris_graph | wc -l ; python3 -c "print('estimate docstring coverage')" 2>/dev/null
  ls README* ARCHITECTURE* docs/ CONTRIBUTING* 2>/dev/null; find . -iname "*.md" -path "*polaris*" | head
Estimate docstring coverage (functions/classes WITH a docstring vs total). Note presence/absence of README, ARCHITECTURE.md, ADRs, docs/ site, module-level docstrings. Report the doc gap quantitatively.`,
  },
  {
    key: 'tablestakes',
    title: 'Review table-stakes (tests, CI, typing, deps, secrets)',
    research: `Research what an INDEPENDENT external code reviewer (e.g. a large telecom vendor doing due diligence in 2025-2026) checks BEYOND config/naming/docs: automated tests + coverage, CI/CD (GitHub Actions), type hints + mypy/pyright, linting + formatting (ruff, black), dependency pinning + reproducible installs (lockfiles, uv/poetry, pinned versions), SECRETS HYGIENE (no keys committed, .env in .gitignore, secret scanning), structured logging, and error-handling consistency. What "passing" looks like for each. Concrete + current.`,
    auditHints: `Audit ${REPO} for review table-stakes. Use Bash:
  ls -d tests test 2>/dev/null; find . -name "test_*.py" -o -name "*_test.py" | wc -l
  ls .github/workflows 2>/dev/null; ls pyproject.toml setup.cfg ruff.toml mypy.ini .pre-commit-config.yaml requirements*.txt poetry.lock uv.lock 2>/dev/null
  cat .gitignore 2>/dev/null | grep -iE "env|secret|key" ; git -C ${REPO} ls-files | grep -iE "\\.env$|secret|credential" | head
  grep -rnE "sk-[a-zA-Z0-9]{20}|api_key\\s*=\\s*\\"[a-zA-Z0-9]" src/polaris_graph | head
Report: test count + whether CI exists, typing/lint config presence, dependency pinning method, and ANY secret hygiene issues (committed .env, hardcoded keys). Flag secret leaks as CRITICAL.`,
  },
]

// pipeline: research each axis, then audit our repo against it (no barrier between axes)
const sections = await pipeline(
  AXES,
  (ax) => agent(
    `You are a senior software architect researching 2026 best practices. ${ax.research}\n\nReturn a tight, concrete markdown brief titled "## Best practice (2026): ${ax.title}" — patterns, named tools, and what "good" looks like. No fluff.`,
    { label: `research:${ax.key}`, phase: 'Research' }
  ),
  (bestPractice, ax) => agent(
    `You are auditing a real Python codebase to prepare for an INDEPENDENT external code review (client: Telus). You have Bash, Grep, and Read tools. Work in the repo at ${REPO}.\n\nTHE 2026 BEST PRACTICE for this axis:\n${bestPractice}\n\nNOW AUDIT OUR CODE for "${ax.title}". ${ax.auditHints}\n\nActually RUN the commands (adapt as needed), read representative files, and QUANTIFY. Return a markdown section:\n### ${ax.title}\n- **Best practice (1-2 lines):** ...\n- **Our current state (quantified, with file:line examples):** ...\n- **Gap severity:** LOW / MEDIUM / HIGH / CRITICAL + one-line why\n- **Recommended fix (scoped to THIS repo, concrete):** ...\n- **Risk of the fix to the running pipeline (score/faithfulness must not break):** ...\nBe specific and honest; real counts, real filenames.`,
    { label: `audit:${ax.key}`, phase: 'Audit' }
  ),
)

const clean = sections.filter(Boolean)

const plan = await agent(
  `You are the lead engineer writing a remediation plan to make a research-pipeline codebase pass an INDEPENDENT external code review (client: Telus). The codebase hits a high accuracy score but is messy: no inter-stage checkpoints, hardcoded values/model-choices everywhere, marketing-adjective file/variable names (honest/final/r3/sweep), leaked external component names (FS-Researcher, STORM), near-zero documentation, and unknown test/CI/typing hygiene.\n\nHere are the six per-axis audit sections (each: best practice, our state, gap severity, fix, risk):\n\n${clean.join('\n\n---\n\n')}\n\nWrite a PRIORITIZED, PHASED remediation plan as markdown with:\n1. **Executive summary** — the 3-4 biggest risks a reviewer would flag first, and the headline of the plan.\n2. **Severity-ranked table** — axis | gap severity | effort (S/M/L) | risk-to-pipeline | priority.\n3. **Phased roadmap** — Phase 0 (quick wins / low-risk, e.g. secret hygiene, a central config module, README), Phase 1 (naming + de-vendoring via safe mechanical rename + adapters), Phase 2 (checkpointing/resumability), Phase 3 (docs + tests + CI). For each phase: what, why, concrete first steps, and how to sequence it so the RUNNING pipeline (its RACE score + faithfulness behavior) is NEVER destabilized (e.g. mechanical renames behind aliases, config extraction that defaults to today's literals byte-identically).\n4. **Guardrails** — explicit rules (e.g. every config extraction must default to the current hardcoded value so behavior is byte-identical; renames go through deprecation aliases; no behavior change in the same commit as a rename).\n5. **What to show the Telus reviewer first.**\nBe concrete and realistic. This plan will be shown to the project owner for approval.`,
  { label: 'synthesize-plan', phase: 'Synthesize' }
)

return { plan, sections: clean }
