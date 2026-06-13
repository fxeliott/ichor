"""Tests for ``calibration_witness`` (ADR-119, Chantier B slice-4).

Pure-core forward-test of the conviction-calibration candidates. Synthetic
samples; the chronological-split and OOS-selection properties are asserted
directly.
"""

from __future__ import annotations

from ichor_api.services.calibration_witness import (
    CalibrationWitnessReport,
    WitnessRow,
    _chronological_split,
    format_witness_markdown,
    run_calibration_witness,
)


class TestChronologicalSplit:
    def test_splits_earlier_train_later_test(self) -> None:
        train, test = _chronological_split([(0.1, 0), (0.2, 1), (0.3, 0), (0.4, 1), (0.5, 0)], 0.6)
        assert train == [(0.1, 0), (0.2, 1), (0.3, 0)]  # cut = int(5*0.6) = 3
        assert test == [(0.4, 1), (0.5, 0)]

    def test_no_leak_test_is_strictly_after_train(self) -> None:
        samples = [(i / 100, i % 2) for i in range(10)]
        train, test = _chronological_split(samples, 0.7)
        assert len(train) == 7 and len(test) == 3
        assert max(p for p, _ in train) < min(p for p, _ in test)


class TestRunWitness:
    def _overconfident(self, asset: str, n: int) -> list[tuple[str, float, int]]:
        # alternating 0.9/0.1 forecasts that each realise ~50% → strongly
        # over-confident; a calibrator that pulls toward 0.5 beats raw OOS.
        out: list[tuple[str, float, int]] = []
        pattern = [(0.9, 1), (0.1, 0), (0.9, 0), (0.1, 1)]
        for i in range(n):
            p, y = pattern[i % 4]
            out.append((asset, p, y))
        return out

    def test_empty_samples_no_rows(self) -> None:
        rep = run_calibration_witness([])
        assert rep.rows == ()
        assert rep.any_conclusive_improvement is False

    def test_pooled_row_appended(self) -> None:
        rep = run_calibration_witness(self._overconfident("X", 20))
        labels = [r.label for r in rep.rows]
        assert labels == ["X", "POOLED"]  # one asset + pooled

    def test_per_asset_grouping_sorted(self) -> None:
        samples = self._overconfident("EUR", 20) + self._overconfident("XAU", 20)
        rep = run_calibration_witness(samples)
        assert [r.label for r in rep.rows] == ["EUR", "XAU", "POOLED"]

    def test_overconfident_calibration_beats_raw_oos(self) -> None:
        rep = run_calibration_witness(self._overconfident("X", 24), min_conclusive_test=4)
        pooled = next(r for r in rep.rows if r.label == "POOLED")
        assert pooled.improved is True  # a calibrator pulls 0.9/0.1 → ~0.5 OOS
        assert pooled.selected != "identity"
        assert pooled.selected_brier < pooled.identity_brier
        assert pooled.conclusive is True  # n_test >= 4
        assert rep.any_conclusive_improvement is True

    def test_well_calibrated_declines(self) -> None:
        # genuinely calibrated: 0.5 forecasts that realise 50% up → no candidate
        # can beat raw (Brier 0.25) OOS → the search returns identity.
        good = [("X", 0.5, i % 2) for i in range(30)]
        rep = run_calibration_witness(good, min_conclusive_test=4)
        pooled = next(r for r in rep.rows if r.label == "POOLED")
        assert pooled.selected == "identity"
        assert pooled.improved is False

    def test_thin_test_split_flagged_inconclusive(self) -> None:
        # default min_conclusive_test = 30; 20 samples → n_test = 8 → thin
        rep = run_calibration_witness(self._overconfident("X", 20))
        pooled = next(r for r in rep.rows if r.label == "POOLED")
        assert pooled.n_test == 8
        assert pooled.conclusive is False
        assert rep.any_conclusive_improvement is False  # improvement but not conclusive

    def test_insufficient_when_train_or_test_empty(self) -> None:
        rep = run_calibration_witness([("X", 0.9, 1)])  # cut = int(0.6) = 0 → empty train
        row = next(r for r in rep.rows if r.label == "X")
        assert row.selected == "insufficient"
        assert row.improved is False and row.conclusive is False


class TestFormatMarkdown:
    def test_table_and_honest_no_edge_verdict(self) -> None:
        rep = run_calibration_witness(
            [("X", 0.5, i % 2) for i in range(30)],
            min_conclusive_test=4,
        )
        md = format_witness_markdown(rep)
        assert "Conviction-calibration OOS witness" in md
        assert "| series |" in md
        assert "no re-calibration beats the raw conviction" in md  # honest no-edge

    def test_conclusive_improvement_verdict(self) -> None:
        rep = run_calibration_witness(
            [(a, p, y) for a in ("X",) for p, y in [(0.9, 1), (0.1, 0), (0.9, 0), (0.1, 1)] * 6],
            min_conclusive_test=4,
        )
        md = format_witness_markdown(rep)
        assert rep.any_conclusive_improvement is True
        assert "beats the raw conviction OOS on a" in md
        # no trade-signal tokens leak into the report (ADR-017 doctrine)
        for token in (" BUY ", " SELL ", "long ", "short "):
            assert token not in md

    def test_report_is_typed(self) -> None:
        rep = run_calibration_witness(self._samples())
        assert isinstance(rep, CalibrationWitnessReport)
        assert all(isinstance(r, WitnessRow) for r in rep.rows)

    def _samples(self) -> list[tuple[str, float, int]]:
        return [("X", 0.6, 1), ("X", 0.4, 0), ("X", 0.7, 1), ("X", 0.3, 0), ("X", 0.55, 1)]


class TestCliReadOnly:
    """The witness CLI must NEVER mutate the DB (ADR-119 read-only contract).
    A static source guard pins this against a future edit that adds a write."""

    def test_cli_source_has_no_write_calls(self) -> None:
        import inspect

        from ichor_api.cli import run_calibration_witness as cli

        src = inspect.getsource(cli)
        for forbidden in (".add(", ".add_all(", ".commit(", ".flush(", ".delete(", ".merge("):
            assert forbidden not in src, f"CLI must be read-only; found {forbidden!r}"
