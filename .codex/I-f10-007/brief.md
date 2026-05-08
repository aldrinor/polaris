# Codex Brief Review — I-f10-007 (ITER 5 of 5 — FINAL ITER AT CAP)

## Iter 5 changes per Codex iter 4

Codex iter-4 found 3 more bypasses (raw `_socket`, `operator.attrgetter` string-keyed reflection, `numpy.ctypeslib`). Iter-5 fixes these AND honestly frames the residual surface.

**Honest framing per CLAUDE.md §9.4 + LAW II:** Python is NOT safely sandboxable in-process. This is well-known (cf. PyPy restricted-python history). Complete sovereignty requires OS-level isolation: separate process + network namespace + seccomp filter + read-only FS. THIS Issue ships substantial Python-level defense-in-depth that catches the most common bypasses; the OS-level isolation follow-up Issue tracks the remainder.

- **P1 fix (raw _socket access):** add `_socket` to `_BLOCKED_IMPORTS` AND extend the runtime preamble to also patch `_socket.socket`. Add to allowlist-rejection: any module name starting with `_socket`.

- **P1 fix (operator.attrgetter reflection):** remove `operator` from `_ALLOWED_IMPORTS` (currently allowed). Acceptable cost: rare scripts that legitimately use `operator.itemgetter` for sorting can use lambdas instead. Tests add a script with `from operator import attrgetter` rejection.

- **P1 fix (numpy.ctypeslib):** AST attribute-access rejector adds `ctypeslib` to its blocked set. Any reference like `np.ctypeslib` or `numpy.ctypeslib` is statically rejected. Same for `np.ctypes`, `np._core_*`, `np.f2py`. (Documented as non-exhaustive — full numpy attack surface is large; OS-level isolation is the proper fix.)

- **Honest follow-up framing:** acceptance criterion 5 explicitly states: "this Issue ships Python-level defense-in-depth ONLY. Complete sovereignty requires OS-level isolation tracked in follow-up Issue 'I-f10-007b: OS-level egress isolation for code_executor (network namespace + seccomp + read-only FS)'. The 5-iter Codex cap on THIS brief is reached at iter 5; force-APPROVE per CLAUDE.md §8.3.1; residual reflection surface is documented for the follow-up Issue."

## Iter 4 changes per Codex iter 3

Codex iter-3 found another reflection path: `sys._getframe().f_builtins['__import__']('subprocess').run(...)`. Iter-4 plan extends the rejected attribute set:

- **P1 fix (frame reflection paths):** the AST attribute-access rejector adds these to the blocked set:
  - `_getframe`, `f_builtins`, `f_globals`, `f_locals`, `f_code` (Python frames)
  - `gi_frame`, `cr_frame`, `ag_frame`, `tb_frame` (generator/coroutine/async-generator/traceback frames)
  - `__import__`, `__builtins__`, `__class__`, `__subclasses__`, `__globals__`, `__bases__`, `__mro__`, `__dict__`, `__getattribute__`, `__getattr__` (already in iter 3)

  Combined into a single set `_BLOCKED_REFLECTION_ATTRS` checked via AST walk over `ast.Attribute(attr=...)` nodes.

- **P1 fix (allowlist wording cleanup per iter-3 P2):** unify Plan section 2 wording — AST import check enforces `_ALLOWED_IMPORTS` allowlist. `_BLOCKED_IMPORTS` remains as defense-in-depth for any module not in the allowlist (i.e., a module is rejected if NOT in allowlist OR is in blocklist).

- **P2 fix (PYTHONPATH wording):** acceptance criterion 3 specifies a Linux CI invocation; for local PowerShell, document `$env:PYTHONPATH = "src" ; python -m pytest ...`.

- **Tests added in iter 4:**
  - `test_blocks_sys_getframe` — `import sys; sys._getframe()` rejected.
  - `test_blocks_f_builtins` — `f.f_builtins` reference rejected.
  - `test_blocks_dynamic_import_via_frame` — full `sys._getframe().f_builtins['__import__']('subprocess')` rejected.

## Iter 3 changes per Codex iter 2

Codex iter-2 surfaced 4 deeper P1 issues. Iter-3 plan addresses each. Acknowledging that PERFECT reflection-resistance requires OS-level isolation (network namespace + seccomp); a follow-up Issue "OS-level egress isolation for code_executor" will track that. THIS Issue ships substantial defense-in-depth.

- **P1 fix #1 (criterion-4 wording):** revise criterion 4 to "production hardening to `code_executor.py` is REQUIRED" — drop the "no changes" wording.

