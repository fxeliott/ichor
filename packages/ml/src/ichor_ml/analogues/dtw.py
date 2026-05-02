"""Historical analogues via Dynamic Time Warping (dtaidistance).

Given the current price+vol pattern over the last N days, find the K closest
historical patterns from the indexed library, return their forward returns
distribution. Use for narrative + risk anchoring in briefings.

Per ARCHITECTURE_FINALE: 22 historical tail events indexed (Phase 1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from dtaidistance import dtw


@dataclass
class AnalogueMatch:
    library_event_id: str
    """e.g. '2008-09-15-LehmanBrothers' or '2020-03-12-COVID'."""
    distance: float
    """DTW distance, lower = closer match."""
    forward_returns: list[float]
    """Realized returns at +1d, +5d, +22d post-event."""


@dataclass
class HistoricalEvent:
    event_id: str
    pattern: np.ndarray  # shape (T,), normalized
    forward_returns_d1_d5_d22: tuple[float, float, float]


class DTWAnalogueMatcher:
    """Match the current pattern against a library of historical events."""

    def __init__(self, library: list[HistoricalEvent]) -> None:
        if not library:
            raise ValueError("Empty library — index ≥ 1 historical event")
        self._library = library

    def find_top_k(
        self,
        current_pattern: np.ndarray,
        k: int = 3,
        max_distance: float | None = None,
    ) -> list[AnalogueMatch]:
        """Return the K closest matches, sorted by distance ascending."""
        if current_pattern.ndim != 1:
            raise ValueError(f"Expected 1D pattern, got {current_pattern.shape}")

        # Z-score normalize the query so DTW compares shape, not absolute level
        query = (current_pattern - current_pattern.mean()) / (current_pattern.std() + 1e-9)

        scored: list[tuple[float, HistoricalEvent]] = []
        for ev in self._library:
            dist = dtw.distance(query, ev.pattern, use_pruning=True)
            if max_distance is not None and dist > max_distance:
                continue
            scored.append((dist, ev))

        scored.sort(key=lambda x: x[0])
        return [
            AnalogueMatch(
                library_event_id=ev.event_id,
                distance=float(dist),
                forward_returns=list(ev.forward_returns_d1_d5_d22),
            )
            for dist, ev in scored[:k]
        ]

    @staticmethod
    def normalize_pattern(raw_series: np.ndarray) -> np.ndarray:
        """Z-score normalize for indexing into the library."""
        return (raw_series - raw_series.mean()) / (raw_series.std() + 1e-9)
