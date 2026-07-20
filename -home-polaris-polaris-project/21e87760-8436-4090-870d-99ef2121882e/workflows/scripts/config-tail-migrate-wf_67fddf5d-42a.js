export const meta = {
  name: 'config-tail-migrate',
  description: 'AST-codemod migrate the remaining ~879 raw os.getenv reads to resolve(), byte-identical, characterization-tested, codex-sol(max) gated to CONFIG-CONSOLIDATED (or documented owner-decision remainder)',
  phases: [{ title: 'Migrate' }],
}

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['approach','sites_migrated','sites_remaining','byte_identical_evidence','codex_token','codex_reasoning','iterations','owner_decision_remainder','not_covered'],
  properties: {
    approach: { type: 'string', description: 'how the migration was done (codemod details)' },
    sites_migrated: { type: 'string', description: 'count + which categories migrated' },
    sites_remaining: { type: 'string', description: 'count + why (secrets/computed/conflicting) still raw' },
    byte_identical_evidence: { type: 'string', description: 'characterization test result (resolve()==os.getenv over all keys) + py_compile/import' },
    codex_token: { type: 'string', description: 'CONFIG-CONSOLIDATED or CONFIG-PARTIAL on convergence' },
    codex_reasoning: { type: 'string' },
    iterations: { type: 'number' },
    owner_decision_remainder: { type: 'string', description: 'keys that genuinely need an operator product decision (e.g. conflicting defaults) and cannot be resolved autonomously' },
    not_covered: { type: 'string' },
  },
}

const TREE = '/home/polaris/wt/gateinv'

phase('Migrate')
const result = await agent(`You are a Claude implementer under the govkit spawn contract: ONE shot, trace the WHOLE path, evidence (file:line) or it does not count, put gaps in not_covered. Tree: ${TREE} (gate-inversion, which now HAS the settings foundation: src/polaris_graph/settings.py resolve() + config_defaults.py registry + 833 already-migrated sites, tests/test_config_registry.py + test_settings_models.py GREEN). Do NOT commit — return the result; the caller commits.

GOAL — item 1, config consolidation. Codex verdict was CONFIG-NOT because ~879 raw os.getenv/os.environ reads remain OUTSIDE the central layer across ~197 files in src/polaris_graph, and there are double-definitions (a key defined in config_defaults.py AND read raw with a hardcoded literal — editing the registry silently no-ops the raw site). Reduce this to the central layer, BYTE-IDENTICAL (never change a resolved value).

METHOD — deterministic AST codemod, NOT hand edits and NOT an LLM rewriting code:
1. Write/adapt a codemod (ast or libcst) that finds every real os.getenv("KEY", <literal>) / os.environ.get("KEY", <literal>) Call node in src/polaris_graph and, for the MECHANICALLY-SAFE ones, (a) registers "KEY": <the exact literal> in config_defaults.py if absent (and asserts it MATCHES if already present — a MISMATCH is a conflicting-default, do NOT auto-resolve it, record it), (b) rewrites the call to resolve("KEY"). Edit ONLY real Call nodes — never strings/comments/docstrings. Guard whole-file if os/resolve is locally rebound.
2. DO NOT migrate (leave raw + list them): secret keys (*_KEY/_TOKEN/credentials — need a separate SecretStr pass), computed/multiline/non-literal defaults (can't be a static registry string), and CONFLICTING defaults (same key, different literals at different sites — needs an operator product decision). Removing the double-definitions is IN scope where the two literals AGREE.
3. Preserve the byte-identical contract: resolve(key) == os.getenv(key, registered_default) for a fresh env read per call (no cached module instance).

VERIFY (this is the proof, existence is not): run tests/test_config_registry.py + tests/test_settings_models.py (must stay GREEN), then extend/point the registry-parity test so resolve()==os.getenv over ALL newly-migrated keys; py_compile every changed module; import-smoke the heaviest modules. State exact counts from commands you ran (paste them).

CODEX GATE (codex-sol MAX, reads files itself): write a summary + the codemod + key hunks + the parity-test output to /tmp/codex_configtail.md prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY verify: (1) the migrated os.getenv->resolve sites are BYTE-IDENTICAL (each registered default equals the old literal); (2) no string/comment was edited; (3) double-definitions removed only where literals agreed; (4) secrets/computed/conflicting keys were correctly LEFT raw and listed, not silently changed; (5) the parity test proves resolve()==os.getenv over the migrated keys. How many raw reads remain and are they all genuinely owner-decision or separate-pass? Emit CONFIG-CONSOLIDATED (mechanical tail done + byte-identical, only owner-decision/secret keys remain) or CONFIG-PARTIAL + what is left.' then run: cd ${TREE} && timeout 900 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=max - < /tmp/codex_configtail.md 2>&1 | tail -40
If REVISE/PARTIAL for a fixable reason, fix and re-gate, up to 3 loops. Owner-decision keys (conflicting defaults) are NOT a failure — list them in owner_decision_remainder; codex should still emit CONFIG-CONSOLIDATED if the mechanical tail is byte-identical and only genuine owner decisions remain.

Return the schema. Do NOT commit. Be honest: if you cannot make it byte-identical, say so in not_covered rather than shipping a value change.`, { schema: SCHEMA, phase: 'Migrate', label: 'config-tail' })

return { result }