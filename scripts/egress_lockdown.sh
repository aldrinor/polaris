#!/bin/bash
# I-carney-003 — install iptables egress lockdown on the host.
# I-carney-008 iter-3 — IPv6 (ip6tables) parity added per Codex P1-2.
#
# Reads /etc/polaris/egress_allowlist.txt and installs rules in BOTH OUTPUT
# (host) and DOCKER-USER (container forwarded traffic) chains so neither
# host nor containers can reach off-allowlist destinations on 80/443.
#
# Both IPv4 (iptables) AND IPv6 (ip6tables) chains are installed in parallel
# because Vexxhost VMs default to dual-stack. An IPv4-only lockdown would
# leak HTTPS over IPv6.
#
# Idempotent: flushes the POLARIS_EGRESS_HOST + POLARIS_EGRESS_DOCKER chains
# before reapplying. Per Codex iter-2 P1-003: covers BOTH host outbound
# AND Docker-bridge-forwarded container traffic.
#
# Run AFTER the first `docker compose build` (build-time hosts in
# config/egress_allowlist.txt are deb.debian.org / pypi.org / etc).

set -eo pipefail

ALLOWLIST_PATH="${POLARIS_EGRESS_ALLOWLIST:-/etc/polaris/egress_allowlist.txt}"
LOG_FILE="${POLARIS_EGRESS_LOG:-/var/log/polaris-egress.log}"

if [ ! -f "$ALLOWLIST_PATH" ]; then
    echo "[egress] ERROR: allowlist file not found at $ALLOWLIST_PATH" >&2
    echo "[egress] copy config/egress_allowlist.txt → $ALLOWLIST_PATH first" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "[egress] ERROR: must run as root (uses iptables + ip6tables)" >&2
    exit 1
fi

log() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$ts] $*" | tee -a "$LOG_FILE"
}

