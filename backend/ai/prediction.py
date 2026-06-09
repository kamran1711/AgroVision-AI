from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _is_valid(x: Any) -> bool:
    try:
        val = float(x)
        return not math.isnan(val)
    except Exception:
        return False


def predict_stress_trend(
    *,
    weather_forecast: Optional[Dict[str, Any]] = None,
    soil_current: float = 0.30,
    horizon: int = 12
) -> Dict[str, Any]:
    """
    Advanced Stress Forecasting:
    Uses the future humidity/temp forecast from the weather API to calculate
    a 24-hour predictive stress curve.
    """
    weather_forecast = weather_forecast or {}
    future_h = weather_forecast.get("future_humidity", [])
    future_t = weather_forecast.get("future_temperature", [])
    
    # If no real forecast, fallback to a neutral baseline
    if not future_h:
        future_h = [60.0] * horizon
    if not future_t:
        future_t = [25.0] * horizon

    stress_curve: List[float] = []
    
    # Heuristic: Stress increases with high humidity (>75%) and high temp (>30°C)
    # Soil multiplier: if soil is too dry (<0.15) or too wet (>0.45), risk is doubled
    soil_mult = 1.0
    if _is_valid(soil_current):
        if soil_current < 0.15 or soil_current > 0.45:
            soil_mult = 1.5

    for i in range(min(horizon, len(future_h))):
        h = float(future_h[i])
        t = float(future_t[i]) if i < len(future_t) else 25.0
        
        # Environmental risk factor (0..1)
        # Humidity risk starts at 50%
        h_risk = max(0.0, min(1.0, (h - 50.0) / 40.0))
        # Temp risk starts at 22°C
        t_risk = max(0.0, min(1.0, (t - 22.0) / 15.0))
        
        # Weighted forecast risk
        point_risk = (0.7 * h_risk + 0.3 * t_risk) * soil_mult
        stress_curve.append(round(min(1.0, point_risk), 3))

    return {
        "forecast": {
            "future_humidity": future_h[:horizon],
            "future_temperature": future_t[:horizon],
            "stress_risk_future": stress_curve,
        }
    }
