#!/usr/bin/env bash
# Register Wikipedia Pageviews + arXiv q-fin crons on Hetzner.
#
# - wikipedia_pageviews: macro/geo article attention proxy. Daily 06:00.
# - arxiv_qfin: latest q-fin papers as news_items academic. Daily 06:30.

set -euo pipefail

# ── wikipedia_pageviews
cat > /etc/systemd/system/ichor-wikipedia-pageviews.service <<'EOF'
[Unit]
Description=Ichor Wikipedia pageviews poller (macro article watchlist)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_collectors wikipedia_pageviews --persist
TimeoutStartSec=180
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-wikipedia-pageviews.timer <<'EOF'
[Unit]
Description=Ichor Wikipedia pageviews trigger (daily 06:00 Paris)

[Timer]
OnCalendar=*-*-* 06:00:00 Europe/Paris
Unit=ichor-wikipedia-pageviews.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

# ── arxiv_qfin
cat > /etc/systemd/system/ichor-arxiv-qfin.service <<'EOF'
[Unit]
Description=Ichor arXiv q-fin papers poller
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_collectors arxiv_qfin --persist
TimeoutStartSec=180
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-arxiv-qfin.timer <<'EOF'
[Unit]
Description=Ichor arXiv q-fin trigger (daily 06:30 Paris)

[Timer]
OnCalendar=*-*-* 06:30:00 Europe/Paris
Unit=ichor-arxiv-qfin.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-wikipedia-pageviews.timer ichor-arxiv-qfin.timer

echo "=== Installed Wiki + arXiv timers ==="
systemctl list-timers ichor-wikipedia-pageviews.timer ichor-arxiv-qfin.timer --no-pager