# Resolve allowlist domains to unique A records (IPv4).
resolve_allowlist_v4() {
    local domain ip
    while IFS= read -r domain; do
        # Skip blanks + comments.
        [[ -z "$domain" || "$domain" =~ ^# ]] && continue
        while IFS= read -r ip; do
            [ -n "$ip" ] && echo "$ip"
        done < <(getent ahostsv4 "$domain" 2>/dev/null | awk '{print $1}' | sort -u)
    done < "$ALLOWLIST_PATH" | sort -u
}

# Resolve allowlist domains to unique AAAA records (IPv6).
resolve_allowlist_v6() {
    local domain ip
    while IFS= read -r domain; do
        [[ -z "$domain" || "$domain" =~ ^# ]] && continue
        while IFS= read -r ip; do
            [ -n "$ip" ] && echo "$ip"
        done < <(getent ahostsv6 "$domain" 2>/dev/null | awk '{print $1}' | sort -u)
    done < "$ALLOWLIST_PATH" | sort -u
}

# Install one chain (IPv4 or IPv6) into parent.
# $1 = chain name, $2 = parent chain, $3 = resolved IPs, $4 = iptables binary.
install_chain() {
    local chain_name="$1"
    local parent_chain="$2"
    local resolved="$3"
    local ipt="$4"

    log "installing chain $chain_name into $parent_chain ($ipt)"

    # (Re)create the chain.
    "$ipt" -F "$chain_name" 2>/dev/null || "$ipt" -N "$chain_name"

    # Allow loopback + established + related.
    "$ipt" -A "$chain_name" -o lo -j ACCEPT || true
    "$ipt" -A "$chain_name" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    # Allow DNS (53), NTP (123).
    "$ipt" -A "$chain_name" -p udp --dport 53 -j ACCEPT
    "$ipt" -A "$chain_name" -p tcp --dport 53 -j ACCEPT
    "$ipt" -A "$chain_name" -p udp --dport 123 -j ACCEPT

    # Allow link-local cloud metadata. 169.254.169.254/32 for IPv4, fe80::/10
    # for IPv6 link-local block. OpenStack on Vexxhost emits cloud-init via
    # the IPv4 metadata endpoint; IPv6 link-local stays permissive for ND/RA.
    if [ "$ipt" = "iptables" ]; then
        "$ipt" -A "$chain_name" -d 169.254.169.254/32 -j ACCEPT
    else
        "$ipt" -A "$chain_name" -d fe80::/10 -j ACCEPT
    fi

    # Allow allowlisted IPs on 443 + 80.
    while IFS= read -r ip; do
        [ -z "$ip" ] && continue
        "$ipt" -A "$chain_name" -d "$ip" -p tcp --dport 443 -j ACCEPT
        "$ipt" -A "$chain_name" -d "$ip" -p tcp --dport 80 -j ACCEPT
    done <<< "$resolved"

    # Drop everything else on 80/443.
    "$ipt" -A "$chain_name" -p tcp --dport 443 -j LOG --log-prefix "[POLARIS-EGRESS-DROP] "
    "$ipt" -A "$chain_name" -p tcp --dport 443 -j DROP
    "$ipt" -A "$chain_name" -p tcp --dport 80 -j LOG --log-prefix "[POLARIS-EGRESS-DROP] "
    "$ipt" -A "$chain_name" -p tcp --dport 80 -j DROP

    # Wire the chain into the parent if not already done.
    if ! "$ipt" -C "$parent_chain" -j "$chain_name" 2>/dev/null; then
        "$ipt" -I "$parent_chain" 1 -j "$chain_name"
    fi

    log "chain $chain_name ($ipt) installed with $(echo "$resolved" | grep -c -v '^$') allowed IPs"
}

main() {
    log "egress lockdown starting (allowlist=$ALLOWLIST_PATH)"
    local resolved_v4 resolved_v6
    resolved_v4=$(resolve_allowlist_v4)
    resolved_v6=$(resolve_allowlist_v6)
    if [ -z "$resolved_v4" ] && [ -z "$resolved_v6" ]; then
        echo "[egress] ERROR: allowlist resolved to zero IPs (v4 AND v6)" >&2
        exit 1
    fi
    if [ -z "$resolved_v4" ]; then
        log "WARN: zero IPv4 resolutions from allowlist — IPv4 lockdown will drop everything"
    fi
    if [ -z "$resolved_v6" ]; then
        log "WARN: zero IPv6 resolutions from allowlist — IPv6 lockdown will drop everything"
    fi

    # ---- IPv4 ----
    install_chain "POLARIS_EGRESS_HOST" "OUTPUT" "$resolved_v4" "iptables"
    if ! iptables -L DOCKER-USER >/dev/null 2>&1; then
        iptables -N DOCKER-USER 2>/dev/null || true
        iptables -I FORWARD 1 -j DOCKER-USER 2>/dev/null || true
    fi
    install_chain "POLARIS_EGRESS_DOCKER" "DOCKER-USER" "$resolved_v4" "iptables"

    # ---- IPv6 ----
    # ip6tables must be present (default on Ubuntu 24.04). If not, fail
    # loudly rather than leak.
    if ! command -v ip6tables >/dev/null 2>&1; then
        echo "[egress] ERROR: ip6tables not found; IPv6 leak would occur. Install iptables-persistent or disable IPv6." >&2
        exit 1
    fi
    install_chain "POLARIS_EGRESS_HOST_V6" "OUTPUT" "$resolved_v6" "ip6tables"
    if ! ip6tables -L DOCKER-USER >/dev/null 2>&1; then
        ip6tables -N DOCKER-USER 2>/dev/null || true
        ip6tables -I FORWARD 1 -j DOCKER-USER 2>/dev/null || true
    fi
    install_chain "POLARIS_EGRESS_DOCKER_V6" "DOCKER-USER" "$resolved_v6" "ip6tables"

    log "egress lockdown complete (IPv4 + IPv6)"
}

main "$@"
