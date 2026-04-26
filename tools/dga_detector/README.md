# DGA detector

Cheap, dependency-free triage tool for finding algorithmically
generated domain names in your Pi-hole query log.

## How it scores

For every unique domain queried in the lookback window, we strip
the TLD and score the registrable label on:

| Feature | What it catches |
|---|---|
| **Shannon entropy** | Random-looking strings (high entropy) |
| **English bigram log-likelihood** | Strings made of unusual letter pairs |
| **Length** | DGAs cluster in the 12–24 char band |
| **Digit ratio** | Many DGAs sprinkle digits |

Each feature is normalized to `[0, 1]` and combined into a single
composite score. Higher = more DGA-like. We're **not** classifying;
we're sorting 50,000 domains so a human looks at the right 25.

## Examples

```bash
# Score a single label, no DB needed
$ python3 dga_detector.py --score kq8fzjwlmbpxqr3
         label: kq8fzjwlmbpxqr3
        length: 15
       entropy: 3.773
     bigram_ll: -3.85
   digit_ratio: 0.067
         score: 0.842

$ python3 dga_detector.py --score github
         label: github
        length: 6
       entropy: 2.252
     bigram_ll: -2.01
   digit_ratio: 0.0
         score: 0.077
```

## Triage on real data

```bash
# Top 25 in the last 24h
sudo python3 dga_detector.py --hours 24 --top 25

# One specific client
sudo python3 dga_detector.py --client 10.0.0.42 --hours 12

# Pipeable
sudo python3 dga_detector.py --tsv --top 200 > today.tsv
```

## Tuning

- Bump `--min-score` until the false positives are tolerable. CDNs
  produce a lot of high-entropy hostnames (`x39kdmqp.cloudfront.net`)
  and you'll want to allowlist their parent domains in your head.
- Run it per-client. A CDN-heavy laptop is noisy; a smart bulb that
  suddenly produces 50 high-score domains is *very* not noisy.
- Pair with the canary watcher: a host hitting both your DGA list
  *and* a canary in the same hour is the alert you wake up for.

## Limits

This is a heuristic and proud of it.

- Won't beat dictionary-DGAs (e.g. Suppobox uses real English words).
- Won't beat short DGAs that imitate brand names.
- Will produce false positives on legitimate CDNs and hash-named
  storage URLs.

It catches the lazy DGA families and serves as a forcing function:
if you can read the top-25 every morning in 60 seconds, you'll start
to recognise patterns the heuristic doesn't.
