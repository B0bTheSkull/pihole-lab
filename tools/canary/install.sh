#!/usr/bin/env bash
# Add canary domains to Pi-hole's local DNS as A records pointing at
# 192.0.2.1 (TEST-NET-1, RFC5737 — guaranteed unroutable). The point
# isn't where they resolve; it's that the lookup gets logged.
#
# Run on the Pi-hole host. Idempotent — re-running won't duplicate.
set -euo pipefail

LIST="${1:-$(dirname "$0")/canary_domains.list}"
SINK_IP="192.0.2.1"
HOSTS_FILE="/etc/pihole/custom.list"   # Pi-hole reads this for local DNS

if [[ ! -f "$LIST" ]]; then
    echo "[!] canary list not found: $LIST" >&2
    exit 2
fi

if [[ ! -w "$HOSTS_FILE" ]]; then
    echo "[!] need write access to $HOSTS_FILE — re-run with sudo" >&2
    exit 2
fi

added=0
while IFS= read -r line; do
    line="${line%%#*}"; line="${line//[[:space:]]/}"
    [[ -z "$line" ]] && continue
    entry="${SINK_IP} ${line}"
    if ! grep -qxF "$entry" "$HOSTS_FILE"; then
        echo "$entry" >> "$HOSTS_FILE"
        added=$((added+1))
    fi
done < "$LIST"

echo "[+] Added $added new canary entr$([[ $added -eq 1 ]] && echo y || echo ies)."
echo "[+] Reloading Pi-hole DNS…"
pihole restartdns reload-lists >/dev/null
echo "[+] Done. Confirm with: dig +short admin-portal.canary.lan @127.0.0.1"
