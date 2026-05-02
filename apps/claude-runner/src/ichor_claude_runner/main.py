"""FastAPI on :8765, exposed to Hetzner via Cloudflare Tunnel only."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="Ichor Claude Runner (local)",
    version="0.0.0",
    description="Win11 local subprocess wrapper — Phase 0 skeleton",
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
