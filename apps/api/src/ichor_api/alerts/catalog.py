"""Alert catalog — 33 alert types per AUDIT_V3 §4.2 + ARCHITECTURE_FINALE
"5 nouveaux Crisis Mode triggers".

Each definition encodes :
  - code : stable string ID (used in DB + UI)
  - severity : info | warning | critical
  - description : 1-line human summary
  - default threshold + direction (override per-asset in policy file)
  - crisis_mode : if True, this trigger counts toward Crisis Mode composite
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "warning", "critical"]
Direction = Literal["above", "below", "cross_up", "cross_down"]


@dataclass(frozen=True)
class AlertDef:
    code: str
    severity: Severity
    title_template: str
    metric_name: str
    default_threshold: float
    default_direction: Direction
    crisis_mode: bool = False
    description: str = ""


# Original 28 alerts from PLAN
PLAN_ALERTS: tuple[AlertDef, ...] = (
    AlertDef(
        "HY_OAS_WIDEN",
        "warning",
        "HY OAS spread elargi de {value:.0f} bps",
        "BAMLH0A0HYM2_d",
        50,
        "above",
        description="High Yield credit spread widening",
    ),
    AlertDef(
        "HY_OAS_CRISIS",
        "critical",
        "HY OAS critique a {value:.0f} bps",
        "BAMLH0A0HYM2",
        800,
        "above",
        crisis_mode=True,
    ),
    AlertDef(
        "IG_OAS_WIDEN",
        "warning",
        "IG OAS spread elargi de {value:.0f} bps",
        "BAMLC0A0CMTRIV_d",
        30,
        "above",
    ),
    AlertDef("VIX_SPIKE", "warning", "VIX spike a {value:.1f}", "VIXCLS", 25, "above"),
    AlertDef(
        "VIX_PANIC",
        "critical",
        "VIX panique a {value:.1f}",
        "VIXCLS",
        35,
        "above",
        crisis_mode=True,
    ),
    AlertDef("MOVE_SPIKE", "warning", "MOVE (vol Treasury) a {value:.1f}", "MOVE", 130, "above"),
    AlertDef(
        "DXY_BREAKOUT_UP", "info", "DXY breakout haussier {value:.2f}", "DXY_close", 105, "cross_up"
    ),
    AlertDef(
        "DXY_BREAKOUT_DOWN",
        "info",
        "DXY breakout baissier {value:.2f}",
        "DXY_close",
        100,
        "cross_down",
    ),
    AlertDef(
        "FED_FUNDS_REPRICE",
        "info",
        "Repricing Fed funds 6m de {value:.0f} bps",
        "fedfut_6m_d",
        25,
        "above",
    ),
    AlertDef(
        "ECB_DEPO_REPRICE",
        "info",
        "Repricing ECB depo 6m de {value:.0f} bps",
        "ecbfut_6m_d",
        25,
        "above",
    ),
    AlertDef(
        "USDJPY_INTERVENTION_RISK",
        "warning",
        "USDJPY proche zone intervention BoJ {value:.2f}",
        "USD_JPY_close",
        158,
        "above",
    ),
    AlertDef(
        "XAU_BREAKOUT_ATH", "info", "XAUUSD nouvel ATH {value:.0f}", "XAU_USD_high", 2900, "above"
    ),
    AlertDef(
        "OIL_INVENTORY_SHOCK",
        "warning",
        "Inventaire petrole surprise {value:.1f}M bbl",
        "EIA_crude_chg",
        -5,
        "below",
    ),
    AlertDef(
        "FOMC_TONE_SHIFT",
        "warning",
        "FOMC ton shift Hansen-McMahon {value:+.2f}",
        "fomc_tone_z",
        1.5,
        "above",
    ),
    AlertDef("ECB_TONE_SHIFT", "warning", "BCE ton shift {value:+.2f}", "ecb_tone_z", 1.5, "above"),
    AlertDef(
        "DATA_SURPRISE_Z",
        "warning",
        "Surprise macro {asset} z={value:+.2f}",
        "data_surprise_z",
        2.0,
        "above",
        description=(
            "Citi-style Eco Surprise proxy : (last - rolling_mean_24) / rolling_std_24 "
            "on key US macro releases (PAYEMS, UNRATE, CPIAUCSL, PCEPI, INDPRO, GDPC1). "
            "Polarity-corrected so positive = positive economic surprise. UNRATE is "
            "inverted. Fires when |z| >= 2.0 on any constituent series, source-stamped "
            "FRED:<series_id>. Cf services/surprise_index.py + ADR-033."
        ),
    ),
    AlertDef(
        "REAL_YIELD_GOLD_DIVERGENCE",
        "warning",
        "XAU/DFII10 corr divergence {asset} z={value:+.2f}",
        "real_yield_gold_div_z",
        2.0,
        "above",
        description=(
            "60d rolling correlation between XAU (FRED:GOLDAMGBD228NLBM) and 10Y TIPS "
            "real yield (FRED:DFII10). Historical baseline ~ -0.5 to -0.7 (carry channel). "
            "Z-score against trailing 250d distribution of rolling-corr ; fires when |z| "
            ">= 2.0. Divergence = gold no longer driven by real yields — geopol premium, "
            "intervention, debasement narrative. Cf services/real_yield_gold_check.py + ADR-034."
        ),
    ),
    AlertDef(
        "COT_NET_FLIP", "warning", "COT positionnement net flip {asset}", "cot_net_z", 2.0, "above"
    ),
    AlertDef(
        "RISK_REVERSAL_25D",
        "warning",
        "Risk reversal 25d {asset} {value:+.2f}",
        "rr25_z",
        2.0,
        "above",
    ),
    AlertDef(
        "GEX_FLIP",
        "warning",
        "GEX dealer gamma flip negatif",
        "gex_d",
        0,
        "cross_down",
        crisis_mode=True,
    ),
    AlertDef(
        "LIQUIDITY_TIGHTENING",
        "warning",
        "RRP+TGA stress liquidite {value:.0f}B",
        "liq_proxy_d",
        -200,
        "below",
    ),
    AlertDef(
        "CONCEPT_DRIFT_DETECTED",
        "warning",
        "Drift detecte modele {model_id}",
        "drift_score",
        0.7,
        "above",
    ),
    AlertDef(
        "BIAS_BRIER_DEGRADATION",
        "warning",
        "Brier degradation {value:+.2f} 7j",
        "brier_change_7d",
        0.10,
        "above",
    ),
    AlertDef(
        "MODEL_PREDICTION_OUTLIER",
        "info",
        "Prediction outlier {model_id} z={value:+.1f}",
        "pred_z",
        3.0,
        "above",
    ),
    AlertDef(
        "REGIME_CHANGE_HMM",
        "info",
        "Regime HMM bascule {prev}->{new}",
        "hmm_state_change",
        1,
        "above",
    ),
    AlertDef(
        "ANALOGUE_MATCH_HIGH",
        "info",
        "DTW analogue historique fort {match_event}",
        "dtw_dist",
        0.15,
        "below",
    ),
    AlertDef(
        "VPIN_TOXICITY_HIGH",
        "warning",
        "VPIN flow toxicity eleve {value:.2f}",
        "vpin_p99",
        0.35,
        "above",
    ),
    AlertDef(
        "HAR_RV_FORECAST_SPIKE",
        "info",
        "HAR-RV prevoit vol J+1 {value:+.0f}%",
        "har_rv_h1_chg",
        30,
        "above",
    ),
    AlertDef(
        "NEWS_NEGATIVE_BURST",
        "warning",
        "Burst news negatif FinBERT {value:.2f}",
        "news_neg_5min",
        0.7,
        "above",
    ),
    AlertDef(
        "POLYMARKET_PROBABILITY_SHIFT",
        "info",
        "Polymarket {market} shift {value:+.0f}pp",
        "poly_chg_24h",
        10,
        "above",
    ),
)

# 5 NEW alerts from AUDIT_V2 §4.2 + ARCHITECTURE_FINALE
AUDIT_V2_ALERTS: tuple[AlertDef, ...] = (
    AlertDef(
        "SOFR_SPIKE",
        "critical",
        "SOFR spike a {value:.2f}% vs FOMC mid",
        "SOFR_d",
        25,
        "above",
        crisis_mode=True,
        description="Funding stress signal",
    ),
    AlertDef(
        "FX_PEG_BREAK",
        "critical",
        "Peg FX casse: {pair} {value:+.2f}%",
        "fx_peg_dev",
        1.0,
        "above",
        crisis_mode=True,
        description="USD/HKD, USD/CNH stability check",
    ),
    AlertDef(
        "DEALER_GAMMA_FLIP",
        "warning",
        "Dealer gamma flip negatif {asset}",
        "gex_dealer",
        0,
        "cross_down",
        crisis_mode=True,
    ),
    AlertDef(
        "TREASURY_AUCTION_TAIL",
        "warning",
        "Treasury auction tail {tenor} {value:+.2f} bps",
        "auction_tail_bps",
        2.0,
        "above",
    ),
    AlertDef(
        "LIQUIDITY_BIDASK_WIDEN",
        "warning",
        "Bid/ask spread elargi {asset} {value:+.0f}%",
        "ba_spread_z",
        2.5,
        "above",
        crisis_mode=True,
    ),
)

ALL_ALERTS: tuple[AlertDef, ...] = PLAN_ALERTS + AUDIT_V2_ALERTS

# Quick lookup
BY_CODE: dict[str, AlertDef] = {a.code: a for a in ALL_ALERTS}

# Crisis Mode composite — fires when N >= 2 of these are active
CRISIS_TRIGGERS: tuple[str, ...] = tuple(a.code for a in ALL_ALERTS if a.crisis_mode)


def get_alert_def(code: str) -> AlertDef:
    if code not in BY_CODE:
        raise KeyError(f"Unknown alert code: {code}. Valid: {sorted(BY_CODE)}")
    return BY_CODE[code]


def assert_catalog_complete() -> None:
    """Sanity check at startup: total = 35 alerts, all unique codes."""
    codes = [a.code for a in ALL_ALERTS]
    assert len(codes) == len(set(codes)), f"Duplicate alert codes: {codes}"
    assert len(ALL_ALERTS) == 35, f"Expected 35 alerts, got {len(ALL_ALERTS)}"
    assert len(CRISIS_TRIGGERS) >= 5, f"Expected ≥5 crisis triggers, got {len(CRISIS_TRIGGERS)}"
