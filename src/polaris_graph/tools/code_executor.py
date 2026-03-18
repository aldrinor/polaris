"""
Sandboxed Python code execution for research data analysis.

Executes LLM-generated Python analysis scripts in an isolated subprocess
with timeout enforcement, import restrictions, and output size limits.
Scripts receive data via JSON stdin, produce results via JSON stdout,
and may generate matplotlib figures returned as base64 PNG.

This is what makes POLARIS competitive with Claude Code: the LLM can
write arbitrary Python analysis scripts that run on real evidence data,
producing custom statistical analyses, charts, and tables.
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from src.polaris_graph.llm.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LAW VI: All configuration from environment variables
# ---------------------------------------------------------------------------

_TIMEOUT = int(os.getenv("PG_CODE_EXEC_TIMEOUT", "30"))
_MAX_OUTPUT_SIZE = int(os.getenv("PG_CODE_EXEC_MAX_OUTPUT", "1000000"))  # 1MB
_MAX_SCRIPT_SIZE = int(os.getenv("PG_CODE_EXEC_MAX_SCRIPT", "50000"))  # 50KB
_MAX_INPUT_DATA_SIZE = int(os.getenv("PG_CODE_EXEC_MAX_INPUT", "5000000"))  # 5MB
_MAX_RETRY_ATTEMPTS = int(os.getenv("PG_CODE_EXEC_MAX_RETRIES", "1"))
_DATA_PREVIEW_ITEMS = int(os.getenv("PG_CODE_EXEC_PREVIEW_ITEMS", "20"))
_DATA_PREVIEW_MAX_CHARS = int(os.getenv("PG_CODE_EXEC_PREVIEW_CHARS", "8000"))

# GAP-3: Sandbox file I/O directories (LAW VI: from env with defaults)
_SANDBOX_READ_DIR = os.getenv("PG_SANDBOX_READ_DIR", "outputs/polaris_graph")
_SANDBOX_WRITE_DIR = os.getenv("PG_SANDBOX_WRITE_DIR", "outputs/analysis")

# ---------------------------------------------------------------------------
# Security: blocked imports and dangerous patterns
# ---------------------------------------------------------------------------

# NOTE: "sys" is intentionally NOT blocked because scripts need sys.stdin
# to read input data. The subprocess runs in an isolated environment with
# restricted env vars, and dangerous operations (file I/O, exec, eval,
# network access) are blocked by other rules below.
_BLOCKED_IMPORTS = frozenset({
    "os",
    "subprocess",
    "shutil",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "smtplib",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "importlib",
    "builtins",
    "pickle",
    "shelve",
    "code",
    "codeop",
    "compile",
    "compileall",
    "py_compile",
    "zipimport",
    "pkgutil",
    "runpy",
    "webbrowser",
    "xmlrpc",
    "telnetlib",
    "poplib",
    "imaplib",
    "nntplib",
    "pty",
    "pipes",
    "resource",
    "fcntl",
    "termios",
    "mmap",
})

# Additional dangerous patterns beyond import blocking
_DANGEROUS_PATTERNS = [
    (r'\bopen\s*\(', "File open() is not allowed; read data from stdin only"),
    (r'\b__import__\s*\(', "__import__() is not allowed"),
    (r'\bexec\s*\(', "exec() is not allowed"),
    (r'\beval\s*\(', "eval() is not allowed"),
    (r'\bglobals\s*\(', "globals() is not allowed"),
    (r'\blocals\s*\(', "locals() is not allowed"),
    (r'\bgetattr\s*\(', "getattr() is not allowed"),
    (r'\bsetattr\s*\(', "setattr() is not allowed"),
    (r'\bdelattr\s*\(', "delattr() is not allowed"),
    (r'\bcompile\s*\(', "compile() is not allowed"),
    (r'\bbreakpoint\s*\(', "breakpoint() is not allowed"),
]

# Allowed imports that scripts may use
_ALLOWED_IMPORTS = frozenset({
    "numpy",
    "np",
    "pandas",
    "pd",
    "scipy",
    "scipy.stats",
    "scipy.optimize",
    "scipy.interpolate",
    "scipy.signal",
    "matplotlib",
    "matplotlib.pyplot",
    "plt",
    "json",
    "sys",
    "math",
    "statistics",
    "collections",
    "collections.abc",
    "re",
    "datetime",
    "decimal",
    "fractions",
    "itertools",
    "functools",
    "operator",
    "copy",
    "io",
    "base64",
    "textwrap",
    "string",
    "typing",
    "dataclasses",
    "enum",
    "numbers",
    "csv",
    "pprint",
})


# ---------------------------------------------------------------------------
# Sandbox directory management
# ---------------------------------------------------------------------------

def _prepare_sandbox_env() -> dict[str, str]:
    """Create the sandbox write directory and return absolute paths.

    Returns a dict with SANDBOX_READ_DIR and SANDBOX_WRITE_DIR as absolute
    paths suitable for injection into the subprocess environment.

    The write directory is created if it does not exist. The read directory
    is not created (it must already exist with evidence files).
    """
    read_abs = str(Path(_SANDBOX_READ_DIR).resolve())
    write_abs = str(Path(_SANDBOX_WRITE_DIR).resolve())

    # Ensure write directory exists
    Path(write_abs).mkdir(parents=True, exist_ok=True)

    return {
        "SANDBOX_READ_DIR": read_abs,
        "SANDBOX_WRITE_DIR": write_abs,
    }


def get_sandbox_paths() -> dict:
    """Return sandbox directory paths for script reference.

    Returns:
        {"read_dir": str, "write_dir": str}
    """
    sandbox = _prepare_sandbox_env()
    return {
        "read_dir": sandbox["SANDBOX_READ_DIR"],
        "write_dir": sandbox["SANDBOX_WRITE_DIR"],
    }


# ---------------------------------------------------------------------------
# Script validation
# ---------------------------------------------------------------------------

def validate_script(script: str) -> tuple[bool, str]:
    """Check a script for blocked imports and dangerous patterns.

    Performs static analysis only -- does not execute the script. Checks
    import statements against the blocklist and scans for dangerous
    built-in function calls.

    Args:
        script: Python source code to validate.

    Returns:
        Tuple of (is_safe, reason). is_safe is True if the script passes
        all checks. reason explains the first violation found (empty
        string when safe).
    """
    if not script or not script.strip():
        return False, "Script is empty"

    if len(script) > _MAX_SCRIPT_SIZE:
        return False, (
            f"Script exceeds maximum size ({len(script)} > {_MAX_SCRIPT_SIZE} bytes)"
        )

    # Normalize line continuations for analysis
    normalized = script.replace("\\\n", " ")

    # Check each line for import violations
    # Split semicolon-separated statements into separate lines
    raw_lines = normalized.split("\n")
    expanded_lines = []
    for raw_line in raw_lines:
        expanded_lines.extend(raw_line.split(";"))

    for line_num, raw_line in enumerate(expanded_lines, start=1):
        line = raw_line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        # Check "import X" and "from X import Y"
        import_match = re.match(
            r'(?:from\s+(\S+)\s+import|import\s+(\S+))', line
        )
        if import_match:
            module_name = import_match.group(1) or import_match.group(2)
            # Strip trailing punctuation (semicolons, commas)
            module_name = re.sub(r'[^a-zA-Z0-9_.]', '', module_name)
            # Check the top-level module (e.g., "os" from "os.path")
            top_module = module_name.split(".")[0]
            if top_module in _BLOCKED_IMPORTS:
                return False, (
                    f"Line {line_num}: Blocked import '{top_module}' "
                    f"(security restriction)"
                )

    # Check for dangerous built-in patterns
    for pattern, reason in _DANGEROUS_PATTERNS:
        match = re.search(pattern, normalized)
        if match:
            # Check if the match is inside a comment or string
            # (rough heuristic: find the line containing the match)
            match_pos = match.start()
            preceding = normalized[:match_pos]
            line_start = preceding.rfind("\n") + 1
            line_text = normalized[line_start:].split("\n")[0].strip()

            # Skip if the pattern appears inside a comment
            comment_pos = line_text.find("#")
            match_in_line = match.start() - line_start
            if comment_pos >= 0 and match_in_line > comment_pos:
                continue

            # Skip if inside a string literal (very rough check)
            before_match = line_text[:match_in_line]
            single_quotes = before_match.count("'") - before_match.count("\\'")
            double_quotes = before_match.count('"') - before_match.count('\\"')
            if single_quotes % 2 == 1 or double_quotes % 2 == 1:
                continue

            return False, f"Dangerous pattern detected: {reason}"

    return True, ""


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------

async def execute_analysis_script(
    script: str,
    input_data: dict | None = None,
    timeout: int | None = None,
) -> dict:
    """Execute a Python analysis script in a sandboxed subprocess.

    The script runs in a fresh Python process with a temp working directory.
    Data is passed via stdin as JSON. Results are expected as JSON on stdout.
    Matplotlib figures embedded as base64 PNG in the JSON output are extracted
    into the "charts" field.

    The subprocess environment includes SANDBOX_READ_DIR and SANDBOX_WRITE_DIR
    pointing to controlled directories for evidence file access and result output.

    Args:
        script: Python code to execute. Must print JSON to stdout.
        input_data: Dict passed to the script via stdin as JSON. The script
            reads it with ``json.load(sys.stdin)``.
        timeout: Max execution time in seconds. Defaults to PG_CODE_EXEC_TIMEOUT.

    Returns:
        Dictionary with:
            - success: Whether execution completed without errors
            - stdout: Raw stdout content
            - stderr: Raw stderr content
            - result: Parsed JSON from stdout (None on failure)
            - charts: List of extracted chart dicts with base64 images
            - execution_time_seconds: Wall-clock execution time
            - error: Error description (None on success)
    """
    effective_timeout = timeout if timeout is not None else _TIMEOUT

    empty_result = {
        "success": False,
        "stdout": "",
        "stderr": "",
        "result": None,
        "charts": [],
        "execution_time_seconds": 0.0,
        "error": None,
    }

    # Validate the script first
    is_safe, safety_reason = validate_script(script)
    if not is_safe:
        logger.warning(
            "[code_executor] Script validation failed: %s", safety_reason
        )
        return {**empty_result, "error": f"Validation failed: {safety_reason}"}

    # Unconditionally enforce Agg backend -- prevents Windows Tk display hangs
    agg_preamble = "import matplotlib\nmatplotlib.use('Agg')\n"
    if "matplotlib" in script and "matplotlib.use(" not in script:
        script = agg_preamble + script

    # Prepare stdin data
    stdin_json = ""
    if input_data is not None:
        try:
            stdin_json = json.dumps(input_data, default=str)
        except (TypeError, ValueError) as exc:
            return {
                **empty_result,
                "error": f"Failed to serialize input_data: {str(exc)[:200]}",
            }
        if len(stdin_json) > _MAX_INPUT_DATA_SIZE:
            return {
                **empty_result,
                "error": (
                    f"Input data exceeds maximum size "
                    f"({len(stdin_json)} > {_MAX_INPUT_DATA_SIZE} bytes)"
                ),
            }

    # Write script and input to temp files
    script_path = None
    input_path = None
    work_dir = tempfile.mkdtemp(prefix="polaris_exec_")

    try:
        # Write script
        script_path = os.path.join(work_dir, "analysis_script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        # Write input data if provided
        if stdin_json:
            input_path = os.path.join(work_dir, "input_data.json")
            with open(input_path, "w", encoding="utf-8") as f:
                f.write(stdin_json)

    except Exception as exc:
        logger.error(
            "[code_executor] Failed to write temp files: %s", str(exc)[:200]
        )
        _cleanup_temp(work_dir, script_path, input_path)
        return {
            **empty_result,
            "error": f"Failed to write temp files: {str(exc)[:200]}",
        }

    # Execute in subprocess
    start_time = time.monotonic()

    try:
        # Build command
        cmd = [sys.executable, "-u", script_path]

        # Prepare stdin
        stdin_bytes = stdin_json.encode("utf-8") if stdin_json else None

        # Run in a thread to avoid blocking the event loop
        proc_result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_subprocess,
                cmd=cmd,
                stdin_data=stdin_bytes,
                timeout=effective_timeout,
                cwd=work_dir,
            ),
            timeout=effective_timeout + 5,  # Grace period for thread overhead
        )

        elapsed = time.monotonic() - start_time

        if proc_result["returncode"] != 0:
            stderr_preview = proc_result["stderr"][:1000] if proc_result["stderr"] else ""
            logger.warning(
                "[code_executor] Script failed (exit=%d, %.1fs): %s",
                proc_result["returncode"],
                elapsed,
                stderr_preview,
            )
            return {
                "success": False,
                "stdout": proc_result["stdout"][:_MAX_OUTPUT_SIZE],
                "stderr": proc_result["stderr"][:_MAX_OUTPUT_SIZE],
                "result": None,
                "charts": [],
                "execution_time_seconds": round(elapsed, 3),
                "error": f"Script exited with code {proc_result['returncode']}: {stderr_preview}",
            }

        # Parse stdout
        raw_stdout = proc_result["stdout"]
        if len(raw_stdout) > _MAX_OUTPUT_SIZE:
            logger.warning(
                "[code_executor] Output truncated from %d to %d bytes",
                len(raw_stdout),
                _MAX_OUTPUT_SIZE,
            )
            raw_stdout = raw_stdout[:_MAX_OUTPUT_SIZE]

        if not raw_stdout.strip():
            return {
                "success": False,
                "stdout": "",
                "stderr": proc_result["stderr"][:_MAX_OUTPUT_SIZE],
                "result": None,
                "charts": [],
                "execution_time_seconds": round(elapsed, 3),
                "error": "Script produced no stdout output",
            }

        # Parse JSON result
        try:
            parsed = json.loads(raw_stdout.strip())
        except json.JSONDecodeError as exc:
            # Try to extract JSON from mixed output (script may have print
            # statements before the JSON)
            parsed = _extract_json_from_output(raw_stdout)
            if parsed is None:
                return {
                    "success": False,
                    "stdout": raw_stdout[:2000],
                    "stderr": proc_result["stderr"][:_MAX_OUTPUT_SIZE],
                    "result": None,
                    "charts": [],
                    "execution_time_seconds": round(elapsed, 3),
                    "error": f"Invalid JSON output: {str(exc)[:200]}",
                }

        # Extract charts (base64 PNG images)
        charts = _extract_charts(parsed)

        logger.info(
            "[code_executor] Script completed successfully in %.1fs: "
            "%d chars output, %d charts",
            elapsed,
            len(raw_stdout),
            len(charts),
        )

        return {
            "success": True,
            "stdout": raw_stdout,
            "stderr": proc_result["stderr"][:_MAX_OUTPUT_SIZE],
            "result": parsed,
            "charts": charts,
            "execution_time_seconds": round(elapsed, 3),
            "error": None,
        }

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start_time
        logger.warning(
            "[code_executor] Script timed out after %.1fs (limit=%ds)",
            elapsed,
            effective_timeout,
        )
        return {
            **empty_result,
            "execution_time_seconds": round(elapsed, 3),
            "error": f"Script timed out after {effective_timeout}s",
        }

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        logger.error(
            "[code_executor] Unexpected error: %s", str(exc)[:300]
        )
        return {
            **empty_result,
            "execution_time_seconds": round(elapsed, 3),
            "error": f"Execution error: {str(exc)[:300]}",
        }

    finally:
        _cleanup_temp(work_dir, script_path, input_path)


# ---------------------------------------------------------------------------
# LLM-driven analysis: generate script then execute
# ---------------------------------------------------------------------------

async def generate_and_execute_analysis(
    client: OpenRouterClient,
    evidence_data: list[dict],
    analysis_question: str,
    research_context: str = "",
) -> dict:
    """Ask the LLM to write a Python analysis script, then execute it.

    This is the "Claude Code for research" function. The LLM sees the
    evidence data, writes a custom analysis script tailored to the question,
    and we execute it in a sandboxed subprocess.

    On execution failure, the error is fed back to the LLM for one retry
    attempt with corrective instructions.

    Args:
        client: OpenRouter LLM client for script generation.
        evidence_data: Structured data to analyze (list of evidence dicts).
        analysis_question: What to analyze, e.g. "Compare removal efficiency
            across studies".
        research_context: Topic context for better script generation.

    Returns:
        Same structure as execute_analysis_script with an additional
        "generated_script" field containing the Python code that was run.
    """
    if not evidence_data:
        logger.warning(
            "[code_executor] generate_and_execute_analysis called with "
            "empty evidence_data"
        )
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "result": None,
            "charts": [],
            "execution_time_seconds": 0.0,
            "error": "No evidence data provided",
            "generated_script": "",
        }

    # Build data preview for the LLM prompt
    preview_items = evidence_data[:_DATA_PREVIEW_ITEMS]
    preview_json = json.dumps(preview_items, indent=2, default=str)
    if len(preview_json) > _DATA_PREVIEW_MAX_CHARS:
        preview_json = preview_json[:_DATA_PREVIEW_MAX_CHARS] + "\n... (truncated)"

    # Describe the data schema from the first item
    schema_description = ""
    if evidence_data:
        sample = evidence_data[0]
        schema_lines = []
        for key, val in sample.items():
            val_type = type(val).__name__
            val_preview = str(val)[:80]
            schema_lines.append(f"  - {key} ({val_type}): e.g. \"{val_preview}\"")
        schema_description = "\n".join(schema_lines)

    # Generate the script
    script = await _generate_script(
        client=client,
        evidence_data=evidence_data,
        preview_json=preview_json,
        schema_description=schema_description,
        analysis_question=analysis_question,
        research_context=research_context,
        error_feedback=None,
    )

    if not script:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "result": None,
            "charts": [],
            "execution_time_seconds": 0.0,
            "error": "LLM failed to generate a valid script",
            "generated_script": "",
        }

    # Execute the script
    result = await execute_analysis_script(
        script=script,
        input_data={"data": evidence_data, "question": analysis_question},
    )
    result["generated_script"] = script

    # Retry once on failure with error feedback
    if not result["success"] and _MAX_RETRY_ATTEMPTS > 0:
        error_msg = result.get("error", "") or result.get("stderr", "")
        logger.info(
            "[code_executor] First execution failed, retrying with error feedback: %s",
            str(error_msg)[:200],
        )

        retry_script = await _generate_script(
            client=client,
            evidence_data=evidence_data,
            preview_json=preview_json,
            schema_description=schema_description,
            analysis_question=analysis_question,
            research_context=research_context,
            error_feedback=str(error_msg)[:2000],
        )

        if retry_script:
            retry_result = await execute_analysis_script(
                script=retry_script,
                input_data={"data": evidence_data, "question": analysis_question},
            )
            retry_result["generated_script"] = retry_script

            if retry_result["success"]:
                logger.info("[code_executor] Retry succeeded")
                return retry_result

            # Both attempts failed; return the retry result with both scripts
            logger.warning(
                "[code_executor] Retry also failed: %s",
                str(retry_result.get("error", ""))[:200],
            )
            retry_result["generated_script"] = (
                f"# === ATTEMPT 1 (failed) ===\n{script}\n\n"
                f"# === ATTEMPT 2 (failed) ===\n{retry_script}"
            )
            return retry_result

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_subprocess(
    cmd: list[str],
    stdin_data: bytes | None,
    timeout: int,
    cwd: str,
) -> dict:
    """Run a subprocess synchronously (called via asyncio.to_thread).

    Returns dict with returncode, stdout, stderr strings.
    """
    import subprocess

    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            # Restrict environment: only pass essential variables + sandbox paths
            env=_build_restricted_env(),
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", errors="replace"),
            "stderr": proc.stderr.decode("utf-8", errors="replace"),
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Process killed after {timeout}s timeout",
        }
    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Process error: {str(exc)[:500]}",
        }


def _build_restricted_env() -> dict[str, str]:
    """Build a restricted environment for the subprocess.

    Passes only the variables needed for Python and data analysis libraries
    to function. No API keys, no network configuration.

    Includes SANDBOX_READ_DIR and SANDBOX_WRITE_DIR for controlled file
    access to evidence files and analysis output.
    """
    env = {}

    # Python needs these to find its stdlib and packages
    for key in ("PATH", "PYTHONPATH", "PYTHONHOME", "SYSTEMROOT", "TEMP", "TMP",
                "VIRTUAL_ENV", "CONDA_PREFIX", "USERPROFILE", "HOME",
                "APPDATA", "LOCALAPPDATA"):
        val = os.environ.get(key)
        if val is not None:
            env[key] = val

    # Matplotlib needs a writable config dir
    env["MPLCONFIGDIR"] = tempfile.gettempdir()

    # Prevent matplotlib from trying to use a GUI backend
    env["MPLBACKEND"] = "Agg"

    # NumPy/OpenBLAS thread control (prevent fork bombs)
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"

    # Sandbox file I/O directories for scripts that need evidence access
    sandbox = _prepare_sandbox_env()
    env["SANDBOX_READ_DIR"] = sandbox["SANDBOX_READ_DIR"]
    env["SANDBOX_WRITE_DIR"] = sandbox["SANDBOX_WRITE_DIR"]

    return env


def _extract_json_from_output(raw_output: str) -> dict | None:
    """Try to extract valid JSON from output that may contain non-JSON lines.

    Scripts sometimes print debug output before the JSON. This function
    scans for the last JSON object or array in the output.
    """
    # Try to find the last { ... } block
    lines = raw_output.strip().split("\n")

    # Strategy 1: Try parsing from the last line that starts with "{"
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("{"):
            candidate = "\n".join(lines[i:])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # Strategy 2: Find the outermost { } pair
    first_brace = raw_output.find("{")
    last_brace = raw_output.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidate = raw_output[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None


def _extract_charts(parsed_result: dict | list) -> list[dict]:
    """Extract chart data (base64 PNG images) from parsed script output.

    Looks for "charts" key in the result, or any field containing
    "image_base64" data. Validates that base64 data decodes to valid PNG.

    Returns list of {"title": str, "image_base64": str} dicts.
    """
    charts = []

    if isinstance(parsed_result, dict):
        raw_charts = parsed_result.get("charts", [])
    elif isinstance(parsed_result, list):
        raw_charts = parsed_result
    else:
        return charts

    if not isinstance(raw_charts, list):
        return charts

    for chart in raw_charts:
        if not isinstance(chart, dict):
            continue

        image_b64 = chart.get("image_base64", "")
        if not image_b64 or not isinstance(image_b64, str):
            continue

        # Validate PNG magic bytes
        try:
            decoded = base64.b64decode(image_b64)
            if len(decoded) < 8:
                logger.warning(
                    "[code_executor] Chart '%s' has < 8 bytes, skipping",
                    chart.get("title", "unknown"),
                )
                continue
            if decoded[:4] != b'\x89PNG':
                logger.warning(
                    "[code_executor] Chart '%s' is not valid PNG (magic: %s), skipping",
                    chart.get("title", "unknown"),
                    decoded[:4].hex(),
                )
                continue
        except Exception:
            logger.warning(
                "[code_executor] Chart '%s' base64 decode failed, skipping",
                chart.get("title", "unknown"),
            )
            continue

        charts.append({
            "title": str(chart.get("title", f"Chart {len(charts) + 1}")),
            "image_base64": image_b64,
        })

    return charts


def _cleanup_temp(
    work_dir: str | None,
    script_path: str | None,
    input_path: str | None,
) -> None:
    """Remove temporary files and directory. Errors are logged, not raised."""
    import shutil

    for path in (script_path, input_path):
        if path is not None:
            try:
                os.unlink(path)
            except OSError:
                pass

    if work_dir is not None:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def _extract_code_block(llm_response: str) -> str:
    """Extract Python code from an LLM response that may contain markdown fences.

    Handles: ```python ... ```, ```py ... ```, ``` ... ```, or raw code.
    If multiple code blocks exist, returns the largest one.
    """
    # Try to find fenced code blocks
    pattern = r'```(?:python|py)?\s*\n(.*?)```'
    matches = re.findall(pattern, llm_response, re.DOTALL)

    if matches:
        # Return the largest code block (most likely the actual script)
        return max(matches, key=len).strip()

    # No fences found; check if the entire response looks like Python code
    stripped = llm_response.strip()
    if stripped.startswith("import ") or stripped.startswith("# ") or stripped.startswith("from "):
        return stripped

    # Try removing any leading/trailing non-code text
    lines = stripped.split("\n")
    code_lines = []
    in_code = False
    for line in lines:
        if (
            line.strip().startswith(("import ", "from ", "def ", "class ", "#"))
            or line.strip() == ""
            or re.match(r'^\s', line)
        ):
            in_code = True
        if in_code:
            code_lines.append(line)

    if code_lines:
        return "\n".join(code_lines).strip()

    return stripped


async def _generate_script(
    client: OpenRouterClient,
    evidence_data: list[dict],
    preview_json: str,
    schema_description: str,
    analysis_question: str,
    research_context: str,
    error_feedback: str | None,
) -> str:
    """Generate a Python analysis script via the LLM.

    Args:
        client: OpenRouter LLM client.
        evidence_data: Full evidence data list (for metadata).
        preview_json: JSON preview of first N items.
        schema_description: Human-readable schema of the data.
        analysis_question: What the user wants to analyze.
        research_context: Topic context.
        error_feedback: If this is a retry, the error from the first attempt.

    Returns:
        Python script string, or empty string on failure.
    """
    error_section = ""
    if error_feedback:
        error_section = f"""
