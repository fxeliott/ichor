"""benchmark_gate.py — Chantier A : out-of-sample edge gate (ADR-114).

Pure-core, deterministic, **I/O-free**. Answers the only question that makes
Ichor's verdict more than narrative (PLAN_DIRECTEUR §5 Chantier A): does the
``SessionVerdict`` directional read beat a passive (buy-and-hold) and a naive
(persistence) baseline, **out-of-sample, transaction costs included**?

Gate semantics (PLAN_DIRECTEUR §5 gate A, verbatim): the gate is that **the
report exists and is reproducible, NOT that Ichor wins.** This module reports
beat / no-beat **honestly** (doctrine #11 calibrated honesty) and fabricates
no win.

ADR-017 boundary: this module scores DIRECTION + CONVICTION only. It maps a
directional read to a hypothetical **signed window return for measurement**,
never to a trade order; the human-readable ``honest_verdict`` is regex-guarded
against BUY/SELL/TP/SL tokens (mirror of ``session_verdict._FORBIDDEN_VERDICT_
TOKENS_RE``).

ADR-009 (Voie D): zero LLM call, zero network, zero spend — pure arithmetic.

Anti-leakage by design: the baselines are **causal by construction**
(``persistence`` uses the prior same-asset session only; ``always_long`` uses
no data), so the walk-forward out-of-sample evaluation cannot leak future
information into a past prediction.

Scope (ADR-114 slice-1): pure-core only. The CLI that joins
``session_card_audit`` verdicts with realised NY-window returns from Polygon
intraday and persists the report is slice-2 (needs production data).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

# Mirror of ``ichor_brain.session_verdict.VerdictDirection`` — kept local to
# keep this pure-core module dependency-light (no cross-package import).
from typing import Literal

Direction = Literal["up", "down", "neutral"]

# ADR-022 cap mirror — conviction is a percentage on the 0..95 scale, like
# ``SessionVerdict.conviction_pct`` / ``Scenario.conviction_pct`` (CAP_95 * 100).
# Kept local to preserve this module's pure-core independence.
_CONVICTION_PCT_MAX = 95.0

# ADR-017 boundary mirror — byte-identical PATTERN to the forbidden-token set
# in ``session_verdict._FORBIDDEN_VERDICT_TOKENS_RE`` (session_verdict.py:77-80)
# and ``scenarios._FORBIDDEN_MECHANISM_TOKENS_RE`` (scenarios.py:50-53). The two
# upstream constants differ in NAME but share this exact pattern.
_FORBIDDEN_VERDICT_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


def _assert_adr017_clean(text: str) -> str:
    """Raise if ``text`` smuggles a trade-instruction token. The benchmark
    describes measured outcomes; it never prescribes an action."""
    if _FORBIDDEN_VERDICT_TOKENS_RE.search(text):
        raise ValueError(
            "ADR-017 boundary violated : benchmark prose contains a forbidden "
            f"trade-signal token. Got: {text!r}."
        )
    return text


@dataclass(frozen=True, slots=True)
class VerdictOutcomeSample:
    """One ``(asset, NY-session day)`` observation: what Ichor predicted and
    what the NY window actually did.

    ``realized_return_pct`` is the realised return of Eliot's NY window
    (open→close of the ``ny_14h_to_20h_paris`` window) expressed in **percent**
    (``+0.42`` = +0.42 %). It is computed upstream (slice-2 CLI) from Polygon
    intraday bars; the pure-core only needs the number.
    """

    asset: str
    session_date: date
    predicted_direction: Direction
    conviction_pct: float  # 0..95 (ADR-022 cap)
    realized_return_pct: float

    def __post_init__(self) -> None:
        # ADR-022 fail-closed boundary on this module's OWN input. A conviction
        # outside 0..95 would yield a Brier score outside [0, 1] — impossible for
        # a true Brier. Upstream Pydantic models already cap it, but the pure-core
        # defends its own contract rather than silently scoring a nonsense
        # calibration (verifier-flagged, doctrine #11 calibrated honesty).
        if not 0.0 <= self.conviction_pct <= _CONVICTION_PCT_MAX:
            raise ValueError(
                f"conviction_pct must be within 0..{_CONVICTION_PCT_MAX} "
                f"(ADR-022 cap); got {self.conviction_pct}."
            )

    def realized_direction(self, dead_band_pct: float) -> Direction:
        """Classify the realised move with a neutral dead-band: a move smaller
        than ``dead_band_pct`` in magnitude counts as ``neutral`` (a flat /
        range session, which Eliot would pass)."""
        if self.realized_return_pct > dead_band_pct:
            return "up"
        if self.realized_return_pct < -dead_band_pct:
            return "down"
        return "neutral"


def _position_return_pct(
    direction: Direction, realized_return_pct: float, cost_pct: float
) -> float:
    """Net return of taking ``direction`` over the window. ``neutral`` = flat
    (no position, no cost). A taken position pays ``cost_pct`` (round-trip)."""
    if direction == "up":
        return realized_return_pct - cost_pct
    if direction == "down":
        return -realized_return_pct - cost_pct
    return 0.0


@dataclass(frozen=True, slots=True)
class StrategyMetrics:
    """Aggregated performance of one strategy over a sample set."""

    name: str
    n_sessions: int
    n_positions: int  # sessions where the strategy was non-neutral
    coverage: float  # n_positions / n_sessions
    total_return_pct: float
    mean_return_per_session_pct: float
    hit_rate: float | None  # directional accuracy over positions (None if 0)
    win_rate: float | None  # fraction of positions with positive net return


def _compute_metrics(
    name: str,
    samples: list[VerdictOutcomeSample],
    predictions: list[Direction],
    *,
    cost_pct: float,
    dead_band_pct: float,
) -> StrategyMetrics:
    """Compute :class:`StrategyMetrics` for ``predictions`` aligned index-wise
    to ``samples``."""
    if len(samples) != len(predictions):
        raise ValueError(
            f"samples ({len(samples)}) and predictions ({len(predictions)}) must be the same length"
        )
    n_sessions = len(samples)
    n_positions = 0
    hits = 0
    wins = 0
    total = 0.0
    for sample, predicted in zip(samples, predictions, strict=True):
        net = _position_return_pct(predicted, sample.realized_return_pct, cost_pct)
        total += net
        if predicted != "neutral":
            n_positions += 1
            if predicted == sample.realized_direction(dead_band_pct):
                hits += 1
            if net > 0.0:
                wins += 1
    return StrategyMetrics(
        name=name,
        n_sessions=n_sessions,
        n_positions=n_positions,
        coverage=(n_positions / n_sessions) if n_sessions else 0.0,
        total_return_pct=total,
        mean_return_per_session_pct=(total / n_sessions) if n_sessions else 0.0,
        hit_rate=(hits / n_positions) if n_positions else None,
        win_rate=(wins / n_positions) if n_positions else None,
    )


def _ichor_predictions(samples: list[VerdictOutcomeSample]) -> list[Direction]:
    return [s.predicted_direction for s in samples]


def _always_long_predictions(samples: list[VerdictOutcomeSample]) -> list[Direction]:
    """Buy-and-hold analog for a daily-reset window strategy: always long the
    NY window. Uses no data → causal."""
    return ["up" for _ in samples]


def _persistence_predictions(
    samples: list[VerdictOutcomeSample], *, dead_band_pct: float
) -> list[Direction]:
    """Naive baseline: today's prediction = yesterday's realised direction,
    **per asset**. The first session of each asset has no prior → ``neutral``.
    Causal by construction (only uses strictly earlier same-asset data).

    ``samples`` MUST be sorted by ``(asset, session_date)`` — :func:`evaluate`
    guarantees this.
    """
    predictions: list[Direction] = []
    prev_dir_by_asset: dict[str, Direction] = {}
    for sample in samples:
        predictions.append(prev_dir_by_asset.get(sample.asset, "neutral"))
        prev_dir_by_asset[sample.asset] = sample.realized_direction(dead_band_pct)
    return predictions


def classic_buy_and_hold_total_return_pct(
    samples: list[VerdictOutcomeSample], *, cost_pct: float
) -> float:
    """Classic single-entry buy-and-hold: enter long once, hold across every
    session, exit once (one round-trip cost). Sum of realised window returns
    minus a single ``cost_pct``. Reported alongside the daily ``always_long``
    baseline for context."""
    if not samples:
        return 0.0
    return sum(s.realized_return_pct for s in samples) - cost_pct


def brier_score(samples: list[VerdictOutcomeSample], *, dead_band_pct: float) -> float | None:
    """Brier calibration of ``conviction_pct`` as the probability the
    directional read is correct, over **positional** (non-neutral) samples.

    For each positional sample: ``p = conviction_pct / 100`` (ADR-022 0..95
    scale), ``outcome = 1`` if the predicted direction matched the realised
    direction else ``0``; Brier = mean ``(p - outcome) ** 2``. Lower is better.
    ``None`` if there are no positional samples.
    """
    se = 0.0
    n = 0
    for sample in samples:
        if sample.predicted_direction == "neutral":
            continue
        p = sample.conviction_pct / 100.0
        outcome = (
            1.0 if sample.predicted_direction == sample.realized_direction(dead_band_pct) else 0.0
        )
        se += (p - outcome) ** 2
        n += 1
    return (se / n) if n else None


def walk_forward_splits(
    n: int, *, train_size: int, test_size: int, step: int
) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """Pure index helper. Yield ``(train_idx, test_idx)`` tuples over a
    time-ordered series of length ``n``: each test window is strictly **after**
    its train window (no overlap, order preserved → no look-ahead).

    Rolls forward by ``step``. Stops when a full ``test_size`` window no longer
    fits. Returns ``[]`` if the series is too short for one split.
    """
    if train_size <= 0 or test_size <= 0 or step <= 0:
        raise ValueError("train_size, test_size and step must be positive")
    splits: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    start = 0
    while start + train_size + test_size <= n:
        train = tuple(range(start, start + train_size))
        test = tuple(range(start + train_size, start + train_size + test_size))
        splits.append((train, test))
        start += step
    return splits


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Reproducible result of one benchmark run (ADR-114). Carries the honest
    beat / no-beat booleans — never a fabricated win."""

    window: str  # "in_sample" | "walk_forward_oos"
    assets: tuple[str, ...]
    n_sessions: int
    cost_pct: float
    dead_band_pct: float
    ichor: StrategyMetrics
    always_long: StrategyMetrics
    persistence: StrategyMetrics
    classic_buy_and_hold_total_return_pct: float
    brier: float | None
    ichor_beats_always_long: bool
    ichor_beats_persistence: bool
    honest_verdict: str


