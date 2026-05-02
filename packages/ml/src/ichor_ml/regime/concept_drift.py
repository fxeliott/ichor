"""Concept drift detection — ADWIN + Page-Hinkley via river.

When a model's prediction error distribution shifts beyond a configured
threshold, river flags drift. We use BOTH detectors to reduce false-positives
(ADWIN catches gradual drift, Page-Hinkley catches abrupt jumps).
"""

from __future__ import annotations

from dataclasses import dataclass

from river.drift import ADWIN, PageHinkley


@dataclass
class DriftEvent:
    detector_name: str
    series_index: int
    """Position in the input stream where drift was first flagged."""
    severity: float
    """Detector-specific magnitude. Higher = stronger drift signal."""


class DriftMonitor:
    """Wraps both ADWIN and Page-Hinkley. Returns events when EITHER fires.

    Usage:
        mon = DriftMonitor()
        for i, error in enumerate(model_errors_stream):
            events = mon.update(error)
            for e in events:
                log.warning("drift", **e.__dict__)
    """

    def __init__(
        self,
        *,
        adwin_delta: float = 0.002,
        ph_threshold: float = 50.0,
        ph_min_instances: int = 30,
    ) -> None:
        self._adwin = ADWIN(delta=adwin_delta)
        self._ph = PageHinkley(threshold=ph_threshold, min_instances=ph_min_instances)
        self._index = 0

    def update(self, value: float) -> list[DriftEvent]:
        events: list[DriftEvent] = []
        idx = self._index
        self._index += 1

        self._adwin.update(value)
        if self._adwin.drift_detected:
            events.append(
                DriftEvent(
                    detector_name="ADWIN",
                    series_index=idx,
                    severity=float(self._adwin.estimation),
                )
            )

        self._ph.update(value)
        if self._ph.drift_detected:
            events.append(
                DriftEvent(
                    detector_name="PageHinkley",
                    series_index=idx,
                    severity=float(value),
                )
            )

        return events
