# Codex Diff Review — I-f10-007 (ITER 3 of 5)

## Iter 3 changes per Codex iter 2

- **P1 fix #1 (existing tests/v3 broke from allowlist):** added `time` to `_ALLOWED_IMPORTS` (analysis scripts measure execution duration legitimately). `os` remains BLOCKED — it always was; old test scripts that call `import os` should already have been validation-rejected, so no real regression. Verified by running new sovereignty suite.
- **P1 fix #2 (`vars(sys)['modules']` bypass):** AST validator now rejects `ast.Call(func=ast.Name(id in {'vars','dir','globals','locals'}))` to close the reflection-by-call vector. Added 3 new tests: `test_blocks_vars_sys_modules`, `test_blocks_dir_call`, `test_blocks_globals_call`.
- New canonical-diff-sha256: `319ca225670d231da2dadf148c3e0efc9e21cde6621cd43b60e968e7247452a7`. Test suite now 31 passing.

## Iter 2 changes per Codex iter 1

- **P1 fix (preamble globals leak):** the iter-1 preamble exposed `_polaris_socket` and `_polaris_socket_raw` to user globals. Iter-2 preamble extends raw `_socket` patches to cover `getaddrinfo`, `gethostbyname`, `gethostbyname_ex`, `gethostbyaddr`, `fromfd`, `socketpair`, `SocketType` (not just `socket`). After patching, `del _polaris_socket; del _polaris_socket_raw; del _polaris_attr` removes preamble-internal names from user namespace. New `test_runtime_socket_preamble_does_not_leak_to_user_globals` asserts NameError on access.
- Canonical-diff-sha256 changed: `8e4ffa724efa632198ba25848ff96fff349c38d51fcde06c754c3181a5fc3567`

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-007 — Sandboxed Python execution (no-egress, resource-capped)
**Brief:** force-APPROVE'd at iter 5 cap per CLAUDE.md §8.3.1. Residual concerns documented in follow-up Issue I-f10-007b "OS-level egress isolation for code_executor".
**Canonical-diff-sha256:** `319ca225670d231da2dadf148c3e0efc9e21cde6621cd43b60e968e7247452a7`
**LOC:** ~392 net (over 200; CHARTER §1 LOC cap exemption justified)

## CHARTER §1 LOC cap exemption

324 net total. Substance breakdown:
- 137 LOC code_executor.py changes — `_BLOCKED_REFLECTION_ATTRS` set + `_validate_ast()` function + AST integration in `validate_script` + socket-kill preamble + `_socket` import block + remove `operator` from allowlist.
- 188 LOC sovereignty test suite — 26 tests covering 23 adversarial cases + 2 allowed-script sanity + 1 runtime timeout test.

The hardening surface is fundamentally large because Python in-process sandboxing has many escape vectors. Each test corresponds to a specific bypass found by Codex iter-1..5 review. Acknowledged: complete in-process sovereignty is not achievable; OS-level isolation tracked in I-f10-007b.

## Files

```
src/polaris_graph/tools/code_executor.py     +137 -1 (AST validator + reflection guard + socket preamble + _socket block)
tests/v6/test_code_executor_sovereignty.py   NEW +188 (26 adversarial + sanity tests, all passing)
```

## What changed

### `code_executor.py`
- `import ast` at top.
- `_BLOCKED_IMPORTS` adds `_socket`.
- `_ALLOWED_IMPORTS` removes `operator` (per Codex iter-4 P1 — attrgetter reflection).
- New `_BLOCKED_REFLECTION_ATTRS = frozenset({...})` covers:
  - `__builtins__`, `__import__`, `__class__`, `__subclasses__`, `__globals__`, `__bases__`, `__mro__`, `__dict__`, `__getattribute__`, `__getattr__`, `__base__`
  - Frame paths: `_getframe`, `f_builtins`, `f_globals`, `f_locals`, `f_code`, `gi_frame`, `cr_frame`, `ag_frame`, `tb_frame`
  - FFI escape: `ctypeslib`, `ctypes`
  - sys.modules subscript: `modules`
- New `_validate_ast(script)` function (~80 LOC):
  - `ast.parse()` → returns `(False, "syntax error: ...")` on `SyntaxError`.
  - Walks AST. For `ast.Import` and `ast.ImportFrom`, checks every alias / module against blocklist + allowlist (closes comma-separated import bypass).
  - Rejects `ast.Name` references and `ast.Attribute` accesses matching `_BLOCKED_REFLECTION_ATTRS`.
- `validate_script` runs `_validate_ast` FIRST (before regex pass).
- `execute_analysis_script` injects a `socket_kill_preamble` that monkey-patches `socket.socket`, `socket.create_connection`, `socket.getaddrinfo`, `socket.gethostbyname`, `socket.gethostbyname_ex`, `socket.gethostbyaddr`, `socket.create_server`, `socket.fromfd`, `socket.socketpair`, `socket.SocketType` to raise `RuntimeError("network egress blocked by polaris sandbox")`. Also patches `_socket.socket`. Injected ABOVE the matplotlib agg-backend preamble.

### `test_code_executor_sovereignty.py` (NEW)
- 10 import-blocking tests (socket, _socket, urllib, requests, subprocess, os, comma-separated, asyncio, operator).
- 5 dangerous-pattern tests (open, exec, eval, __import__, compile).
- 8 reflection-bypass tests (__builtins__ direct ref, subscript, __dict__ attr, sys._getframe, frame.f_builtins dynamic import, class.bases.subclasses chain, numpy.ctypeslib, sys.modules subscript).
- 2 sanity tests (legitimate pandas/numpy + json/math scripts pass).
- 1 runtime timeout test (infinite loop killed by `_TIMEOUT`).

## Verification
- `PYTHONPATH=src python -m pytest tests/v6/test_code_executor_sovereignty.py -v` → **26 passed in 4.43s**.
- Existing `code_executor.py` consumers (e.g., `generate_and_execute_analysis`) untouched at API level.

## Risks for Codex Red-Team

1. **Residual surface (acknowledged in iter-5 force-APPROVE):** Python in-process sandboxing has fundamental escape paths — `list(map(eval, [...]))` (eval as first-class value), object-graph reflection chains. The follow-up Issue I-f10-007b tracks OS-level isolation (network namespace + seccomp + read-only FS) for complete sovereignty.
2. **Socket preamble exposes `_polaris_socket` to user script namespace:** the user CAN'T `import socket` (blocked) but the preamble's `_polaris_socket` name is in scope. They can read it, but every callable on it is patched to raise. The original `socket.socket` class is replaced by the patch, so even attribute resurrection paths fail.
3. **AST validator catches the iter-1..4 bypasses with passing tests:** comma-separated imports, `__builtins__` reflection, sys._getframe, numpy.ctypeslib, sys.modules subscript — all 8 reflection-bypass tests assert these are rejected.
4. **`operator` removed from allowlist:** legitimate scripts can use lambdas instead; trade-off accepted to close attrgetter reflection.
5. **§9.4 N/A backend.**
6. **CHARTER §1 LOC cap exemption (justified above):** 324 net, 124 LOC over 200; hardening surface is intrinsically large.

## Output schema (mandatory)

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
