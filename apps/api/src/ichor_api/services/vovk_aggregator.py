"""Phase D W115 — Vovk-Zhdanov Aggregating Algorithm for the Brier game.

Reference : Vovk & Zhdanov 2009, "Prediction with expert advice for the
Brier game", JMLR 10:2445-2471, Proposition 2 + Theorem 1.

Mathematical contract :

* N experts each emit a probability `p_i ∈ [0, 1]` for the binary
  outcome `y ∈ {0, 1}` (in our case, `target_up`).
* Brier loss per expert : `L_i = (p_i - y)²`.
* AA weight update (exponential, η-mixable) :
      w_{t+1}(i) ∝ w_t(i) · exp(−η · L_i)
  renormalized so Σ w = 1.
* **η = 1** : optimal for the Brier game (Vovk-Zhdanov 2009, Theorem 1).
  C_η = 1 at η = 1 is the supremum keeping the mixability constant
  bounded.
* Substitution function (Proposition 2) : for n=2 (binary outcome,
  Ichor's case), the η=1 substitution reduces to the **weighted mean**
  γ = Σ w_i · p_i. This is what we ship.
* Regret bound (Theorem 1) : Regret_T(AA) ≤ ln(N) / η = ln(N), constant
  in T. That's the AA's killer feature vs ERM / no-regret learners.

The class is intentionally a small (~50 LOC) pure-Python primitive —
no DB, no async, no I/O. The CLI in `cli/run_brier_aggregator.py`
loads/persists pocket weights from `brier_aggregator_weights` and
writes one `auto_improvement_log` audit row per update.

Caveat for W116 multidimensional extension : the simple weighted-mean
substitution is EXACT for the n=2 Brier game at η=1. For n>2 (the
7-bucket Pass-6 scenarios in W116/ADR-085), strict optimality requires
the simplex-projection variant from Vovk-Zhdanov Prop 2. The weighted
mean is already a valid mixable predictor (proper proper-loss
aggregation) and matches industry practice ; we'll pin the n>2 choice
in a future ADR if/when W116 needs sharper bounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class VovkBrierAggregator:
    """Vovk-Zhdanov Aggregating Algorithm for the binary Brier game.

    Construct with the number of experts ; call `predict` to get the
    AA-aggregated probability, then `update` to revise weights once
    the realized outcome `y ∈ {0, 1}` is known.

    Weights are kept in a Python list aligned with the caller's expert
    ordering — the caller is responsible for that mapping (typically
    `expert_kinds: tuple[str, ...]` stored alongside).
    """

    n_experts: int
    eta: float = 1.0
    """Brier-game mixability optimum (Vovk-Zhdanov 2009, Theorem 1)."""
    weights: list[float] = field(default_factory=list)
    cumulative_losses: list[float] = field(default_factory=list)
    n_observations: int = 0

    def __post_init__(self) -> None:
        if self.n_experts < 1:
            raise ValueError(f"n_experts must be >= 1, got {self.n_experts}")
        if self.eta <= 0.0:
            raise ValueError(f"eta must be > 0, got {self.eta}")
        if not self.weights:
            self.weights = [1.0 / self.n_experts] * self.n_experts
        elif len(self.weights) != self.n_experts:
            raise ValueError(f"weights length {len(self.weights)} != n_experts {self.n_experts}")
        else:
            self._renormalize_weights()
        if not self.cumulative_losses:
            self.cumulative_losses = [0.0] * self.n_experts
        elif len(self.cumulative_losses) != self.n_experts:
            raise ValueError(
                f"cumulative_losses length {len(self.cumulative_losses)} "
                f"!= n_experts {self.n_experts}"
            )

    def _renormalize_weights(self) -> None:
        s = sum(self.weights)
        if s <= 0.0:
            # Pathological : every expert was assigned weight zero.
            # Reset to uniform — the AA invariant is "weights sum to 1".
            self.weights = [1.0 / self.n_experts] * self.n_experts
            return
        self.weights = [w / s for w in self.weights]

    def predict(self, expert_predictions: list[float]) -> float:
        """Return the AA-aggregated `P(target_up=1)`.

        For the binary Brier game at η=1, the substitution function
        (Vovk-Zhdanov Prop 2) reduces to the weighted mean of expert
        predictions — that's what this returns.
        """
        if len(expert_predictions) != self.n_experts:
            raise ValueError(
                f"expert_predictions length {len(expert_predictions)} != n_experts {self.n_experts}"
            )
        for i, p in enumerate(expert_predictions):
            if not 0.0 <= p <= 1.0:
                raise ValueError(f"expert_predictions[{i}]={p!r} not in [0, 1]")
        return sum(w * p for w, p in zip(self.weights, expert_predictions, strict=True))

    def update(self, expert_predictions: list[float], realized: int) -> None:
        """Apply the AA exponential weight update for one realized
        outcome.

        `realized` must be exactly 0 or 1 (binary outcome — Ichor's
        `target_up` over the session window).
        """
        if realized not in (0, 1):
            raise ValueError(f"realized must be 0 or 1, got {realized!r}")
        if len(expert_predictions) != self.n_experts:
            raise ValueError(
                f"expert_predictions length {len(expert_predictions)} != n_experts {self.n_experts}"
            )
        new_weights: list[float] = []
        for i, (w, p) in enumerate(zip(self.weights, expert_predictions, strict=True)):
            loss = (p - realized) ** 2
            self.cumulative_losses[i] += loss
            new_weights.append(w * math.exp(-self.eta * loss))
        self.weights = new_weights
        self._renormalize_weights()
        self.n_observations += 1

    def regret_bound(self) -> float:
        """Theorem 1 : Regret_T(AA) ≤ ln(N) / η. Constant in T.

        At η = 1 this equals `ln(n_experts)` (≈ 1.39 for N=4 experts,
        the typical Ichor pocket size). The AA's master prediction
        cumulative Brier loss is bounded by `(best expert's loss) +
        ln(N)` — no T dependence.
        """
        return math.log(self.n_experts) / self.eta
