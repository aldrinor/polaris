"""I-f10-007: Sovereignty CI test for code_executor sandbox.

Validation-time + runtime adversarial tests proving the sandbox blocks
common Python sandbox-escape vectors. Honest framing: complete in-process
sovereignty is not achievable in Python; OS-level isolation (network
namespace + seccomp + read-only FS) tracked in I-f10-007b follow-up.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.tools.code_executor import (
    execute_analysis_script,
    validate_script,
)


# ---------------------------------------------------------------------------
# Validation-time rejection: blocked imports
# ---------------------------------------------------------------------------

def test_blocks_socket_import():
    ok, _ = validate_script("import socket")
    assert ok is False


def test_blocks_underscore_socket_import():
    ok, _ = validate_script("import _socket")
    assert ok is False


def test_blocks_urllib_import():
    ok, _ = validate_script("import urllib.request")
    assert ok is False


def test_blocks_requests_import():
    ok, _ = validate_script("import requests")
    assert ok is False


def test_blocks_subprocess_import():
    ok, _ = validate_script("import subprocess")
    assert ok is False


def test_blocks_os_import():
    ok, _ = validate_script("import os")
    assert ok is False


def test_blocks_comma_separated_socket_import():
    """Codex iter-1 P1: `import json, socket` previously bypassed the regex."""
    ok, _ = validate_script("import json, socket")
    assert ok is False


def test_blocks_comma_separated_urllib_import():
    ok, _ = validate_script("import sys, urllib.request")
    assert ok is False


def test_blocks_non_allowlisted_module():
    """Allowlist enforcement: asyncio is not in _ALLOWED_IMPORTS."""
    ok, _ = validate_script("import asyncio")
    assert ok is False


def test_blocks_operator_import():
    """operator removed from allowlist (Codex iter-4 P1: attrgetter reflection)."""
    ok, _ = validate_script("from operator import attrgetter")
    assert ok is False


# ---------------------------------------------------------------------------
# Validation-time rejection: dangerous patterns
# ---------------------------------------------------------------------------

def test_blocks_open_call():
    ok, _ = validate_script("open('/etc/passwd')")
    assert ok is False


def test_blocks_exec_call():
    ok, _ = validate_script("exec('print(1)')")
    assert ok is False


def test_blocks_eval_call():
    ok, _ = validate_script("eval('1+1')")
    assert ok is False


def test_blocks_dunder_import():
    ok, _ = validate_script("__import__('os')")
    assert ok is False


def test_blocks_compile_call():
    ok, _ = validate_script("compile('x', '<s>', 'exec')")
    assert ok is False


# ---------------------------------------------------------------------------
# Validation-time rejection: reflection bypasses (Codex iter-1..4 P1 fixes)
# ---------------------------------------------------------------------------

def test_blocks_builtins_direct_reference():
    """Codex iter-1 P1: __builtins__ direct name reference."""
    ok, _ = validate_script("x = __builtins__")
    assert ok is False


def test_blocks_builtins_subscript():
    """Codex iter-1 P1: __builtins__['__import__']('socket')."""
    ok, _ = validate_script("__builtins__['__import__']('socket')")
    assert ok is False


def test_blocks_builtins_dict_attr():
    """Codex iter-1 P1: __builtins__.__dict__['__import__']('socket')."""
    ok, _ = validate_script("__builtins__.__dict__['__import__']('socket')")
    assert ok is False


def test_blocks_sys_getframe():
    """Codex iter-3 P1: sys._getframe access."""
    ok, _ = validate_script("import sys\nf = sys._getframe()")
    assert ok is False


def test_blocks_dynamic_import_via_frame():
    """Codex iter-3 P1: sys._getframe().f_builtins['__import__']('subprocess')."""
    ok, _ = validate_script(
        "import sys\nimp = sys._getframe().f_builtins['__import__']\nimp('subprocess')"
    )
    assert ok is False


def test_blocks_class_subclasses_chain():
    """Object-graph reflection: ().__class__.__bases__[0].__subclasses__()."""
    ok, _ = validate_script("().__class__.__bases__[0].__subclasses__()")
    assert ok is False


def test_blocks_numpy_ctypeslib():
    """Codex iter-4 P1: numpy.ctypeslib FFI escape."""
    ok, _ = validate_script("import numpy as np\nnp.ctypeslib.load_library('libc', '/')")
    assert ok is False


def test_blocks_sys_modules_subscript():
    """Codex iter-5 P1: sys.modules['os'].system(...)."""
    ok, _ = validate_script("import sys\nsys.modules['os'].system('id')")
    assert ok is False


def test_blocks_vars_sys_modules():
    """Codex iter-2 diff P1: vars(sys)['modules']['os'].system(...) bypass."""
    ok, _ = validate_script("import sys\nvars(sys)['modules']['os'].system('id')")
    assert ok is False


def test_blocks_dir_call():
    """Reflection: dir(...) is blocked as part of the vars/dir/globals/locals set."""
    ok, _ = validate_script("import sys\ndir(sys)")
    assert ok is False


def test_blocks_globals_call():
    """Reflection: globals() exposes the script's own namespace; blocked."""
    ok, _ = validate_script("globals()")
    assert ok is False


