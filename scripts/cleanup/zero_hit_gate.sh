#!/usr/bin/env bash
# scripts/cleanup/zero_hit_gate.sh — CI-safe rename-completeness gate
# iter 11 CLEAN-BASH-VERSION-1 fix: requires Bash 4+ for associative arrays.
# Document hard runtime requirement.
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
    echo "ERROR: zero_hit_gate.sh requires Bash 4+ (assoc arrays). Got: $BASH_VERSION" >&2
    exit 64
fi
set -euo pipefail
PATTERN="$1"
# iter 11 CLEAN-GATE-ERRMASK-1 fix: explicit exit-code handling.
# git grep returns 0 on hits, 1 on no matches, 2+ on real errors (bad regex,
# bad pathspec, repo issue). Earlier `|| true` masked all failures including
# bad-pathspec false-passes. Now distinguish:
set +e
OUTPUT=$(git grep -n -E "$PATTERN" -- \
    ':!archive/' \
    ':!state/polaris_restart/' \
    ':!outputs/audits/' \
    ':!outputs/codex_findings/' \
    ':!.codex/_archive_pre_v6_2/' \
    ':!.codex/continuous/' \
    ':!.codex/round_*/' \
    ':!.codex/deep_dive_round_*/' \
    ':!logs/session_log.md' \
    ':!.legacy/' \
    2>&1)
RC=$?
set -e
case $RC in
    0) ;;          # hits found — process normally below
    1) OUTPUT="" ;;  # no matches — pass through as empty
    *)
        echo "ERROR: git grep failed (rc=$RC). Output: $OUTPUT" >&2
        exit $RC
        ;;
esac
# iter 8 CLEAN-GATE-COMMENT-2 fix: do NOT strip generic # lines.
# Markdown headings, multiline-string boundaries, YAML refs in comments,
# Python docstrings — none of these are "harmless" by virtue of starting with #.
# An old-name reference in a Markdown heading or a Python comment is STILL stale
# and STILL fails the rename-completeness gate. Codex iter 7 identified this:
# the iter 7 spec wrongly false-passed `^[^:]*:[0-9]+:[[:space:]]*#` lines.
#
# If a specific occurrence MUST be allowlisted (e.g., a literal historical
# string in a docs/file_directory.md table row that documents the rename), it
# must be added to a per-pattern allowlist file at `scripts/cleanup/gate_allowlists/<pattern>.txt`.
# iter 9 CLEAN-GATE-ALLOWLIST-1 fix: convention is `path:line:` (trailing colon) —
# matches the `git grep -n` output format `<path>:<line>:<content>` exactly.
# Each allowlist entry must include the trailing colon to anchor on the line boundary.
# PR-1 dryrun-iter-6 P2-002 fix: use printf to avoid echo's trailing newline,
# which `tr -c` would otherwise translate into a trailing underscore. Allowlist
# filenames documented as `<pattern_slug>.txt` would not match if the slug had
# an extra trailing underscore from the echo newline.
PATTERN_SLUG=$(printf '%s' "$PATTERN" | tr -c '[:alnum:]_' '_' | head -c 64)
ALLOWLIST_FILE="scripts/cleanup/gate_allowlists/${PATTERN_SLUG}.txt"
if [ -f "$ALLOWLIST_FILE" ]; then
    # iter 10 CLEAN-GATE-ALLOWLIST-ANCHOR-1 fix: anchored exact-prefix match.
    # Substring-style `grep -qF` would false-allow partial matches (e.g. allowlist
    # entry `path:5:` would match `path:50:` lines too). Use awk equality test
    # against `<path>:<lineno>:` exactly.
    # Allowlist file: each line is exactly `<path>:<lineno>:` with trailing colon.
    # Empty/comment lines (`^$|^#`) are ignored.
    declare -A ALLOWLIST_SET
    while IFS= read -r entry; do
        [[ -z "$entry" || "$entry" =~ ^# ]] && continue
        ALLOWLIST_SET["$entry"]=1
    done < "$ALLOWLIST_FILE"
    FILTERED=""
    while IFS= read -r line; do
        # Each grep -n line: <path>:<lineno>:<content>
        prefix=$(echo "$line" | awk -F: '{print $1":"$2":"}')
        if [[ -z "${ALLOWLIST_SET[$prefix]:-}" ]]; then
            FILTERED+="$line"$'\n'
        fi
    done <<< "$OUTPUT"
else
    FILTERED="$OUTPUT"
fi
if [ -n "${FILTERED//[[:space:]]/}" ]; then
    echo "REFS REMAIN — gate fails:" >&2
    echo "$FILTERED" >&2
    if [ -f "$ALLOWLIST_FILE" ]; then
        echo "(Per-pattern allowlist consulted: $ALLOWLIST_FILE)" >&2
    fi
    exit 1
fi
exit 0
