# 01 · Architecture: how the request actually flows

## The DNS request path, before Pi-hole

```
[Your laptop]                                  [ISP DNS]                [Authoritative]
     |                                              |                          |
     |  1. "what IP is doubleclick.net?"            |                          |
     |--------------------------------------------->|                          |
     |                                              |  2. recursive lookup     |
     |                                              |------------------------->|
     |                                              |                          |
     |                                              |<-------------------------|
     |                                              |     "8.7.198.46"         |
     |<---------------------------------------------|                          |
     |  3. "doubleclick.net is at 8.7.198.46"       |                          |
     |                                              |                          |
     |  4. opens TCP connection to 8.7.198.46                                  |
     |  5. tracker beacon fires                                                |
```

Your laptop trusts whatever DNS it was handed by DHCP. Every device on the LAN does the same independent lookup. None of it is logged (by you), none of it is filtered, and your ISP sees every domain.

## The DNS request path, with Pi-hole

```
[Your laptop]              [Pi-hole]              [unbound]            [Root → TLD → Auth]
     |                        |                       |                       |
     |  1. "doubleclick.net?" |                       |                       |
     |----------------------->|                       |                       |
     |                        |  2. on blocklist?     |                       |
     |                        |     YES → return      |                       |
     |                        |     0.0.0.0           |                       |
     |<-----------------------|                       |                       |
     |  3. "0.0.0.0"          |                       |                       |
     |                        |                       |                       |
     |  4. tries to connect to 0.0.0.0 → fails silently. No tracker fires.    |
```

For a domain that's NOT on a blocklist:

```
[Your laptop]              [Pi-hole]              [unbound]            [Root → TLD → Auth]
     |                        |                       |                       |
     |  1. "github.com?"      |                       |                       |
     |----------------------->|                       |                       |
     |                        |  2. not blocked.      |                       |
     |                        |     forward upstream  |                       |
     |                        |---------------------->|                       |
     |                        |                       |  3. recurse           |
     |                        |                       |---------------------->|
     |                        |                       |<----------------------|
     |                        |<----------------------|     "140.82.121.4"    |
     |<-----------------------|                       |                       |
     |  4. "140.82.121.4"     |                       |                       |
```

Two important details:

1. **unbound is a real recursive resolver running locally on the Pi.** It walks the DNS tree itself starting from the root servers. We are *not* forwarding to Cloudflare/Google in steady state — we use Cloudflare as an emergency fallback only. This means:
   - No upstream provider has a complete log of your queries
   - No dependency on a third party to function
   - Slightly higher latency on cache misses (one-time cost per domain)

2. **The browser doesn't know anything is being filtered.** It just gets `0.0.0.0` or NXDOMAIN. The same response a domain would give if it didn't exist. No fingerprintable signal of "I'm running an ad blocker."

## The component layout

```
┌─────────────────────────────────────────────┐
│  Raspberry Pi 5  (10.0.0.163)               │
│                                             │
│  ┌─────────────┐    ┌──────────────┐        │
│  │  Pi-hole    │───▶│   unbound    │───▶ Internet
│  │  (port 53)  │    │  (port 5335) │       (root DNS)
│  └──────┬──────┘    └──────────────┘        │
│         │                                   │
│         ▼                                   │
│  ┌─────────────┐                            │
│  │  lighttpd   │◀──── admin web UI          │
│  │  (port 80)  │                            │
│  └─────────────┘                            │
└─────────────────────────────────────────────┘
            ▲
            │ DNS queries from LAN
            │
   [Phones, laptops, smart TV, IoT...]
```

- **Pi-hole** binds port 53 (DNS) and answers queries from the LAN. Decides allow vs block.
- **unbound** binds 127.0.0.1:5335 — only Pi-hole can talk to it. Does the actual recursive resolution.
- **lighttpd** serves the admin web UI on port 80 of the Pi. (Set behind a password; consider a reverse proxy with TLS later.)

## Where blocklists come from

Pi-hole's "gravity" is a periodically-rebuilt SQLite database of domains-to-block. The default is the StevenBlack hosts list (~150k entries combining ads + malware + trackers). For production deployments, layering 4–8 lists from [firebog.net](https://v.firebog.net/hosts/lists.php?type=tick) gets you to ~750k entries with very low false-positive rates if you stick to the green-checkmarked lists.

The trade-off: more lists = more domains blocked = more false positives. We start with defaults, watch the dashboard, and add lists as we find their value.

## What about DoH / encrypted DNS?

Modern Firefox and Chrome can route DNS over HTTPS (DoH) to Cloudflare or NextDNS, bypassing the system resolver entirely. **This breaks Pi-hole.** Mitigations:

1. Disable DoH in the browser (effective for managed devices, not for guest devices)
2. Block DoH resolver IPs at the firewall (cat-and-mouse, not foolproof)
3. Run Pi-hole as a DoH endpoint itself so devices use it for encrypted DNS

For a home lab, just disable DoH in your browser settings. If a device on your LAN bypasses Pi-hole via DoH, you'll see "missing" queries when comparing browser activity vs. Pi-hole logs — that's diagnosable.

## Failure modes to plan for

| Failure | Consequence | Mitigation |
|---|---|---|
| Pi crashes / SD corruption | LAN has no DNS, nothing works | Router configured with secondary DNS (Cloudflare) |
| Pi-hole upgrade fails | Same | Snapshot config in `configs/`, test on Pi before promoting |
| unbound bug / outage | Pi-hole still works (falls back to upstream) | Pi-hole has Cloudflare as backup upstream |
| Blocklist false positive | One site doesn't load | Whitelist domain via UI |
| Local DNS poisoning attempt | Devices get malicious answers | DNSSEC validation in unbound |

The "lose all DNS" failure mode is real and must be designed against. We do this with **router-level redundancy**: the router hands out Pi-hole as primary DNS and Cloudflare as secondary. If Pi-hole stops responding, devices fall back automatically. We lose blocking during the outage but not connectivity.
