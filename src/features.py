from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureConfig:
    """
    Kept for project continuity.

    The easy MVP does heuristic risk scoring without engineered features.
    """

    lookback_steps: int = 12

