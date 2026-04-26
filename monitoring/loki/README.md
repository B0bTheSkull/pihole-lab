# Loki + Promtail log pipeline

Centralizes Pi-hole's `pihole.log` and `FTL.log` (and optionally
Suricata's `eve.json`) into Loki so you can grep across them in
Grafana with LogQL — way more useful than `grep`-on-the-Pi.

## Architecture

```
[Pi-hole host]                                  [Monitoring host]
  /var/log/pihole/pihole.log
  /var/log/pihole/FTL.log     ── promtail ──►   Loki  ──►  Grafana
  /var/log/suricata/eve.json
```

Loki runs on the monitoring host (separate from the Pi, ideally).
Promtail runs *on the Pi* because that's where the logs live.

## Bring up Loki

From the parent directory:

```bash
docker compose -f docker-compose.yml -f loki/docker-compose.loki.yml up -d
```

This adds Loki on `:3100` and wires it as a Grafana datasource.

## Install promtail on the Pi

```bash
# 1. Download
curl -L -o /usr/local/bin/promtail \\
    https://github.com/grafana/loki/releases/latest/download/promtail-linux-arm64
chmod +x /usr/local/bin/promtail

# 2. Drop config
sudo mkdir -p /etc/promtail /var/lib/promtail
sudo cp promtail-config.yml /etc/promtail/promtail.yml
$EDITOR /etc/promtail/promtail.yml   # set Loki URL to your monitoring host

# 3. Service
sudo cp promtail.service /etc/systemd/system/promtail.service
sudo systemctl daemon-reload
sudo systemctl enable --now promtail
sudo systemctl status promtail
```

## LogQL examples

In Grafana → Explore → datasource Loki:

```logql
# Every gravity-blocked query in the last hour
{job="pihole", stream="queries", event="gravity"}

# All FTL warnings/errors
{job="pihole", stream="ftl"} |~ "(?i)warn|error|fatal"

# DNS queries from a single client
{job="pihole", stream="queries"} |~ "from 10\\.0\\.0\\.42"

# Suricata alerts joined with their source IPs
{job="suricata", event_type="alert"} | json | line_format "{{.src_ip}} -> {{.dest_ip}} {{.alert.signature}}"

# Failed SSH attempts (cross-stream)
{job="syslog"} |~ "Failed password"
```

## Why Loki over ELK

ELK is fine for an org. For a homelab, Loki is dramatically less
fussy: it doesn't index log content, just labels, so the disk
footprint is small and ingest is cheap. The trade-off is you can't
do free-text search; you grep within a label-selected stream.
That's a fine fit for "show me Pi-hole logs from yesterday."

If you outgrow Loki, the upgrade path to ELK or OpenSearch is
straightforward — both speak Logstash/Filebeat which can re-tail
the same files.
