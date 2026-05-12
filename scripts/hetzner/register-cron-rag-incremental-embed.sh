#!/usr/bin/env bash
# Register the nightly RAG incremental-embed runner on Hetzner.
#
# W110g — ADR-086 Phase C. Embeds NEW session_card_audit rows generated
# in the last 36 h (over-cover the 24 h cron jitter window) into
# `rag_chunks_index`. Idempotent — `embed_session_cards.py` skips cards
# already present by (source_type='session_card', source_id=card.id).
#
# Scheduled at 03:00 Europe/Paris :
#   * AFTER the reconciler (02:00) so today's session-window outcomes
#     are persisted on the cards before we embed them.
#   * BEFORE the Brier optimizer (03:30) — irrelevant ordering, but
#     keeps the nightly cluster compact.
#   * Wall-time : ~5-30 s for a normal day (32 cards × ~40 ms ONNX CPU).
#     If the embed model isn't downloaded yet, first run pays a one-shot
#     ~5-10 s warmup ; cached under `/var/lib/ichor/hf-cache/` thereafter.
#
# Smoke verify after install :
#   systemctl list-timers ichor-rag-incremental-embed.timer --no-pager
#   journalctl -u ichor-rag-incremental-embed.service --since today --no-pager | tail -50
#   psql -d ichor -c "SELECT count(*) FROM rag_chunks_index WHERE indexed_at > now() - interval '1 day';"
#
# ADR-086 invariants this timer respects :
#   * Past-only retrieval (Invariant 1) — this timer is a WRITER, so the
#     embargo applies on the READ path (`retrieve_analogues`).
#   * Voie D (Invariant 2) — bge-small-en-v1.5 ONNX CPU, self-hosted,
#     no paid API. Model + tokenizer cached locally after first warmup.
#   * Cap5 exclusion (Invariant 3) — `rag_chunks_index` not in
#     `services.tool_query_db.ALLOWED_TABLES` ; the W110e CI guard
#     enforces this on every CI run.

set -euo pipefail

# The 36 h cushion documented below is implemented via the CLI flag
# `--days 2` in the systemd unit (systemd has no shell expansion) +
# `Persistent=true` on the timer (catches up missed runs). Idempotent
# skip-by-source_id makes over-coverage safe.

cat > /etc/systemd/system/ichor-rag-incremental-embed.service <<'EOF'
[Unit]
Description=Ichor RAG incremental embed (W110g ADR-086 Phase C)
After=network-online.target postgresql.service ichor-reconciler.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
# Cache the HF model files in a stable location so the first warmup
# pays only once across reboots + venv resets. The ichor user must
# own this dir : `install -d -o ichor -g ichor /var/lib/ichor/hf-cache`.
Environment=HF_HOME=/var/lib/ichor/hf-cache
Environment=SENTENCE_TRANSFORMERS_HOME=/var/lib/ichor/hf-cache
# --days 2 covers the last 48 h of cards ; idempotent skip-by-source_id
# handles overlap from previous runs. --batch-size 50 = ~150 KB per
# commit. (systemd unit files have no shell expansion, hence the
# CLI-side --days flag instead of $(date) substitution.)
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.embed_session_cards \
    --days 2 \
    --batch-size 50
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-rag-incremental-embed.timer <<'EOF'
[Unit]
Description=Ichor RAG incremental embed trigger (nightly 03:00 Paris)

[Timer]
OnCalendar=*-*-* 03:00:00 Europe/Paris
Unit=ichor-rag-incremental-embed.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Ensure the model-cache dir exists with correct ownership.
install -d -o ichor -g ichor -m 0755 /var/lib/ichor/hf-cache

systemctl daemon-reload
systemctl enable --now ichor-rag-incremental-embed.timer

echo "=== Installed RAG incremental embed timer ==="
systemctl list-timers ichor-rag-incremental-embed.timer --no-pager
