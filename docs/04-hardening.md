# 04 · Hardening: securing the resolver itself

Pi-hole is now infrastructure. Every device on the network depends on it. That means we treat it like infrastructure — not like a project Pi we can leave with default everything.

## Threat model

The Pi sees every DNS query made on the LAN. An attacker who compromises it can:

- Log all browsing activity, attributing every query to a client IP
- Inject malicious answers (e.g., `bank.com → attacker IP`) to MITM sensitive sessions
- Sinkhole legitimate domains to deny service
- Use the device as a pivot into the rest of the LAN

Realistic attack vectors:

| Vector | Likelihood | Mitigation |
|---|---|---|
| Brute-force SSH on port 22 from internet | Low (no port forward) but high if exposed | Key-only auth, fail2ban, no port-forward |
| Compromised device on LAN scans/attacks Pi | Medium (smart TVs, IoT) | UFW firewall, only DNS+SSH+web ports open |
| Pi-hole web UI exploit | Low but real (it's PHP) | Strong admin password, web UI not exposed beyond LAN |
| Insecure plaintext HTTP for admin login | High over hostile networks | TLS via reverse proxy, or restrict admin to specific IPs |
| Stale CVEs in Pi-hole / unbound / dnsmasq | Medium over time | Unattended security upgrades |
| SD card corruption / hardware failure | Real (the original card died) | Quality storage, monitoring, backup config |

We address each below.

## SSH hardening

```bash
# /etc/ssh/sshd_config (or a drop-in in /etc/ssh/sshd_config.d/10-hardening.conf)
PermitRootLogin no
PasswordAuthentication no            # ← enable AFTER you've confirmed key auth works
PubkeyAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
PrintMotd no
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 3
LoginGraceTime 30
AllowUsers pi
```

Disable password auth **after** you've copied your key — locking yourself out is a real failure mode. Test with `ssh -o PreferredAuthentications=password pi@<ip>` before disabling; it should fail.

> 📸 **Screenshot to capture:** `screenshots/ssh-hardened.png` — `cat /etc/ssh/sshd_config.d/10-hardening.conf` showing the applied directives.

## fail2ban

```bash
sudo apt-get install -y fail2ban
sudo cp /etc/fail2ban/jail.{conf,local}
```

In `/etc/fail2ban/jail.local`, ensure `[sshd]` is active with `bantime = 1h`, `findtime = 10m`, `maxretry = 5`. Trivial to set up; high-leverage against script kiddies if SSH is ever exposed.

## Firewall (ufw)

```bash
sudo apt-get install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Only what we actually need:
sudo ufw allow from 10.0.0.0/24 to any port 22 proto tcp comment 'SSH from LAN'
sudo ufw allow from 10.0.0.0/24 to any port 53 comment 'DNS from LAN'
sudo ufw allow from 10.0.0.0/24 to any port 80 proto tcp comment 'admin UI from LAN'

sudo ufw enable
sudo ufw status verbose
```

Restrict source to `10.0.0.0/24` so even if a port-forward gets misconfigured, the Pi won't accept traffic from anywhere else.

> 📸 **Screenshot to capture:** `screenshots/ufw-status.png` — `sudo ufw status verbose` output.

## Pi-hole admin UI

Defaults are weak in two ways:

1. **HTTP-only.** Admin password goes over the wire in plaintext. On a fully-trusted home LAN this is acceptable; in any larger network, put it behind a reverse proxy with TLS (Caddy is two lines of config and gets a valid cert if you have a domain pointed at the LAN — otherwise self-signed).

2. **Default port 80 reachable.** The `ufw` rule above already restricts source IPs. Beyond that, consider:
   - Renaming the admin path
   - Restricting the admin UI to your workstation IP only

## Unattended security upgrades

```bash
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades   # answer "Yes"
```

Default behavior installs Debian security updates automatically. Pi-hole and unbound get rolled in via apt as well. The Pi will reboot itself if needed (configurable).

For a piece of LAN infra, **get this on**. Pi-hole has had real CVEs (notably CVE-2020-11108 RCE in the admin UI). You don't want to be the person whose home network was owned because a 2-year-old vuln went unpatched.

## Monitoring + alerting

The Pi crashing silently is the worst-case operational failure. Two layers:

**1. Self-test from another machine.** A cron on your workstation that pings DNS every 5 minutes and emails/notifies if it fails:

```bash
#!/bin/bash
# /usr/local/bin/check-pihole.sh
if ! dig @10.0.0.163 +short +time=2 +tries=1 cloudflare.com >/dev/null; then
    notify-send "Pi-hole down" "DNS resolution via Pi failed at $(date)"
fi
```

Crontab: `*/5 * * * * /usr/local/bin/check-pihole.sh`.

**2. SD-card health.** Even without the original card's failures, microSDs in 24/7 service degrade. Add to /etc/fstab:

```
# Reduce write amplification on the SD card
tmpfs   /tmp    tmpfs   defaults,nosuid,nodev   0 0
tmpfs   /var/log/pihole/  tmpfs   defaults,nosuid,nodev,size=64m   0 0
```

Trade-off: logs lost on reboot. Worth it if the alternative is a card that dies in 6 months.

> 📸 **Screenshot to capture:** `screenshots/monitoring.png` — output of `dig @10.0.0.163 +short cloudflare.com` from another machine, demonstrating end-to-end check.

## Backup the config

Periodically:

```bash
ssh pi@10.0.0.163 "P='<password>'; echo \$P | sudo -S pihole -a -t" \
    > backups/pihole-teleporter-$(date +%F).tar.gz
```

`pihole -a -t` creates a "teleporter" archive containing all blocklists, allowlists, custom rules, and config. Restoring is a one-line operation. Keep at least the last 4 weekly snapshots.

## Public exposure

If any of these are true, **change them**:

- Pi's port 22 / 53 / 80 forwarded from the WAN — DON'T. There is no good reason to.
- Pi-hole admin UI accessible from outside the LAN — DON'T. If you need remote access, route it through Tailscale or a WireGuard VPN, never direct.
- Pi running as an open recursive resolver on a public IP — DON'T. Open resolvers get conscripted into DNS amplification DDoS attacks. If you're publicly reachable on UDP/53, use response-rate-limiting at minimum, but really, just don't.

## The defense-in-depth picture

Pi-hole + the above hardening gives you:

- **DNS filtering** for trackers/malware (the original goal)
- **A logged DNS audit trail** for every device
- **A hardened SSH endpoint** suitable for being a long-term LAN box
- **Automated patching** so old vulns don't pile up
- **Monitoring** so you know when it breaks before your roommate does

This is now infrastructure. Treat it accordingly: snapshot configs in git, document changes, don't tinker without a backup.