IMPORTANT: The previous script failed with this error:
{error_feedback}

Fix the error and generate a corrected script. Common issues:
- json.load(sys.stdin) fails if stdin is empty: wrap in try/except
- Missing import: ensure all used modules are imported
- Type errors: data values may be strings, not numbers; convert explicitly
- Index errors: check list lengths before indexing
"""

    prompt = f"""Write a Python data analysis script to answer this question:

QUESTION: {analysis_question}

RESEARCH CONTEXT: {research_context or "General research analysis"}

DATA SCHEMA (each item has these fields):
{schema_description}

DATA PREVIEW ({len(evidence_data)} total items, showing first {min(len(evidence_data), _DATA_PREVIEW_ITEMS)}):
{preview_json}
{error_section}
REQUIREMENTS:
1. Read input data from stdin: `import json, sys; data = json.load(sys.stdin)["data"]`
2. The question is also available: `question = json.load(sys.stdin)["question"]`
   (but read stdin only ONCE into a variable first)
3. Available imports: numpy, pandas, scipy, scipy.stats, matplotlib, json, sys, math,
   statistics, collections, re, datetime, itertools, functools, io, base64
4. DO NOT import: os, subprocess, socket, requests, or any network library
5. DO NOT use open(), exec(), eval(), or any file I/O
6. Set matplotlib backend: `import matplotlib; matplotlib.use('Agg')`
7. For charts: save to BytesIO, encode as base64 PNG:
   ```
   import io, base64
   buf = io.BytesIO()
   plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
   buf.seek(0)
   img_b64 = base64.b64encode(buf.read()).decode('utf-8')
   plt.close()
   ```