def test_blocks_eval_alias():
    """Codex iter-3 diff P1: first-class aliasing `e = eval; e(...)`."""
    ok, _ = validate_script("e = eval\ne('1+1')")
    assert ok is False


def test_blocks_open_alias():
    ok, _ = validate_script("o = open\no('/etc/passwd')")
    assert ok is False


def test_blocks_vars_alias_sys_modules():
    ok, _ = validate_script("import sys\nv = vars\nv(sys)['modules']")
    assert ok is False


def test_blocks_getattr_alias():
    ok, _ = validate_script("g = getattr\ng({}, 'x')")
    assert ok is False


# ---------------------------------------------------------------------------
# Allowed scripts pass
# ---------------------------------------------------------------------------

def test_allowed_pandas_numpy_passes():
    """Sanity: legitimate analysis scripts still validate."""
    ok, _ = validate_script(
        "import pandas as pd\nimport numpy as np\nx = np.array([1,2,3])\nprint({'mean': float(x.mean())})"
    )
    assert ok is True


def test_allowed_imports_with_alias_passes():
    ok, _ = validate_script("import json\nimport math\nprint(json.dumps({'pi': math.pi}))")
    assert ok is True


def test_time_module_allowed():
    """`time` is needed by analysis scripts that measure execution duration."""
    ok, _ = validate_script("import time\nimport json\nprint(json.dumps({'t': time.time()}))")
    assert ok is True


# ---------------------------------------------------------------------------
# Runtime sovereignty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_timeout_cap_kills_runaway_loop():
    """Resource cap: infinite loop killed by timeout."""
    result = await execute_analysis_script(
        "while True:\n    pass",
        timeout=2,
    )
    assert result["success"] is False
    assert "timeout" in (result.get("error") or "").lower() or result["execution_time_seconds"] >= 2.0


@pytest.mark.asyncio
async def test_runtime_socket_preamble_does_not_leak_to_user_globals():
    """Codex iter-1 P1 (diff): the socket preamble's `_polaris_socket` and
    `_polaris_socket_raw` names must NOT remain in user script globals after
    patching. Otherwise validated scripts could call `_polaris_socket_raw.
    getaddrinfo(...)` to bypass the no-egress claim."""
    # User script tries to access the preamble's leaked names. Both should
    # raise NameError (preamble cleaned them up) and the script overall
    # fails (returncode != 0); the executor surfaces the error.
    script = (
        "import json, sys\n"
        "try:\n"
        "    _polaris_socket\n"
        "    leaked = 'polaris_socket'\n"
        "except NameError:\n"
        "    leaked = None\n"
        "try:\n"
        "    _polaris_socket_raw\n"
        "    leaked_raw = 'polaris_socket_raw'\n"
        "except NameError:\n"
        "    leaked_raw = None\n"
        "print(json.dumps({'leaked': leaked, 'leaked_raw': leaked_raw}))\n"
    )
    result = await execute_analysis_script(script)
    assert result["success"] is True
    assert result["result"]["leaked"] is None
    assert result["result"]["leaked_raw"] is None
