# Per-device DNS profile

Reads the Pi-hole FTL DB and writes a markdown report of every
client on the LAN: total queries, block ratio, top destinations
(allowed and blocked), and a hand-tuned "loudness" verdict.

The output is ready to paste straight into a writeup or post in
chat. It's the table I wished I had after 24h of running Pi-hole.

## Usage

```bash
# To stdout
sudo python3 device_profile.py --hours 24

# Friendly names for IPs (recommended — way easier to read)
cp names.example.json names.json
$EDITOR names.json
sudo python3 device_profile.py --hours 24 --names names.json

# Write to a file (e.g. for committing into the writeup)
sudo python3 device_profile.py --hours 24 \
    --names names.json \
    --out ../../docs/03-analysis-device-table.md
```

## Verdicts

| Verdict | Heuristic |
|---|---|
| **very loud** | > 1500 queries/hour |
| **loud** | > 400 queries/hour |
| **suspicious** | > 60% block ratio AND > 50 q/hr (lots of telemetry trying to phone home) |
| **chatty** | > 500 unique domains in window (likely a browser-using client) |
| **ok** | none of the above |

These are deliberately blunt — adjust the thresholds in
`loudness()` once you know your own baseline.
