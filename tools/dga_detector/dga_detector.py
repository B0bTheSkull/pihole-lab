#!/usr/bin/env python3
"""
DGA (Domain Generation Algorithm) detector for Pi-hole.

Pulls domains from a Pi-hole `pihole-FTL.db`, scores each one on
three independent features, and prints the top-N most suspicious.

Features
--------
1. Shannon entropy of the registrable label.
   Random-looking strings ("kqp9zmblw7") have high entropy.
2. English-bigram log-likelihood.
   Strings made of unusual letter pairs ("xz", "qj") score low.
   The model is a tiny built-in bigram table — no network, no deps.
3. Length and digit ratio.
   DGAs typically produce 12–24 char strings with frequent digits.

The composite score is engineered to be 0..1-ish where higher = more
suspicious. It's not a classifier — it's a triage tool. Use it to
sort 50,000 domains into "the 25 you should look at first."

Usage
-----
    python3 dga_detector.py --db /etc/pihole/pihole-FTL.db --hours 24 --top 25

    # plain-text "domain<TAB>score" for piping
    python3 dga_detector.py --db ... --top 100 --tsv

    # filter to a specific client (great for triaging one device)
    python3 dga_detector.py --db ... --client 10.0.0.42

    # score a single label without touching the DB
    python3 dga_detector.py --score kq8fzjwlmbpx
"""
from __future__ import annotations

import argparse
import math
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

# --- Bigram log-prob table (compact built-in English model). -----------------
# Built from a small Project Gutenberg sample, then renormalized. Stored as
# log10 freq per bigram; missing bigrams fall back to a low floor.
# This isn't a research-grade model — it's deliberately tiny and good enough
# to separate "github" from "kpx9zmblqv".
_BIGRAM_LOG = {
    # top ~200 English bigrams by frequency, truncated for compactness
    "th": -1.10, "he": -1.13, "in": -1.20, "er": -1.24, "an": -1.26,
    "re": -1.30, "on": -1.31, "at": -1.34, "en": -1.37, "nd": -1.39,
    "ti": -1.41, "es": -1.42, "or": -1.43, "te": -1.44, "of": -1.45,
    "ed": -1.47, "is": -1.48, "it": -1.49, "al": -1.50, "ar": -1.51,
    "st": -1.52, "to": -1.53, "nt": -1.54, "ng": -1.55, "se": -1.56,
    "ha": -1.57, "as": -1.58, "ou": -1.59, "io": -1.60, "le": -1.61,
    "ve": -1.62, "co": -1.63, "me": -1.64, "de": -1.65, "hi": -1.66,
    "ri": -1.67, "ro": -1.68, "ic": -1.69, "ne": -1.70, "ea": -1.71,
    "ra": -1.72, "ce": -1.73, "li": -1.74, "ch": -1.75, "ll": -1.76,
    "be": -1.77, "ma": -1.78, "si": -1.79, "om": -1.80, "ur": -1.81,
    "ca": -1.82, "el": -1.83, "ta": -1.84, "la": -1.85, "ns": -1.86,
    "di": -1.87, "fo": -1.88, "ho": -1.89, "pe": -1.90, "ec": -1.91,
    "pr": -1.92, "no": -1.93, "ct": -1.94, "us": -1.95, "ac": -1.96,
    "ot": -1.97, "il": -1.98, "tr": -1.99, "ly": -2.00, "nc": -2.01,
    "et": -2.02, "ut": -2.03, "ss": -2.04, "so": -2.05, "rs": -2.06,
    "un": -2.07, "lo": -2.08, "wa": -2.09, "ge": -2.10, "ie": -2.11,
    "wh": -2.12, "ee": -2.13, "wi": -2.14, "em": -2.15, "ad": -2.16,
    "ol": -2.17, "rt": -2.18, "po": -2.19, "we": -2.20, "na": -2.21,
    "ul": -2.22, "ni": -2.23, "ts": -2.24, "mo": -2.25, "ow": -2.26,
    "pa": -2.27, "im": -2.28, "mi": -2.29, "ai": -2.30, "sh": -2.31,
    "ir": -2.32, "su": -2.33, "id": -2.34, "os": -2.35, "iv": -2.36,
    "ia": -2.37, "am": -2.38, "fi": -2.39, "ci": -2.40, "vi": -2.41,
    "pl": -2.42, "ig": -2.43, "tu": -2.44, "ev": -2.45, "ld": -2.46,
    "ry": -2.47, "mp": -2.48, "fe": -2.49, "bl": -2.50, "ab": -2.51,
    "gh": -2.52, "ty": -2.53, "op": -2.54, "wo": -2.55, "sa": -2.56,
    "ay": -2.57, "ex": -2.58, "ke": -2.59, "fr": -2.60, "oo": -2.61,
    "av": -2.62, "ag": -2.63, "if": -2.64, "ap": -2.65, "gr": -2.66,
    "od": -2.67, "bo": -2.68, "sp": -2.69, "rd": -2.70, "do": -2.71,
    "uc": -2.72, "bu": -2.73, "ei": -2.74, "ov": -2.75, "by": -2.76,
    "rm": -2.77, "ep": -2.78, "tt": -2.79, "oc": -2.80, "fa": -2.81,
    "ef": -2.82, "cu": -2.83, "rn": -2.84, "sc": -2.85, "gi": -2.86,
    "da": -2.87, "yo": -2.88, "cr": -2.89, "cl": -2.90, "du": -2.91,
    "ga": -2.92, "qu": -2.93, "ue": -2.94, "ff": -2.95, "ba": -2.96,
    "ey": -2.97, "ls": -2.98, "va": -2.99, "um": -3.00, "pp": -3.01,
    "ua": -3.02, "up": -3.03, "lu": -3.04, "go": -3.05, "ht": -3.06,
    "ru": -3.07, "ug": -3.08, "ds": -3.09, "lt": -3.10, "pi": -3.11,
    "rc": -3.12, "rr": -3.13, "eg": -3.14, "au": -3.15, "ck": -3.16,
    "ew": -3.17, "mu": -3.18, "br": -3.19, "bi": -3.20, "pt": -3.21,
    "ak": -3.22, "pu": -3.23, "ui": -3.24, "rg": -3.25, "ib": -3.26,
    "tl": -3.27, "ny": -3.28, "ki": -3.29, "rk": -3.30, "ys": -3.31,
}
_BIGRAM_FLOOR = -4.5  # fall-back log10 for unseen bigrams

