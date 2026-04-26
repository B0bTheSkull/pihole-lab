#!/usr/bin/env python3
"""
Detect DoH / DoT bypass attempts in Pi-hole's FTL database.

Reads a Pi-hole `pihole-FTL.db` (SQLite) and reports clients that have
queried known encrypted-DNS endpoints in the lookback window.

Usage:
    sudo python3 detect_doh_attempts.py \\
        --db /etc/pihole/pihole-FTL.db \\
        --blocklist blocklist_doh_dot.txt \\
        --hours 24

Exits non-zero if any client made >= --threshold queries to a DoH/DoT host,
so it can drop into cron and page via stderr.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path


def load_blocklist(path: Path) -> set[str]:
    out: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return out


def query_recent(db: Path, hosts: set[str], since: int) -> list[tuple[str, str, int, str]]:
    """Return rows of (client, domain, count, first_seen_iso) for matching queries."""
    if not hosts:
        return []
    placeholders = ",".join("?" for _ in hosts)
    sql = f"""
        SELECT client, domain, COUNT(*) AS hits, MIN(timestamp) AS first_seen
        FROM queries
        WHERE timestamp >= ?
          AND domain IN ({placeholders})
        GROUP BY client, domain
        ORDER BY hits DESC
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.execute(sql, [since, *sorted(hosts)])
        rows = []
        for client, domain, hits, first_seen in cur:
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(first_seen))
            rows.append((client, domain, int(hits), iso))
        return rows
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=Path("/etc/pihole/pihole-FTL.db"))
    ap.add_argument(
        "--blocklist",
        type=Path,
        default=Path(__file__).with_name("blocklist_doh_dot.txt"),
    )
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument(
        "--threshold",
        type=int,
        default=1,
        help="alert if a single client makes at least this many DoH queries",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"[!] FTL DB not found: {args.db}", file=sys.stderr)
        return 2
    if not args.blocklist.exists():
        print(f"[!] Blocklist not found: {args.blocklist}", file=sys.stderr)
        return 2

    hosts = load_blocklist(args.blocklist)
    if not hosts:
        print("[!] Blocklist is empty after parsing", file=sys.stderr)
        return 2

    since = int(time.time()) - args.hours * 3600
    rows = query_recent(args.db, hosts, since)

    by_client: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for client, domain, hits, first_seen in rows:
        by_client[client].append((domain, hits, first_seen))

    flagged = {c: r for c, r in by_client.items() if sum(h for _, h, _ in r) >= args.threshold}

    if args.json:
        import json

        out = {
            "lookback_hours": args.hours,
            "threshold": args.threshold,
            "total_hosts_watched": len(hosts),
            "flagged_clients": {
                c: [{"domain": d, "hits": h, "first_seen": fs} for d, h, fs in v]
                for c, v in flagged.items()
            },
        }
        print(json.dumps(out, indent=2))
    else:
        if not flagged:
            print(f"[+] No DoH/DoT bypass attempts in the last {args.hours}h.")
            return 0
        print(
            f"[!] {len(flagged)} client(s) attempted DoH/DoT in the last {args.hours}h:\n"
        )
        for client, items in sorted(flagged.items(), key=lambda kv: -sum(h for _, h, _ in kv[1])):
            total = sum(h for _, h, _ in items)
            print(f"  {client}  ({total} queries)")
            for domain, hits, first_seen in sorted(items, key=lambda x: -x[1]):
                print(f"    - {domain:40s}  {hits:>4d}  first: {first_seen}")
            print()

    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
