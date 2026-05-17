#!/usr/bin/env python3
"""POLARIS secret-pattern scanner — Plan v13 §C-scan.

Scans verdict-rerun output (and proxy logs) for credential exfiltration
patterns. Used by GitHub Actions verdict-validate job; runs on scrubbed
output BEFORE artifact publish.

Per Codex round-9 review: covers documented exfil targets including
OpenAI/Anthropic/GitHub/AWS/GCP/Slack/Stripe/PEM/Bearer-auth/basic-auth.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Compiled patterns. Each is (regex, friendly_name).
SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # OpenAI (sk-, sk-admin-, sk-proj-, sk-svcacct-)
    (re.compile(r"sk-(?:admin|proj|svcacct)?-?[A-Za-z0-9_-]{20,}"), "openai_api_key"),
    # Anthropic
    (re.compile(r"sk-ant-(?:api|admin)\d+-[A-Za-z0-9_-]{20,}"), "anthropic_api_key"),
    # GitHub PATs / tokens
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"), "github_token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github_pat"),
    # AWS access key IDs (long-lived + temporary)
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "aws_key_id"),
    # GitLab
    (re.compile(r"glpat-[A-Za-z0-9_-]{20,}"), "gitlab_pat"),
    # Hugging Face
    (re.compile(r"hf_[A-Za-z0-9]{30,}"), "huggingface_token"),
    # NPM
    (re.compile(r"npm_[A-Za-z0-9]{30,}"), "npm_token"),
    # PyPI
    (re.compile(r"pypi-[A-Za-z0-9_-]{30,}"), "pypi_token"),
    # Slack
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"), "slack_token"),
    # Google
    (re.compile(r"AIza[A-Za-z0-9_-]{30,}"), "google_api_key"),
    (re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"), "google_oauth"),
    # Stripe
    (re.compile(r"sk_live_[A-Za-z0-9]{20,}"), "stripe_secret"),
    (re.compile(r"rk_live_[A-Za-z0-9]{20,}"), "stripe_restricted"),
    # PEM blocks (covers RSA, EC, OPENSSH, DSA, PGP)
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "pem_private_key"),
    (re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"), "openssh_private_key"),
    # Generic bearer / basic auth
    (re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE), "bearer_token"),
    (re.compile(r"https?://[^:\s]+:[^@\s]+@"), "basic_auth_url"),
    # I-sec-001 (#535): vendor keys missed by the original list — these are
    # exactly the shapes that leaked into committed .codex/ transcripts and
    # were not caught by GitHub push protection either.
    (re.compile(r"jina_[A-Za-z0-9_]{20,}"), "jina_api_key"),
    (re.compile(r"\bfc-[A-Za-z0-9]{20,}\b"), "firecrawl_api_key"),
    (re.compile(r"\bfw_[A-Za-z0-9]{20,}"), "fireworks_api_key"),
    # Configured POLARIS .env secret-var NAME followed by a key-shaped value —
    # a vendor-agnostic catch for a `.env` dump (Exa / Semantic-Scholar / Vast
    # and any future credential have no distinctive value prefix).
    (re.compile(
        r"(?i)\b(?:JINA_API_KEY|EXA_API_KEY|FIRECRAWL_API_KEY|FIREWORKS_API_KEY"
        r"|GEMINI_API_KEY|SEMANTIC_SCHOLAR_API_KEY|VAST_API_KEY"
        r"|OPENROUTER_API_KEY|OPEN_PAGERANK_API_KEY|NCBI_API_KEY"
        r"|OVH_APPLICATION_KEY|OVH_APPLICATION_SECRET|OVH_CONSUMER_KEY"
        r"|POLARIS_AUTH_SECRET|POLARIS_JWT_SECRET)"
        r"""\s*[:=]\s*["']?[A-Za-z0-9._/+~=-]{20,}"""),
     "configured_secret_assignment"),
]


def scan(path: Path) -> list[dict]:
    text = path.read_text(errors="replace")
    hits = []
    for pattern, name in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            hits.append({
                "pattern": name,
                "match_prefix": value[:8] + "...(redacted)",
                "match_length": len(value),
                "file": str(path),
                "offset": match.start(),
            })
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Files to scan")
    parser.add_argument("--strict", action="store_true",
                       help="Exit 1 on any match (default: exit 0 with stderr report)")
    args = parser.parse_args()

    all_hits = []
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            print(f"scan_for_secrets: WARN file missing {p}", file=sys.stderr)
            continue
        all_hits.extend(scan(path))

    if all_hits:
        print(json.dumps({"secrets_detected": all_hits}, indent=2), file=sys.stderr)
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
