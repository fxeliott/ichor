"""Azure Neural TTS FR free tier wrapper + Piper local fallback.

Free tier (verified 2026-05 — see docs/AUDIT_V3.md §3):
  - 5M characters/month gratuit (F0 tier)
  - Voice fr-FR-DeniseNeural (default) or fr-FR-HenriNeural (A/B test)
  - REST API, no SDK required
  - Region: westeurope (closest to France)

Fallback: Piper local self-host (siwis-medium MIT, runs on Hetzner CPU).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Literal

import httpx
import structlog

from .text_normalize import preprocess_finance_fr

log = structlog.get_logger(__name__)

VoiceFR = Literal["fr-FR-DeniseNeural", "fr-FR-HenriNeural"]


class AzureTTSQuotaExceeded(RuntimeError):
    """Azure returned 429 / 401 quota error → fallback to Piper."""


class AzureTTSDownError(RuntimeError):
    """Azure 5xx or network error → fallback to Piper."""


async def azure_neural_tts(
    text: str,
    *,
    voice: VoiceFR = "fr-FR-DeniseNeural",
    region: str = "westeurope",
    speech_key: str | None = None,
    ssml_pauses: bool = True,
) -> bytes:
    """Synthesize French audio via Azure Speech Cognitive Services.

    Returns: MP3 bytes (audio-24khz-160kbitrate-mono-mp3 encoding).

    Raises:
        AzureTTSQuotaExceeded on 401/429.
        AzureTTSDownError on 5xx or network error.
    """
    key = speech_key or os.environ.get("AZURE_SPEECH_KEY", "").strip()
    if not key:
        raise AzureTTSDownError("AZURE_SPEECH_KEY not set")

    if ssml_pauses:
        body = _wrap_ssml(text, voice)
        content_type = "application/ssml+xml"
    else:
        body = text
        content_type = "text/plain"

    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            url,
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": content_type,
                "X-Microsoft-OutputFormat": "audio-24khz-160kbitrate-mono-mp3",
                "User-Agent": "ichor/0.0.0",
            },
            content=body.encode("utf-8") if isinstance(body, str) else body,
        )

    if r.status_code in (401, 429):
        raise AzureTTSQuotaExceeded(f"Azure TTS rejected: {r.status_code} {r.text[:200]}")
    if r.status_code >= 500:
        raise AzureTTSDownError(f"Azure TTS server error: {r.status_code} {r.text[:200]}")
    r.raise_for_status()

    log.info("azure_tts.ok", chars=len(text), voice=voice, audio_bytes=len(r.content))
    return r.content


def _wrap_ssml(text: str, voice: str) -> str:
    """Minimal SSML envelope with sentence/comma pauses."""
    # Escape XML special chars
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Add pauses (200ms after comma, 400ms after period)
    text = text.replace(", ", ', <break time="200ms"/> ').replace(". ", '. <break time="400ms"/> ')
    return (
        '<speak version="1.0" xml:lang="fr-FR" '
        'xmlns="http://www.w3.org/2001/10/synthesis">'
        f'<voice name="{voice}">{text}</voice>'
        "</speak>"
    )


async def piper_local_tts(
    text: str,
    *,
    voice_model: str = "fr_FR-siwis-medium",
    piper_binary: str = "piper",
) -> bytes:
    """Fallback: run Piper locally (CPU-only, ~1s per sentence).

    Requires `piper` binary + the voice model file installed.
    Returns: WAV bytes.
    """
    proc = await asyncio.create_subprocess_exec(
        piper_binary,
        "--model", voice_model,
        "--output-raw",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(text.encode("utf-8"))
    if proc.returncode != 0:
        raise RuntimeError(f"piper failed: {stderr.decode(errors='replace')[:200]}")

    log.info("piper_tts.ok", chars=len(text), voice=voice_model, audio_bytes=len(stdout))
    return stdout


async def synthesize_briefing(
    text: str,
    *,
    lexicon_file: Path | None = None,
    voice: VoiceFR = "fr-FR-DeniseNeural",
) -> bytes:
    """Top-level entrypoint: normalize text + try Azure, fall back to Piper.

    Returns audio bytes (MP3 from Azure, WAV from Piper).
    """
    normalized = preprocess_finance_fr(text, lexicon_file=lexicon_file)
    try:
        return await azure_neural_tts(normalized, voice=voice)
    except (AzureTTSQuotaExceeded, AzureTTSDownError) as e:
        log.warning("tts.azure_fallback_to_piper", error=str(e))
        return await piper_local_tts(normalized)
