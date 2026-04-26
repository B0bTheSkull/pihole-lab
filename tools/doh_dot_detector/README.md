# DoH / DoT egress detector

Pi-hole only sees DNS that comes to it. A device that has hardcoded
DoH (DNS-over-HTTPS) or DoT (DNS-over-TLS) — Firefox with "Use
Cloudflare", a smart TV, a phone in private-relay mode — punches a
hole right through your network policy.

This tool does two things:

1. **Blocks the obvious endpoints** at the DNS layer (`blocklist_doh_dot.txt`).
   Once they're sinkholed, the client either falls back to system
   DNS (good — Pi-hole sees it) or breaks (also good — now you know
   it's there).
2. **Detects which clients tried.** `detect_doh_attempts.py` scans
   the FTL database for queries to those endpoints and prints the
   guilty IPs.

## Install the blocklist on Pi-hole

The cleanest way is to host this file somewhere reachable by the Pi
(GitHub raw URL works) and add it as an adlist:

```bash
pihole -a adlist add https://raw.githubusercontent.com/B0bTheSkull/pihole-lab/main/tools/doh_dot_detector/blocklist_doh_dot.txt
pihole -g     # rebuild gravity
```

Or, for a one-shot manual block:

```bash
grep -vE '^(#|$)' blocklist_doh_dot.txt | xargs -I{} pihole -b -nr -domainonly {}
```

## Run the detector

On the Pi (where the DB lives):

```bash
sudo python3 detect_doh_attempts.py --hours 24
```

From another host (after `scp`ing the DB or mounting it via SSHFS):

```bash
python3 detect_doh_attempts.py --db ./pihole-FTL.db --hours 24
```

Add `--json` to feed the output into another tool, or wire it into cron:

```cron
# /etc/cron.d/doh-watch
0 * * * * pihole /usr/local/bin/detect_doh_attempts.py --hours 1 --threshold 5 \\
    || logger -t doh-watch "DoH/DoT bypass attempt detected"
```

## Why this matters

A residential network with Pi-hole and *no* DoH blocking is mostly
theatre — anything modern phones home over 443 with hardcoded
resolvers. Blocking the bootstrap hostnames forces clients back onto
your resolver, which is the only place you have visibility.

The detector matters more than the blocklist: even after blocking,
the *attempt* is the signal. A device that retries `dns.google` 200
times an hour is worth a name and a deeper look.
