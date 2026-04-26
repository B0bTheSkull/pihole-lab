#!/usr/bin/env python3
"""
Watch the Pi-hole FTL database for queries to canary domains.

Run on a cron loop (every 5 min is plenty). On a hit, prints a
high-signal alert to stderr and exits non-zero so cron MAILTO or
a wrapper shell script can page.

Usage:
    sudo python3 watch_canaries.py \\
        --db /etc/pihole/pihole-FTL.db \\
        --canaries canary_domains.list \\
        --state /var/lib/canary-watch/last_seen \\
        --window-min 10
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path


def load_canaries(p: Path) -> set[str]:
    out = set()
    for line in p.read_text().splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            out.add(line)
    return out


def read_state(p: Path) -> int:
    try:
        return int(p.read_text().strip())
    except (OSError, ValueError):
        return 0


def write_state(p: Path, ts: int) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(ts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=Path("/etc/pihole/pihole-FTL.db"))
    ap.add_argument(
        "--canaries", type=Path, default=Path(__file__).with_name("canary_domains.list")
    )
    ap.add_argument(
        "--state",
        type=Path,
        default=Path("/var/lib/canary-watch/last_seen"),
        help="file to track the highest timestamp we've already seen",
    )
    ap.add_argument(
        "--window-min",
        type=int,
        default=0,
        help="if >0, ignore --state and look back this many minutes",
    )
    args = ap.parse_args()

    canaries = load_canaries(args.canaries)
    if not canaries:
        print("[!] No canaries loaded", file=sys.stderr)
        return 2

    if args.window_min > 0:
        since = int(time.time()) - args.window_min * 60
    else:
        since = read_state(args.state)

    placeholders = ",".join("?" for _ in canaries)
    sql = f"""
        SELECT timestamp, client, domain, status
        FROM queries
        WHERE timestamp > ?
          AND domain IN ({placeholders})
        ORDER BY timestamp ASC
    """
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        rows = list(con.execute(sql, [since, *sorted(canaries)]))
    finally:
        con.close()

    if not rows:
        if args.window_min == 0:
            write_state(args.state, int(time.time()))
        return 0

    print("=" * 70, file=sys.stderr)
    print("!! CANARY HIT — internal-only domain was queried by a LAN host !!", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    for ts, client, domain, status in rows:
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
        print(f"  {iso}  {client:>15s}  ->  {domain}   (FTL status={status})", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(
        "Investigate the client. Canary domains are never queried by clean hosts —\n"
        "this is a misconfig, a malicious tool, or a curious user with a hosts file.",
        file=sys.stderr,
    )

    if args.window_min == 0:
        write_state(args.state, int(rows[-1][0]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
