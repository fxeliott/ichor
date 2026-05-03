"""Shared test fixtures — canned LLM responses for the 4 passes."""

from __future__ import annotations

import json
from collections.abc import Sequence

from ichor_brain.runner_client import RunnerCall, RunnerResponse


REGIME_OK_JSON = {
    "quadrant": "haven_bid",
    "rationale": (
        "VIX printed 18.2 (up from 14.1 last week), DXY at 105.30 (up "
        "+1.2%), US10Y down to 4.18% — classic flight-to-safety move."
    ),
    "confidence_pct": 72.0,
    "macro_trinity_snapshot": {
        "DXY": 105.30,
        "US10Y": 4.18,
        "VIX": 18.2,
        "DFII10": 1.85,
        "BAMLH0A0HYM2": 3.1,
    },
}


ASSET_OK_JSON = {
    "asset": "EUR_USD",
    "bias_direction": "short",
    "conviction_pct": 65.0,
    "magnitude_pips_low": 25.0,
    "magnitude_pips_high": 60.0,
    "timing_window_start": "2026-05-04T07:00:00+00:00",
    "timing_window_end":   "2026-05-04T15:00:00+00:00",
    "mechanisms": [
        {
            "claim": "US-DE 10Y diff widened +12bps in the last 5 sessions",
            "sources": ["DGS10", "IRLTLT01DEM156N"],
        },
        {
            "claim": "ECB Lagarde dovish pivot in May 2 speech",
            "sources": ["https://www.ecb.europa.eu/press/key/date/2026/html/ecb.sp260502.en.html"],
        },
    ],
    "catalysts": [
        {
            "time": "2026-05-04T12:30:00+00:00",
            "event": "US NFP April release",
            "expected_impact": "high",
        }
    ],
    "correlations_snapshot": {"EURUSD_DXY_60d": -0.91},
    "polymarket_overlay": [
        {
            "market": "fed-cut-jun-2026",
            "yes_price": 0.18,
            "divergence_vs_consensus": -0.06,
        }
    ],
}


STRESS_OK_JSON = {
    "counter_claims": [
        {
            "claim": "EZ HICP services component re-accelerating to 4.1% YoY",
            "strength_pct": 35.0,
            "sources": ["https://ec.europa.eu/eurostat"],
        },
        {
            "claim": "EUR/USD COT managed-money short positioning at 80th percentile — stretched",
            "strength_pct": 40.0,
            "sources": ["EUR/USD"],
        },
    ],
    "revised_conviction_pct": 45.0,
    "notes": "65 - (40 * 0.5) = 45. Stretched short positioning is the dominant counter.",
}


INVALIDATION_OK_JSON = {
    "conditions": [
        {
            "condition": "DXY breaks below 104.50 intraday",
            "threshold": "104.50",
            "source": "DXY",
        },
        {
            "condition": "ECB hawkish surprise from any Governing Council member",
            "threshold": "explicit hawkish quote",
            "source": "https://www.ecb.europa.eu/press/key/date/2026/html/index.en.html",
        },
    ],
    "review_window_hours": 8,
}


def _wrap_json(obj: dict) -> str:
    return f"```json\n{json.dumps(obj, ensure_ascii=False)}\n```"


def four_pass_responses(
    *,
    regime: dict | None = None,
    asset: dict | None = None,
    stress: dict | None = None,
    invalidation: dict | None = None,
    duration_ms: int = 12_000,
) -> list[RunnerResponse]:
    """Build a 4-element list of canned RunnerResponses for the orchestrator."""
    payloads: Sequence[dict] = (
        regime or REGIME_OK_JSON,
        asset or ASSET_OK_JSON,
        stress or STRESS_OK_JSON,
        invalidation or INVALIDATION_OK_JSON,
    )
    return [
        RunnerResponse(text=_wrap_json(p), raw={"stub": True}, duration_ms=duration_ms)
        for p in payloads
    ]


class _StubCriticVerdict:
    """Mimics the ichor_agents.critic.reviewer.CriticVerdict surface."""

    def __init__(
        self,
        verdict: str = "approved",
        confidence: float = 0.95,
        findings: list | None = None,
        suggested_footer: str = "",
    ):
        self.verdict = verdict
        self.confidence = confidence
        self.findings = findings or []
        self.suggested_footer = suggested_footer


def stub_critic_fn(verdict: str = "approved", confidence: float = 0.95):
    """Return a `critic_fn` callable for `Orchestrator(critic_fn=...)`."""

    def _fn(*, briefing_markdown, source_pool, asset_whitelist):
        return _StubCriticVerdict(verdict=verdict, confidence=confidence)

    return _fn


def assert_call_contracts(calls: list[RunnerCall]) -> None:
    """All four calls must carry a non-empty system + prompt + cache_key."""
    assert len(calls) == 4, f"expected 4 calls, got {len(calls)}"
    for i, c in enumerate(calls):
        assert c.system.strip(), f"call {i}: empty system"
        assert c.prompt.strip(), f"call {i}: empty prompt"
        assert c.cache_key, f"call {i}: missing cache key"
        assert c.model in {"opus", "sonnet", "haiku"}, f"call {i}: bad model {c.model}"
