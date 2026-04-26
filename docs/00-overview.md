# 00 · Overview: why network-level DNS filtering

## DNS is the soft underbelly of every connection

Before your browser ever opens a TCP connection to a tracker, it asks: *"what IP is `doubleclick.net`?"* That question is a **DNS query**, and it goes to whatever resolver your machine is configured to use — usually whatever your router handed out via DHCP, which in turn is usually whatever your ISP runs.

This means a few things most people never think about:

1. **Every site you visit is observed by your DNS provider** — the resolver sees every domain you look up, even for HTTPS sites where the *content* is encrypted. The destination is in plaintext until DoH/DoT is in play, which most home networks don't enforce.
2. **DNS is a control plane** — if you can answer "what IP is `doubleclick.net`?" with `0.0.0.0`, the connection never happens. No HTTP request, no tracker fired, no JavaScript loaded. The browser thinks the host is unreachable and moves on.
3. **It's network-wide** — every device on the LAN that uses your DNS gets the same protection. Phones, smart TVs, the kid's tablet, the IoT toaster. No browser extensions to install per-device.

This is the core insight Pi-hole leverages.

## What Pi-hole is, in one sentence

Pi-hole is a DNS resolver that returns NXDOMAIN (or 0.0.0.0) for domains on a blocklist, and forwards everything else to a real upstream resolver.

That's it. The magic is in scope (network-wide), maintainability (curated blocklists update automatically), and observability (you get a dashboard showing every query made by every device).

## What it actually blocks

The default and community blocklists target:

- **Ad networks** — DoubleClick, AdSense, AppNexus, Taboola, etc.
- **Behavioral trackers** — analytics pixels, fingerprinting libraries, retargeting beacons
- **Telemetry endpoints** — phoning-home from operating systems, smart TVs, "smart" appliances
- **Malware C2 / phishing domains** — community-curated threat intel feeds
- **Cryptominers** — JS miners that try to use your CPU when you visit a sketchy page

It does **not** block:

- Anything embedded in the same domain as the content (first-party tracking)
- DoH (DNS-over-HTTPS) traffic that bypasses the system resolver — modern Chrome/Firefox can do this
- Tracking that uses raw IP addresses instead of domains (rare)

These limits are why DNS filtering is **one layer**, not the whole answer. Combined with HTTPS-only browsers, content-blocking extensions, and good DNS-over-HTTPS hygiene, it's a strong foundation. Alone, it's a meaningful improvement but not a fortress.

## Why this matters from a blue-team perspective

DNS is one of the highest-signal observation points on a network. Almost every modern attack — phishing, malware C2, data exfiltration, supply-chain compromise — touches DNS at some point. Owning your network's resolver means:

- **Visibility:** every query is logged, attributable to a client IP. Deviations from normal patterns are detectable.
- **Sinkholing:** new threat intel can be applied immediately by appending domains to a blocklist.
- **Defense-in-depth:** even if a malware sample gets executed, if its hardcoded C2 domain resolves to `0.0.0.0`, the attacker has lost.

Enterprise tools that do this exist (Cisco Umbrella, Infoblox, NextDNS Pro). Pi-hole is the open-source, home-scale version of the same idea.

## The threat model going the other way

Once Pi-hole is your network's resolver, **it sees every DNS query from every device**. That's a privileged position. Compromising the Pi means:

- Logging all browsing (already true of any DNS provider)
- Redirecting domains by injecting custom answers (e.g. `bank.com → attacker IP`)
- Holding the network hostage if the service goes down (DNS broken = nothing works)

So we treat the Pi as **trusted infrastructure** and harden it accordingly. See `04-hardening.md`.

## What's in the rest of these docs

- **`01-architecture.md`** — the actual request path. What happens between a packet leaving your phone and the page rendering, with and without Pi-hole in the middle.
- **`02-deployment.md`** — the build, step by step, with verification at each stage.
- **`03-analysis.md`** — reading the dashboard. The first day of query logs is genuinely surprising.
- **`04-hardening.md`** — securing the Pi as critical network infrastructure.
