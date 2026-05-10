# RUNBOOK-017: Activate the MyFXBook Community Outlook collector

**Goal**: turn the MyFXBook collector from `dormant` to live so retail
FX positioning ratios start populating `myfxbook_outlooks` every 4 hours.

**Time**: ~3 minutes total. ~1 minute on web, ~1 minute on Hetzner.

**Pre-requisite**: an account on https://www.myfxbook.com (Google OAuth
sign-up is fine for this part — but read step 1, the API needs more).

---

## Background

ADR-074 ratified the W77 pivot from OANDA orderbook (discontinued
Sept 2024) to MyFXBook Community Outlook (free tier, 100 req/24h
limit, IP-bound session). The collector was deployed in
**dormant mode**: it skips silently when env vars
`ICHOR_API_MYFXBOOK_EMAIL` + `ICHOR_API_MYFXBOOK_PASSWORD` are unset.

The MyFXBook v1 API is email + password classic auth — no OAuth, no
bearer token. **A Google OAuth sign-up does not give you an API
password by default.** Step 1 below sets a local password.

## Step 1 — Set a local password on MyFXBook (web, ~1 min)

1. Open https://www.myfxbook.com/settings in a browser where you're
   already logged in.
2. Look for the **Login** tab/section. The page exposes "change
   registered email address, password and set up 2-Factor
   Authentication".
3. Set a new password. Save.
4. Optionally set an email if Google OAuth didn't expose one (your
   primary Gmail is usually used as the MyFXBook email).

**Choose a password you'll only paste once** in step 2 below. The
script writes it into `/etc/ichor/api.env` (mode 0640, owner
`ichor:ichor`) and never echoes it back.

## Step 2 — Run the activation script (Hetzner, ~1 min)

```bash
ssh ichor-hetzner
sudo /opt/ichor/scripts/hetzner/activate_myfxbook.sh
```

The script will:

- Prompt for `MyFXBook email`: type it, press Enter.
- Prompt for `MyFXBook password (will not echo)`: type it, press Enter.
  (Characters are not displayed.)
- Backup `/etc/ichor/api.env` to `/etc/ichor/api.env.bak.<timestamp>`.
- Replace any existing `ICHOR_API_MYFXBOOK_*` lines, append new ones.
- Restart `ichor-api`.
- Trigger one run of `ichor-collector@myfxbook_outlook.service`.
- Query Postgres for any `myfxbook_outlooks` rows in the last 5 min.

**Expected success output** (last lines):

```
✅ 6 myfxbook_outlooks rows persisted in the last 5 min.
Latest snapshot:
 pair  | long_pct | short_pct | fetched_at
-------+----------+-----------+----------------------
 ...
✅ MyFXBook collector ACTIVATED. Timer will fire every 4h.
```

You should see one row per Ichor pair: EURUSD, GBPUSD, USDJPY,
AUDUSD, USDCAD, XAUUSD.

## Failure modes

### "❌ No rows persisted"

The script emits this when the trigger run completed but the table
is empty. Most common causes:

| Cause                                           | Fix                            |
| ----------------------------------------------- | ------------------------------ |
| Password not set on MyFXBook (Google-only auth) | Step 1 of this runbook         |
| Wrong email or password typed                   | Re-run the script              |
| MyFXBook account suspended / 2FA blocking API   | Disable 2FA temporarily, retry |
| MyFXBook free-tier rate limit (100 req/24h hit) | Wait 24h, retry                |

The journal lines printed by the script reveal the exact reason. Look
for `myfxbook.login_failed`, `myfxbook.login_rejected`, or
`myfxbook.outlook_failed`.

### "ichor-api failed to come back up after restart"

Indicates a syntactic problem in `/etc/ichor/api.env` after the
update. The script restores the backup automatically, so the previous
state is preserved. Investigate via:

```bash
sudo systemctl status ichor-api
sudo journalctl -u ichor-api -n 50
```

## Verification (one-shot DB check)

```bash
sudo -u postgres psql ichor -c \
  "SELECT pair, ROUND(long_pct::numeric,1) AS long_pct, \
          ROUND(short_pct::numeric,1) AS short_pct, fetched_at \
   FROM myfxbook_outlooks ORDER BY fetched_at DESC LIMIT 12;"
```

You should see two snapshots (12 rows total = 2 fetches × 6 pairs)
once the timer has had time to fire twice — one immediate via the
script trigger, then the next scheduled at 00:00, 04:00, 08:00,
12:00, 16:00, or 20:00 Europe/Paris.

## Deactivation (rollback)

If you want to put the collector back to dormant:

```bash
ssh ichor-hetzner
sudo sed -i \
  -e '/^ICHOR_API_MYFXBOOK_EMAIL=/d' \
  -e '/^ICHOR_API_MYFXBOOK_PASSWORD=/d' \
  /etc/ichor/api.env
sudo systemctl restart ichor-api
sudo systemctl stop ichor-collector-myfxbook_outlook.timer
sudo systemctl disable ichor-collector-myfxbook_outlook.timer
```

The DB rows already persisted are kept.

## Related

- **ADR-074** : MyFXBook replaces discontinued OANDA orderbook
- `apps/api/src/ichor_api/collectors/myfxbook_outlook.py`
- `scripts/hetzner/activate_myfxbook.sh` (this runbook's helper)
- `apps/api/src/ichor_api/services/data_pool.py:_section_myfxbook_outlook`
  (where the activated data surfaces inside data_pool)
