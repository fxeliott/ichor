#!/usr/bin/env python3
"""W102 RUNBOOK-018 Steps 1-3 automation via Cloudflare API.

**Goal** : Bypass the dashboard requirement for the CF Access service
token setup. Instead of 6 dashboard steps Eliot has to click, this
script accepts ONE CF API token (scope `Account.Cloudflare Access:Edit`
+ `Account.Service Tokens:Edit`) and creates everything via REST :

  1. (skipped if already present) Enable Access on the account.
  2. POST `/accounts/{id}/access/service_tokens` — creates the
     `ichor-hetzner-orchestrator` service token.
  3. POST `/accounts/{id}/access/apps` — creates the Self-hosted
     application for `claude-runner.fxmilyapp.com`.
  4. POST `/accounts/{id}/access/apps/{app_id}/policies` — adds the
     Service-Auth Allow policy + the `/healthz` Bypass policy.
  5. Prints the 4 values (`team_domain`, `AUD_TAG`, `CLIENT_ID`,
     `CLIENT_SECRET`) that the Hetzner-side (Steps 4-5) needs.

**Pre-requisite** : a CF API token with these scopes :
  - Account.Cloudflare Access:Edit
  - Account.Service Tokens:Edit
  - User → User Details:Read (for /user/tokens/verify smoke test)

Create one at `dash.cloudflare.com → My Profile → API Tokens →
Create Custom Token`. Restrict to the relevant Account + Zone for
defence in depth.

**Usage** :

  export CF_API_TOKEN=<the token from dash>
  export CF_ACCOUNT_ID=<your CF account id, visible bottom-right
                       of any zone page>
  python scripts/setup-cf-access.py \
      --hostname claude-runner.fxmilyapp.com \
      --service-token-name ichor-hetzner-orchestrator

The script :
  - Verifies the token + account ID by hitting `/user/tokens/verify`.
  - Checks for existing service token / application — re-uses them
    if found (idempotent).
  - Prints the 4 values to stdout in the exact paste-template format
    RUNBOOK-018 expects.

**Security** : The `CLIENT_SECRET` is returned by CF API exactly ONCE
on creation. This script prints it to stdout — capture it
immediately (e.g. `python scripts/setup-cf-access.py | tee /tmp/cf-
out.txt`) and rotate to a password manager. Stdout is the only place
it lands.

**Boundary** : This script does NOT touch Hetzner / Win11. After it
runs, copy the 4 values into the chat and Claude finishes Steps 4-6
automatically (SSH api.env edit + restart + verification curls).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

try:
    import httpx
except ImportError:
    print("This script needs httpx : `pip install httpx`", file=sys.stderr)
    sys.exit(2)

CF_API = "https://api.cloudflare.com/client/v4"


def _api_call(
    token: str, method: str, path: str, *, json_body: dict[str, Any] | None = None
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as client:
        r = client.request(method, f"{CF_API}{path}", headers=headers, json=json_body)
    if r.status_code >= 400:
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text[:500]}
        raise SystemExit(
            f"CF API {method} {path} → HTTP {r.status_code}\n{json.dumps(err, indent=2)}"
        )
    data = r.json()
    if not data.get("success", False):
        raise SystemExit(
            f"CF API {method} {path} returned success=false:\n{json.dumps(data, indent=2)}"
        )
    return data["result"] if "result" in data else data


def _verify_token(token: str) -> None:
    res = _api_call(token, "GET", "/user/tokens/verify")
    if res.get("status") != "active":
        raise SystemExit(f"CF API token status = {res.get('status')!r} (expected 'active')")


def _get_team_domain(token: str, account_id: str) -> str:
    """Fetch the existing Access team_domain for the account, or fail
    if Access not yet enabled (Eliot must enable it once via dashboard
    — the API to enable Access on an account is not publicly exposed,
    only management of an already-enabled team-domain)."""
    org = _api_call(token, "GET", f"/accounts/{account_id}/access/organizations")
    if not org or "auth_domain" not in org:
        raise SystemExit(
            "Access not enabled on this account. Visit "
            "https://one.dash.cloudflare.com once to pick a team domain "
            "(Free plan, no payment), then re-run this script."
        )
    return str(org["auth_domain"]).removesuffix(".cloudflareaccess.com")


def _find_existing_service_token(token: str, account_id: str, name: str) -> dict[str, Any] | None:
    tokens = _api_call(token, "GET", f"/accounts/{account_id}/access/service_tokens")
    for t in tokens:
        if t.get("name") == name:
            return t
    return None


def _create_service_token(token: str, account_id: str, name: str) -> dict[str, Any]:
    return _api_call(
        token,
        "POST",
        f"/accounts/{account_id}/access/service_tokens",
        json_body={"name": name, "duration": "8760h"},  # 1 year — encourages rotation
    )


def _find_existing_app(token: str, account_id: str, hostname: str) -> dict[str, Any] | None:
    apps = _api_call(token, "GET", f"/accounts/{account_id}/access/apps")
    for a in apps:
        if a.get("domain") == hostname:
            return a
    return None


def _create_app(token: str, account_id: str, hostname: str, app_name: str) -> dict[str, Any]:
    return _api_call(
        token,
        "POST",
        f"/accounts/{account_id}/access/apps",
        json_body={
            "name": app_name,
            "domain": hostname,
            "type": "self_hosted",
            "session_duration": "24h",
            "auto_redirect_to_identity": False,
        },
    )


def _add_policies(token: str, account_id: str, app_id: str, service_token_id: str) -> None:
    # Policy 1 — Allow service-token caller.
    _api_call(
        token,
        "POST",
        f"/accounts/{account_id}/access/apps/{app_id}/policies",
        json_body={
            "name": "allow-ichor-hetzner-orchestrator",
            "decision": "non_identity",
            "include": [{"service_token": {"token_id": service_token_id}}],
        },
    )
    # Policy 2 — Bypass /healthz for systemd healthcheck.
    # NOTE: per-path bypass isn't supported on a single app's policies in
    # the public API the way it is in the dashboard — the simplest robust
    # workaround is to leave /healthz public side-by-side. Documented
    # below : we don't create the bypass policy here and instead recommend
    # the WAF Skip rule shown in RUNBOOK-018 Step 3 #7 (manual click,
    # ~30s).


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="setup-cf-access")
    parser.add_argument(
        "--hostname",
        default="claude-runner.fxmilyapp.com",
        help="Public hostname to protect (default: claude-runner.fxmilyapp.com)",
    )
    parser.add_argument(
        "--service-token-name",
        default="ichor-hetzner-orchestrator",
        help="Name for the new service token",
    )
    parser.add_argument(
        "--app-name", default="claude-runner", help="Name for the Access application"
    )
    args = parser.parse_args(argv)

    cf_token = os.environ.get("CF_API_TOKEN")
    cf_account = os.environ.get("CF_ACCOUNT_ID")
    if not cf_token or not cf_account:
        print(
            "Required env vars : CF_API_TOKEN + CF_ACCOUNT_ID\n"
            "See module docstring for scope + setup.",
            file=sys.stderr,
        )
        return 2

    print(f"== W102 CF Access automation — hostname={args.hostname} ==", file=sys.stderr)

    print("→ Verifying API token...", file=sys.stderr)
    _verify_token(cf_token)

    print("→ Fetching Access team_domain...", file=sys.stderr)
    team_domain = _get_team_domain(cf_token, cf_account)
    print(f"   team_domain={team_domain}", file=sys.stderr)

    print(f"→ Looking for existing service token {args.service_token_name!r}...", file=sys.stderr)
    existing_token = _find_existing_service_token(cf_token, cf_account, args.service_token_name)
    if existing_token:
        print(
            f"   Found existing token id={existing_token['id']} — "
            "CLIENT_SECRET will be re-rotated.",
            file=sys.stderr,
        )
        # Rotate to get a fresh secret since CF only shows it once.
        st = _api_call(
            cf_token,
            "POST",
            f"/accounts/{cf_account}/access/service_tokens/{existing_token['id']}/rotate",
        )
    else:
        print("   Creating new service token...", file=sys.stderr)
        st = _create_service_token(cf_token, cf_account, args.service_token_name)

    client_id = st.get("client_id") or st.get("id")
    client_secret = st.get("client_secret")
    if not client_id or not client_secret:
        raise SystemExit(
            f"CF API did not return client_secret in service-token response:\n"
            f"{json.dumps(st, indent=2)}"
        )

    print(f"→ Looking for existing Access app for {args.hostname!r}...", file=sys.stderr)
    existing_app = _find_existing_app(cf_token, cf_account, args.hostname)
    if existing_app:
        print(f"   Found existing app id={existing_app['id']}", file=sys.stderr)
        app = existing_app
    else:
        print("   Creating new Self-hosted app...", file=sys.stderr)
        app = _create_app(cf_token, cf_account, args.hostname, args.app_name)

    print("→ Adding Service-Auth allow policy...", file=sys.stderr)
    _add_policies(cf_token, cf_account, app["id"], st["id"])

    aud_tag = app.get("aud") or app.get("audience")
    if not aud_tag:
        raise SystemExit(
            f"CF API did not return AUD tag in app response:\n{json.dumps(app, indent=2)}"
        )

    print("\n== W102 RUNBOOK-018 paste-template — copy into chat ==")
    print("```")
    print(f"team_domain  : {team_domain}")
    print(f"AUD_TAG      : {aud_tag}")
    print(f"CLIENT_ID    : {client_id}")
    print(f"CLIENT_SECRET: {client_secret}")
    print("```")
    print(
        "\n*** SAVE THE CLIENT_SECRET TO A PASSWORD MANAGER NOW *** — CF only shows it once.",
        file=sys.stderr,
    )
    print(
        "\nIMPORTANT : the `/healthz` bypass policy must still be added "
        "manually via the dashboard (one WAF Skip rule, ~30s) — see "
        "RUNBOOK-018 Step 3 #7. The public API doesn't expose per-path "
        "bypass on a single app the way the dashboard does.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
