#!/usr/bin/env bash
# Register the weekly W116c LLM addendum generator on Hetzner.
#
# ADR-087 Phase D loop #4 (after W116b PBS post-mortem). Reads recent
# anti-skill post_mortem audit rows, calls the LLM via claude-runner
# (ADR-009 Voie D : Max plan, ZERO Anthropic API spend, ADR-023 Haiku
# low effort), inserts generated addendum text into `pass3_addenda`.
# Pass-3 stress prompts then consume those addenda via the round-22
# stage-2 caller wire (gated by `pass3_addenda_injection_enabled`).
#
# Scheduled at Sunday 19:00 Europe/Paris :
#   * After the W116b PBS post-mortem cron (Sunday 18:00) — depends on
#     its `loop_kind='post_mortem'` audit rows as input.
#   * Wall-time : ~5-10 s per pocket × 10 max pockets = 1-2 min total.
#   * Rate-limit guard : default --max-pockets 10 caps weekly LLM
#     calls at 10 per Sunday, well within Max plan tolerance.
#
# Smoke verify after install :
#   systemctl list-timers ichor-addendum-generator.timer --no-pager
#   journalctl -u ichor-addendum-generator.service --since "1 week ago" --no-pager | tail -30
#   psql -d ichor -c "SELECT count(*) FROM pass3_addenda WHERE status='active' AND created_at > now() - interval '7 days';"
#   psql -d ichor -c "SELECT count(*) FROM auto_improvement_log WHERE loop_kind='meta_prompt' AND ran_at > now() - interval '7 days';"
#
# ADR-087 invariants this timer respects :
#   * Gated by feature_flag `w116c_llm_addendum_enabled` (default
#     False) — fail-closed when disabled, no LLM call ever happens.
#   * loop_kind='meta_prompt' for the W116c audit row (matches the
#     ADR-087 enum ; W117 GEPA also writes meta_prompt).
#   * ADR-017 regex filter on generated text (defense-in-depth
#     beyond the prompt's NO TRADE SIGNALS instruction).
#   * Voie D : zero `import anthropic` — routes via
#     ichor_agents.claude_runner.call_agent_task_async ONLY.

set -euo pipefail

# OnFailure drop-in dir must exist BEFORE the heredoc writes to it.
mkdir -p /etc/systemd/system/ichor-addendum-generator.service.d

cat > /etc/systemd/system/ichor-addendum-generator.service <<'EOF'
[Unit]
Description=Ichor W116c LLM addendum generator (ADR-087 Phase D loop #4)
After=network-online.target postgresql.service ichor-post-mortem-pbs.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
# Default flags : 7 d window, 10 pockets max per run. Tune via override
# drop-in if needed. The 10-pocket cap is the rate-limit guard against
# Max plan abuse detection.
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_addendum_generator
TimeoutStartSec=1800
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-addendum-generator.service.d/notify.conf <<'EOF'
[Unit]
OnFailure=ichor-notify@%n.service
EOF

cat > /etc/systemd/system/ichor-addendum-generator.timer <<'EOF'
[Unit]
Description=Ichor W116c addendum generator trigger (weekly Sunday 19:00 Paris)

[Timer]
OnCalendar=Sun *-*-* 19:00:00 Europe/Paris
Unit=ichor-addendum-generator.service
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-addendum-generator.timer

echo "=== Installed W116c LLM addendum generator timer ==="
systemctl list-timers ichor-addendum-generator.timer --no-pager
