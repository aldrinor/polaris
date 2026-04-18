"""
Extract every env var referenced by live code under src/ + scripts/,
group by prefix, write a curated inventory to
docs/pipeline_audit_context/08_env_var_inventory.md.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"

# Match os.environ["X"], os.environ.get("X"), os.getenv("X")
ENV_RE = re.compile(
    r"""os\.(?:environ(?:\.get)?|getenv)\s*(?:\[|\()\s*["']([A-Z][A-Z0-9_]*)["']"""
)


def extract_vars() -> dict[str, list[tuple[Path, int]]]:
    """Return {var_name: [(file_path, line_number), ...]}"""
    hits: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for base in (SRC, SCRIPTS):
        for py in base.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for ln_idx, line in enumerate(lines, 1):
                for m in ENV_RE.finditer(line):
                    hits[m.group(1)].append((py, ln_idx))
    return dict(hits)


def group_by_prefix(vars_: dict[str, list]) -> dict[str, dict[str, list]]:
    groups: dict[str, dict[str, list]] = defaultdict(dict)
    for name, uses in sorted(vars_.items()):
        if name.startswith("PG_"):
            prefix = "PG_* (pipeline A and shared)"
        elif name.startswith("POLARIS_"):
            prefix = "POLARIS_* (pipeline B UI + deployment)"
        elif name.startswith("OPENROUTER_"):
            prefix = "OPENROUTER_* (LLM gateway)"
        elif name.startswith("OPENAI_"):
            prefix = "OPENAI_* (OpenAI SDK)"
        elif name.startswith("POLARIS_") or name.startswith("PW_"):
            prefix = "PW_* (Playwright visual tests)"
        elif name.startswith("VQA_"):
            prefix = "VQA_* (visual QA tests)"
        elif name.startswith("FIRECRAWL_"):
            prefix = "FIRECRAWL_* (Firecrawl API)"
        elif name.startswith("EXA_") or name.startswith("PG_EXA_"):
            prefix = "EXA_* (Exa search)"
        elif name.startswith("JINA_") or name.startswith("PG_JINA_"):
            prefix = "JINA_* (Jina Reader)"
        elif name.startswith("VLLM_") or name.startswith("OLLAMA_"):
            prefix = "Local LLM (sovereign mode)"
        elif name.endswith("_API_KEY") or "KEY" in name:
            prefix = "API KEYS / secrets"
        else:
            prefix = "OTHER"
        groups[prefix][name] = uses
    return groups


def write_inventory():
    vars_ = extract_vars()
    groups = group_by_prefix(vars_)
    total = sum(len(g) for g in groups.values())
    out = ROOT / "docs" / "pipeline_audit_context" / "08_env_var_inventory.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("# Environment variable inventory\n\n")
        f.write(
            f"Auto-generated from a static AST scan of `src/` + `scripts/` "
            f"on 2026-04-18. **{total} total env vars referenced** across "
            f"{len(list(SRC.rglob('*.py'))) + len(list(SCRIPTS.rglob('*.py')))} "
            f".py files. Produced by `scripts/produce_env_var_inventory.py`.\n\n"
        )
        f.write(
            "**Scope**: any `os.getenv(...)`, `os.environ[...]`, "
            "`os.environ.get(...)` with a literal string name. "
            "Dynamic env-var construction (f-strings, concatenation) is "
            "not captured here.\n\n"
        )
        f.write("## Summary by prefix\n\n")
        f.write("| Prefix | Count |\n|---|---|\n")
        for prefix in sorted(groups.keys()):
            f.write(f"| {prefix} | {len(groups[prefix])} |\n")
        f.write("\n---\n\n")

        for prefix in sorted(groups.keys()):
            f.write(f"## {prefix}\n\n")
            f.write("| Variable | First referenced at |\n|---|---|\n")
            for name, uses in sorted(groups[prefix].items()):
                first = uses[0]
                rel = first[0].relative_to(ROOT).as_posix()
                f.write(f"| `{name}` | `{rel}:{first[1]}` |\n")
            f.write("\n")

        f.write("---\n\n## Caveats\n\n")
        f.write(
            "- Only literal-string env vars are captured. "
            "`os.getenv(f\"PG_{x}_TIMEOUT\")` is invisible.\n"
            "- A variable referenced in multiple files shows only the "
            "FIRST occurrence. For full usage map, regenerate with a "
            "more detailed collector.\n"
            "- Pipeline membership (A vs B) is inferred from file path. "
            "Variables referenced in files shared across pipelines "
            "appear under whichever pipeline's file they're found first.\n"
        )
    print(f"Wrote {out}")
    print(f"Total vars: {total}")
    return total


if __name__ == "__main__":
    write_inventory()
