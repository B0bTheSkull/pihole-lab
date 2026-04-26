# Pi-hole observability stack (Prometheus + Grafana + Loki)

The default Pi-hole UI is fine. Time-series graphs over weeks are not
fine — they're read off a SQLite file on the Pi and the UI throws up
its hands once the data set is interesting. So: ship the metrics
elsewhere.

```
            ┌─────────────────┐
   Pi-hole──┤ pihole-exporter ├──► Prometheus ──► Grafana
            └─────────────────┘
   Pi-hole logs ─► promtail ─► Loki ─► Grafana (Logs panel)
```

## Bring it up

```bash
cp .env.example .env
$EDITOR .env       # set PIHOLE_PASSWORD and a real Grafana password
docker compose up -d
```

Visit:
- Grafana: <http://localhost:3000>
- Prometheus: <http://localhost:9090>
- Exporter raw metrics: <http://localhost:9617/metrics>

The "Pi-hole — DNS overview" dashboard is auto-provisioned on first
boot via `grafana/provisioning/`.

## What you get

- **Block %** as a live gauge — way more legible than the default UI.
- **Queries-per-second** rate graph — spikes correlate with users
  waking, smart-TV evenings, and the occasional "what is happening?"
  IoT device.
- **Top clients / top blocked** as bar gauges.
- **Pi-hole UP/DOWN** as a single tile — useful when you point a
  status board at it.

## Add the log pipeline

Loki + promtail come from `loki/docker-compose.loki.yml`. They're a
separate compose file so you can opt in:

```bash
docker compose -f docker-compose.yml -f loki/docker-compose.loki.yml up -d
```

See `loki/README.md` for the promtail config and how queries look.

## Notes

- The exporter image is unofficial but well-maintained. Pin a tag in
  production rather than running `:latest`.
- Don't expose Grafana to the internet. UFW it to LAN only, or sit
  it behind your VPN.
- If the Pi-hole admin password rotates, restart the exporter:
  `docker compose restart pihole-exporter`.
