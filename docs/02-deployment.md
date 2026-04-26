# 02 · Deployment

This doc captures the actual build, decisions made, and verification at each step.

## Pre-flight

| Decision | Choice | Reasoning |
|---|---|---|
| Hardware | Raspberry Pi 5 (8GB) | Way overkill for Pi-hole alone, leaves headroom for adding Suricata/Zeek later |
| OS | Raspberry Pi OS Lite (Bookworm, arm64) | No GUI overhead; this is a server |
| Hostname | `pihole` | Matches role; descriptive over creative |
| User | `pi` (SSH key auth + password fallback) | Standard, password kept for easy bring-up |
| IP | `10.0.0.163` (DHCP, will be reserved later) | Stable address required so other devices can reliably point to it |
| Upstream DNS | Cloudflare 1.1.1.1 / 1.0.0.1 (fallback only) | unbound handles primary recursion; Cloudflare is backup |
| Recursive resolver | `unbound` on 127.0.0.1:5335 | Avoids depending on any single upstream provider |

## Step 1 — Bringing the Pi online without a display

The SD card was flashed with Raspberry Pi OS Lite. To enable headless SSH on first boot, the boot partition needs:

- Empty file named `ssh` → enables SSHd at boot
- File `userconf.txt` with `pi:<hashed-password>` → creates the user (modern Pi OS no longer ships a default `pi/raspberry` account)

```bash
# On a workstation, with the SD card mounted at /media/$USER/bootfs
touch /media/$USER/bootfs/ssh
echo "pi:$(echo 'TEMP_PASSWORD' | openssl passwd -6 -stdin)" > /media/$USER/bootfs/userconf.txt
sync && udisksctl unmount -b /dev/sda1
```

> 📸 **Screenshot to capture:** `screenshots/01-flashed-card.png` — `ls /media/$USER/bootfs/` showing `ssh` and `userconf.txt` files present.

The Pi was then plugged into the LAN switch and powered on. After ~90 seconds it was discoverable via `nmap`.

### Gotcha: NordVPN blocked LAN discovery

A NordVPN client running on the workstation had `LAN Discovery: disabled` and `ARP Ignore: enabled`. This caused `nmap -sn 10.0.0.0/24` to only see the gateway and self. Fix:

```bash
nordvpn set lan-discovery on
nordvpn set arp-ignore off
```

Worth flagging for any home lab — VPN clients aggressively isolate the local LAN by default.

## Step 2 — SSH access and key auth

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C "workstation -> pihole"
ssh-copy-id pi@10.0.0.163
ssh pi@10.0.0.163  # passwordless from this point
```

Password authentication is **kept enabled** for now, since the Pi may be rebuilt during the lab phase. After production stabilization, password auth can be disabled in `/etc/ssh/sshd_config` (`PasswordAuthentication no`).

## Step 3 — System update + hostname + timezone

```bash
sudo apt-get update
sudo apt-get -y upgrade
sudo hostnamectl set-hostname pihole
sudo sed -i 's/raspberrypi/pihole/g' /etc/hosts
sudo timedatectl set-timezone America/Denver
```

> 📸 **Screenshot to capture:** `screenshots/02-pi-baseline.png` — output of `hostnamectl` and `timedatectl status` showing the updated values.

## Step 4 — Install Pi-hole (unattended)

The official installer is interactive, but it accepts `--unattended` if `/etc/pihole/setupVars.conf` is pre-populated. Our config:

```ini
# /etc/pihole/setupVars.conf
PIHOLE_INTERFACE=eth0
IPV4_ADDRESS=10.0.0.163/24
IPV6_ADDRESS=
PIHOLE_DNS_1=127.0.0.1#5335    # unbound (primary)
PIHOLE_DNS_2=1.1.1.1            # Cloudflare (fallback)
QUERY_LOGGING=true
INSTALL_WEB_SERVER=true
INSTALL_WEB_INTERFACE=true
LIGHTTPD_ENABLED=true
CACHE_SIZE=10000
DNS_FQDN_REQUIRED=true
DNS_BOGUS_PRIV=true
DNSMASQ_LISTENING=local
BLOCKING_ENABLED=true
DNSSEC=false                    # unbound handles DNSSEC; don't double up
```

> Note: `unbound` is installed and configured *before* Pi-hole, so the `127.0.0.1#5335` upstream is already live when Pi-hole points to it.

Install:

```bash
curl -sSL https://install.pi-hole.net | sudo PIHOLE_SKIP_OS_CHECK=true bash -s -- --unattended
```

> 📸 **Screenshot to capture:** `screenshots/03-pihole-install.png` — terminal output of the install completing, showing the admin URL and the generated web password.

## Step 5 — Install + configure unbound

```bash
sudo apt-get -y install unbound

# Pull root hints
sudo curl -o /var/lib/unbound/root.hints https://www.internic.net/domain/named.root
sudo chown unbound:unbound /var/lib/unbound/root.hints
```

Config file: `/etc/unbound/unbound.conf.d/pi-hole.conf` — see `configs/unbound-pi-hole.conf` in this repo for the full file.

Restart and verify:

```bash
sudo systemctl restart unbound
sudo systemctl status unbound --no-pager | head -12

# Test resolution directly through unbound
dig @127.0.0.1 -p 5335 github.com +short
# Expect: an IP, with reasonable latency
```

