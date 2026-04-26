# pihole-lab

Network-level DNS sinkhole deployment on a Raspberry Pi 5, plus analysis of what your home network is *actually* doing when you're not looking.

> "Breaking things to make them stronger" — except here we break the third-party tracking economy on our own LAN.

## What this is

A documented deployment of [Pi-hole](https://pi-hole.net/) acting as the authoritative DNS resolver for a home network, paired with [unbound](https://nlnetlabs.nl/projects/unbound/) for recursive resolution so we're not dependent on a single upstream provider.

This isn't "I clicked install." It's:

- the **architectural reasoning** for putting DNS-layer filtering in front of every device on the network
- the **deployment** with concrete config and verification at every step
- a **traffic analysis** of what the network looked like before vs. after — which IoT devices phone home, how often, and to where
- the **hardening** of the resolver itself so it doesn't become a single point of failure or compromise

## Hardware

| Component | Detail |
|---|---|
| Board | Raspberry Pi 5 (8GB) |
| Storage | 117GB SSD over USB |
| OS | Debian 12 (Bookworm), arm64 |
| Network | Ethernet, static lease on LAN |

## Repo layout

```
pihole-lab/
├── README.md            # this file
├── writeup.md           # the blog post
├── docs/
│   ├── 00-overview.md   # what Pi-hole is and why network-level DNS filtering matters
│   ├── 01-architecture.md  # how the request path actually works
│   ├── 02-deployment.md    # step-by-step build with verification
│   ├── 03-analysis.md      # reading the dashboard, finding the noisy devices
│   └── 04-hardening.md     # locking down the resolver itself
├── configs/             # exported Pi-hole + unbound config
├── screenshots/         # captures referenced in docs
├── tools/               # detection tooling built on top of Pi-hole
│   ├── doh_dot_detector/   # block + detect DoH/DoT bypass attempts
│   ├── canary/             # internal honey-domains + watcher
│   ├── dga_detector/       # entropy/bigram triage of suspicious domains
│   ├── device_profile/     # per-client DNS report generator
│   └── suricata_correlation/ # join Suricata flows with Pi-hole answers
└── monitoring/          # observability stack
    ├── docker-compose.yml      # Prometheus + Grafana + pihole-exporter
    ├── prometheus.yml
    ├── grafana/                # auto-provisioned dashboard
    └── loki/                   # log shipping (Loki + promtail)
```

## Detections built on top

This isn't just "I installed Pi-hole." The `tools/` directory adds a
small library of detections that turn the resolver into a passive
sensor:

| Tool | What it catches |
|---|---|
| **DoH/DoT detector** | Devices trying to bypass the resolver via encrypted DNS |
| **Canary domains** | Internal recon, misconfigured hosts, browser-history leaks |
| **DGA detector** | Algorithmically generated C2 domains (entropy + bigram triage) |
| **Device profile** | "Which device on my LAN is the loudest, and why?" |
| **Suricata correlator** | Flows that hit IPs the client never resolved (hardcoded callbacks, tunnels) |

Each tool is a single Python script + a README; no heavy
dependencies, runs on the Pi or any host with read access to
`pihole-FTL.db`.

## Skills demonstrated

- DNS protocol fundamentals (recursion, caching, DNSSEC)
- Linux service deployment and systemd unit hardening
- Network traffic analysis at the DNS layer
- Threat-modeling a piece of self-hosted infrastructure
- Documentation suitable for a non-expert reader

## Status

Built April 2026. Active deployment.
