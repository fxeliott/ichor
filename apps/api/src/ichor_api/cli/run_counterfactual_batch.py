"""CLI runner for the weekly Pass 5 counterfactual batch.

Wires the existing POST /v1/sessions/{id}/counterfactual endpoint
into a weekly cron that probes the latest session card per asset
with a "drop the top catalyst" counter-scenario, then logs the
robustness_score for the post-mortem to digest.

Algorithm :
  1. For each Phase 1 asset, fetch the most recent session_card_audit
     row (composite PK ; ORDER BY generated_at DESC LIMIT 1).
  2. Pick a scrubbed_event from the card's catalysts JSON (first entry's
     "label" or "title" field). If catalysts is empty, fall back to a
     generic "if the dominant macro driver had not materialized".
  3. Call the apps/api Pass 5 endpoint via httpx (loopback, no auth
     since we run on the same host) — it persists into
     session_card_counterfactuals + returns the parsed result.
  4. Print a one-line summary per asset.

Cadence : weekly Sun 20:00 Europe/Paris (1h after post-mortem at
19:00 — the post-mortem already has fresh Brier deltas, this batch
gives it next week's robustness signal).

Skips gracefully when ICHOR_API_CLAUDE_RUNNER_URL is empty (Pass 5
needs Claude). The endpoint enforces the same requirement and
returns 503, which we log and continue.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from sqlalchemy import desc, select

from ..config import get_settings
from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit

log = structlog.get_logger(__name__)

# Same Phase 1 universe as run_har_rv / run_hmm_regime.
ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
)

_LOOKBACK_DAYS = 7
_DEFAULT_SCRUB = "if the dominant macro driver from this week had not materialized"


def _pick_scrub_event(catalysts) -> str:
    """Extract a short scrubbed_event from the card's catalysts JSON."""
    if not catalysts:
        return _DEFAULT_SCRUB
    # Common shapes : list[str], list[dict], dict
    if isinstance(catalysts, list) and catalysts:
        head = catalysts[0]
        if isinstance(head, str):
            return head[:480]
        if isinstance(head, dict):
            for key in ("label", "title", "name", "event", "text"):
                v = head.get(key)
                if isinstance(v, str) and v:
                    return v[:480]
    if isinstance(catalysts, dict):
        for key in ("label", "title", "primary"):
            v = catalysts.get(key)
            if isinstance(v, str) and v:
                return v[:480]
    return _DEFAULT_SCRUB


async def _latest_card_for_asset(session, *, asset: str, since: datetime):
    stmt = (
        select(SessionCardAudit)
        .where(
            SessionCardAudit.asset == asset,
            SessionCardAudit.generated_at >= since,
        )
        .order_by(desc(SessionCardAudit.generated_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _trigger_pass5(
    *, base_url: str, card_id: str, scrubbed_event: str, client: httpx.AsyncClient
) -> tuple[int, dict | None]:
    """POST /v1/sessions/{card_id}/counterfactual. Returns (status, body|None)."""
    url = f"{base_url}/v1/sessions/{card_id}/counterfactual"
    try:
        r = await client.post(url, json={"scrubbed_event": scrubbed_event})
        body = None
        try:
            body = r.json()
        except ValueError:
            pass
        return r.status_code, body
    except httpx.HTTPError as e:
        log.warning("pass5_batch.http_error", card_id=card_id, error=str(e)[:200])
        return 0, None


async def run(*, persist: bool, base_url: str | None = None) -> int:
    settings = get_settings()
    if not settings.claude_runner_url:
        print(
            "Pass 5 batch · ICHOR_API_CLAUDE_RUNNER_URL is empty — skipping. "
            "(Pass 5 needs the claude-runner Voie D ; configure to enable.)",
            file=sys.stderr,
        )
        return 0

    # Default to localhost — the cron runs on the same machine as the API.
    api_base = base_url or f"http://127.0.0.1:{settings.port}"

    sm = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS)

    async with sm() as session:
        cards = []
        for asset in ASSETS:
            card = await _latest_card_for_asset(session, asset=asset, since=since)
            if card is not None:
                cards.append(card)

    print(f"Pass 5 batch · {len(cards)} cards to probe (one per asset, last {_LOOKBACK_DAYS}d)")

    if not cards:
        return 0

    if not persist:
        for c in cards:
            scrub = _pick_scrub_event(c.catalysts)
            print(
                f"  [{c.asset:10s}] {c.generated_at.isoformat()} bias={c.bias_direction} "
                f"conv={c.conviction_pct:.0f}% scrub='{scrub[:80]}'"
            )
        return 0

    n_ok = 0
    n_fail = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        for card in cards:
            scrub = _pick_scrub_event(card.catalysts)
            status, body = await _trigger_pass5(
                base_url=api_base,
                card_id=str(card.id),
                scrubbed_event=scrub,
                client=client,
            )
            if status == 200 and body:
                conv_orig = card.conviction_pct
                conv_cf = body.get("counterfactual_conviction_pct", 0.0)
                delta = body.get("confidence_delta", 0.0)
                print(
                    f"  ✓ [{card.asset:10s}] orig {conv_orig:.0f}% → cf {conv_cf:.0f}% "
                    f"(δ {delta:+.2f}) scrub='{scrub[:60]}'"
                )
                n_ok += 1
            else:
                print(
                    f"  ✗ [{card.asset:10s}] HTTP {status} — {body if body else 'no body'}"
                )
                n_fail += 1

    print(f"Pass 5 batch · {n_ok} ok, {n_fail} failed")
    return 0 if n_fail == 0 else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_counterfactual_batch")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--base-url", default=None, help="API base URL (default: localhost:port)")
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, base_url=args.base_url))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
