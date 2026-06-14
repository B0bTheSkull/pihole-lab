#!/bin/bash
# Bulletproof Pi-hole DNS even with NordVPN's nordlynx hijack.
# Strategy: take resolv.conf away from NetworkManager + systemd-resolved
# and pin it statically at Pi-hole. Nord can mangle per-link DNS all it wants;
# libc reads the static file and goes to Pi-hole directly.

set -e

PIHOLE_IP="10.0.0.163"

echo "=== removing the old dispatcher (we don't need it anymore) ==="
sudo rm -f /etc/NetworkManager/dispatcher.d/90-nordlynx-dns

echo "=== telling NetworkManager not to manage /etc/resolv.conf ==="
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/90-dns-none.conf >/dev/null <<EOF
[main]
dns=none
systemd-resolved=false
EOF

echo "=== disabling systemd-resolved stub (so it stops owning 127.0.0.53) ==="
sudo systemctl disable --now systemd-resolved 2>/dev/null || true

echo "=== writing static /etc/resolv.conf -> Pi-hole ==="
# /etc/resolv.conf may be a symlink to systemd-resolved's stub-resolv.conf; nuke it.
sudo rm -f /etc/resolv.conf
sudo tee /etc/resolv.conf >/dev/null <<EOF
# Managed manually. Do not let NetworkManager or systemd-resolved touch this.
nameserver $PIHOLE_IP
options edns0 trust-ad timeout:2 attempts:2
EOF
# chattr +i to make it immutable so Nord/NM/etc can't rewrite it
sudo chattr +i /etc/resolv.conf 2>/dev/null || echo "(chattr unavailable, file may be rewritten on reboot — re-run script if so)"

echo "=== reloading NetworkManager ==="
sudo systemctl reload NetworkManager || sudo systemctl restart NetworkManager
sleep 2

echo "=== reconnecting Nord so we test under the actual hijack conditions ==="
nordvpn disconnect >/dev/null 2>&1 || true
sleep 1
nordvpn connect
sleep 4

echo
echo "=========================="
echo "=== verification ==="
echo "=========================="
echo "--- /etc/resolv.conf ---"
cat /etc/resolv.conf
echo "--- nord status ---"
nordvpn status | head -5
echo "--- dig (expect 0.0.0.0 then real IPs) ---"
dig doubleclick.net +short
dig ad.doubleclick.net +short
dig example.com +short
echo "--- which server answered? ---"
dig example.com | grep "SERVER:"
echo
echo "If doubleclick returned 0.0.0.0 -> Pi-hole is winning. Done."
echo "To undo this later: sudo chattr -i /etc/resolv.conf && sudo systemctl enable --now systemd-resolved && sudo rm /etc/NetworkManager/conf.d/90-dns-none.conf && sudo systemctl restart NetworkManager"
