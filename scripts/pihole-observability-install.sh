#!/bin/bash
# Stand up Pi-hole observability: Prometheus + Grafana + pihole-exporter + node-exporter
# Run on the Pi (the box at 10.0.0.163), as a sudoer.
# Idempotent — safe to re-run.

set -euo pipefail

STACK_DIR="/opt/pihole-stack"
PIHOLE_PASSWORD_HINT="(your rotated Pi-hole admin password — needed for the exporter to auth against the Pi-hole API)"

echo "=== install docker (official convenience script) ==="
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "(you may need to log out + back in for the docker group to apply, but sudo will work right now)"
fi
sudo systemctl enable --now docker

echo "=== create stack dir ==="
sudo mkdir -p "$STACK_DIR"/{prometheus,grafana/provisioning/datasources,grafana/provisioning/dashboards,grafana/dashboards}
sudo chown -R "$USER:$USER" "$STACK_DIR"
cd "$STACK_DIR"

echo "=== prompt for Pi-hole password (for pihole-exporter API auth) ==="
if [ ! -f .env ]; then
  read -rsp "Enter Pi-hole admin web password $PIHOLE_PASSWORD_HINT: " PIHOLE_PW
  echo
  GRAFANA_PW="$(openssl rand -base64 18)"
  cat > .env <<EOF
PIHOLE_PASSWORD=$PIHOLE_PW
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PW
EOF
  chmod 600 .env
  echo "Generated Grafana admin password (saved in .env, chmod 600):"
  echo "  $GRAFANA_PW"
  echo "Stash it in your password manager now."
else
  echo ".env already exists — reusing."
fi

echo "=== prometheus.yml ==="
cat > prometheus/prometheus.yml <<'EOF'
global:
  scrape_interval: 30s
  evaluation_interval: 30s

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ['localhost:9090']

  - job_name: node
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: pihole
    static_configs:
      - targets: ['pihole-exporter:9617']
EOF

echo "=== grafana datasource ==="
cat > grafana/provisioning/datasources/prometheus.yml <<'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF

echo "=== grafana dashboard provider ==="
cat > grafana/provisioning/dashboards/dashboards.yml <<'EOF'
apiVersion: 1
providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
EOF

echo "=== fetch community dashboards (Pi-hole + Node Exporter Full) ==="
# Pi-hole Exporter dashboard (grafana #10176) and Node Exporter Full (#1860)
curl -fsSL "https://grafana.com/api/dashboards/10176/revisions/3/download" -o grafana/dashboards/pihole.json || echo "(pihole dashboard fetch failed, continuing)"
curl -fsSL "https://grafana.com/api/dashboards/1860/revisions/37/download" -o grafana/dashboards/node-exporter.json || echo "(node-exporter dashboard fetch failed, continuing)"

echo "=== docker-compose.yml ==="
cat > docker-compose.yml <<'EOF'
services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    restart: unless-stopped
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
      - '--storage.tsdb.path=/prometheus'
    networks: [obs]

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    restart: unless-stopped
    pid: host
    network_mode: host  # so it sees real host NIC stats
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'

  pihole-exporter:
    image: ekofr/pihole-exporter:latest
    container_name: pihole-exporter
    restart: unless-stopped
    environment:
      PIHOLE_HOSTNAME: 172.17.0.1   # docker0 gateway = host
      PIHOLE_PORT: 80
      PIHOLE_PASSWORD: ${PIHOLE_PASSWORD}
      INTERVAL: 30s
      PORT: 9617
    networks: [obs]

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_AUTH_ANONYMOUS_ENABLED: "false"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    networks: [obs]

volumes:
  prometheus_data:
  grafana_data:

networks:
  obs:
    driver: bridge
EOF

echo "=== ufw: open port 3000 to LAN + tailnet (Grafana) ==="
sudo ufw allow from 10.0.0.0/24 to any port 3000 proto tcp comment "grafana-lan" || true
# tailscale0 is already wide-open from earlier setup, no rule needed for tailnet

echo "=== bring stack up ==="
sudo docker compose --env-file .env up -d
sleep 5

echo "=== container status ==="
sudo docker compose ps

echo
echo "============================================================"
echo "Grafana: http://10.0.0.163:3000  (or http://pihole.taile6ee13.ts.net:3000)"
echo "  user: admin"
echo "  pw:   see $STACK_DIR/.env on the Pi"
echo "Prometheus: http://10.0.0.163:9090 (LAN-only — not exposed to tailnet by default)"
echo "============================================================"
echo
echo "Dashboards auto-loaded: 'Pi-hole Exporter' + 'Node Exporter Full'"
echo "Give it ~60s to start scraping, then refresh Grafana."
