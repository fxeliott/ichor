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
        "BOE_TONE_SHIFT",
        "warning",
        "BoE ton shift {value:+.2f}",
        "boe_tone_z",
        1.5,
        "above",
        description=(
            "Bank of England MPC tone shift detector. FOMC-Roberta zero-shot "
            "transfer (gtfintechlab) on cb_speeches WHERE central_bank='BoE'. "
            "Aggregates net_hawkish across last 24h speeches, persists into "
            "fred_observations BOE_TONE_NET, computes 90d rolling z. Fires "
            "when |z| >= 1.5. Drives GBP/USD + GBP/JPY repricing. 2026 context: "
            "BoE pivoted hawkish March 2026 post Middle-East energy shock; "
            "Bailey centrist between Pill/Greene/Mann hawks and Dhingra/Taylor "
            "doves. Cf services/cb_tone_check.py + ADR-040."
        ),
    ),
    AlertDef(
        "BOJ_TONE_SHIFT",
        "warning",
        "BoJ ton shift {value:+.2f}",
        "boj_tone_z",
        1.5,
        "above",
        description=(
            "Bank of Japan tone shift detector. FOMC-Roberta zero-shot transfer "
            "on cb_speeches WHERE central_bank='BoJ'. Aggregates net_hawkish "
            "across last 24h speeches, persists into fred_observations "
            "BOJ_TONE_NET, computes 90d rolling z. Fires when |z| >= 1.5. "
            "Drives USD/JPY (intervention sensitivity at 158+) + JPY carry "
            "trades. 2026 context: post-2024 negative rates exit + YCC end, "
            "Ueda gradual normalization with shunto-wage as anchor. Cf "
            "services/cb_tone_check.py + ADR-040."
        ),
    ),
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
        "QUAD_WITCHING",
        "info",
        "Quad-witching T-{value:.0f} ({asset})",
        "quad_witching_t_minus",
        5,
        "below",
        description=(
            "Proximity flag for the 4 annual quad-witching Fridays (3rd Friday of "
            "Mar/Jun/Sep/Dec). Fires T-5 through T-0. Volume 2-3x normal, gamma "
            "re-pricing pops, dealer rebalancing risk. SPX/NDX-impacted. "
            "Cf services/quad_witching_check.py + ADR-035."
        ),
    ),
    AlertDef(
        "OPEX_GAMMA_PEAK",
        "info",
        "Monthly OPEX T-{value:.0f} ({asset})",
        "opex_t_minus",
        2,
        "below",
        description=(
            "Proximity flag for monthly options expiration (3rd Friday of every month). "
            "Fires T-2 through T-0. Less violent than quad witching but same gamma-unwind "
            "dynamics ; flag T-1 so trader anticipates dealer positioning shift Friday AM. "
            "Cf services/quad_witching_check.py + ADR-035."
        ),
    ),
    AlertDef(
        "GEOPOL_FLASH",
        "warning",
        "Burst geopolitique AI-GPR z={value:+.2f}",
        "ai_gpr_z",
        2.0,
        "above",
        description=(
            "AI-GPR daily index (Caldara-Iacoviello 2022 AER ; AI version SF Fed 2026). "
            "Z-score of latest reading vs trailing 30d distribution. |z| >= 2.0 = "
            "significant geopolitical risk repricing — affects FX havens (XAU, JPY, "
            "CHF, USD) bidirectionally per dollar smile regime. Source: "
            "matteoiacoviello.com/ai_gpr.html. Cf services/geopol_flash_check.py + ADR-036."
        ),
    ),
    AlertDef(
        "TARIFF_SHOCK",
        "warning",
        "Burst narrative tarif count_z={value:+.2f}",
        "tariff_count_z",
        2.0,
        "above",
        description=(
            "GDELT 2.0 article-burst detector on tariff narrative (tariff, trade war, "
            "Section 301/232/122, IEEPA, USTR, protectionism, reciprocal tariff, ART "
            "program, Liberation Day, etc). Combined gate: today's article count "
            "z-score >= 2.0 AGAINST trailing 30d daily-count baseline AND avg(tone) "
            "<= -1.5. Macro-broad (USD/CNH, USD/MXN, EUR/USD, gold, equity risk "
            "premia react). 2026 context: post-SCOTUS Learning Resources v Trump, "
            "Section 301 wave (76 simultaneous investigations, March 2026). Source: "
            "gdelt:tariff_filter. Cf services/tariff_shock_check.py + ADR-037."
        ),
    ),
    AlertDef(
        "MEGACAP_EARNINGS_T_1",
        "info",
        "Mag-7 earnings T-{value:.0f} ({asset})",
        "megacap_t_minus_days",
        1,
        "below",
        description=(
            "Magnificent 7 earnings T-1 proximity flag. Iterates AAPL/MSFT/GOOGL/AMZN/"
            "META/NVDA/TSLA via yfinance and fires when any has earnings within T-1 "
            "(today or tomorrow). Mag-7 ~ 27% of S&P 500 earnings power 2026 (Zacks); "
            "binary catalyst impacts SPX/NDX vol skew, dealer gamma, USD haven demand "
            "if expected miss. Source: yfinance:earnings_calendar. asset = ticker for "
            "trader drill-back. Cf services/megacap_earnings_check.py + ADR-038."
        ),
    ),
    AlertDef(
        "GEOPOL_REGIME_STRUCTURAL",
        "info",
        "Regime structurel geopol z_252d={value:+.2f}",
        "ai_gpr_z_252d",
        2.0,
        "above",
        description=(
            "Structural-window companion to GEOPOL_FLASH (ADR-036). 252-day rolling "
            "z-score on AI-GPR daily index — captures slow-build escalations "
            "(Russia-Ukraine cumulative arc, Taiwan-strait gradual militarization, "
            "US-China multi-year decoupling) that the 30d window dampens because "
            "the rolling baseline drifts up with the absolute risk level. Severity "
            "info: structural shifts are context flags not actionable signals. The "
            "warning-level GEOPOL_FLASH remains the trader-actionable pathway. "
            "Cf services/geopol_regime_check.py + ADR-039."
        ),
    ),
    AlertDef(
        "TERM_PREMIUM_REPRICING",
        "warning",
        "Term premium repricing z={value:+.2f}",
        "term_premium_z",
        2.0,
        "above",
        description=(
            "10-year Treasury term premium repricing detector. Z-score of "
            "FRED:THREEFYTP10 (Kim-Wright model) latest reading vs trailing "
            "90d distribution. Fires when |z| >= 2.0. Expansion regime "
            "(z > 0) drives gold up, USD weak, mortgage rates up despite "
            "Fed cuts (long-end disconnect, Bond Vigilante regime, fiscal-"
            "stress narrative). Contraction regime (z < 0) drives flight-"
            "to-quality bond bid + USD strong. 2026 macro context: term "
            "premium expanding due to Trump fiscal expansion + Fed "
            "independence questions per Hartford/SSGA/NY Life outlooks. "
            "Cf services/term_premium_check.py + ADR-041."
        ),
    ),
    AlertDef(
        "MACRO_QUARTET_STRESS",
        "warning",
        "Macro quartet stress {value:.0f}/4 dims aligned",
        "quartet_stress_count",
        3,
        "above",
        description=(
            "Composite 4-dimension stress regime detector. Z-score of DXY "
            "(DTWEXBGS) + 10Y (DGS10) + VIX (VIXCLS) + HY OAS (BAMLH0A0HYM2) "
            "each on rolling 90d. Fires when N >= 3 of 4 dimensions are "
            "|z| > 2.0 (3-of-4 alignment per TORVAQ + OFR FSI methodology). "
            "Regime tagged 'stress' (all positive z), 'complacency' (all "
            "negative z), or 'mixed' (no directional consensus). Adds the "
            "credit-stress dimension that the original macro trinity missed "
            "— without HY OAS, March 2020 COVID + 2008 GFC funding-stress "
            "regimes are systematically under-detected. Cf "
            "services/macro_quartet_check.py + ADR-042."
        ),
    ),
    AlertDef(
        "DOLLAR_SMILE_BREAK",
        "warning",
        "Dollar smile broken — US-driven instability ({value:.0f}/4)",
        "dollar_smile_conditions_met",
        4,
        "above",
        description=(
            "Detects the 'broken smile' / 'crooked smile' / 'US-driven "
            "instability' regime that classic Dollar Smile (Stephen Jen 2001) "
            "doesn't handle. 4-condition AND gate: term_premium_z > +2 "
            "(fiscal stress) AND dxy_z < -1 (USD weakening) AND vix_z < +1 "
            "(not panic — distinguishes from classic LEFT smile) AND "
            "hy_oas_z < +1 (no credit stress — distinguishes from funding "
            "stress). When all 4 align: US itself becomes source of "
            "instability, safe-haven bid evaporates, $26T unhedged foreign "
            "USD assets create exit loop. Per Stephen Jen Bloomberg "
            "2025-11-12 + Wellington 'Crooked Smile' April 2025 + Eurizon "
            "SLJ Capital 2026 outlook. Source: FRED:THREEFYTP10+DTWEXBGS+"
            "VIXCLS+BAMLH0A0HYM2. Cf services/dollar_smile_check.py + ADR-043."
        ),
    ),
    AlertDef(
        "VIX_TERM_INVERSION",
        "warning",
        "VIX term backwardation ratio={value:.4f}",
        "vix_term_ratio",
        1.0,
        "above",
        description=(
            "Detects VIX term-structure inversion (backwardation) — when "
            "1-month implied vol VIXCLS > 3-month implied vol VXVCLS. The "
            "ratio crossing 1.0 signals near-term stress exceeding longer-"
            "dated expectations. RARE — historically coincides with major "
            "stress: 2008 GFC, 2011 US debt downgrade, 2015 China devaluation, "
            "Feb 2018 Volmageddon, late-2018 sell-off, March 2020 COVID. "
            "Empirical 2010-2017 (Macrosynergy/QuantSeeker): inverted curve "
            "has SIGNIFICANT positive relation with subsequent SPX returns "
            "= contrarian signal often near bottoms. Trader use: reduce "
            "dip-buying aggression, expect overnight gap risk, watch for "
            "all-clear ratio < 1.0 reset (e.g. April 2020 marked durable "
            "bottom). Source: FRED:VIXCLS+VXVCLS. Cf services/vix_term_check.py "
            "+ ADR-044."
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
    """Sanity check at startup: total = 47 alerts, all unique codes."""
    codes = [a.code for a in ALL_ALERTS]
    assert len(codes) == len(set(codes)), f"Duplicate alert codes: {codes}"
    assert len(ALL_ALERTS) == 47, f"Expected 47 alerts, got {len(ALL_ALERTS)}"
    assert len(CRISIS_TRIGGERS) >= 5, f"Expected ≥5 crisis triggers, got {len(CRISIS_TRIGGERS)}"
