"""calibration_witness.py — Chantier B slice-4 (ADR-119).

Pure-core, I/O-free. Turns the slice-2/3 calibration candidates
(``conviction_calibration.select_calibrator_oos``) into an actual,
reproducible OUT-OF-SAMPLE witness over the realised track-record: *does
re-calibrating the conviction beat leaving it raw, measured on data the fit
never saw?*

Discipline (ADR-116/117/118): only the OOS answer is meaningful, and a thin
sample is reported as **inconclusive**, never spun as an edge. The witness
fits on the chronologically EARLIER cards and scores on the LATER ones (a
real forward test, no leakage), per asset and pooled, and states N honestly.

This module decides nothing live: it produces a report. Wiring a winning
calibrator into the verdict stays a separate GATED step (deploy + sustained
witness). The CLI ``cli/run_calibration_witness.py`` feeds it real
``session_card_audit`` rows; this core is unit-tested on synthetic samples.

Doctrine: ADR-009 (Voie D) — zero LLM / IO / spend, pure arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conviction_calibration import select_calibrator_oos

# A held-out test split below this many cards is reported but flagged
# inconclusive (mirrors the ADR-116 IC95 honesty guard: a small-sample delta
# is suggestive, not proof).
_MIN_CONCLUSIVE_TEST = 30
_DEFAULT_KS: tuple[float, ...] = (0.0, 5.0, 20.0, 50.0)


@dataclass(frozen=True, slots=True)
class WitnessRow:
    """One asset (or ``POOLED``) forward-test result. ``selected`` is the
    OOS-chosen calibrator label (``identity`` = "do not calibrate beat every
    candidate"). ``improved`` is True only when ``selected`` strictly beats the
    raw/identity Brier on the held-out split. ``conclusive`` is False when the
    test split is too thin to trust the delta."""

    label: str
    n_train: int
    n_test: int
    identity_brier: float
    selected: str
    selected_brier: float
    improved: bool
    conclusive: bool


@dataclass(frozen=True, slots=True)
class CalibrationWitnessReport:
    rows: tuple[WitnessRow, ...]
    train_frac: float
    min_conclusive_test: int

    @property
    def any_conclusive_improvement(self) -> bool:
        """True only if at least one row shows a calibrator that BOTH beats raw
        OOS AND rests on a non-thin test split — the honest "this is worth
        wiring" signal."""
        return any(r.improved and r.conclusive for r in self.rows)


def _chronological_split(
    samples: list[tuple[float, int]], train_frac: float
) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
    """Split a TIME-ORDERED ``(p_up, y)`` list into (earlier train, later test).
    No shuffle — the test set is strictly in the forecast future of the train
    set, so the witness cannot leak."""
    cut = int(len(samples) * train_frac)
    return samples[:cut], samples[cut:]


def _witness_row(
    label: str,
    samples: list[tuple[float, int]],
    *,
    train_frac: float,
    ks: tuple[float, ...],
    n_bins: int,
    min_conclusive_test: int,
) -> WitnessRow:
    train, test = _chronological_split(samples, train_frac)
    sel = select_calibrator_oos(train, test, ks=ks, n_bins=n_bins)
    if sel is None:
        # empty train or test → cannot witness; report honestly as a no-op row
        return WitnessRow(
            label=label,
            n_train=len(train),
            n_test=len(test),
            identity_brier=0.0,
            selected="insufficient",
            selected_brier=0.0,
            improved=False,
            conclusive=False,
        )
    return WitnessRow(
        label=label,
        n_train=len(train),
        n_test=len(test),
        identity_brier=sel.identity_test_brier,
        selected=sel.best_label,
        selected_brier=sel.best_test_brier,
        improved=sel.improved,
        conclusive=len(test) >= min_conclusive_test,
    )


def run_calibration_witness(
    samples: list[tuple[str, float, int]],
    *,
    train_frac: float = 0.6,
    ks: tuple[float, ...] = _DEFAULT_KS,
    n_bins: int = 10,
    min_conclusive_test: int = _MIN_CONCLUSIVE_TEST,
) -> CalibrationWitnessReport:
    """Forward-test the calibration candidates on ``(asset, p_up, y)`` samples
    that MUST already be sorted oldest-first. Produces one row per asset plus a
    ``POOLED`` row, each a chronological train/test OOS selection. Honest by
    construction: a thin test split is flagged inconclusive and the identity
    (no calibration) is always a candidate the search can return."""
    by_asset: dict[str, list[tuple[float, int]]] = {}
    pooled: list[tuple[float, int]] = []
    for asset, p_up, y in samples:
        by_asset.setdefault(asset, []).append((p_up, y))
        pooled.append((p_up, y))

    rows: list[WitnessRow] = [
        _witness_row(
            asset,
            pairs,
            train_frac=train_frac,
            ks=ks,
            n_bins=n_bins,
            min_conclusive_test=min_conclusive_test,
        )
        for asset, pairs in sorted(by_asset.items())
    ]
    if pooled:
        rows.append(
            _witness_row(
                "POOLED",
                pooled,
                train_frac=train_frac,
                ks=ks,
                n_bins=n_bins,
                min_conclusive_test=min_conclusive_test,
            )
        )
    return CalibrationWitnessReport(
        rows=tuple(rows),
        train_frac=train_frac,
        min_conclusive_test=min_conclusive_test,
    )


def format_witness_markdown(report: CalibrationWitnessReport) -> str:
    """Render the report as a reproducible markdown table + an HONEST verdict.
    States plainly when the data is too thin to conclude — never an invented
    edge (ADR-118)."""
    lines = [
        "# Conviction-calibration OOS witness (ADR-119)",
        "",
        f"Chronological forward test — fit on the earliest {report.train_frac:.0%} of "
        f"each series, score on the rest. A held-out split < {report.min_conclusive_test} "
        "cards is flagged inconclusive (suggestive, not proof).",
        "",
        "| series | n_train | n_test | raw Brier | selected | selected Brier | beats raw? | conclusive? |",
        "| --- | ---: | ---: | ---: | --- | ---: | :---: | :---: |",
    ]
    for r in report.rows:
        beats = "yes" if r.improved else "no"
        conc = "yes" if r.conclusive else "thin"
        lines.append(
            f"| {r.label} | {r.n_train} | {r.n_test} | {r.identity_brier:.4f} | "
            f"{r.selected} | {r.selected_brier:.4f} | {beats} | {conc} |"
        )
    lines.append("")
    if report.any_conclusive_improvement:
        winners = ", ".join(
            f"{r.label} ({r.selected}: {r.identity_brier:.4f}→{r.selected_brier:.4f})"
            for r in report.rows
            if r.improved and r.conclusive
        )
        lines.append(
            f"**Verdict:** a re-calibration beats the raw conviction OOS on a "
            f"non-thin split for: {winners}. Candidate for a GATED live-wiring "
            "step (deploy + sustained re-witness)."
        )
    else:
        lines.append(
            "**Verdict:** no re-calibration beats the raw conviction on a "
            "conclusive (non-thin) out-of-sample split yet — the honest read is "
            "that the track-record is still too short to trust a correction. "
            "Keep emitting the raw conviction; re-run as more cards reconcile."
        )
    return "\n".join(lines)
