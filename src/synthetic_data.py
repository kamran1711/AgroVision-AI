from __future__ import annotations

import math
import random
import sys
from typing import Dict, List

from pathlib import Path

# Allow running this file directly (so `config.py` in the parent folder is importable).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import SYNTHETIC_RANDOM_SEED, SYNTHETIC_TIME_STEPS


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def generate_synthetic_dataset(
    *,
    zone_rows: int,
    zone_cols: int,
    time_steps: int = SYNTHETIC_TIME_STEPS,
    random_seed: int = SYNTHETIC_RANDOM_SEED,
) -> List[Dict]:
    """
    Create a small, self-contained demo dataset (pure Python).

    Schema:
      zone_id, zone_row, zone_col, t,
      ndvi, soil_moisture, air_temperature, humidity, leaf_wetness
    """
    rng = random.Random(random_seed)

    rows: List[Dict] = []
    for zr in range(zone_rows):
        for zc in range(zone_cols):
            zone_id = zr * zone_cols + zc

            # Stress onset controls the late-time behavior.
            onset_t = rng.randint(int(time_steps * 0.35), max(int(time_steps * 0.7), int(time_steps * 0.35) + 1))
            stress_strength = rng.uniform(0.15, 0.65)

            # Baselines.
            base_ndvi = rng.uniform(0.55, 0.85)
            base_moist = rng.uniform(0.20, 0.55)
            base_temp = rng.uniform(18.0, 30.0)
            base_rh = rng.uniform(40.0, 85.0)
            base_leaf_wet = rng.uniform(0.05, 0.30)

            # Precompute denominators for smooth decline/surge curves.
            denom = max(1, (time_steps - 1) - onset_t)

            for t in range(time_steps):
                frac = 0.0
                if t >= onset_t:
                    frac = (t - onset_t) / denom

                # Gradual decline if stressed.
                decline = stress_strength * (0.35 * frac)

                # Conducive conditions around onset.
                moist_surge = stress_strength * (0.35 * frac)
                wet_surge = stress_strength * (0.55 * frac)

                # Temporal seasonality + noise.
                ndvi_noise = rng.gauss(0.0, 0.015)
                moist_noise = rng.gauss(0.0, 0.02)
                rh_noise = rng.gauss(0.0, 2.0)
                temp_noise = rng.gauss(0.0, 0.7)
                wet_noise = rng.gauss(0.0, 0.02)

                ndvi = base_ndvi - decline + 0.03 * math.sin(2.0 * math.pi * t / 30.0) + ndvi_noise
                soil_moisture = base_moist + moist_surge + 0.04 * math.sin(2.0 * math.pi * t / 25.0) + moist_noise
                air_temp = base_temp + 2.0 * math.sin(2.0 * math.pi * t / 40.0) + temp_noise
                humidity = base_rh + 3.0 * math.sin(2.0 * math.pi * t / 35.0) + rh_noise

                leaf_wetness = base_leaf_wet + wet_surge + 0.1 * math.sin(2.0 * math.pi * t / 22.0) + wet_noise
                leaf_wetness = _clamp(leaf_wetness, 0.0, 1.0)

                rows.append(
                    {
                        "zone_id": int(zone_id),
                        "zone_row": int(zr),
                        "zone_col": int(zc),
                        "t": int(t),
                        "ndvi": float(ndvi),
                        "soil_moisture": float(soil_moisture),
                        "air_temperature": float(air_temp),
                        "humidity": float(humidity),
                        "leaf_wetness": float(leaf_wetness),
                    }
                )

    return rows