def _build_report(
    *,
    window: str,
    samples: list[VerdictOutcomeSample],
    predictions_by_strategy: dict[str, list[Direction]],
    cost_pct: float,
    dead_band_pct: float,
) -> BenchmarkReport:
    ichor = _compute_metrics(
        "ichor",
        samples,
        predictions_by_strategy["ichor"],
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
    )
    always_long = _compute_metrics(
        "always_long",
        samples,
        predictions_by_strategy["always_long"],
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
    )
    persistence = _compute_metrics(
        "persistence",
        samples,
        predictions_by_strategy["persistence"],
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
    )
    beats_long = ichor.total_return_pct > always_long.total_return_pct
    beats_persist = ichor.total_return_pct > persistence.total_return_pct
    assets = tuple(sorted({s.asset for s in samples}))
    edge = "confirmé" if (beats_long and beats_persist) else "non confirmé"
    verdict = _assert_adr017_clean(
        f"Sur {len(samples)} séances ({window}), le rendu net d'Ichor = "
        f"{ichor.total_return_pct:.2f}% vs always-long {always_long.total_return_pct:.2f}% "
        f"et persistance {persistence.total_return_pct:.2f}% (coûts {cost_pct:.3f}% inclus). "
        f"Edge out-of-sample {edge}."
    )
    return BenchmarkReport(
        window=window,
        assets=assets,
        n_sessions=len(samples),
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
        ichor=ichor,
        always_long=always_long,
        persistence=persistence,
        classic_buy_and_hold_total_return_pct=classic_buy_and_hold_total_return_pct(
            samples, cost_pct=cost_pct
        ),
        brier=brier_score(samples, dead_band_pct=dead_band_pct),
        ichor_beats_always_long=beats_long,
        ichor_beats_persistence=beats_persist,
        honest_verdict=verdict,
    )


