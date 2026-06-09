from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskScoringConfig:
    lookback_steps: int = 12
    # Thresholds below are tuned for the synthetic demo generator.
    moist_threshold: float = 0.30
    wet_threshold: float = 0.20
    rh_threshold: float = 60.0

    # Weighting for the heuristic risk score in [0, 1].
    w_ndvi_drop: float = 0.45
    w_moist: float = 0.20
    w_wet: float = 0.15
    w_rh: float = 0.20


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def clamp01(x: float) -> float:
    return clamp(x, 0.0, 1.0)


def risk_from_lookback(
    *,
    ndvi_last: float,
    ndvi_change_lb: float,
    soil_moisture_mean_lb: float,
    leaf_wetness_mean_lb: float,
    humidity_mean_lb: float,
    cfg: RiskScoringConfig,
) -> float:
    """
    Simple, explainable "risk probability" heuristic.

    Production-quality systems should replace this with a learned model
    (CNN/LSTM over spectral + sensor features) once real ground truth exists.
    """
    # Convert changes/levels into normalized scores in [0, 1].
    score_ndvi = clamp01((-ndvi_change_lb) / 0.20)  # drop => higher score
    score_moist = clamp01((soil_moisture_mean_lb - cfg.moist_threshold) / 0.30)
    score_wet = clamp01((leaf_wetness_mean_lb - cfg.wet_threshold) / 0.50)
    score_rh = clamp01((humidity_mean_lb - cfg.rh_threshold) / 30.0)

    risk = (
        cfg.w_ndvi_drop * score_ndvi
        + cfg.w_moist * score_moist
        + cfg.w_wet * score_wet
        + cfg.w_rh * score_rh
    )

    # Conducive conditions gate (again tuned to the synthetic generator).
    conducive = (
        soil_moisture_mean_lb > 0.42
        and leaf_wetness_mean_lb > 0.35
        and humidity_mean_lb > 65.0
    )
    risk *= 1.15 if conducive else 0.75
    return clamp01(risk)


def predict_latest_risks(
    *,
    zones: dict,
    cfg: RiskScoringConfig,
) -> list[dict]:
    """
    zones maps:
      zone_id -> {
        zone_row, zone_col,
        series: [(t, ndvi, soil_moisture, air_temperature, humidity, leaf_wetness), ...]
      }
    """
    out = []
    for zone_id, z in zones.items():
        series = sorted(z["series"], key=lambda x: x[0])
        if not series:
            continue

        lb = min(cfg.lookback_steps, len(series))
        window = series[-lb:]
        ndvi_last = float(window[-1][1])
        ndvi_vals = [float(r[1]) for r in window]
        ndvi_mean_lb = sum(ndvi_vals) / len(ndvi_vals)
        ndvi_change_lb = ndvi_last - ndvi_mean_lb

        moist_vals = [float(r[2]) for r in window]
        wet_vals = [float(r[5]) for r in window]
        rh_vals = [float(r[4]) for r in window]
        moist_mean_lb = sum(moist_vals) / len(moist_vals)
        wet_mean_lb = sum(wet_vals) / len(wet_vals)
        rh_mean_lb = sum(rh_vals) / len(rh_vals)

        risk = risk_from_lookback(
            ndvi_last=ndvi_last,
            ndvi_change_lb=ndvi_change_lb,
            soil_moisture_mean_lb=moist_mean_lb,
            leaf_wetness_mean_lb=wet_mean_lb,
            humidity_mean_lb=rh_mean_lb,
            cfg=cfg,
        )

        out.append(
            {
                "zone_id": int(zone_id),
                "t": int(window[-1][0]),
                "zone_row": int(z["zone_row"]),
                "zone_col": int(z["zone_col"]),
                "risk_probability": float(risk),
                "ndvi_last": ndvi_last,
                "ndvi_change_lb": float(ndvi_change_lb),
                "moist_mean_lb": float(moist_mean_lb),
                "wet_mean_lb": float(wet_mean_lb),
                "rh_mean_lb": float(rh_mean_lb),
            }
        )

    out.sort(key=lambda r: (r["zone_row"], r["zone_col"]))
    return out