> 📸 **Screenshot to capture:** `screenshots/04-unbound-test.png` — terminal output of the `dig` command resolving via unbound on port 5335.

## Step 6 — Verification (without touching the router)

This is the safe testing step. We confirm Pi-hole works **from one machine** before promoting it to the whole network.

From a workstation on the same LAN:

```bash
# Allowed domain — should resolve normally
dig @10.0.0.163 github.com +short

# Known-blocked domain — should return 0.0.0.0 or NXDOMAIN
dig @10.0.0.163 doubleclick.net +short
```

> 📸 **Screenshot to capture:** `screenshots/05-block-test.png` — both `dig` outputs side by side, one resolving and one blocked.

Visit `http://10.0.0.163/admin/` in a browser → log in with the password from Step 4.

> 📸 **Screenshot to capture:** `screenshots/06-pihole-dashboard.png` — fresh Pi-hole dashboard.

## Step 7 — LAN promotion (when ready)

> ⚠️ **This is the one step that affects the whole network.** Schedule it for a moment when nothing important is using the network. Avoid mid-game / mid-call windows.

Two options:

**Option A — set the Pi as DNS via the router (recommended).** Log into the router admin UI → DHCP / LAN settings → set primary DNS to `10.0.0.163`, secondary to `1.1.1.1`. Devices will pick up the change as their DHCP leases renew (or you can force it by reconnecting Wi-Fi).

**Option B — manual per-device.** Set DNS on each device manually. Tedious but doesn't require router admin.

After promotion, **reserve the Pi's IP** in the router so it never changes:

- Router admin UI → DHCP → Address Reservations → bind MAC `xx:xx:xx:xx:xx:xx` to `10.0.0.163`.

> 📸 **Screenshot to capture:** `screenshots/07-router-dns.png` — router DNS settings after change. (Redact your gateway public IP if the screenshot would show it.)

## Step 8 — Sanity check after promotion

```bash
# From a freshly-leased device
nslookup doubleclick.net
# Should return 0.0.0.0
```

Pi-hole dashboard → "Query Log" should show queries from multiple client IPs, not just the one test workstation.

> 📸 **Screenshot to capture:** `screenshots/08-multi-client-traffic.png` — Pi-hole "Top Clients" widget showing several active LAN devices.

## What's in `configs/`

- `unbound-pi-hole.conf` — full unbound config we deployed
- `unbound-pi-hole.conf.live` — copy pulled back from the running Pi (for diff/audit)
- `setupVars.conf` — Pi-hole initial config (sanitized — no password)
- `pihole.toml.live` — Pi-hole v6 generated config after install (sanitized snapshot)

These are committed so the deployment is reproducible from scratch.

## Gotchas hit during this build

Real things that bit during this deployment, captured so future-me doesn't repeat them.

### NordVPN + LAN discovery

A NordVPN client running on the workstation blocked LAN scanning (`nmap -sn` only saw the gateway and self) and later blocked DNS queries to the Pi specifically — even though `ping` worked. Diagnosis path:

- `nordvpn settings` → `LAN Discovery: disabled`, `ARP Ignore: enabled` were the culprits for discovery
- For DNS specifically: NordVPN's nftables rules apparently catch outbound port 53 separately, even with LAN discovery on. Threat Protection Lite off didn't fix it; `nordvpn allowlist add subnet` is rejected when LAN discovery is on.
- Net effect: **the workstation can't query the Pi for DNS while NordVPN is connected**. Other devices on the LAN are unaffected.
- Workaround for testing: SSH into the Pi and `dig @127.0.0.1` from there, or query from a phone.

### `auto-trust-anchor-file` declared twice

Including `auto-trust-anchor-file: "/var/lib/unbound/root.key"` in our custom unbound config caused unbound to fail to start because Debian's package ships `/etc/unbound/unbound.conf.d/root-auto-trust-anchor-file.conf` which already declares it. Symptom: `unbound-checkconf` reports `error in trustanchors config`. Fix: don't redeclare; the Debian default is sufficient.

### Pi-hole v6 setupVars.conf migration

The installer accepted our pre-staged `/etc/pihole/setupVars.conf` and migrated it to `/etc/pihole/pihole.toml`. **However**, immediately after install, `pihole reloadlists` failed with `FTL_PID_FILE: readonly variable` (a script bug in `utils.sh`), and `pihole-FTL` did not pick up gravity at runtime — every query was forwarded upstream, blocking 0%. A hard `systemctl restart pihole-FTL` after install reloaded gravity correctly. **Always restart FTL after the unattended installer finishes**, until this script bug is fixed upstream.

### Original SD card had filesystem corruption

The first card we used reported `EFSBADCRC` errors on inode 185016 *during the apt upgrade*, mid-deployment. The card was a microSD in a USB reader (per `lsusb`: `Super Top microSD card reader`). For Pi-hole acting as the LAN's DNS, dying media is a non-starter — we wiped, reflashed onto a fresh card, and resumed from this exact step. Capturing here as a reminder: **use known-good media for infra Pis**, ideally a quality USB SSD or at minimum a Samsung Endurance / SanDisk High Endurance microSD.