def _sorted_by_asset_date(
    samples: list[VerdictOutcomeSample],
) -> list[VerdictOutcomeSample]:
    return sorted(samples, key=lambda s: (s.asset, s.session_date))


def evaluate(
    samples: list[VerdictOutcomeSample],
    *,
    cost_pct: float = 0.0,
    dead_band_pct: float = 0.0,
) -> BenchmarkReport:
    """In-sample evaluation over all ``samples`` (headline diagnostic).

    Samples are sorted by ``(asset, session_date)`` so the ``persistence``
    baseline is well-defined and deterministic.
    """
    ordered = _sorted_by_asset_date(samples)
    predictions = {
        "ichor": _ichor_predictions(ordered),
        "always_long": _always_long_predictions(ordered),
        "persistence": _persistence_predictions(ordered, dead_band_pct=dead_band_pct),
    }
    return _build_report(
        window="in_sample",
        samples=ordered,
        predictions_by_strategy=predictions,
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
    )


def evaluate_walk_forward(
    samples: list[VerdictOutcomeSample],
    *,
    train_size: int,
    test_size: int,
    step: int,
    cost_pct: float = 0.0,
    dead_band_pct: float = 0.0,
) -> BenchmarkReport | None:
    """Out-of-sample walk-forward evaluation.

    Per asset, sort by date, take walk-forward ``(train, test)`` splits, and
    pool the **test** samples (the out-of-sample observations) into a single
    report. Causal baselines use each asset's full date-ordered series, so a
    test-window prediction never sees future data. (When ``step > test_size``
    leaves gaps, a pooled test prediction may lean on a prior session no window
    scored; this stays causal — the predecessor is strictly earlier — it is
    simply not itself an out-of-sample observation.)

    Returns ``None`` if **no** asset has enough history for a single split —
    an honest "insufficient out-of-sample history yet" rather than a fabricated
    report (ADR-114 thin-window risk).
    """
    by_asset: dict[str, list[VerdictOutcomeSample]] = {}
    for sample in samples:
        by_asset.setdefault(sample.asset, []).append(sample)

    oos_samples: list[VerdictOutcomeSample] = []
    oos_persistence: list[Direction] = []
    for asset_samples in by_asset.values():
        series = sorted(asset_samples, key=lambda s: s.session_date)
        # Per-asset causal persistence over the FULL series (a test prediction
        # may legitimately use a prior sample that lives in the train window).
        persistence_full = _persistence_predictions(series, dead_band_pct=dead_band_pct)
        splits = walk_forward_splits(
            len(series), train_size=train_size, test_size=test_size, step=step
        )
        seen_test: set[int] = set()
        for _train, test in splits:
            for idx in test:
                if idx in seen_test:
                    continue  # overlapping test windows: count each session once
                seen_test.add(idx)
                oos_samples.append(series[idx])
                oos_persistence.append(persistence_full[idx])

    if not oos_samples:
        return None

    predictions = {
        "ichor": _ichor_predictions(oos_samples),
        "always_long": _always_long_predictions(oos_samples),
        "persistence": oos_persistence,
    }
    return _build_report(
        window="walk_forward_oos",
        samples=oos_samples,
        predictions_by_strategy=predictions,
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
    )


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}%"