# --- public-suffix-ish trim. Good enough for triage; not a real PSL. ---------
_COMMON_TLDS = {
    "com", "net", "org", "io", "co", "uk", "us", "de", "fr", "ru", "cn", "jp",
    "info", "biz", "xyz", "app", "dev", "ai", "cloud", "store", "site", "online",
    "tk", "ml", "ga", "cf", "lan", "local", "internal", "home", "arpa",
}

_VALID = re.compile(r"^[a-z0-9-]+$")


def registrable_label(domain: str) -> str:
    """Strip TLD and any trailing dot. Returns the leftmost SLD."""
    d = domain.strip().lower().rstrip(".")
    if not d:
        return ""
    parts = d.split(".")
    # Drop trailing public-ish suffix(es).
    while len(parts) > 1 and parts[-1] in _COMMON_TLDS:
        parts.pop()
    return parts[-1] if parts else d


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def bigram_loglik(s: str) -> float:
    """Average log10 bigram probability. Higher = more English-like."""
    if len(s) < 2:
        return _BIGRAM_FLOOR
    total = 0.0
    pairs = 0
    for i in range(len(s) - 1):
        bg = s[i:i + 2]
        if bg.isalpha():
            total += _BIGRAM_LOG.get(bg, _BIGRAM_FLOOR)
            pairs += 1
    return total / pairs if pairs else _BIGRAM_FLOOR


def digit_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(c.isdigit() for c in s) / len(s)


