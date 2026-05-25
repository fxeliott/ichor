"""event_proximity_engine -- Engine 8 Event-Driven (Mission centrale axis-4
"anticipation par profondeur").

r147 (ADR-099 §Impl) -- closes 1/5 ABSENT engines from the 12-engine
blueprint. Pure compute, no I/O beyond DB session. Reads `economic_events`
forward window + `vix_observations` regime gate + r141 surprise classifier
output ; emits an `EventProximityFactor` consumed by the new
`_factor_event_anticipation` builder in `confluence_engine.py`.

WHAT THIS ENGINE DOES (honest scope)
====================================

For the next high-impact macro event in the lookahead window (default 48h),
emits a literature-cited PRIOR estimate of expected drift magnitude (in
basis points) calibrated by :

  expected_drift_bp = baseline_bp[event_class]
                    × impact_multiplier[level]    (1.0/0.4/0.0 high/med/low)
                    × time_decay(minutes_until)   (linear: 1 - mu/window)
                    × vix_regime_gate             (1.0/0.4/0.1 by VIX p75/p50)
                    × business_cycle_sign         (+1 expansion / -1 contraction)

ACADEMIC FOUNDATIONS (verbatim citations, NOT memory)
-----------------------------------------------------

- Lucca & Moench (2015) "The Pre-FOMC Announcement Drift", Journal of
  Finance 70:329-371. Original pre-FOMC drift : ~50bp avg S&P 500 return
  in 24h pre-FOMC window, 1994-2011 sample. NY Fed SR 512.
- Kurov, Halova-Wolfe & Gilbert (2021) "The Disappearing Pre-FOMC
  Announcement Drift", attenuation post-2016 attributed to FedWatch
  popularity reducing pre-FOMC uncertainty. CRITICAL : drift is regime-
  conditional, NOT universal -- alive in high-VIX environments 2022-2024,
  muted low-VIX 2016-2019.
- Boyd, Hu & Jagannathan (2005) "Why Bad News Is Usually Good for Stocks",
  Journal of Finance. Mechanism : interest-rate channel dominates in
  expansions (good news for stocks), cash-flow channel dominates in
  contractions (bad news for stocks). Reaction SIGN flips with business
  cycle phase.
- arXiv 2212.04525 (2022) "Monetary Uncertainty as Determinant of
  Response of Stock Market to Macro News" : "Good MNA surprise → +30bp
  cash-flow channel and -23bp per 1% monetary uncertainty risk-free-rate
  channel" -- counter-intuitive regime guard empirically confirmed.
- Peng & Pan (2024) SSRN 4764451 : 10Y UST yield drops 0.79bp on day
  before FOMC (1994-2022), driven entirely by the term premium ; magnitude
  intensifies (1.91bp) conditional on high Macro Attention Index.
- Vojtko-Dujava SSRN 5384407 (June 2025) "Pre-Announcement Drift for BoE,
  BoJ, SNB" : MAIN result = POSITIVE pre-drift for those 3 central banks.
  RBA/BoC NEGATIVE drift = SECONDARY histogram observation only (commodity-
  exporter divergence hypothesis), single-source unreplicated working paper.
  r150 sign-flip implementation deferred ; magnitude-only as cold-start prior
  + runtime caveat surfaces the single-source weakness honestly (lesson #38
  trader-claims-hypothesis-verify + lesson #11 calibrated refusal).
- Birz & Lott (2011) "The effect of macroeconomic news on stock returns:
  New evidence from newspaper coverage", *Journal of Banking and Finance*
  35(11):2791-2800. Tested GDP, unemployment, retail sales, durable goods :
  GDP + unemployment significant, retail sales + durable goods = expected
  sign but STATISTICALLY INSIGNIFICANT correlation. Negative-result peer-
  reviewed grounding for r155 `Retail_Sales` class at LOW baseline 5 bp +
  `low_signal_confidence` sentinel (clamps confidence to "low" regardless
  of VIX/time, parity with `vix_observation_missing` clamp pattern). 3rd
  magnitude-uncertainty sentinel after r150 `single_source_direction` +
  r153 `asymmetric_negativity_bias`.

PATTERN #15 R59-DISPROVE HONEST-UNMAPPED SUBSET (r147+r150+r153+r154+r155)
-------------------------------------------------------------------------

Per Pattern #15 R59-disprove-before-commit (now stable across 8 applications),
these event classes were considered for mapping but REJECTED because the
researcher web R59 verify found NO peer-reviewed source quantifying their
reaction-beta in basis points (or only single-source unreplicated working
papers). All kept HONESTLY UNMAPPED rather than fabricating a baseline :

  - r147 BoJ Ueda Speeches              (single-source media, no academic study)
  - r147 BoC Macklem Speeches           (zero academic event study)
  - r147 Fed Chair non-FOMC speeches    (Kohn-Sack 2004 found NO effect)
  - r147 Trump Speeches                 (content-dependent, 1-4h fade per
                                         Bianchi-Gomez-Komlos 2022)
  - r147 RBNZ Breman Speeches           (single-source unreplicated)
  - r155 PMI Services (US ISM Services + S&P Global Flash Composite) :
        Flannery-Protopapadakis 2002 RFS EXCLUDED PMI from 6 priced factors ;
        Lucca-Moench 2015 JoF found pre-drift FOMC-unique NOT generalizable ;
        ABDV 2007 JIE announcement list unverifiable (paywall/binary PDFs) ;
        Wang-Yang 2018/2023 IJFE asymmetric-PMI is China-only single-source
        unreplicated (Vojtko-Dujava class risk).
  - r155 Ivey PMI (CAD)                 (no peer-reviewed bp magnitude found)
  - r155 Philly Fed Manufacturing Index (regional Fed survey, literature thin)

The pattern is self-correcting at multi-round timescale : r152-r154 baseline
citations (ABDV 2007 for ISM=15 ; Pinchuk 2022 for 11-25bp aggregate band)
are themselves vérifiable AT THE ABSTRACT LEVEL only (paywall PDFs unreadable
via WebFetch). All Engine 8 baselines are therefore COLD-START PRIORS pending
empirical replacement (r156+ Dukascopy 1-min multi-year reaction-beta
backfill is the canonical empirical-grounded alternative).

HONEST SCOPE LIMITATIONS (doctrine #11 + lesson #37)
---------------------------------------------------

- Magnitude is a LITERATURE-CITED PRIOR, not an empirically-calibrated
  point estimate from Ichor's own historical data. Future r148+ extension
  candidate : daily-bar realized-reaction backfill via Stooq/yfinance.
- Sign is business-cycle conditional ; with no `output_gap_proxy` wired
  today (deferred r148+), defaults to `+1` (expansion baseline per Boyd-
  Hu-Jagannathan) WITH explicit caveat in the output.
- Cold-start gap on per-event-class N<3 : the historical reaction beta
  is NOT yet read from past actuals (would require r144 backfill to
  accumulate >3 months) ; r147 ships the prior-only formula. r148+
  candidate : empirical regression of past `magnitude_pct` × realized
  drift.
- VIX regime gate degrades to `low` confidence if no VIX observation in
  last 4 sessions (data-honesty fail-closed).

ADR-017 boundary
----------------

Output is GEOMETRIC/PROBABILISTIC : `expected_drift_magnitude_bp` (signed
scalar) + `expected_drift_direction` ("up"/"down"/"unknown"). NEVER
imperative ("BUY" / "SELL" / "LONG" / "SHORT" forbidden). Confluence
engine consumes this as one of 12 factors aggregated into score_long /
score_short -- the per-asset transmission stays in the verdict/confluence
layer (parity with r137 inflation_surprise + r136 MacroSurprisePanel
doctrine).

ADR refs : ADR-099 §Impl(r147) -- Mission centrale Axis-4 anticipation par profondeur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent, FredObservation

__all__ = [
    "EVENT_CLASS_BASELINE_BP",
    "DriftDirection",
    "EventConfidence",
    "EventProximityFactor",
    "ImpactLevel",
    "VixRegimeGate",
    "assess_event_proximity",
]


ImpactLevel = Literal["low", "medium", "high"]
EventConfidence = Literal["high", "medium", "low", "unavailable"]
VixRegimeGate = Literal["above_p75", "p50_to_p75", "below_p50", "unavailable"]
DriftDirection = Literal["up", "down", "unknown"]


# ── Baseline drift magnitudes (literature-cited PRIORS, in basis points) ──
#
# These are NOT empirically calibrated from Ichor's own historical data.
# Sources cited in module docstring. Each value represents the avg pre-event
# drift magnitude documented in the academic literature for that event class.
EVENT_CLASS_BASELINE_BP: dict[str, float] = {
    # Central bank statements — Lucca-Moench 2015 + Quantpedia 2024 extensions
    "FOMC": 50.0,
    "ECB": 35.0,
    "BoE": 25.0,
    "BoJ": 15.0,
    # r149 — AUD/CAD/JPY central-bank extensions. Magnitude ~ 25bp aligned with
    # BoE per FX-G10 vol regime.
    # r150 single-source disclosure (researcher web R59) : Vojtko-Dujava SSRN
    # 5384407 (June 2025) paper title is "Pre-Announcement Drift for BoE, BoJ,
    # SNB" — its main result is POSITIVE drift for those 3. RBA/BoC NEGATIVE
    # drift appears only as secondary histogram observation (commodity-exporter
    # divergence hypothesis), unreplicated single source. Sign-flip deferred
    # indefinitely until peer-reviewed replication ; magnitude-only POSITIVE
    # 25bp as cold-start prior + caveat surfaces the source weakness honestly.
    "RBA": 25.0,
    "BoC": 25.0,
    # Tankan quarterly survey (BoJ's flagship business sentiment) — magnitude
    # aligns with BoJ baseline per JPY vol regime.
    "Tankan": 15.0,
    # Tier-1 US macro — generic 20bp estimate (smaller than Fed, larger than tier-2)
    "NFP": 20.0,
    "CPI": 20.0,
    # r150 — generic Employment family (AUD/CAD bare "Employment Change" + cross-
    # currency "Unemployment Rate"). Magnitude aligned with NFP per labor-market
    # release literature priors (Lucca-Moench 2015 + Kurov 2021 — 18 macro
    # announcements, employment-class events all ~20bp magnitude).
    "Employment": 20.0,
    # r152 — PCE / GDP first-class mapping. Empirically captures the Tue May 26
    # Core PCE Price Index + Thu May 28 Prelim GDP q/q events that were
    # previously falling through to `high_other` 10bp (under-priced). PCE is
    # FOMC's preferred core inflation gauge → similar magnitude to CPI per
    # Kurov 2021 18-announcements study ; GDP is intermediate between CPI and
    # FOMC per BIS macro-announcement reaction literature (less surprise per
    # release because quarterly, but higher growth-channel impact).
    "PCE": 20.0,
    "GDP": 25.0,
    # r153 — US sentiment indicators first-class mapping. Closes the engagement
    # gap empirically witnessed r152 Playwright where "CB Consumer Confidence"
    # rendered as "Catalyseur non-classé". Empirical SSH probe found ~73% of
    # 60d high+medium impact FF titles were unmapped pre-r153 (94 events
    # surveyed). The 3 new classes below cover the 4 highest-frequency
    # unmapped US sentiment indicators (CCI + UoM Prelim/Revised + ISM Mfg/Svc).
    #
    # CCI (Conference Board Consumer Confidence) = 10bp baseline + asymmetric
    # negativity bias. Anchor : Akhtar-Faff-Oliver-Subrahmanyam 2012 *JBF* 36
    # "Stock salience and the asymmetric market effect of consumer sentiment
    # news" (US S&P/DJIA data, replicates 2011 AUS study) + Pinchuk 2022 arXiv
    # 2212.04525 (aggregate 11-25 bp/1σ MNA band). Asymmetric : bad sentiment
    # surprise → significant negative ; good surprise → muted/no reaction.
    # Engine 8 pre-event emits `direction=unknown` + sentinel
    # `asymmetric_negativity_bias` (mirroring r150 `single_source_direction`
    # pattern — but BETTER EVIDENCED : 2 peer-reviewed papers US data, not 1
    # working paper). Forward-looking magnitude is conditional on negative
    # surprise realization ; pre-event direction NOT determinable from
    # business_cycle_sign alone (asymmetry breaks the symmetric +1/-1 logic).
    # r153 trader YELLOW-3 methodology note : 10bp ≈ Akhtar 2012 |CAR| on
    # negative surprise × Pinchuk 2022 pre-event/event ratio (lower-tier
    # within the 11-25bp aggregate MNA band — sentiment surveys move equity
    # less than NFP/CPI/FOMC per ABDV 2007 intraday volatility regression).
    "CCI": 10.0,
    # Michigan = same family as CCI (consumer sentiment, asymmetric). Anchor
    # via Akhtar 2012 (covers both CCI + Michigan) + Andersen-Bollerslev-
    # Diebold-Vega 2007 *JIE* (Michigan in volatility-significant set). Prelim
    # > Revised magnitude qualitative consensus ; Engine 8 treats both same
    # tier (honest scope — sub-component decomposition r154+).
    "Michigan": 10.0,
    # ISM (Institute for Supply Management) = 15bp. Anchor : Andersen-
    # Bollerslev-Diebold-Vega 2007 *JIE* (intraday ISM significant in
    # equity-vol regression) + Pinchuk 2022 aggregate band upper-mid. ISM
    # Manufacturing PMI + ISM Services PMI both share class (Services class
    # has thinner academic coverage post-2008 → docstring caveat). NOT
    # asymmetric per literature.
    "ISM": 15.0,
    # r154 — CB Governor scheduled-speech mappings. Calibrated honest scope :
    # only 3 CB Speaker classes have sufficient peer-reviewed literature to
    # ship ; BoJ / BoC / Fed-Chair-non-FOMC / Trump speeches kept UNMAPPED
    # honestly per Pattern #15 R59-disprove (no academic per-event-bp study).
    # Magnitudes 5-15 bp band (well below FOMC=50 / ECB=35 baselines — these
    # are SCHEDULED speeches, not policy decisions).
    #
    # ECB_Speech (Lagarde + ECB President speeches outside decision-day press
    # conferences) = 7bp symmetric. Anchor : Ehrmann-Fratzscher 2007 ECB WP
    # 557 (monetary-inclination statements move rates 1.5-2.5 bp — equity
    # extrapolation conservative 7bp via VIX-gated multiplier) + Cieslak-
    # Schrimpf 2019 *JIE* (50%+ ECB press conferences carry non-monetary
    # news → speeches are an information channel separate from decisions).
    # NOT asymmetric per literature.
    "ECB_Speech": 7.0,
    # BoE_Speech (Bailey + BoE Governor scheduled speeches, including Mansion
    # House annual) = 8bp symmetric. Anchor : Ehrmann-Fratzscher 2007 BoE-
    # specific communication-dispersion 6-10 bp (UK rates ; equity extrap
    # conservative midpoint 8bp). NOT asymmetric per literature.
    "BoE_Speech": 8.0,
    # SNB_Speech (Schlegel + SNB Chairman scheduled speeches) = 10bp +
    # asymmetric_negativity_bias sentinel. Anchor : Ranaldo-Rossi 2009 *JIMF*
    # (SNB verbal interventions DO move assets, contrast with Kohn-Sack 2004
    # finding ordinary Fed speeches do NOT). 2024 SNB textual-analysis paper
    # documents NEGATIVE-sentiment moves sectors faster than positive →
    # asymmetric_negativity_bias applies (parity with CCI/Michigan r153).
    # Honest scope note : Ranaldo-Rossi data is 2000-2005 (pre-floor-cap) ;
    # may not generalize to post-2015 free-float SNB regime — caveat surfaces.
    "SNB_Speech": 10.0,
    # r155 — Retail Sales family (US "Retail Sales m/m" + "Core Retail Sales
    # m/m" + GBP/CAD bare variants). HONEST LOW baseline 5bp + new sentinel
    # `low_signal_confidence`. Anchor : Birz-Lott 2011 *JBF* "The effect of
    # macroeconomic news on stock returns: New evidence from newspaper
    # coverage" — tested GDP, unemployment, durable goods AND retail sales ;
    # GDP+unemployment significant, durable+retail = expected sign BUT
    # statistically insignificant correlation. The negative result is itself
    # a calibration anchor : retail sales news moves equity in the expected
    # direction but with effect size BELOW statistical detection power.
    # 5bp = floor estimate (well below NFP=20, CPI=20, GDP=25, ISM=15 in our
    # current ladder), with the new `low_signal_confidence` sentinel +
    # confidence clamp ensuring downstream consumers can mechanically filter
    # on the weak-evidence class (parity with r150 `single_source_direction`
    # + r153 `asymmetric_negativity_bias` mechanical-honesty patterns).
    #
    # PATTERN #15 R59-disprove 8th application context (r155, 2026-05-25) :
    # The r155 ⭐ AUTO-RECO was "PMI Services class extension" (Flash Mfg/Svc
    # PMI EUR/GBP/USD + ISM Services). Researcher web R59 dispatched found
    # NO peer-reviewed source quantifying ISM Services PMI or Flash Composite
    # PMI reaction-beta in basis points (8 queries) : Flannery-Protopapadakis
    # 2002 RFS EXCLUDED PMI from 6 priced factors ; Lucca-Moench 2015 JoF
    # found pre-drift FOMC-unique NOT generalizable to PMI ; ABDV 2007 JIE
    # announcement list unverifiable (paywall/binary PDFs) ; Wang-Yang
    # 2018/2023 IJFE asymmetric-PMI is China-only single-source unreplicated
    # (Vojtko-Dujava class risk). Pattern #15 reaches 8 stable applications
    # (r147 Bauer DP21003 + r148 daily-bar + r150×2 VIX/RBA-BoC + r153
    # Karnaukh-Vrolijk + r153 ISM-Services-honest + r154 CB-Speaker-honest-
    # subset + r155 PMI-Services-REJECT). PMI Services + Ivey PMI + Philly
    # Fed Manufacturing Index kept HONESTLY UNMAPPED per the doctrine.
    "Retail_Sales": 5.0,
    # Other high-impact macro (PPI, etc. — literature thin or already
    # covered elsewhere — r156+ to expand or stay honest).
    "high_other": 10.0,
    # Tier-2 events
    "medium": 3.0,
    "low": 1.0,
}


_LOOKAHEAD_WINDOW_MIN_DEFAULT = 48 * 60  # 48 hours in minutes
_VIX_LOOKBACK_SESSIONS = 4
_VIX_P50 = 18.0  # rough long-run median ; r148+ candidate : compute empirically
_VIX_P75 = 24.0  # rough long-run 75th percentile


@dataclass(frozen=True)
class EventProximityFactor:
    """Output of `assess_event_proximity()` -- descriptive only (ADR-017).

    All directional fields are GEOMETRIC/PROBABILISTIC ; NEVER imperative.
    The frontend strips signs at the UI boundary per r142 trader RED-1
    discipline (parity with `confluence_engine.Driver`).

    Fields :
        next_event_id              : UUID stringified, or None if no future
                                     event in window.
        next_event_title           : ForexFactory title verbatim, or None.
        next_event_currency        : ISO 3-letter currency, or None.
        next_event_minutes_until   : Minutes from `now` to `scheduled_at`,
                                     positive int, or None.
        next_event_impact          : "high"/"medium"/"low", or None.
        next_event_class           : Mapped event class ("FOMC"/"NFP"/etc.),
                                     or None if title unmapped.
        expected_drift_direction   : "up"/"down"/"unknown". "unknown" when
                                     business cycle proxy unavailable.
        expected_drift_magnitude_bp: Literature-cited PRIOR in basis points,
                                     signed. None if `event_class` unmapped
                                     OR data confidence is too low.
        confidence                 : "high"/"medium"/"low"/"unavailable".
        vix_regime_gate            : "above_p75"/"p50_to_p75"/"below_p50"/
                                     "unavailable".
        caveat                     : Verbatim 1-line honest-scope disclosure
                                     for downstream Driver.evidence field.
        literature_anchor          : Verbatim citation string.
        parse_failures             : Frozenset of sentinel labels surfacing
                                     data-quality issues honestly (parity
                                     with `SurpriseClassification`).
    """

    next_event_id: str | None
    next_event_title: str | None
    next_event_currency: str | None
    next_event_minutes_until: int | None
    next_event_impact: ImpactLevel | None
    next_event_class: str | None
    expected_drift_direction: DriftDirection
    expected_drift_magnitude_bp: float | None
    confidence: EventConfidence
    vix_regime_gate: VixRegimeGate
    caveat: str
    literature_anchor: str
    parse_failures: frozenset[str] = field(default_factory=frozenset)


# ── Title → event class mapping ──────────────────────────────────────
#
# Substring-match (case-insensitive) on `EconomicEvent.title` ; first match
# wins. Order matters : more-specific patterns (e.g. "Core CPI") MUST come
# BEFORE generic ones ("CPI"). `_TITLE_FRAGMENT_BLOCKED` (r149) acts as a
# defensive negative-list checked BEFORE positive matching, mirroring the
# r144 reconciler `TITLE_FRAGMENT_BLOCKED` pattern. The ForexFactory XML
# feed strips country prefixes ("Cash Rate" not "AU Cash Rate"), so
# substring collisions across countries are real (e.g. RBA "Cash Rate"
# substring-matches RBNZ "Official Cash Rate"). Pattern naming convention
# matches the verbatim FF XML titles empirically extracted from
# `https://nfs.faireconomy.media/ff_calendar_thisweek.xml` 2026-05-22.
_TITLE_TO_EVENT_CLASS: tuple[tuple[str, str], ...] = (
    # FOMC family
    ("fomc statement", "FOMC"),
    ("fomc press conference", "FOMC"),
    ("federal funds rate", "FOMC"),
    ("fomc meeting minutes", "FOMC"),
    # ECB family
    ("ecb press conference", "ECB"),
    ("ecb main refinancing rate", "ECB"),
    ("ecb monetary policy statement", "ECB"),
    ("ecb deposit facility rate", "ECB"),
    # BoE family
    ("boe monetary policy report", "BoE"),
    ("boe official bank rate", "BoE"),
    ("mpc meeting minutes", "BoE"),
    # BoJ family (r149 broadened — was BoJ outlook + policy rate only)
    ("boj outlook report", "BoJ"),
    ("boj policy rate", "BoJ"),
    ("boj press conference", "BoJ"),
    ("boj summary of opinions", "BoJ"),
    # RBA family (r149 new — Vojtko-Dujava SSRN 5384407)
    ("rba monetary policy statement", "RBA"),
    ("rba press conference", "RBA"),
    ("rba rate statement", "RBA"),
    ("statement on monetary policy", "RBA"),  # quarterly SoMP, often bare
    ("cash rate", "RBA"),  # bare 2-word FF XML title for RBA decision
    # BoC family (r149 new — Vojtko-Dujava SSRN 5384407)
    ("boc monetary policy report", "BoC"),
    ("boc press conference", "BoC"),
    ("boc rate statement", "BoC"),
    ("overnight rate", "BoC"),  # bare FF XML title for BoC decision
    # Tankan (r149 new — Japan flagship business sentiment, quarterly)
    ("tankan", "Tankan"),
    # r153 — Consumer Confidence (Conference Board) family. Asymmetric class.
    # MORE SPECIFIC than any catch-all ; ordered EARLY to preserve match order.
    # Empirical 60d fixture catches "CB Consumer Confidence" exactly.
    ("cb consumer confidence", "CCI"),
    ("conference board consumer confidence", "CCI"),
    # r153 — Michigan Consumer Sentiment family (UoM = University of Michigan).
    # Both Prelim + Revised release variants. Asymmetric class.
    ("prelim uom consumer sentiment", "Michigan"),
    ("revised uom consumer sentiment", "Michigan"),
    ("uom consumer sentiment", "Michigan"),
    # r153 — Michigan inflation expectations sub-component. Treated same class
    # as headline Michigan per literature (Akhtar 2012) ; engine cannot
    # decompose without FF XML sub-field parsing (honest scope, r154+).
    ("prelim uom inflation expectations", "Michigan"),
    ("uom inflation expectations", "Michigan"),
    # r153 — ISM family (US Institute for Supply Management). Manufacturing
    # first (early-month, higher tier), Services second. ISM Non-Manufacturing
    # is the older name for ISM Services — both mapped to same class.
    ("ism manufacturing pmi", "ISM"),
    ("ism services pmi", "ISM"),
    ("ism non-manufacturing pmi", "ISM"),
    ("ism manufacturing prices", "ISM"),
    # r154 — CB Governor scheduled-speech mappings (literature-anchored
    # subset, Pattern #15 R59-disprove honest scope). MORE SPECIFIC than the
    # generic "monetary policy statement" BoJ fallback ; ordered EARLY to
    # preserve first-match-wins. Each pattern matches a verbatim FF title
    # substring witnessed in the 60d empirical fixture.
    #
    # ECB_Speech : "ECB President Lagarde Speaks" + future Lagarde successor
    # variants. Substring "ecb president" is safer than bare "lagarde" (less
    # collision risk if a non-ECB Lagarde shows up). Order BEFORE the BoJ
    # fallback "monetary policy statement".
    ("ecb president", "ECB_Speech"),
    # BoE_Speech : "BOE Gov Bailey Speaks" + Mansion House annual speech +
    # any future BoE Governor successor. Substring "bailey" is the simplest
    # match for current governor ; "mansion house" covers the annual speech.
    ("bailey", "BoE_Speech"),
    ("mansion house", "BoE_Speech"),
    # SNB_Speech : "SNB Chairman Schlegel Speaks" + future SNB Chairman
    # variants. Substring "snb chairman" is more durable than "schlegel".
    ("snb chairman", "SNB_Speech"),
    # r152 — PCE family (FOMC's preferred core inflation gauge). MORE SPECIFIC
    # than generic CPI patterns ; ordered BEFORE CPI to preserve first-match-wins.
    ("core pce price index", "PCE"),
    ("pce price index", "PCE"),
    # r152 — GDP family (high-impact growth-channel release, quarterly). Generic
    # patterns catch US Advance/Prelim/Final + EZ/JP GDP variants.
    # r153 — added "gdp m/m" + "prelim gdp price index" for UK/CAD monthly GDP
    # + US GDP deflator (Prelim GDP Price Index q/q is the deflator component,
    # same release window as headline GDP, similar magnitude class).
    ("advance gdp q/q", "GDP"),
    ("prelim gdp q/q", "GDP"),
    ("final gdp q/q", "GDP"),
    ("gdp q/q", "GDP"),
    ("gdp m/m", "GDP"),  # r153 — UK + CAD monthly GDP
    ("prelim gdp price index", "GDP"),  # r153 — US GDP deflator
    # r155 — Retail Sales family. Ordered BEFORE NFP-specific to preserve
    # first-match-wins (no substring collision risk : "retail sales" doesn't
    # appear in NFP or Employment titles, but defensive ordering anyway).
    # Single pattern "retail sales m/m" captures ALL 5 fixture variants via
    # substring : "Retail Sales m/m" (USD/GBP/CAD bare) AND "Core Retail Sales
    # m/m" (USD/CAD Core variant has "retail sales m/m" as substring at
    # position 5). Same Retail_Sales class for all — Birz-Lott 2011 didn't
    # differentiate Core vs Headline.
    ("retail sales m/m", "Retail_Sales"),
    # Tier-1 US macro — NFP-specific (US-only) before generic Employment family
    ("non-farm employment change", "NFP"),
    ("nonfarm payrolls", "NFP"),
    # r150 — generic employment family for AUD/CAD bare "Employment Change"
    # (FF XML title without "Non-Farm" prefix) + cross-currency "Unemployment
    # Rate". Empirically verified in prod DB : 1 AUD high-impact + 1 CAD high-
    # impact + 1 USA high-impact each in last 30 days (researcher web R59 +
    # prod SQL probe r149+r150). Magnitude 20bp aligned with NFP (literature
    # priors for labor-market releases per Lucca-Moench 2015 + Kurov 2021).
    ("employment change", "Employment"),
    ("unemployment rate", "Employment"),
    # CPI variants — more specific BEFORE generic to preserve match order
    ("core cpi m/m", "CPI"),
    ("core cpi y/y", "CPI"),
    ("trimmed mean cpi", "CPI"),  # r149 AUD-specific (RBA preferred-core)
    ("trimmed cpi", "CPI"),  # r149 CAD-specific (StatCan BoC-preferred)
    ("median cpi", "CPI"),  # r149 CAD-specific
    ("common cpi", "CPI"),  # r149 CAD-specific
    ("tokyo core cpi", "CPI"),  # r149 JPY-specific
    ("national core cpi", "CPI"),  # r149 JPY-specific
    ("cpi m/m", "CPI"),  # shared US/CAD bare title
    ("cpi y/y", "CPI"),
    # Generic fallback patterns (r149) — matched ONLY if no specific
    # pattern above matched ; ForexFactory uses bare titles for JPY BoJ
    # rate decisions (`Monetary Policy Statement` with country=JPY).
    ("monetary policy statement", "BoJ"),
)


# r149 — defensive negative-list. Checked BEFORE positive patterns ; returning
# None for blocked titles prevents silent misclassification. Each entry must
# have a comment explaining the specific collision risk it guards against.
_TITLE_FRAGMENT_BLOCKED: frozenset[str] = frozenset(
    {
        # RBNZ "Official Cash Rate" (NZD) substring-matches RBA "Cash Rate" (AUD).
        # No Ichor asset has NZD exposure today (per config.py:151-161), but
        # blocking here is defensive future-proofing against the silent-class
        # collision if NZD_USD or AUD_NZD is ever added to the tracked set.
        "official cash rate",
        # r153 — ADP "ADP Non-Farm Employment Change" (USD) silently substring-
        # matches the NFP-specific pattern "non-farm employment change" → would
        # misclassify ADP as the BLS-NFP class. ADP is a PRIVATE survey by ADP
        # Research Institute (~26 million worker payroll sample), methodologically
        # DISTINCT from BLS Non-Farm Payrolls (gov't establishment survey).
        # Empirically ADP-NFP correlation has WEAKENED post-2020 (BLS rebench-
        # marks rendered ADP a noisy leading indicator). The r144 actuals
        # reconciler already blocks "adp" upstream ; mirror that defensive
        # block here to prevent silent misclassification on the engine side.
        "adp non-farm employment change",
        # r153 — RBNZ "Monetary Policy Statement" (NZD) silently substring-
        # matches the BoJ generic-fallback pattern "monetary policy statement"
        # → would misclassify RBNZ as BoJ. RBNZ ≠ BoJ in literature priors :
        # RBNZ uses Official Cash Rate (NZD-specific tightening cycle), BoJ
        # uses YCC + JGB purchases (post-2024 normalization regime).
        # Defensive future-proofing for the same reason as "official cash rate"
        # block above — if NZD asset is ever tracked, silent collision would
        # fire on every RBNZ MPC meeting (8/year).
        "rbnz monetary policy statement",
    }
)


# r154 code-reviewer N-1 fix : moved from inline (`assess_event_proximity` hot
# path) to module-level constant. Saves one frozenset allocation per session-
# card × asset × pass + aligns with codebase convention (every other frozenset/
# map in this module is module-level). Pattern : the canonical asymmetric
# event classes that emit `direction="unknown"` + `asymmetric_negativity_bias`
# sentinel pre-event regardless of `business_cycle_sign`. r153 added CCI +
# Michigan ; r154 adds SNB_Speech per Ranaldo-Rossi 2009 + 2024 SNB
# textual-analysis paper.
_ASYMMETRIC_NEGATIVITY_CLASSES: frozenset[str] = frozenset({"CCI", "Michigan", "SNB_Speech"})


# r155 — Low-signal-confidence class set. Mechanically signals that an event
# class has peer-reviewed literature with EXPECTED SIGN but STATISTICALLY
# INSIGNIFICANT correlation (cf Birz-Lott 2011 *JBF* for Retail Sales). The
# magnitude IS quantified (cold-start prior at floor) but the user / consumer
# should KNOW the effect is below classical detection power. Confidence is
# clamped to "low" (parity with `vix_observation_missing` clamping pattern) +
# `low_signal_confidence` sentinel surfaced in `parse_failures` (parity with
# r150 `single_source_direction` + r153 `asymmetric_negativity_bias` —
# mechanical downstream filtering on weak-evidence class).
#
# This is the 3rd magnitude-uncertainty sentinel in the Engine 8 honest-scope
# ladder :
#   r150 `single_source_direction` — direction prior weakly grounded
#   r153 `asymmetric_negativity_bias` — symmetric sign breaks
#   r155 `low_signal_confidence` — magnitude effect-size below detection
# Each surfaces a DIFFERENT axis of weak-evidence honesty without overlapping
# (a class can hold multiple sentinels in principle — none currently do).
_LOW_SIGNAL_CONFIDENCE_CLASSES: frozenset[str] = frozenset({"Retail_Sales"})


def _map_title_to_event_class(title: str) -> str | None:
    """Pure-fn substring lookup ; returns None if no class mapped.

    Honest scope : maps high-impact event titles for USD/EUR/GBP/AUD/CAD/JPY
    central banks + tier-1 macro (FOMC/ECB/BoE/RBA/BoC/BoJ/NFP/CPI/Tankan) to
    academic event classes. r149 broadened the r147 baseline (FOMC/ECB/BoE/BoJ
    + NFP/CPI) with RBA/BoC families + Tankan + JPY/AUD/CAD CPI variants per
    researcher web R59 FF XML verbatim verification. Unmapped titles → None
    (caller surfaces "event_class_unmapped" sentinel in parse_failures, never
    silent). Blocked titles (per `_TITLE_FRAGMENT_BLOCKED`) also return None
    defensively, even if a positive pattern would otherwise match.
    """
    if not title:
        return None
    needle = title.lower().strip()
    # r149 — defensive blocked-list short-circuit before positive matching
    for blocked in _TITLE_FRAGMENT_BLOCKED:
        if blocked in needle:
            return None
    for fragment, cls in _TITLE_TO_EVENT_CLASS:
        if fragment in needle:
            return cls
    return None


def _impact_multiplier(impact: str | None) -> float:
    """Map FF impact tier to drift multiplier per Lucca-Moench + Kurov 2021
    conditioning. High events drive the bulk of drift ; low events ≈ noise."""
    if impact == "high":
        return 1.0
    if impact == "medium":
        return 0.4
    return 0.0  # low impact OR unknown → no expected drift


def _time_decay(minutes_until: int, window_minutes: int) -> float:
    """Linear time decay : 1.0 at t=0 (firing) ; 0.0 at t=window edge.

    Honest scope : Lucca-Moench observed a 24h pre-FOMC drift but the
    intensity profile is roughly linear in the academic literature
    (with some intra-day pickup in the final 60min). r147 ships the
    simple linear approximation ; r148+ candidate : empirical decay
    fit from realized intraday bars."""
    if minutes_until <= 0:
        return 1.0  # event firing now / just passed → full magnitude
    if minutes_until >= window_minutes:
        return 0.0
    return 1.0 - (minutes_until / window_minutes)


def _vix_regime_to_gate(vix_value: float | None) -> tuple[VixRegimeGate, float]:
    """Per Kurov-Halova-Wolfe-Gilbert (2021) + QuantSeeker 2024 replication
    through Dec 2024 : pre-FOMC drift is concentrated in HIGH-VIX regimes
    (VIX > p75 ~24), attenuated in p50-p75 (~18-24), near-zero in low-VIX
    (<p50 ~18). Returns (gate_label, multiplier)."""
    if vix_value is None:
        return "unavailable", 0.0
    if vix_value >= _VIX_P75:
        return "above_p75", 1.0
    if vix_value >= _VIX_P50:
        return "p50_to_p75", 0.4
    return "below_p50", 0.1


async def _latest_vix_value(session: AsyncSession, now: datetime) -> float | None:
    """Read latest VIX observation (FRED:VIXCLS) in last N sessions for
    regime gate.

    VIX is stored in `fred_observations` per the same pattern as
    `services/vix_term_structure.py` (FRED VIXCLS series ID, daily
    cadence). Returns None if no observation in `_VIX_LOOKBACK_SESSIONS`
    sessions (data-honesty fail-closed → vix_regime_gate=unavailable →
    confidence capped low).
    """
    lookback_floor = now - timedelta(days=_VIX_LOOKBACK_SESSIONS * 2)  # business-day approx
    stmt = (
        select(FredObservation)
        .where(
            FredObservation.series_id == "VIXCLS",
            FredObservation.observation_date >= lookback_floor.date(),
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None or row.value is None:
        return None
    return float(row.value)


def _currencies_for_asset(asset: str) -> tuple[str, ...]:
    """Map asset code to currencies whose events affect it.

    Honest scope : USD-base / X-USD assets pull USD events ; EURUSD/GBPUSD
    also pull their respective non-USD currency. Equity indices pull USD
    only (FOMC is dominant ; foreign-bank events ≈ noise for SPX/NAS).
    """
    asset = asset.upper()
    if asset == "EUR_USD":
        return ("USD", "EUR")
    if asset == "GBP_USD":
        return ("USD", "GBP")
    if asset == "USD_JPY":
        return ("USD", "JPY")
    if asset == "AUD_USD":
        return ("USD", "AUD")
    if asset == "USD_CAD":
        return ("USD", "CAD")
    if asset in {"XAU_USD", "SPX500_USD", "NAS100_USD"}:
        return ("USD",)
    return ("USD",)  # safe default


async def assess_event_proximity(
    session: AsyncSession,
    *,
    asset: str,
    now: datetime | None = None,
    lookahead_minutes: int = _LOOKAHEAD_WINDOW_MIN_DEFAULT,
    business_cycle_sign: int | None = None,
) -> EventProximityFactor | None:
    """Compute pre-event drift expectation per literature-cited prior.

    Args :
        session            : SQLAlchemy async session.
        asset              : Asset code (EUR_USD/GBP_USD/XAU_USD/SPX500_USD/
                             NAS100_USD/USD_JPY/AUD_USD/USD_CAD).
        now                : Injection point for deterministic testing.
                             Default `datetime.now(UTC)`.
        lookahead_minutes  : Window depth in minutes (default 48h = 2880).
                             Events further out → not considered. Per
                             code-reviewer SF-2 : if caller passes <= 0,
                             value is silently auto-replaced with the
                             default (2880) — semantic equivalent of
                             "no useful window".
        business_cycle_sign: +1 (expansion, default) or -1 (contraction).
                             None defaults to +1 with explicit caveat
                             surfaced via the `caveat` output field.

    Returns `EventProximityFactor | None`. None means NO future events
    in window (caller surfaces "Aucun event majeur dans les 48h" empty
    state). Engine NEVER raises -- all edge cases honest-handled.

    HONEST SCOPE — TITLE MAPPING COVERAGE (trader YELLOW-3, r149 update) :

    `_TITLE_TO_EVENT_CLASS` covers FOMC/ECB/BoE/BoJ central-bank classes
    + tier-1 US macro (NFP, CPI variants). r149 extended coverage to
    AUD (RBA family + Trimmed Mean CPI), CAD (BoC family + Median/
    Trimmed/Common CPI), JPY (BoJ broadened + Tankan + Tokyo/National
    Core CPI) per researcher web R59 FF XML verbatim. Unmapped titles
    still fall through to `event_class_unmapped` → driver silently None
    per doctrine #11 (no fabricated baseline magnitude).

    HONEST SCOPE — JPY IMPACT FILTER GAP (trader YELLOW-3, r149) :

    ForexFactory empirically marks ALL JPY events as `low` impact in
    prod (0 high + 0 medium over 90 days, including National Core CPI,
    BOJ Summary of Opinions, Monetary Policy Meeting Minutes — verified
    via prod DB query 2026-05-23). `_impact_multiplier()` returns 0.0
    for `low` impact, so r149 JPY title-mapping is FUTURE-PROOFING and
    won't fire under current impact filter. r150+ candidate : either
    elevate JPY impact handling explicitly OR ingest alternative
    provider with proper JPY-event impact rating.

    HONEST SCOPE — RBA/BoC PRE-DRIFT DIRECTION (r150 single-source disclosure) :

    Vojtko-Dujava SSRN 5384407 (June 2025) is titled "Pre-Announcement Drift
    for BoE, BoJ, SNB" — its MAIN result is POSITIVE pre-drift for those 3
    central banks. RBA/BoC NEGATIVE drift appears only as a SECONDARY
    histogram observation (commodity-exporter divergence hypothesis). The
    claim is SINGLE-SOURCE (Quantpedia-affiliated working paper, 71
    downloads, no formal t-statistic battery in the blog write-up) and
    UNREPLICATED. r150 researcher web R59 found NO independent secondary
    confirmation (Kurov / Boyd-Hu-Jagannathan / BIS / RBA / BoC research
    papers do not cover RBA/BoC pre-drift sign). r150 therefore KEEPS the
    POSITIVE baseline_bp + caveat strategy : magnitude-only as cold-start
    prior + runtime caveat surfaces the single-source weakness honestly.
    Sign-flip implementation deferred INDEFINITELY until (a) Vojtko-Dujava
    reaches peer-reviewed publication OR (b) independent replication
    appears (Hu/Pan-style methodology on TSX/ASX intraday).

    R-WITNESS-EMPIRICAL discipline : post-deploy probe
    `SELECT title FROM economic_events WHERE impact='high' AND title
    NOT IN <mapped>` identifies unmapped titles for incremental coverage.

    8 edge cases handled :
      1. No future events in window           → return None
      2. Event already fired                  → next future event picked
      3. Weekend / US holiday                 → no special case (r148+) ;
                                                if no events scheduled
                                                → None (HONEST)
      4. Pre-event window <60min              → confidence='high'
      5. No VIX in last 4 business sessions   → vix_regime_gate='unavailable',
         (~8 calendar days incl. weekends)      confidence capped at 'low',
                                                vix_multiplier=0.4 fallback
      6. business_cycle_sign None             → default +1 + caveat
      7. event_class unmapped                 → magnitude_bp=None,
                                                parse_failures+='event_class_unmapped'
      8. Multiple events in window            → pick highest-impact ;
                                                tie-break by earliest scheduled_at
    """
    if now is None:
        now = datetime.now(UTC)
    if lookahead_minutes <= 0:
        lookahead_minutes = _LOOKAHEAD_WINDOW_MIN_DEFAULT

    parse_failures: set[str] = set()
    cycle_sign_default_applied = business_cycle_sign is None
    if business_cycle_sign is None:
        business_cycle_sign = 1  # expansion default per Boyd-Hu-Jagannathan baseline

    currencies = _currencies_for_asset(asset)
    window_end = now + timedelta(minutes=lookahead_minutes)

    # Query : upcoming events in window, currency-filtered, impact-tier-ordered.
    # Highest-impact wins (edge case 8) ; tie-break by earliest scheduled_at.
    # Impact ordering : "high" > "medium" > "low" via CASE.
    stmt = (
        select(EconomicEvent)
        .where(
            EconomicEvent.scheduled_at.is_not(None),
            EconomicEvent.scheduled_at > now,
            EconomicEvent.scheduled_at <= window_end,
            EconomicEvent.currency.in_(currencies),
            EconomicEvent.impact.in_(("high", "medium")),
        )
        .order_by(EconomicEvent.scheduled_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return None  # edge case 1 : no future events

    # Pick highest-impact ; tie-break by earliest scheduled_at (sorted ASC above).
    high_rows = [r for r in rows if r.impact == "high"]
    pool = high_rows if high_rows else rows
    next_event = pool[0]

    if next_event.scheduled_at is None:  # defensive
        return None

    minutes_until = int((next_event.scheduled_at - now).total_seconds() / 60)
    if minutes_until < 0:
        minutes_until = 0  # edge case 2 defensive (filtered by > now above)

    event_class = _map_title_to_event_class(next_event.title)
    if event_class is None:
        parse_failures.add("event_class_unmapped")

    # VIX regime gate. If unavailable, use a CONSERVATIVE DEFAULT multiplier
    # (0.4, matching p50_to_p75 baseline) so magnitude stays computable —
    # we still want to surface the event identity to the user, just with
    # confidence capped at 'low' (researcher R59 §6 edge case 5).
    vix_value = await _latest_vix_value(session, now)
    vix_gate_label, vix_multiplier = _vix_regime_to_gate(vix_value)
    if vix_gate_label == "unavailable":
        parse_failures.add("vix_observation_missing")
        vix_multiplier = 0.4  # conservative default ; confidence capped 'low'

    # Compute expected drift
    if event_class is None:
        expected_drift_bp: float | None = None
        direction: DriftDirection = "unknown"
    else:
        baseline_bp = EVENT_CLASS_BASELINE_BP.get(event_class, 0.0)
        impact_mult = _impact_multiplier(next_event.impact)
        time_dec = _time_decay(minutes_until, lookahead_minutes)
        magnitude_unsigned = baseline_bp * impact_mult * time_dec * vix_multiplier
        if magnitude_unsigned <= 0.01:
            expected_drift_bp = None  # below noise floor → honest unavailable
            direction = "unknown"
        else:
            signed = magnitude_unsigned * business_cycle_sign
            expected_drift_bp = round(signed, 2)
            direction = "up" if signed > 0 else "down" if signed < 0 else "unknown"

    # r153 — asymmetric-negativity-bias handling for consumer-sentiment classes.
    # Anchor : Akhtar-Faff-Oliver-Subrahmanyam 2012 *JBF* 36 "Stock salience and
    # the asymmetric market effect of consumer sentiment news" (US S&P/DJIA
    # data, replicates 2011 AUS study). Bad sentiment surprise → significant
    # negative equity reaction ; good sentiment surprise → muted / no reaction.
    # Engine 8 is FORWARD-LOOKING (pre-event) and CANNOT know the surprise
    # sign before release — symmetric `business_cycle_sign` direction is
    # MISLEADING for asymmetric classes (would claim "up" in expansion based
    # on a model that empirically breaks for these). Override to `unknown`
    # direction + surface `asymmetric_negativity_bias` sentinel (mirrors r150
    # `single_source_direction` honest-scope pattern but BETTER evidenced —
    # 2 peer-reviewed papers US data, not 1 working paper). Magnitude STAYS
    # as the conditional-on-negative-surprise estimate (caveat string carries
    # the conditional framing). Doctrine #11 calibrated honesty applied.
    # r154 code-reviewer SF-2 architectural fix : when an asymmetric class
    # fires, we set `direction="unknown"` + add the sentinel — but the prior
    # implementation (r153) PRESERVED the SIGNED `expected_drift_bp` carrying
    # `business_cycle_sign` bias from line 672. Downstream `_factor_event_
    # anticipation` would propagate this sign into `Driver.contribution` →
    # Brier pipeline silently inherits business-cycle-default-expansion bias
    # for events where the engine itself emits "unknown" direction. Same
    # doctrine #11 calibrated honesty class as r150 RBA/BoC trader YELLOW-2
    # (caveat string-only honesty was asymmetric). Fix : strip the sign when
    # the asymmetric sentinel fires — the magnitude is INHERENTLY UNSIGNED
    # under the literature framing (conditional-on-negative-surprise estimate,
    # direction unknown pre-event). `_ASYMMETRIC_NEGATIVITY_CLASSES` moved to
    # module-level r154 (N-1 fix).
    if event_class in _ASYMMETRIC_NEGATIVITY_CLASSES and expected_drift_bp is not None:
        direction = "unknown"
        # r154 SF-2 architectural fix : strip business_cycle_sign bias from
        # the magnitude when the asymmetric sentinel fires. The literature
        # framing is conditional-on-negative-surprise UNSIGNED magnitude ;
        # the pre-event direction is unknown ; therefore exporting a signed
        # value would silently propagate business-cycle-default bias into
        # downstream Brier/confluence consumers (which multiply by sign).
        # Set abs() so the magnitude is honest-unsigned and downstream
        # consumers compute on an unbiased prior. Doctrine #11 calibrated
        # honesty applied at the source rather than relying on each
        # downstream consumer to strip the sign (frontend already does,
        # but Brier optimizer was silently inheriting the bias).
        expected_drift_bp = abs(expected_drift_bp)
        parse_failures.add("asymmetric_negativity_bias")

    # r155 — Low-signal-confidence class handling. Birz-Lott 2011 JBF tested
    # retail sales news effect on stock returns : expected sign but
    # statistically insignificant correlation. The magnitude IS shipped
    # (5bp floor) but the confidence should signal honestly that the effect
    # size is below classical detection power. Mechanism : add the sentinel
    # to parse_failures (parity with single_source_direction r150 +
    # asymmetric_negativity_bias r153) AND clamp confidence below (post-
    # ladder). Sentinel + clamp BOTH surface so downstream consumers can
    # filter mechanically. Direction stays as computed by business_cycle_sign
    # because Birz-Lott documented the EXPECTED SIGN (not asymmetric like
    # CCI/Michigan/SNB_Speech).
    if event_class in _LOW_SIGNAL_CONFIDENCE_CLASSES and expected_drift_bp is not None:
        parse_failures.add("low_signal_confidence")

    # Confidence ladder (lesson #37 honest-scope ladder)
    if expected_drift_bp is None:
        confidence: EventConfidence = "unavailable"
    elif vix_gate_label == "unavailable":
        confidence = "low"
    elif minutes_until < 60:
        confidence = "high"
    elif minutes_until < 240:
        confidence = "medium"
    else:
        confidence = "low"

    # r155 — Low-signal-confidence proximity-conditional clamp. Trader r155
    # YELLOW-2 fix : unconditional clamp to "low" was too aggressive for the
    # imminent high-impact case. Birz-Lott documents MAGNITUDE insignificance
    # (effect size below detection), NOT PROXIMITY insignificance — an
    # imminent Retail Sales print (<60min) still warrants "medium" attention
    # even if magnitude direction is statistically weak. Clamp logic :
    #   - imminent (<60min) + computed "high" → demote to "medium"
    #   - all other distances + computed "high" or "medium" → demote to "low"
    # The sentinel (`low_signal_confidence`) ALWAYS fires regardless of
    # proximity — the clamp is the visual-discipline layer, the sentinel is
    # the mechanical-honesty layer.
    if event_class in _LOW_SIGNAL_CONFIDENCE_CLASSES:
        if minutes_until < 60 and confidence == "high":
            confidence = "medium"  # proximity warrants attention despite weak signal
        elif confidence in ("high", "medium"):
            confidence = "low"

    # Caveat : honest-scope verbatim disclosure for Driver.evidence.
    # r147 trader YELLOW-1 : add cold-start prior disclosure ALWAYS to
    # surface that magnitudes are literature-cited PRIORS, not Ichor-data-
    # calibrated. This is the most important honesty signal per doctrine
    # #11 + lesson #37 ; survives until r148+ empirical reaction-beta
    # backfill replaces priors with Ichor-historical estimates.
    caveat_parts: list[str] = []
    if cycle_sign_default_applied:
        caveat_parts.append("Asymétrie cyclique non vérifiée, défaut expansion")
    if vix_gate_label == "unavailable":
        caveat_parts.append("VIX indisponible, gate régime dégradée")
    if event_class is None:
        caveat_parts.append("Classe d'événement non mappée")
    # r150 single-source disclosure (researcher web R59 verification) :
    # Vojtko-Dujava SSRN 5384407 paper title is "Pre-Announcement Drift for
    # BoE, BoJ, SNB" — RBA/BoC NEGATIVE drift appears only as secondary
    # histogram observation. Single-source unreplicated working paper ;
    # r150 KEEPS positive baseline + caveat strategy (no sign-flip in code)
    # until independent peer-reviewed replication appears. Doctrine #11
    # calibrated honesty : surface the source weakness explicitly via BOTH
    # the human-readable caveat string AND the machine-readable
    # `parse_failures` sentinel (r150 trader YELLOW-2 concordance fix :
    # caveat string-only honesty is asymmetric, frontend/Brier consume
    # `Driver.contribution` magnitude without reading caveat ; sentinel
    # lets downstream filter on `single_source_direction` mechanically,
    # mirroring r141 `SurpriseClassification.parse_failures` pattern).
    if event_class in ("RBA", "BoC"):
        caveat_parts.append(
            "Drift pre-event RBA/BoC : source unique non-répliquée "
            "(Vojtko-Dujava SSRN 5384407 — sign-flip secondaire vs BoE/BoJ/SNB)"
        )
        parse_failures.add("single_source_direction")
    # r153 — asymmetric-negativity-bias caveat surface (parity with RBA/BoC
    # sentinel pattern). Anchor : Akhtar-Faff-Oliver-Subrahmanyam 2012 *JBF*
    # (US S&P/DJIA data, replicated AUS 2011 finding) — for CCI + Michigan,
    # bad sentiment surprises move equity SIGNIFICANTLY negative ; good
    # surprises move equity barely. Magnitude 10bp reflects the conditional-
    # on-negative-surprise estimate ; pre-event direction is `unknown` per
    # the asymmetric override above. Caveat surfaces this honestly to user
    # surface AND machine-readable sentinel mirrors RBA/BoC pattern.
    if event_class in ("CCI", "Michigan"):
        # r153 Phase 2 trader YELLOW-2 fix : prior caveat "magnitude
        # significative uniquement sur surprise négative" was borderline
        # directional read for a non-trader user. Reworded to pure
        # epistemic/geometric framing (skew descriptor + literature
        # citation only ; no implied behaviour). Parity with r150 RBA/BoC
        # purely-epistemic disclosure pattern.
        caveat_parts.append(
            "Skew empirique négatif : magnitude observée historiquement "
            "asymétrique selon le signe de la surprise "
            "(Akhtar 2012 JBF + Pinchuk 2022 arXiv)"
        )
    # r154 — SNB_Speech asymmetric skew caveat (parity with CCI/Michigan
    # purely-epistemic framing). Anchor : Ranaldo-Rossi 2009 *JIMF* + 2024
    # SNB textual-analysis paper.
    if event_class == "SNB_Speech":
        caveat_parts.append(
            "Skew empirique négatif : sentiment négatif observé historiquement "
            "plus rapide à propager que sentiment positif "
            "(Ranaldo-Rossi 2009 JIMF, données 2000-2005 pré-floor-cap — "
            "généralisation post-2015 à confirmer)"
        )
    # r154 — ECB_Speech + BoE_Speech symmetric caveat (no asymmetric
    # documented in Ehrmann-Fratzscher 2007 ; effect is rate-channel-only,
    # equity extrapolation conservative). Honest scope flag surfaces that
    # the 7-8bp magnitude is extrapolated from interest-rate event-window
    # studies, not direct equity event studies.
    if event_class in ("ECB_Speech", "BoE_Speech"):
        caveat_parts.append(
            "Magnitude extrapolée de l'event-window taux (Ehrmann-Fratzscher "
            "2007 ECB WP 557) vers l'equity via gate VIX — calibration "
            "equity-specifique r155+"
        )
    # r155 — Retail Sales weak-signal caveat (parity with single_source_direction
    # r150 + asymmetric_negativity_bias r153 purely-epistemic framing). Anchor :
    # Birz-Lott 2011 *JBF* "The effect of macroeconomic news on stock returns:
    # New evidence from newspaper coverage" — retail sales news showed expected
    # sign but statistically insignificant correlation. 5bp = floor estimate,
    # well below NFP/CPI/GDP class — caveat surfaces the weak-evidence honesty.
    if event_class == "Retail_Sales":
        # r155 trader YELLOW-3 fix : caveat reworded action-oriented + simpler
        # framing for non-trader users. Prior "statistiquement non-significative"
        # reads as developer-jargon ; "sans force statistique fiable" surfaces
        # the same epistemic content but more accessibly (parity with r153
        # trader YELLOW-2 epistemic-rewording pattern for CCI/Michigan).
        caveat_parts.append(
            "Faible-signal : la littérature documente la direction attendue "
            "mais sans force statistique fiable (Birz-Lott 2011 JBF)"
        )
    # ALWAYS append the cold-start prior caveat (trader YELLOW-1).
    caveat_parts.append("Magnitude prior littérature, pas calibrée sur historique Ichor")
    caveat = " ; ".join(caveat_parts)

    # r153 — extended literature anchor : add Akhtar 2012 (consumer-sentiment
    # asymmetry, peer-reviewed US data, replaces hallucinated Karnaukh-Vrolijk
    # 2019 caught r153 R59 — pattern #13 + #15 in action) + Andersen-
    # Bollerslev-Diebold-Vega 2007 (intraday ISM significant in equity-vol
    # regression, foundational MNA event-study) + Pinchuk 2022 (aggregate
    # 11-25 bp/1σ MNA band, cleanest cross-class anchor for r152+r153 priors).
    # r155 — extended literature anchor : add Birz-Lott 2011 JBF for the new
    # Retail_Sales class. Their negative-result peer-reviewed finding (expected
    # sign + statistically insignificant correlation) is the calibration anchor
    # for the 5bp floor magnitude + `low_signal_confidence` sentinel pattern.
    literature_anchor = (
        "Lucca-Moench 2015 (drift) + Boyd-Hu-Jagannathan 2005 (asymétrie cyclique) "
        "+ Kurov 2021 (gate VIX) + Akhtar et al. 2012 JBF (asymétrie consumer-sentiment) "
        "+ Andersen-Bollerslev-Diebold-Vega 2007 JIE (MNA intraday) + Pinchuk 2022 arXiv "
        "+ Birz-Lott 2011 JBF (retail-sales faible-signal)"
    )

    # r147 code-reviewer SF-3 : malformed impact → surface sentinel + None,
    # parity with r141 SurpriseClassification honesty discipline. The ORM
    # `EconomicEvent.impact` is String(16) NOT NULL but has no DB CHECK,
    # so malformed values are possible from upstream provider drift.
    if next_event.impact in ("high", "medium", "low"):
        next_event_impact_typed: ImpactLevel | None = next_event.impact  # type: ignore[assignment]
    else:
        next_event_impact_typed = None
        parse_failures.add("impact_value_invalid")

    return EventProximityFactor(
        next_event_id=str(next_event.id),
        next_event_title=next_event.title,
        next_event_currency=next_event.currency,
        next_event_minutes_until=minutes_until,
        next_event_impact=next_event_impact_typed,
        next_event_class=event_class,
        expected_drift_direction=direction,
        expected_drift_magnitude_bp=expected_drift_bp,
        confidence=confidence,
        vix_regime_gate=vix_gate_label,
        caveat=caveat,
        literature_anchor=literature_anchor,
        parse_failures=frozenset(parse_failures),
    )
