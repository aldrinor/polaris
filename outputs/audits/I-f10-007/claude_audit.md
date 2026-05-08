# Claude architect audit — I-f10-007

**Issue:** Sandboxed Python execution (no-egress, resource-capped)
**Branch:** bot/I-f10-007
**Canonical-diff-sha256:** d438f4f8533d87939f4e86c39c90c5f41ee9b159a4a5d608dfdbc324e042b4a1
**Brief verdict:** force-APPROVE'd at iter 5 cap per CLAUDE.md §8.3.1
**Diff verdict:** force-APPROVE'd at iter 3 with applied fixes per CLAUDE.md §8.3.1 cap principle

## Substrate honesty (per CLAUDE.md §9.4 + LAW II)

This Issue ships SUBSTANTIAL Python-level defense-in-depth on top of the existing `validate_script` regex layer. **Honestly framed: complete in-process Python sandboxing is not achievable** — every iteration of Codex review surfaced real bypasses (each P1 applied across iters 1-5 brief and iters 1-3 diff). This is the well-known PyPy-restricted-python history; the only complete solution is OS-level isolation.

**Shipped in this PR (defense-in-depth Python layer):**
- AST-based import allowlist enforcement (closes comma-separated import bypass).
- AST-based reflection-attribute blocklist: `__builtins__`, `__import__`, `__class__`, `__subclasses__`, `__globals__`, `__bases__`, `__mro__`, `__dict__`, `__getattribute__`, `__getattr__`, `__base__`, frame paths (`_getframe`, `f_builtins`, `f_globals`, `f_locals`, `f_code`, `gi_frame`, `cr_frame`, `ag_frame`, `tb_frame`), FFI escape (`ctypeslib`, `ctypes`), sys.modules subscript.
- AST-based dangerous-builtin Name reference rejection (closes first-class aliasing): `vars`, `dir`, `globals`, `locals`, `eval`, `exec`, `open`, `compile`, `getattr`, `setattr`, `delattr`.
- Runtime socket monkey-patch preamble: patches `socket.socket`, `create_connection`, `getaddrinfo`, `gethostbyname`, `gethostbyname_ex`, `gethostbyaddr`, `create_server`, `fromfd`, `socketpair`, `SocketType` and the lower-level `_socket` aliases. Cleans up preamble-internal globals (`del _polaris_socket; del _polaris_socket_raw; del _polaris_attr`) so they aren't visible to user code.
- `_socket` added to `_BLOCKED_IMPORTS`.
- `operator` removed from `_ALLOWED_IMPORTS` (closes attrgetter reflection); `time` added.
- 35 sovereignty tests covering 30+ adversarial cases + 3 sanity + 2 runtime; all passing.

**Residual surface (deferred to follow-up Issue I-f10-007b "OS-level egress isolation for code_executor"):**
- Object-graph reflection deep chains (`(...).__class__.__bases__[0].__subclasses__()` — partially mitigated by `__class__` AST block).
- Hand-crafted bytecode that synthesizes builtin lookups.
- Any future allowlisted module exposing additional native FFI surface.

These remaining vectors require process isolation (network namespace + seccomp + read-only FS) for complete sovereignty. Tracked in I-f10-007b; the canonical sovereign environment (OVH Canada BHS H200 + Vast.ai US dev cluster) is the deployment target where OS-level controls are configured.

## §9.4 N/A backend.

## CHARTER §1 LOC cap
- 416 net (216 LOC over 200). Exemption: hardening surface is intrinsically large because Python in-process sandboxing has many escape vectors. Each LOC closes a specific bypass found by Codex iter-1..5 brief + iter-1..3 diff review. No abstractions added; substrate + tests only.

## Verdict
APPROVE.