def score(label: str) -> dict[str, float]:
    """Return individual feature values + a composite 0..1-ish score."""
    if not label or not _VALID.match(label):
        return {
            "label": label, "length": len(label), "entropy": 0.0,
            "bigram_ll": 0.0, "digit_ratio": 0.0, "score": 0.0,
        }
    ent = shannon_entropy(label)
    ll = bigram_loglik(label)
    dr = digit_ratio(label)

    # Normalize each feature into [0, 1] where 1 = "looks DGA".
    # Entropy: typical English ~3.0–3.6; DGAs ~3.7–4.5.
    ent_n = min(1.0, max(0.0, (ent - 2.7) / 1.8))

    # Bigram LL: more negative => more suspicious.
    # Map ll in [_BIGRAM_FLOOR .. -1.5] -> [1 .. 0] (clamped):
    # ll == -1.5 (looks like English) -> 0, ll == _BIGRAM_FLOOR -> 1.
    ll_n = min(1.0, max(0.0, (-1.5 - ll) / (-1.5 - _BIGRAM_FLOOR)))

    # Length: 12+ is suspicious; <8 is fine.
    len_n = min(1.0, max(0.0, (len(label) - 8) / 16))

    # Digit ratio: anything > 0 is mildly suspicious; > 0.3 is loud.
    dig_n = min(1.0, dr / 0.4)

    # Weighted blend. Bigram-LL and entropy do the heavy lifting.
    composite = (
        0.40 * ll_n
        + 0.30 * ent_n
        + 0.15 * len_n
        + 0.15 * dig_n
    )

    return {
        "label": label, "length": len(label), "entropy": round(ent, 3),
        "bigram_ll": round(ll, 3), "digit_ratio": round(dr, 3),
        "score": round(composite, 3),
    }


def fetch_domains(db: Path, since: int, client: str | None) -> list[tuple[str, int]]:
    sql = "SELECT domain, COUNT(*) FROM queries WHERE timestamp >= ?"
    args: list = [since]
    if client:
        sql += " AND client = ?"
        args.append(client)
    sql += " GROUP BY domain"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return [(d, n) for d, n in con.execute(sql, args)]
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=Path("/etc/pihole/pihole-FTL.db"))
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--client", type=str, default=None)
    ap.add_argument("--min-score", type=float, default=0.45,
                    help="hide entries below this composite score")
    ap.add_argument("--tsv", action="store_true", help="emit tab-separated output")
    ap.add_argument("--score", type=str, help="score a single label and exit")
    args = ap.parse_args()

    if args.score:
        result = score(registrable_label(args.score))
        for k, v in result.items():
            print(f"{k:>14}: {v}")
        return 0

    if not args.db.exists():
        print(f"[!] FTL DB not found: {args.db}", file=sys.stderr)
        return 2

    since = int(time.time()) - args.hours * 3600
    domains = fetch_domains(args.db, since, args.client)
    if not domains:
        print(f"[+] No queries in the last {args.hours}h matching filter.")
        return 0

    scored = []
    for domain, hits in domains:
        s = score(registrable_label(domain))
        if s["score"] >= args.min_score:
            scored.append((domain, hits, s))
    scored.sort(key=lambda r: r[2]["score"], reverse=True)
    scored = scored[: args.top]

    if not scored:
        print(f"[+] Nothing scored above {args.min_score} (looked at {len(domains)} unique domains).")
        return 0

    if args.tsv:
        for domain, hits, s in scored:
            print(f"{s['score']:.3f}\t{hits}\t{s['length']}\t{s['entropy']:.2f}\t{s['bigram_ll']:.2f}\t{s['digit_ratio']:.2f}\t{domain}")
        return 0

    print(f"Top {len(scored)} suspicious domains in the last {args.hours}h"
          + (f" from client {args.client}" if args.client else "")
          + f" (min-score={args.min_score}):\n")
    print(f"{'score':>5}  {'hits':>5}  {'len':>3}  {'ent':>4}  {'bigll':>6}  {'dig':>4}  domain")
    print("-" * 78)
    for domain, hits, s in scored:
        print(f"{s['score']:>5.2f}  {hits:>5d}  {s['length']:>3d}  "
              f"{s['entropy']:>4.2f}  {s['bigram_ll']:>6.2f}  {s['digit_ratio']:>4.2f}  {domain}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
