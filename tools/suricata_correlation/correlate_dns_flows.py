#!/usr/bin/env python3
"""
Correlate Suricata flows with Pi-hole DNS resolutions.

Pi-hole tells you "client X resolved domain Y to IP Z." Suricata
tells you "client X opened a flow to IP Z." Joining them in the
right order tells you:

  - which domain a flow connected to (forensic answer to "what
    did 10.0.0.42 talk to at 03:14am?")
  - which flows connected to IPs Pi-hole *never* resolved for them
    (hardcoded IPs / DoH endpoints / tunnels — hello, signal!)

The correlation rule is simple: a flow from client C to IP I that
starts within `--window` seconds of Pi-hole answering a query for
domain D from client C with answer I gets attributed to D.

Usage:
    python3 correlate_dns_flows.py \\
        --ftl /etc/pihole/pihole-FTL.db \\
        --eve /var/log/suricata/eve.json \\
        --hours 24

    # write a CSV report
    python3 correlate_dns_flows.py ... --csv flows.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterator


def load_dns_resolutions(ftl: Path, hours: int) -> dict[tuple[str, str], list[tuple[int, str]]]:
    """
    Returns {(client, ip): [(timestamp, domain), ...]} sorted by timestamp.
    Uses queries + query_storage tables (FTL v6 splits replies out).
    Falls back gracefully if the schema doesn't have answers.
    """
    since = int(time.time()) - hours * 3600
    out: dict[tuple[str, str], list[tuple[int, str]]] = {}

    con = sqlite3.connect(f"file:{ftl}?mode=ro", uri=True)
    try:
        # Schema check: FTL v6 has a `query_storage` table with
        # additional info; the legacy `queries` table is the common
        # denominator. We just need (timestamp, client, domain) and
        # we'll pair against the *next* answer for the same query.
        # If `additional_info` (JSON) has reply IPs we use them; else
        # we fall back to no-answer mode and only correlate on dest IP
        # appearing in suricata = domain queried in same window.
        cur = con.execute(
            """
            SELECT timestamp, client, domain, additional_info
            FROM queries
            WHERE timestamp >= ?
            """,
            (since,),
        )
        for ts, client, domain, addl in cur:
            ips: list[str] = []
            if addl:
                try:
                    payload = json.loads(addl)
                    if isinstance(payload, dict):
                        # Pi-hole stores answers under various keys depending
                        # on version; try the common ones.
                        for key in ("CNAME", "answers", "reply", "ips"):
                            v = payload.get(key)
                            if isinstance(v, list):
                                ips.extend(str(x) for x in v)
                            elif isinstance(v, str):
                                ips.append(v)
                except (json.JSONDecodeError, TypeError):
                    pass
            for ip in ips or [""]:
                out.setdefault((client, ip), []).append((ts, domain))
    finally:
        con.close()

    for k in out:
        out[k].sort()
    return out


def iter_flows(eve: Path) -> Iterator[dict]:
    with eve.open("r", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event_type") in {"flow", "alert", "tls", "http"}:
                yield ev


def find_domain(
    resolutions: dict[tuple[str, str], list[tuple[int, str]]],
    client: str,
    dst_ip: str,
    flow_start: int,
    window: int,
) -> str | None:
    """Find the most recent domain Pi-hole resolved for client→dst_ip
    within `window` seconds before flow_start."""
    candidates = resolutions.get((client, dst_ip), []) + resolutions.get((client, ""), [])
    best: tuple[int, str] | None = None
    for ts, domain in candidates:
        if ts <= flow_start and flow_start - ts <= window:
            if best is None or ts > best[0]:
                best = (ts, domain)
    return best[1] if best else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ftl", type=Path, default=Path("/etc/pihole/pihole-FTL.db"))
    ap.add_argument("--eve", type=Path, default=Path("/var/log/suricata/eve.json"))
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--window", type=int, default=120,
                    help="seconds between DNS answer and flow start to consider a match")
    ap.add_argument("--csv", type=Path, help="write findings to CSV instead of stdout")
    ap.add_argument("--lan", default="10.0.0.0/24",
                    help="LAN CIDR — flows from outside this are ignored")
    args = ap.parse_args()

    if not args.ftl.exists():
        print(f"[!] FTL DB not found: {args.ftl}", file=sys.stderr)
        return 2
    if not args.eve.exists():
        print(f"[!] eve.json not found: {args.eve}", file=sys.stderr)
        return 2

    import ipaddress
    lan = ipaddress.ip_network(args.lan)
    resolutions = load_dns_resolutions(args.ftl, args.hours)

    matched, unmatched = [], []
    for ev in iter_flows(args.eve):
        src = ev.get("src_ip"); dst = ev.get("dest_ip")
        if not src or not dst:
            continue
        try:
            if ipaddress.ip_address(src) not in lan:
                continue
        except ValueError:
            continue
        ts_str = ev.get("timestamp", "")
        try:
            flow_ts = int(time.mktime(time.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")))
        except (ValueError, TypeError):
            continue

        domain = find_domain(resolutions, src, dst, flow_ts, args.window)
        row = {
            "ts": ts_str, "src": src, "dst": dst,
            "dport": ev.get("dest_port"), "proto": ev.get("proto"),
            "event_type": ev.get("event_type"),
            "domain": domain or "",
            "alert_sig": (ev.get("alert") or {}).get("signature", ""),
        }
        (matched if domain else unmatched).append(row)

    print(f"[+] matched {len(matched)} flows to a Pi-hole resolution")
    print(f"[!] {len(unmatched)} flows had no matching DNS answer")
    print("    (these are the interesting ones — hardcoded IPs, DoH, tunnels)")

    if args.csv:
        with args.csv.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list((matched + unmatched)[0].keys())
                               if (matched + unmatched) else ["ts"])
            w.writeheader()
            w.writerows(matched + unmatched)
        print(f"[+] wrote {args.csv}")
    else:
        for row in unmatched[:20]:
            print(f"  NO-DNS  {row['ts']}  {row['src']:>15s} -> {row['dst']:>15s}:"
                  f"{row['dport']}  alert={row['alert_sig'] or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
