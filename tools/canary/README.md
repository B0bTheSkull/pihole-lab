# Canary (honey) domains

## Idea

Pick names that look like real internal services (`vault-prod.canary.lan`,
`admin-portal.canary.lan`), put them in Pi-hole's local DNS pointing
at `192.0.2.1` (TEST-NET-1 — unroutable), and forget about them.

A clean host should *never* query them. Any query is signal:

| What you see | What it likely means |
|---|---|
| Browser history typeahead hit | Almost always you. Verify and dismiss. |
| Curl/wget from a server | Compromised host running recon. |
| LDAP / SMB / Kerberos client | Worm or attacker enumerating internal infra. |
| Periodic, fixed-interval queries | Something's bedded in. |

It's the lowest-effort detection you can build that catches a class
of real attacker behaviour (internal recon).

## Install

On the Pi-hole host:

```bash
sudo ./install.sh
```

Then verify a canary resolves to the sinkhole:

```bash
dig +short admin-portal.canary.lan @127.0.0.1
# 192.0.2.1
```

## Watch

Drop the watcher in cron (every 5 minutes is fine):

```cron
# /etc/cron.d/canary-watch
*/5 * * * * pihole /usr/local/bin/watch_canaries.py 2>>/var/log/canary-watch.log
```

The first run sets a baseline; subsequent runs only alert on *new*
queries. To re-scan a whole day instead, pass `--window-min 1440`.

## Tuning

- Add a new canary every time you stand up a new internal service.
  Pair real `nas` with fake `backup-nas`. Pair real `grafana` with
  fake `internal-grafana`. The realer they look, the better.
- Keep them out of public DNS. They live in `/etc/pihole/custom.list`
  and resolve only on the LAN.
- Don't tell housemates. Their workstation querying a canary because
  of typo-squat browser autocomplete is the false positive you want
  to learn to recognize fast.
