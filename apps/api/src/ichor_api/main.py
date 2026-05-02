"""FastAPI app entrypoint. Phase 0 — minimal /healthz only."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="Ichor API",
    version="0.0.0",
    description="Ichor backend — Phase 0 skeleton",
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
