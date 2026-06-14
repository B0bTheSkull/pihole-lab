#!/bin/bash
# Run after a Nord reconnect that "broke everything". Tells us exactly which layer is broken.

echo "=== /etc/resolv.conf right now ==="
cat /etc/resolv.conf
echo
echo "=== is it still immutable? (need 'i' in flags) ==="
lsattr /etc/resolv.conf 2>&1
echo
echo "=== ping Pi-hole on LAN (does basic connectivity to it work?) ==="
ping -c2 -W2 10.0.0.163
echo
echo "=== dig directly at Pi-hole (bypasses libc resolv.conf) ==="
dig @10.0.0.163 example.com +short +time=2
dig @10.0.0.163 doubleclick.net +short +time=2
echo
echo "=== dig via system resolver (libc reads /etc/resolv.conf) ==="
dig example.com +short +time=2
dig doubleclick.net +short +time=2
echo
echo "=== which server actually answered the system resolver? ==="
dig example.com | grep "SERVER:"
echo
echo "=== nord-installed iptables rules on port 53 (looking for DNAT/REDIRECT to Nord's resolver) ==="
sudo iptables -t nat -S OUTPUT 2>/dev/null | grep -E "53|dport.*53" | head -20
sudo iptables -S OUTPUT 2>/dev/null | grep -E "dport 53|--dport.*53" | head -20
echo
echo "=== nord's killswitch state ==="
nordvpn settings | grep -E "Kill|Firewall|DNS|Allowlist" -A2
echo
echo "=== ip route (where does default go? where does 10.0.0.163 go?) ==="
ip route get 10.0.0.163
ip route get 1.1.1.1
echo
echo "=== systemd-resolved status (should be inactive) ==="
systemctl is-active systemd-resolved