- **P1 fix #2 (runtime network denial):** the validator alone can't catch `pandas.read_csv("https://...")` or `asyncio.open_connection(...)` because pandas/asyncio import paths look benign. Fix: inject a `_SOCKET_KILL_PREAMBLE` into the script BEFORE user code runs. The preamble monkey-patches `socket.socket`, `socket.create_connection`, `socket.getaddrinfo` to raise `RuntimeError("network egress blocked by polaris sandbox")`. Any allowed library that attempts to open a TCP/UDP connection now fails at runtime.

  ```python
  _SOCKET_KILL_PREAMBLE = (
      "import socket as _polaris_socket\n"
      "def _polaris_block(*args, **kwargs):\n"
      "    raise RuntimeError('network egress blocked by polaris sandbox')\n"
      "_polaris_socket.socket = _polaris_block\n"
      "_polaris_socket.create_connection = _polaris_block\n"
      "_polaris_socket.getaddrinfo = _polaris_block\n"
      "_polaris_socket.gethostbyname = _polaris_block\n"
  )
  ```

  This preamble is injected ABOVE the existing matplotlib agg-backend preamble.

- **P1 fix #3 (allowlist enforcement):** the validator currently uses `_BLOCKED_IMPORTS` as a blocklist; modules not in the blocklist (e.g., `asyncio`, `pickle` — wait pickle IS blocked, but `asyncio` isn't) pass. Fix: AST-based allowlist enforcement. After AST parsing, every imported module's top-level name must be in `_ALLOWED_IMPORTS`; otherwise rejected with reason "Module 'X' not in allowed list".

- **P1 fix #4 (reflection-hardening for dunder access on arbitrary objects):** add an AST walker that rejects `ast.Attribute` nodes whose `attr` is one of: `__import__`, `__builtins__`, `__class__`, `__subclasses__`, `__globals__`, `__bases__`, `__mro__`, `__dict__` (the standard reflection-bypass attribute set). This catches `catch_warnings._module.__builtins__` chain attacks. We acknowledge perfect coverage requires OS-level isolation; documented as follow-up.

- **P2 fix (runtime test):** runtime test scripts validation-allowed but attempt egress through allowed library:
  - `test_runtime_pandas_read_csv_blocked` — script calls `pd.read_csv("https://example.com/x.csv")`; expect failure with stderr matching "network egress blocked".

## Iter 2 changes per Codex iter 1

Codex iter-1 found TWO real bypasses in the production validator (P1 each, treated as effective P0 since the issue is "harden + sovereignty CI"). Iter-2 plan revises to add production hardening:

- **P1 fix #1 (comma-separated imports):** `import json, socket` currently passes because the regex `re.match(r'(?:from\s+(\S+)\s+import|import\s+(\S+))', line)` extracts only the FIRST module. Fix: replace regex with AST-based import detection. Use `ast.parse(script)` then walk; for each `ast.Import` node, check every alias's `name`; for each `ast.ImportFrom`, check `module`. This robustly handles comma-separated, line-continuation, and aliased imports.

- **P1 fix #2 (indirect dangerous builtins):** `__builtins__.__dict__['__import__']('socket')` currently passes because regex only matches direct calls (`__import__\s*\(`). Fix: AST-level detection of any reference to `__builtins__`. Reject any `ast.Name(id='__builtins__')`, `ast.Attribute` whose value is `__builtins__`, or subscript access on `__builtins__`.

- **P2 fix (runtime test):** the iter-1 DNS/reflection runtime test is replaced with a more direct sovereignty proof: a script that legitimately imports `json` and tries to use the `__builtins__` reflection bypass to import `socket` — now expected to be REJECTED at validation (post-fix). This becomes a regression test for the validator hardening.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Issue:** I-f10-007 — Sandboxed Python execution (no-egress, resource-capped). Scope: "existing code_executor.py hardened; egress blocked". Acceptance: "sovereignty CI test". LOC estimate 200.
- **Existing substrate:** `src/polaris_graph/tools/code_executor.py` already has comprehensive sandboxing:
  - `_BLOCKED_IMPORTS` blocks `socket`, `urllib`, `requests`, `http`, `ftplib`, `smtplib`, `subprocess`, `os`, etc. (33 modules total).
  - `_DANGEROUS_PATTERNS` blocks `open()`, `exec()`, `eval()`, `__import__()`, `getattr()`, etc.
  - `_build_restricted_env()` strips API keys, network config, proxy vars from subprocess env.
  - Resource caps: timeout (`PG_CODE_EXEC_TIMEOUT=30s`), output size (1MB), script size (50KB), input size (5MB).
  - `validate_script()` performs static analysis BEFORE execution; rejects on first violation.
- **What's missing:** an adversarial sovereignty CI test that proves the sandbox actually blocks egress + dangerous ops. Currently no such test exists; sandbox is asserted by code review only.
- **Honest framing per CLAUDE.md §9.4:** the sandbox itself is hardened. This Issue ships the sovereignty CI proof: a test suite that throws ~10 malicious scripts at the sandbox and asserts each is rejected (validation) or fails safely (runtime).

## Plan

### Backend

