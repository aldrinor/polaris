#!/bin/bash
# I-carney-008 iter-3 — runtime egress tightening pass.
#
# After first `docker compose build` succeeds, this script:
#   1. copies config/egress_allowlist.txt → /etc/polaris/egress_allowlist.txt
#   2. strips the build-time block (everything between the "BUILD-TIME ONLY"
#      banner and the "I-carney-008: AWS-specific endpoints" banner)
#   3. sets /etc/polaris/runtime_pruned.flag so /transparency can report it
#   4. re-runs egress_lockdown.sh to install the tightened ruleset
#
# Codex iter-2 P2-2: prevents shipping with US-corp build hosts in the
# RUNTIME allowlist.

set -eo pipefail

SRC="${POLARIS_REPO_PATH:-/opt/polaris}/config/egress_allowlist.txt"
DST="/etc/polaris/egress_allowlist.txt"
FLAG="/etc/polaris/runtime_pruned.flag"

if [ "$(id -u)" -ne 0 ]; then
    echo "[runtime-tighten] ERROR: must run as root" >&2
    exit 1
fi
if [ ! -f "$SRC" ]; then
    echo "[runtime-tighten] ERROR: source allowlist not found at $SRC" >&2
    exit 1
fi

mkdir -p /etc/polaris
chmod 750 /etc/polaris

# Strip the build-time block. The block is delimited by:
#   start: "# ----- BUILD-TIME ONLY"
#   end:   "# I-carney-008: AWS-specific endpoints"  (exclusive of this line)
awk '
    /^# ----- BUILD-TIME ONLY/ { in_block=1; next }
    /^# I-carney-008: AWS-specific endpoints/ { in_block=0 }
    !in_block
' "$SRC" > "$DST.tmp"

# Sanity check: pruned file must NOT contain github.com or pypi.org lines.
if grep -qE '^(github\.com|pypi\.org|registry-1\.docker\.io|registry\.npmjs\.org)$' "$DST.tmp"; then
    echo "[runtime-tighten] ERROR: pruning did not remove build-time hosts; aborting" >&2
    rm -f "$DST.tmp"
    exit 1
fi

mv "$DST.tmp" "$DST"
chmod 644 "$DST"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$FLAG"
chmod 644 "$FLAG"

echo "[runtime-tighten] /etc/polaris/egress_allowlist.txt is tightened"
echo "[runtime-tighten] /etc/polaris/runtime_pruned.flag = $(cat $FLAG)"
echo "[runtime-tighten] re-applying iptables/ip6tables lockdown..."

bash "${POLARIS_REPO_PATH:-/opt/polaris}/scripts/egress_lockdown.sh"

echo "[runtime-tighten] done. /transparency build_time_hosts_pruned=true on next request."
