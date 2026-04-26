# Suricata × Pi-hole correlation

Pi-hole catches DNS-layer threats. Suricata catches everything else
on the wire. They're more useful together than apart.

## What this does

For every flow Suricata observes (`event_type=flow`), we ask
Pi-hole: "did this client just resolve this destination IP?"

- **Match** → we know what domain the flow connected to. Forensic
  gold. Now you can answer "what was 10.0.0.42 talking to at 3am?"
  with a domain name, not just an IP.
- **No match** → the client either skipped Pi-hole (DoH, hardcoded
  IP, tunnel) or the flow predates the lookback window. Either way,
  the unmatched set is where the interesting traffic hides.

## Setup

1. Install Suricata on the Pi-hole host (or a separate sensor):

   ```bash
   sudo apt install suricata
   ```

2. Merge `suricata-snippet.yaml` into `/etc/suricata/suricata.yaml`
   (it overrides only the parts that matter).
3. Pull rules:

   ```bash
   sudo suricata-update
   sudo systemctl restart suricata
   ```

4. Confirm `eve.json` is being written:

   ```bash
   tail -f /var/log/suricata/eve.json | jq -r '"\(.event_type) \(.src_ip) -> \(.dest_ip)"'
   ```

## Run the correlator

```bash
sudo python3 correlate_dns_flows.py --hours 24 --csv flows.csv
```

It prints a summary, lists the first 20 *unmatched* flows (your
prime suspects), and optionally writes everything to CSV for later
slicing.

## Tuning

- `--window 120` — how recent a Pi-hole answer can be to count as
  attribution. Bump it for clients with aggressive DNS caching.
- `--lan 10.0.0.0/24` — restrict to flows originating on the LAN
  so you don't count return traffic.

## What you do with this

The unmatched flows are where blue-team triage starts.

- IP appears in zero Pi-hole queries from anyone? Could be a DoH
  endpoint or a hardcoded callback. Check Suricata's `tls.sni`
  field for that flow if you have TLS logging on.
- Same client repeatedly hits IPs without DNS? Beaconing. Note
  the interval, hand it to your detection-engineering side.
- Flow + Suricata alert + no DNS = high priority.
