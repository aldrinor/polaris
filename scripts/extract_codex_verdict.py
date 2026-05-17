#!/usr/bin/env python3
"""Extract the slim verdict block from a raw ``codex exec`` transcript.

I-sec-001 (#535): per-issue Codex review artifacts must be committed as the
bounded §8.3.9 verdict block ONLY — never the full multi-MB transcript, which
routinely captures ``cat .env`` output and leaks credentials into git.

Subcommands:

  extract   Parse the final §8.3.9 verdict block out of a raw transcript,
            re-serialize it canonically (parse-then-emit, so NO trailing
            transcript text can survive), scan the result for secrets
            (shared pattern scanner + local ``.env`` value match), and write
            the slim artifact. Non-zero exit on any secret hit — the ship
            procedure then redacts before commit.

  validate  Confirm a committed file IS a schema-bounded slim verdict block
            (all 7 §8.3.9 keys, valid enums, byte-capped, no trailing
            content). Used by the CI .codex artifact gate; has NO ``.env``
            dependency so it runs identically on any runner.

Usage:
    python scripts/extract_codex_verdict.py extract <raw_transcript> --out <slim.txt>
    python scripts/extract_codex_verdict.py validate <slim.txt>
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# §8.3.9 verdict schema.
SCALAR_KEYS = ("verdict", "convergence_call")
LIST_KEYS = ("novel_p0", "continuing_p0", "p1", "p2",
             "remaining_blockers_for_execution")
ALL_KEYS = ("verdict", "novel_p0", "continuing_p0", "p1", "p2",
            "convergence_call", "remaining_blockers_for_execution")
VALID_VERDICT = {"APPROVE", "REQUEST_CHANGES"}
VALID_CONVERGENCE = {"continue", "accept_remaining"}

# A slim verdict artifact must never approach transcript size. A real verdict
# block is well under 2 KB; 8 KB leaves headroom for verbose findings while
# still being orders of magnitude below a raw transcript.
SLIM_BYTE_CAP = 8192

_KEY_RE = re.compile(
    r"^(?P<key>verdict|novel_p0|continuing_p0|p1|p2|"
    r"convergence_call|remaining_blockers_for_execution)\s*:\s*(?P<val>.*)$"
)
_ITEM_RE = re.compile(r"^\s*-\s?(?P<item>.*)$")


def parse_verdict_block(text: str) -> dict | None:
    """Find the LAST §8.3.9 verdict block in ``text`` and parse it to a dict.

    Returns None if no well-formed block is found. Parsing (not regex
    copy-through) is what guarantees the re-serialized output carries no
    trailing transcript text (I-sec-001 brief §3.1).
    """
    lines = text.splitlines()
    starts = []
    for i, ln in enumerate(lines):
        m = _KEY_RE.match(ln.strip())
        if m and m.group("key") == "verdict" and m.group("val").strip() in VALID_VERDICT:
            starts.append(i)
    if not starts:
        return None

    parsed: dict = {}
    current_list: str | None = None
    for ln in lines[starts[-1]:]:
        stripped = ln.strip()
        if not stripped:
            continue  # blank lines tolerated between keys
        if stripped.startswith("```"):
            break  # closing code fence ends the block
        km = _KEY_RE.match(stripped)
        if km:
            key, val = km.group("key"), km.group("val").strip()
            if key in parsed:
                break  # a repeated key → the block already ended
            if key in SCALAR_KEYS:
                parsed[key] = val
                current_list = None
            else:
                # list key: `[]` = inline-empty (no items follow);
                # anything else = items follow on subsequent `  - ` lines.
                parsed[key] = []
                current_list = None if val == "[]" else key
            continue
        im = _ITEM_RE.match(ln)
        if im is not None and current_list is not None:
            parsed[current_list].append(im.group("item").strip())
            continue
        if current_list and parsed.get(current_list) and ln.startswith((" ", "\t")):
            parsed[current_list][-1] = (
                parsed[current_list][-1] + " " + stripped).strip()
            continue
        break  # transcript prose → the block has ended

    if not all(k in parsed for k in ALL_KEYS):
        return None
    if parsed["verdict"] not in VALID_VERDICT:
        return None
    if parsed["convergence_call"] not in VALID_CONVERGENCE:
        return None
    return parsed


def serialize_verdict(d: dict) -> str:
    """Canonical re-serialization of a parsed verdict block (LF-terminated)."""
    out: list[str] = [f"verdict: {d['verdict']}"]
    for k in ("novel_p0", "continuing_p0", "p1", "p2"):
        items = d.get(k) or []
        if not items:
            out.append(f"{k}: []")
        else:
            out.append(f"{k}:")
            out.extend(f"  - {it}" for it in items)
    out.append(f"convergence_call: {d['convergence_call']}")
    rb = d.get("remaining_blockers_for_execution") or []
    if not rb:
        out.append("remaining_blockers_for_execution: []")
    else:
        out.append("remaining_blockers_for_execution:")
        out.extend(f"  - {it}" for it in rb)
    return "\n".join(out) + "\n"


def _load_env_secret_values(env_path: Path) -> list[str]:
    """Credential-shaped values from a local .env (values only, for substring
    matching — names dropped). Returns [] if .env is absent (e.g. on CI)."""
    if not env_path.is_file():
        return []
    secret_name = re.compile(r"(API_KEY|SECRET|TOKEN|PASSWORD|_KEY)$", re.I)
    vals: list[str] = []
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip().strip('"').strip("'")
        if (secret_name.search(k.strip()) and len(v) >= 20
                and not v.startswith(("http", "${", "/")) and " " not in v):
            vals.append(v)
    return vals


def scan_for_leaks(text: str, env_values: list[str]) -> list[str]:
    """Return leak descriptions — NEVER the secret value itself."""
    hits: list[str] = []
    scanner = _REPO_ROOT / "scripts" / "autoloop" / "scan_for_secrets.py"
    if scanner.is_file():
        with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(text)
            tmp = tf.name
        try:
            r = subprocess.run(
                [sys.executable, str(scanner), tmp, "--strict"],
                capture_output=True, text=True)
            if r.returncode != 0:
                hits.append("scan_for_secrets pattern match")
        finally:
            Path(tmp).unlink(missing_ok=True)
    for v in env_values:
        if v in text:
            hits.append("local .env credential value present in output")
            break
    return hits


def cmd_extract(raw_path: Path, out_path: Path) -> int:
    if not raw_path.is_file():
        print(f"extract_codex_verdict: raw transcript not found: {raw_path}",
              file=sys.stderr)
        return 2
    text = raw_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_verdict_block(text)
    if parsed is None:
        print("extract_codex_verdict: no well-formed verdict block found in "
              f"{raw_path}", file=sys.stderr)
        return 2
    slim = serialize_verdict(parsed)
    if len(slim.encode("utf-8")) > SLIM_BYTE_CAP:
        print(f"extract_codex_verdict: slim verdict exceeds {SLIM_BYTE_CAP}-byte "
              f"cap ({len(slim.encode('utf-8'))} B) — verdict prose too long",
              file=sys.stderr)
        return 3
    leaks = scan_for_leaks(slim, _load_env_secret_values(_REPO_ROOT / ".env"))
    if leaks:
        print("extract_codex_verdict: SECRET detected in extracted verdict — "
              f"NOT writing; redact before commit. {leaks}", file=sys.stderr)
        return 4
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(slim, encoding="utf-8", newline="\n")
    print(f"extract_codex_verdict: wrote slim verdict "
          f"({len(slim)} chars, {parsed['verdict']}) -> {out_path}")
    return 0


def cmd_validate(path: Path) -> int:
    """CI mode — confirm ``path`` IS a schema-bounded slim verdict. No .env."""
    if not path.is_file():
        print(f"validate: file not found: {path}", file=sys.stderr)
        return 2
    raw = path.read_bytes()
    if len(raw) > SLIM_BYTE_CAP:
        print(f"validate: {path} is {len(raw)} B (> {SLIM_BYTE_CAP}-byte slim "
              "cap) — looks like a raw transcript, not a slim verdict",
              file=sys.stderr)
        return 1
    text = raw.decode("utf-8", errors="replace")
    parsed = parse_verdict_block(text)
    if parsed is None:
        print(f"validate: {path} does not parse as a §8.3.9 verdict block",
              file=sys.stderr)
        return 1
    # Reject trailing transcript: the file must equal exactly one canonical
    # serialized block (CRLF-normalized so a CRLF checkout still round-trips).
    if text.replace("\r\n", "\n").strip() != serialize_verdict(parsed).strip():
        print(f"validate: {path} carries content beyond the verdict block "
              "(trailing transcript text or extra lines)", file=sys.stderr)
        return 1
    print(f"validate: {path} OK — schema-bounded slim verdict "
          f"({parsed['verdict']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("extract",
                        help="extract slim verdict from a raw transcript")
    pe.add_argument("raw_transcript")
    pe.add_argument("--out", required=True)
    pv = sub.add_parser(
        "validate", help="validate a file is a schema-bounded slim verdict")
    pv.add_argument("path")
    args = ap.parse_args()
    if args.cmd == "extract":
        return cmd_extract(Path(args.raw_transcript), Path(args.out))
    return cmd_validate(Path(args.path))


if __name__ == "__main__":
    sys.exit(main())