8. Output ONLY valid JSON to stdout via print(json.dumps(result)):
   {{
     "summary": "Brief text summary of findings",
     "statistics": {{"key": "value pairs of computed statistics"}},
     "charts": [{{"title": "Chart Title", "image_base64": "<base64 string>", "description": "What the chart shows"}}],
     "tables": [{{"headers": ["col1", "col2"], "rows": [["val1", "val2"]], "caption": "Table description"}}],
     "insights": ["Key finding 1", "Key finding 2", "Key finding 3"]
   }}
9. Handle missing/null values gracefully (skip or fill, do not crash)
10. Convert string values to numeric where needed (use try/except)
11. Do NOT call plt.show() — only save to buffer
12. Do NOT print anything except the final JSON output

Write ONLY the Python code. No explanations, no markdown formatting outside code."""

    system = (
        "You are a data analyst writing clean, self-contained Python scripts "
        "for scientific data analysis. Your scripts read JSON from stdin, "
        "perform analysis using pandas/numpy/scipy/matplotlib, and output "
        "results as JSON to stdout. Be thorough but handle errors gracefully. "
        "Output ONLY Python code."
    )

    try:
        response = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=4096,
            temperature=0.3,
        )

        raw_content = response.content.strip()
        if not raw_content:
            logger.warning(
                "[code_executor] LLM returned empty response for script generation"
            )
            return ""

        script = _extract_code_block(raw_content)

        if len(script) < 50:
            logger.warning(
                "[code_executor] Generated script too short (%d chars): %s",
                len(script),
                script[:100],
            )
            return ""

        # Validate before returning
        is_safe, reason = validate_script(script)
        if not is_safe:
            logger.warning(
                "[code_executor] Generated script failed validation: %s", reason
            )
            return ""

        return script

    except Exception as exc:
        logger.error(
            "[code_executor] Script generation failed: %s", str(exc)[:300]
        )
        return ""
