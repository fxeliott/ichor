#!/usr/bin/env bash
# Register extended Phase 2 collectors as systemd timers on Hetzner.
#
# Phase 1 timers stay (rss/polymarket/market_data/polygon — registered
# by register-cron-collectors.sh).
#
# Phase 2 adds:
#   - flashalpha (GEX SPX/NDX, twice daily within free-tier 5/d budget)
#   - vix_live (VIX yfinance, every 5 min during US session)
#   - aaii (AAII sentiment weekly, Thursdays 16:00 ET)
#   - bls (BLS labor stats, daily 05:00 Paris)
#   - ecb_sdmx (ECB macro series, daily 05:30 Paris)
#   - dts_treasury (US Treasury cash daily, 04:00 Paris)
#   - boe_iadb (BoE rates, daily 05:00 Paris)
#   - eia_petroleum (oil stocks weekly Wed + STEO monthly)
#   - finra_short (short interest semi-monthly + daily volume)
#   - bluesky (CB officials feed, every 30 min)
#   - yfinance_options (options chains, twice daily)
#
# Phase 2 sweep also formalizes timers for Phase 1 collectors that
# previously had implementations but no dedicated schedule:
#   - fred / fred_extended (FRED REST, 2x/day staggered)
#   - gdelt (GDELT 2.0 DOC, every 30 min — upstream cadence is 15 min)
#   - ai_gpr (Caldara-Iacoviello daily, 23:00 Paris)
#   - cot (CFTC weekly, Sat 02:00 Paris after Fri 15:30 ET release)
#   - central_bank_speeches (BIS + per-CB feeds, every 4h offset +15 min)
#   - kalshi / manifold (prediction markets, every 15 min)
#   - polygon_news (Polygon /v2/reference/news, every 30 min)
#   - forex_factory (FairEconomy weekly XML, 4× per day to catch consensus
#                    revisions ; persists into economic_events table)
#   - mastodon (ATOM feeds for instances/handles/tags listed in
#               ICHOR_API_MASTODON_FOLLOWED_FEEDS env ; persists into
#               news_items with source_kind="social" ; 30-min cadence)
#
# Each timer triggers a oneshot service that loads /etc/ichor/api.env,
# runs the collector via `python -m ichor_api.cli.run_collectors
# <name> --persist`. Same env pattern as every other ichor-* service
# (corrected 2026-05-06 — the original draft referenced a tmpfs-encrypted
# secrets file that was never deployed and silently broke the
# ichor-collector@ template, taking out fred + gdelt + polygon when
# extended ran. Cf. ADR-024 §"Operational drift" and the matching
# fix in register-cron-couche2.sh).

set -euo pipefail

# Service template (single binary, collector name passed as arg).
cat > /etc/systemd/system/ichor-collector@.service <<'EOF'
[Unit]
Description=Ichor collector runner (%i)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_collectors %i --persist
TimeoutStartSec=600
SuccessExitStatus=0 1
StandardOutput=journal
StandardError=journal
EOF