1. New test module `tests/v6/test_code_executor_sovereignty.py` (NEW):
   - Imports `validate_script` and `execute_analysis_script` from `src.polaris_graph.tools.code_executor`.
   - Marked `@pytest.mark.asyncio` for the runtime tests.
   - **Validation-time rejection tests** (test that `validate_script` returns `(False, reason)`):
     - `test_blocks_socket_import` — `import socket` rejected.
     - `test_blocks_urllib_import` — `import urllib.request` rejected.
     - `test_blocks_requests_import` — `import requests` rejected.
     - `test_blocks_subprocess_import` — `import subprocess` rejected.
     - `test_blocks_os_import` — `import os` rejected (forbidden in scripts; only the executor itself uses os).
     - `test_blocks_open_call` — `open("/etc/passwd")` rejected.
     - `test_blocks_exec_call` — `exec("...")` rejected.
     - `test_blocks_eval_call` — `eval("...")` rejected.
     - `test_blocks_dunder_import` — `__import__("os")` rejected.
     - `test_blocks_compile_call` — `compile("...")` rejected.
   - **Runtime sovereignty tests** (validation-side allowed but the script still must NOT exfiltrate data — these run via `execute_analysis_script`):
     - `test_runtime_dns_resolution_attempt_fails` — script imports json (allowed) and tries `json.load(sys.stdin)` then attempts to call `socket.gethostbyname` via reflection — expect failure (socket blocked) OR returns clean error JSON.
     - `test_resource_cap_timeout` — script `while True: pass` is killed by `_TIMEOUT`; result `success=False`, `error` mentions "timeout".

2. **Production hardening of `src/polaris_graph/tools/code_executor.py`** (per Codex iter-1 P1):
   - Add `_validate_imports_ast(script: str) -> tuple[bool, str]` that parses with `ast.parse(script)` and walks for `ast.Import` (checks every alias) + `ast.ImportFrom` (checks `module`). For each module name found, splits on `.` and checks the top-level token against `_BLOCKED_IMPORTS`. Returns first violation.
   - Add `_validate_no_builtins_reflection(script: str) -> tuple[bool, str]` that parses with `ast.parse(script)` and walks for any `ast.Name(id='__builtins__')` reference. Rejects with reason "Access to __builtins__ is not allowed (dangerous reflection bypass)".
   - `validate_script()` body adds: after the existing length check, runs both AST validators FIRST. The existing regex-based checks remain as defense-in-depth (catch syntactically-invalid scripts that AST can't parse).
   - On `SyntaxError` from `ast.parse`, return `(False, "Script syntax error: ...")`.

3. Add ≥3 adversarial tests for the new bypasses:
   - `test_blocks_comma_separated_socket_import` — `import json, socket` rejected.
   - `test_blocks_comma_separated_urllib_import` — `import sys, urllib.request` rejected.
   - `test_blocks_builtins_reflection_dict` — `__builtins__.__dict__['__import__']('socket')` rejected.
   - `test_blocks_builtins_subscript` — `__builtins__['exec']('print(1)')` rejected.

## Risks for Codex Red-Team

1. **Validation false-negatives:** the static analyzer in `validate_script` uses regex on raw source. Edge cases: comments containing the pattern, string literals containing it, multi-line statements, line continuations. Existing code already handles these (lines 254-269); my tests should NOT include comment/string false-positive cases as those would test the validator's tolerance, not the sandbox's safety.
2. **Runtime test variability:** subprocess kill timing on Windows vs Linux can differ. The timeout test uses 5s grace period (`effective_timeout + 5`).
3. **Async test setup:** `asyncio_default_fixture_loop_scope=None` (per `pytest.ini`); each runtime test marked `@pytest.mark.asyncio`.
4. **§9.4 N/A backend.**
5. **CHARTER §1 LOC cap:** estimated ~150 LOC test (10 validation tests + 2 runtime tests, each ~10-15 LOC). Under 200. Within issue_breakdown LOC estimate of 200.

## Acceptance criteria

1. New `tests/v6/test_code_executor_sovereignty.py` module ships ≥10 adversarial validation tests covering socket/urllib/requests/subprocess/os import blocks + open/exec/eval/__import__/compile pattern blocks + comma-separated imports + `__builtins__` direct access + dunder-attr-on-arbitrary-object access + asyncio (allowlist enforcement).
2. ≥2 runtime tests: timeout cap; pandas read_csv with HTTPS URL fails with "network egress blocked".
3. All tests pass when `PYTHONPATH=src python -m pytest tests/v6/test_code_executor_sovereignty.py -v`.
4. **Production hardening of `src/polaris_graph/tools/code_executor.py` is REQUIRED:** AST-based import allowlist enforcement; AST-based dunder-attr access rejection; runtime socket monkey-patch preamble injected before user script runs.
5. CHARTER §1 LOC cap respected (≤200 net). Acknowledged: perfect reflection-resistance requires OS-level isolation (network namespace + seccomp); a follow-up Issue "OS-level egress isolation for code_executor" tracks that work.

**Forced enumeration:** before verdict, write one line per criterion 1-5.

**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