def _fmt_rate(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


# Below this many sessions a directional hit-rate edge is reported as
# statistically unestablished — a 95% CI on a thin sample is too wide to
# distinguish from chance. A senior-quant honesty guard (doctrine #11), NOT a
# hard cutoff: the report still renders, it just refuses to over-claim an edge.
_MIN_SESSIONS_FOR_DIRECTIONAL_CLAIM = 60


def hit_rate_ci95(hit_rate: float | None, n_positions: int) -> tuple[float, float] | None:
    """Normal-approximation (Wald) 95% confidence interval on the directional
    hit-rate over ``n_positions`` independent positional sessions. ``None`` if
    there are no positions.

    Voie D / ADR-009: pure stdlib (no scipy) — z = 1.959963984540054.
    """
    if hit_rate is None or n_positions <= 0:
        return None
    se = math.sqrt(hit_rate * (1.0 - hit_rate) / n_positions)
    half = 1.959963984540054 * se
    return (max(0.0, hit_rate - half), min(1.0, hit_rate + half))


def _significance_lines(report: BenchmarkReport) -> list[str]:
    """Honest statistical caveat on Ichor's directional read (doctrine #11): a
    95% CI on the hit-rate plus an explicit small-sample warning, so a thin
    window can never be read as a confirmed edge."""
    m = report.ichor
    ci = hit_rate_ci95(m.hit_rate, m.n_positions)
    lines = ["", "### Significativite (honnetete statistique)"]
    if ci is None:
        lines.append("- Ichor n'a pris aucune position directionnelle — rien a tester.")
        return lines
    lo, hi = ci
    lines.append(
        f"- Justesse directionnelle Ichor : {_fmt_rate(m.hit_rate)} sur "
        f"{m.n_positions} positions — IC95 [{_fmt_rate(lo)}, {_fmt_rate(hi)}]."
    )
    if lo <= 0.5 <= hi:
        lines.append(
            "- **Attention** — l'IC95 inclut 50 % : la justesse directionnelle est "
            "indistinguible du hasard sur cet echantillon."
        )
    if report.n_sessions < _MIN_SESSIONS_FOR_DIRECTIONAL_CLAIM:
        lines.append(
            f"- **Attention** — echantillon mince ({report.n_sessions} seances < "
            f"{_MIN_SESSIONS_FOR_DIRECTIONAL_CLAIM}) : insuffisant pour conclure a un "
            f"edge. Resultat indicatif, a re-mesurer sur davantage de seances."
        )
    return lines


def format_report_markdown(report: BenchmarkReport) -> str:
    """Render a :class:`BenchmarkReport` as a reproducible, human-readable
    French markdown report — the literal Chantier A gate deliverable
    ("the report exists and is reproducible", PLAN §5 gate A).

    ADR-017 boundary: the rendered text is regex-guarded — it describes
    measured performance, never prescribes a trade.

    Contract / fail-closed notes (verifier-flagged, intentional):
      - ``report`` MUST be non-None. ``evaluate_walk_forward`` can return
        ``None`` (insufficient history) — the caller null-checks before
        rendering (mypy enforces this via the ``BenchmarkReport`` type).
      - The final ``_assert_adr017_clean`` is a fail-closed safety net over
        the WHOLE rendered string. A pathological asset code that literally
        spelled a trade token (e.g. ``"SELL"``) would be REFUSED rather than
        rendered — by design. Real assets are the 5 ``PriorityAsset`` codes
        (EUR_USD / GBP_USD / XAU_USD / SPX500_USD / NAS100_USD), none of
        which trip the boundary, so this path is unreachable in production.
    """
    assets = ", ".join(report.assets) if report.assets else "(aucun)"

    def _row(m: StrategyMetrics) -> str:
        return (
            f"| {m.name} | {_fmt_pct(m.total_return_pct)} | "
            f"{_fmt_pct(m.mean_return_per_session_pct)} | "
            f"{_fmt_rate(m.hit_rate)} | {_fmt_rate(m.win_rate)} | "
            f"{m.n_positions}/{m.n_sessions} |"
        )

    lines = [
        "# Benchmark gate — verdict Ichor vs baselines (ADR-114)",
        "",
        f"- Fenetre : **{report.window}**",
        f"- Actifs : {assets}",
        f"- Seances : **{report.n_sessions}**",
        f"- Cout round-trip : {report.cost_pct:.3f}% · dead-band : {report.dead_band_pct:.3f}%",
        f"- Brier (calibration conviction) : {('n/a' if report.brier is None else f'{report.brier:.4f}')}",
        "",
        "| Strategie | Rendu total | Rendu/seance | Justesse dir. | Win-rate | Positions |",
        "|---|---|---|---|---|---|",
        _row(report.ichor),
        _row(report.always_long),
        _row(report.persistence),
        "",
        # "Achat-conservation" (FR) plutot que le terme EN "buy-and-hold" : le
        # garde-fou ADR-017 ci-dessous matche \bBUY\b, qui se declencherait sur
        # "Buy-and-hold" (frontiere de mot sur le tiret). Le nom de baseline reste
        # ``classic_buy_and_hold_*`` cote code (non rendu via le garde-fou).
        f"- Achat-conservation passif (entree unique) : {_fmt_pct(report.classic_buy_and_hold_total_return_pct)}",
        f"- Ichor bat always-long : **{'OUI' if report.ichor_beats_always_long else 'NON'}**",
        f"- Ichor bat persistance : **{'OUI' if report.ichor_beats_persistence else 'NON'}**",
        "",
        f"> {report.honest_verdict}",
        *_significance_lines(report),
        "",
        "_Gate (PLAN §5 A) : le rapport existe et est reproductible — pas que Ichor gagne._",
    ]
    return _assert_adr017_clean("\n".join(lines))