# Timers — staggered to avoid CPU bursts and respect free-tier rate limits.
#
# Cadence rationale (validated against upstream publishing schedules) :
#   - GDELT 2.0 publishes every 15 min → poll 30 min (we don't need realtime)
#   - CFTC COT releases Fri ~15:30 ET ≈ 21:30 Paris (winter) → fetch Sat 02h
#   - AI-GPR daily file updated in late afternoon US → fetch 23h Paris
#   - FRED series mostly daily → 2× per day (06h + 18h Paris) with random delay
#   - BIS / CB speeches feed every few hours → 4h cadence is enough
#   - Kalshi/Manifold odds shift continuously → 15 min is the sweet spot
#   - Polygon news API is real-time but quota-limited → 30 min batch
declare -A SCHEDULES=(
  # Phase 2 capabilities (existing)
  [flashalpha]="*-*-* 13,21:00:00 Europe/Paris"
  [vix_live]="*:0/5"
  [aaii]="Thu *-*-* 22:30:00 Europe/Paris"
  [bls]="*-*-* 05:00:00 Europe/Paris"
  [ecb_sdmx]="*-*-* 05:30:00 Europe/Paris"
  [dts_treasury]="*-*-* 04:00:00 Europe/Paris"
  [boe_iadb]="*-*-* 05:15:00 Europe/Paris"
  [eia_petroleum]="*-*-* 18:00:00 Europe/Paris"
  [finra_short]="Mon,Tue,Wed,Thu,Fri *-*-* 23:30:00 Europe/Paris"
  [bluesky]="*:0/30"
  [yfinance_options]="*-*-* 14,21:30:00 Europe/Paris"
  # Phase 1 collectors that lacked dedicated timers (added Phase 2 sweep)
  [fred]="*-*-* 06,18:00:00 Europe/Paris"
  [fred_extended]="*-*-* 06,18:30:00 Europe/Paris"
  [gdelt]="*:0/30"
  [ai_gpr]="*-*-* 23:00:00 Europe/Paris"
  # CBOE SKEW daily — published 16:15 ET (~22:15 Paris), poll 23:30 Paris.
  # Source: Yahoo Finance public chart endpoint for ^SKEW (Voie D-compliant,
  # no API key, no paid tier). Wave 24 Phase II Layer 1 add.
  [cboe_skew]="*-*-* 23:30:00 Europe/Paris"
  # CBOE VVIX (vol of VIX) daily — same Yahoo path as SKEW, +5 min stagger.
  # Used alongside SKEW to characterize the full vol-surface state.
  # Wave 29 Phase II Layer 1 add. Voie D-compliant (no API key).
  [cboe_vvix]="*-*-* 23:35:00 Europe/Paris"
  # CME ZQ Fed Funds futures front-month — daily 23:40 Paris (after CBOT
  # ZQ close 17:00 ET ≈ 23:00 Paris). Source: Yahoo Finance ZQ=F. Implied
  # EFFR = 100 - ZQ_price. Wave 47 mini-FedWatch DIY.
  [cme_zq]="*-*-* 23:40:00 Europe/Paris"
  [cot]="Sat *-*-* 02:00:00 Europe/Paris"
  # CFTC TFF (Traders in Financial Futures) weekly — published Friday
  # ~15:30 ET (~21:30 Paris), data Tuesday close. Poll Saturday 02:30 Paris.
  # Source: CFTC Socrata SODA endpoint resource gpe5-46if (TFF Futures-Only).
  # Wave 25 Phase II Layer 1 add. Provides 4-class positioning (Dealer /
  # AssetMgr / LevFunds / Other / Nonrept) per market, used for smart-money
  # divergence detection and macro-fund positioning intelligence.
  [cftc_tff]="Sat *-*-* 02:30:00 Europe/Paris"
  # Treasury TIC Major Foreign Holders monthly. Releases ~3rd week of M+1.
  # Calendar 2026: Jan 15 / Feb 18 / Mar 18 / Apr 15 / May 18 / Jun 18 /
  # Jul 14 / Aug 17. Poll daily 03:00 Paris is conservative — the file
  # rarely updates, idempotent dedup catches no-op runs.
  [treasury_tic]="*-*-* 03:00:00 Europe/Paris"
  # NY Fed Multivariate Core Trend monthly inflation (Wave 71).
  # Released ~1st business day of the month following BEA PCE print
  # (~10:00 ET = 16:00 Paris). Poll daily 17:00 Paris is conservative —
  # CSV is small (~70 KB), idempotent dedup catches no-op runs.
  [nyfed_mct]="*-*-* 17:00:00 Europe/Paris"
  # Note: collector module is `central_bank_speeches.py` but exposed under
  # the canonical short name `cb_speeches` in run_collectors.py:33 (alias).
  # Keep the timer aligned with the CLI target name to avoid the
  # systemd timer creating a service that exits 2 (INVALIDARGUMENT).
  # Doublon `central_bank_speeches.timer` removed on Hetzner 2026-05-08.
  [cb_speeches]="*-*-* 00,04,08,12,16,20:15:00 Europe/Paris"
  [kalshi]="*:0/15"
  [manifold]="*:0/15"
  [polygon_news]="*:0/30"
  # ForexFactory weekly XML — refresh 4×/day to catch consensus revisions
  # (forecast/previous columns change as economists update their numbers).
  [forex_factory]="*-*-* 03,09,15,21:30:00 Europe/Paris"
  # Mastodon ATOM feeds — config-driven via ICHOR_API_MASTODON_FOLLOWED_FEEDS.
  # No-ops silently if env is empty. 30-min cadence is enough for social
  # signal aggregation (decentralized macro commentary, not high-frequency).
  [mastodon]="*:0/30"
)

for name in "${!SCHEDULES[@]}"; do
  cat > /etc/systemd/system/ichor-collector-"${name}".timer <<EOF
[Unit]
Description=Ichor collector trigger (${name})

[Timer]
OnCalendar=${SCHEDULES[$name]}
Unit=ichor-collector@${name}.service
RandomizedDelaySec=60
Persistent=true

[Install]
WantedBy=timers.target
EOF
done

systemctl daemon-reload

# Enable + start
for name in "${!SCHEDULES[@]}"; do
  systemctl enable --now ichor-collector-"${name}".timer
done

echo "=== Installed Phase 2 collector timers (${#SCHEDULES[@]}) ==="
systemctl list-timers --no-pager | grep ichor-collector

echo ""
echo "Next runs:"
for name in "${!SCHEDULES[@]}"; do
  systemctl list-timers ichor-collector-"${name}".timer --no-pager 2>&1 | tail -2 | head -1
done
