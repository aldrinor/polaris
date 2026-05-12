"""
Parse Codex findings frontmatter into loop_state.json-ready dict.

Expects findings.md to START with a YAML frontmatter block like:

    ---
    verdict: READY | NOT_READY | CONDITIONAL
    blocker_count: 0
    medium_count: 2
    rationale: |
      Free-form rationale (may span lines).
    ---

Emits JSON to stdout (or to a specified path). Never raises — always
emits a dict, even on parse failure, so the loop orchestrator can
decide what to do with malformed Codex output.

Usage:
    python scripts/codex_loop_parse.py <findings.md>
    python scripts/codex_loop_parse.py <findings.md> --out <verdict.json>
(Historical `.codex/round_*/` paths archived by I-hygiene-001 GH#432; use
the issue-driven `.codex/I-<prefix>-NNN/` layout for new findings.)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_FRONTMATTER_RE = re.compile(
    r"^\s*---\s*\n(.*?)\n\s*---\s*(?:\n|$)",
    re.DOTALL,
)


def _yaml_parse_minimal(text: str) -> dict:
    """Very small YAML-like parser: top-level key:value pairs + block
    scalars (`key: |`). Avoids a PyYAML dependency in the loop harness.
    """
    result: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(\w[\w_]*)\s*:\s*(\|)?\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, block_marker, rest = m.group(1), m.group(2), m.group(3)
        if block_marker == "|":
            # Block scalar: subsequent indented lines
            buf: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt.startswith(" ") or not nxt.strip():
                    buf.append(nxt.lstrip())
                    i += 1
                else:
                    break
            result[key] = "\n".join(buf).strip()
            continue
        result[key] = rest.strip().strip("'\"")
        i += 1
    return result


def parse_findings(path: Path) -> dict:
    out: dict = {
        "verdict": "UNKNOWN",
        "blocker_count": None,
        "medium_count": None,
        "rationale": "",
        "parse_ok": False,
        "error": "",
        "path": str(path),
    }
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        out["error"] = f"not_found:{path}"
        return out
    except Exception as exc:
        out["error"] = f"read_error:{exc}"
        return out

    m = _FRONTMATTER_RE.match(text)
    if not m:
        out["error"] = "no_frontmatter"
        # Fallback: try to find `verdict:` anywhere near the top
        first_200 = text[:2000]
        fallback_m = re.search(
            r"verdict\s*:\s*(READY|NOT_READY|CONDITIONAL|UNKNOWN)",
            first_200, re.IGNORECASE,
        )
        if fallback_m:
            out["verdict"] = fallback_m.group(1).upper()
        return out

    fm_text = m.group(1)
    parsed = _yaml_parse_minimal(fm_text)

    verdict_raw = (parsed.get("verdict") or "").strip().upper()
    if verdict_raw in {"READY", "NOT_READY", "CONDITIONAL"}:
        out["verdict"] = verdict_raw
    else:
        out["verdict"] = "UNKNOWN"
        out["error"] = f"unexpected_verdict:{verdict_raw!r}"

    for int_key in ("blocker_count", "medium_count"):
        raw = parsed.get(int_key, "")
        try:
            out[int_key] = int(str(raw).strip())
        except Exception:
            out[int_key] = None

    out["rationale"] = parsed.get("rationale", "") or ""
    out["parse_ok"] = bool(
        out["verdict"] in {"READY", "NOT_READY", "CONDITIONAL"}
        and out["blocker_count"] is not None
        and out["medium_count"] is not None
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("findings_path")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    result = parse_findings(Path(args.findings_path))
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out == "-":
        sys.stdout.write(payload)
    else:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
