# Pi-hole lab — one-shot commands for the common workflows.
# Override defaults at the command line, e.g.:
#   make dga DB=./pihole-FTL.db HOURS=12

DB     ?= /etc/pihole/pihole-FTL.db
HOURS  ?= 24
TOP    ?= 25

PYTHON ?= python3

.PHONY: help doh canary-install canary-watch dga profile correlate \
        monitoring-up monitoring-down monitoring-logs

help:
	@echo "Targets:"
	@echo "  doh             Run DoH/DoT bypass detector"
	@echo "  canary-install  Install canary domains on the Pi-hole host"
	@echo "  canary-watch    Run the canary watcher once"
	@echo "  dga             Run DGA triage (top $(TOP) over $(HOURS)h)"
	@echo "  profile         Generate per-device DNS profile to docs/"
	@echo "  correlate       Run Suricata × Pi-hole correlation"
	@echo "  monitoring-up   docker compose up the Prometheus/Grafana stack"
	@echo "  monitoring-down Tear it down"
	@echo "  monitoring-logs Tail the stack logs"

doh:
	$(PYTHON) tools/doh_dot_detector/detect_doh_attempts.py --db $(DB) --hours $(HOURS)

canary-install:
	sudo ./tools/canary/install.sh

canary-watch:
	sudo $(PYTHON) tools/canary/watch_canaries.py --db $(DB) --window-min 60

dga:
	$(PYTHON) tools/dga_detector/dga_detector.py --db $(DB) --hours $(HOURS) --top $(TOP)

profile:
	$(PYTHON) tools/device_profile/device_profile.py \
		--db $(DB) --hours $(HOURS) \
		--names tools/device_profile/names.json \
		--out docs/03-analysis-device-table.md

correlate:
	$(PYTHON) tools/suricata_correlation/correlate_dns_flows.py \
		--ftl $(DB) --hours $(HOURS)

monitoring-up:
	cd monitoring && docker compose up -d

monitoring-down:
	cd monitoring && docker compose down

monitoring-logs:
	cd monitoring && docker compose logs -f --tail=100
