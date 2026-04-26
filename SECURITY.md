# Security & sanitization rules for this repo

## Never commit

- `configs/*.live` — these are exports of the running Pi-hole. The
  Pi-hole v6 `pihole.toml` contains `webserver.api.pwhash` (BALLOON-SHA256
  hash of the admin password) and `webserver.api.totp_secret` if 2FA
  is on. A salted hash is *not* safe to publish — it's still subject
  to offline brute force.
- `configs/pihole-FTL.db` and any backup of it — the DNS query log
  re-identifies your LAN.
- `configs/teleporter*.tar.gz` — same problem, includes hash + TOTP.
- `monitoring/.env` — Pi-hole admin password and Grafana password.
- `tools/device_profile/names.json` — the IP→friendly-name map you
  may have built up; it's a soft privacy leak.
- Suricata `eve.json` — every flow on your LAN.

`.gitignore` covers all of the above. If you ever run `git add -A`,
double-check `git status` before committing.

## How to publish a sanitized snapshot

If you want a `pihole.toml` snippet in the public repo (for the
writeup):

1. Copy the live file to `pihole.toml.snippet`.
2. Strip every `pwhash`, `app_pwhash`, and `totp_secret` value.
3. `grep -E '(pwhash|secret|password)' pihole.toml.snippet` and
   confirm only empty strings or `<REDACTED>` placeholders remain.
4. Then it's fine to commit.

## Network exposure

The Pi-hole admin UI lives at `http://<pi-ip>/admin/` over plain
HTTP. The hardening doc enforces UFW rules limiting it to the LAN
(`10.0.0.0/24`). **Do not** port-forward 80/443 to the Pi from the
internet without putting it behind a TLS-terminating reverse proxy
and IP allowlist.

## If a secret leaks

1. `pihole -a -p '<new-strong-password>'` on the Pi.
2. `git rm --cached configs/<file>` if the file is staged.
3. If a hash already made it to GitHub, force-push *only after*
   rotating the password — and use `git filter-repo` / BFG to scrub
   history. (Force-pushing is destructive; you've been warned.)
