# 03 · Analysis: reading the dashboard

The dashboard isn't just pretty graphs — it's a forensic view of what your network actually does. A lot of it is uncomfortable.

## What you're looking at

The Pi-hole admin UI lives at `http://<pi-ip>/admin/`. The key views:

| View | What it tells you |
|---|---|
| **Dashboard** | Total queries, blocked %, top domains (allowed and blocked), top clients |
| **Query Log** | Every single query, attributable by client IP, with allowed/blocked status |
| **Long-term data** | Same but historical — trend graphs over days/weeks |
| **Network** | List of all known clients on your LAN, last-seen timestamp |
| **Top Domains** | Most-queried allowed and blocked domains |
| **Top Blocked** | Helpful for tuning false positives |

> 📸 **Screenshot to capture:** `screenshots/dashboard-day1.png` — full dashboard within 24h of going live, blocking %, total queries, top blocked domains.

## What surprised me when I looked

A few things you'll likely notice within the first 24 hours, ranked by "huh":

### 1. The percentage of blocked traffic is high

Typical home networks see **20–35% of DNS queries blocked** with default lists, sometimes higher with smart TVs and IoT in the mix. That's not 20–35% of the bytes you transfer — it's 20–35% of *the requests devices make at all*. Most are tracking pixels, telemetry, ad calls.

### 2. Smart TVs are loud

If you have a smart TV, watch it for an hour with Pi-hole on. Then look at the query log filtered to that device's IP. You will see:

- Hundreds of queries per hour to the manufacturer's telemetry domain
- Repeated queries to ad networks even when no ad is on screen
- Queries to analytics services for *every channel switch*

This is a great visualization for blog content. Filter the log to one client, hit "show 1000 entries," and screenshot the wall of telemetry.

> 📸 **Screenshot to capture:** `screenshots/iot-telemetry.png` — query log filtered to a single noisy IoT device, showing repeated telemetry/ad queries.

### 3. Apps you didn't think were tracking, are tracking

Your phone's keyboard app, some random utility, the system itself — every modern OS phones home constantly. Apple, Google, Microsoft all generate steady streams. Some of this is legitimate (push notifications, time sync), some is purely behavioral telemetry.

The best way to investigate: install nothing, do nothing, leave a phone idle for 30 minutes, then check what queries it made. Most won't show in the *blocked* column — they go to `apple.com`, `google.com`, etc. — but you'll see *what frequency* they communicate.

### 4. There's almost always a misbehaving device

Filtering the dashboard's "Top Clients" by query count usually reveals one or two devices that are doing 10× more DNS queries than anything else. That's worth investigating — it's either a smart device with a chatty app, a misconfigured app stuck in a retry loop, or (rarely) malware.

## Tuning: when to whitelist

You'll find a few legit sites broken by default blocklists. Common offenders:

- **Some article paywalls** — break in weird ways because they fingerprint via blocked analytics
- **Microsoft 365 tenant configs** — some Teams telemetry is on the StevenBlack list
- **Captive portals** at hotels/cafes — sometimes use blocked-by-default tracking domains for auth flow

When something doesn't load:

1. Open the Pi-hole admin → **Query Log**
2. Filter to your client IP
3. Sort by time, look for `BLOCKED` entries from the last few seconds
4. Pick the suspicious domain (usually obvious — `tracking.foo.com` won't be the broken site, but `cdn.foo.com` might be)
5. Click "Whitelist" next to it
6. Reload the page

Document each whitelist decision in `configs/whitelist-notes.md` — over time this becomes useful "I know why this domain is allowed" history.

## Detecting interesting things

Beyond the cosmetic value, the query log is genuinely a security tool. Things to watch for:

### Sudden spike in queries from one device

Could be:
- Software update (legitimate)
- Background sync (legitimate)
- Crashloop / runaway process (annoying)
- Beaconing malware (interesting)

A device that suddenly starts querying domains it never queried before, especially DGA-style (long random subdomains), is a signal.

### Queries to known-malicious domains

If your blocklists include threat intel feeds (StevenBlack includes some, [firebog.net](https://v.firebog.net/hosts/lists.php?type=tick) has more), `BLOCKED` entries to `c2.evil.tld`-style domains tell you a device tried to reach a known bad host. That's worth investigating regardless of whether the block "saved" you — the question is *why did it try*.

### Devices using non-Pi-hole DNS

If a device has hardcoded DNS (e.g., a Chromecast that uses 8.8.8.8 directly, or a smart TV doing DoH), you'll see *fewer queries* from it than expected, while it clearly does network activity. That's a sign to either:

- Block its hardcoded DNS at the firewall (force it through Pi-hole)
- Or add it to a deny-list of "devices I don't trust"

### The DNS-over-HTTPS gap

Modern browsers (Firefox especially) default to DoH which bypasses Pi-hole entirely. Easiest test: open the same set of pages in the browser vs. with the system DNS. If Pi-hole's count for that client doesn't change much, DoH is winning. Disable DoH in browser settings to restore visibility.

## What "success" looks like

You're doing it right when:

- Block rate is steady at 20–40% (lower = lists too thin, higher = false positives likely)
- Dashboard "Total clients seen" matches your actual device count
- You've identified at least one device you didn't realize was on the network (the IoT light bulb, the older laptop, the kid's tablet)
- You've manually whitelisted a handful of domains for sites you actually use
- You sleep slightly worse knowing how much your TV talks to its manufacturer

## Exporting data for analysis

Pi-hole stores queries in `/etc/pihole/pihole-FTL.db` (SQLite). Useful for offline analysis — pull it to a workstation and query directly:

```sql
-- Top 20 most-queried domains by client
SELECT client, domain, COUNT(*) as queries
FROM queries
WHERE timestamp > strftime('%s', 'now', '-24 hours')
GROUP BY client, domain
ORDER BY queries DESC
LIMIT 20;

-- Devices that queried something unusual
SELECT client, domain, datetime(timestamp, 'unixepoch') as t
FROM queries
WHERE domain LIKE '%xn--%'    -- punycoded (often phishing)
   OR LENGTH(domain) > 50      -- DGA-style
ORDER BY timestamp DESC
LIMIT 50;
```

The DB is small (single-digit MB even after weeks). Backups belong in `configs/` exports for reproducibility.

## Automating the analysis

Hand-querying the DB gets old fast. The `tools/` directory has scripts that
turn this whole section into a few commands:

- **`tools/device_profile/device_profile.py`** — generates the per-device
  table at the top of this doc directly from `pihole-FTL.db`. Run it on
  any cadence and commit the output. See
  [`03-analysis-device-table.md`](03-analysis-device-table.md) for the
  most recent generated snapshot.
- **`tools/dga_detector/dga_detector.py`** — scores every domain in the
  last 24h for "DGA-ness" (entropy + bigram weirdness + length/digit
  ratio) and prints the top-N suspicious. Way better than the
  `LENGTH(domain) > 50` heuristic above.
- **`tools/canary/watch_canaries.py`** — alerts on any query to a
  honey-domain. Pair with cron.
- **`tools/doh_dot_detector/detect_doh_attempts.py`** — every client that
  tried to reach a DoH/DoT endpoint, with hit counts.

For continuous visibility, the `monitoring/` stack (Prometheus +
Grafana + Loki) gives time-series graphs and full log search across
`pihole.log`, `FTL.log`, and Suricata `eve.json` if you've added it.
