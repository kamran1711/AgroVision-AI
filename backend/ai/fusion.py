from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _risk_level(score: float) -> str:
    if score < 0.33:
        return "Healthy"
    if score < 0.66:
        return "Moderate Risk"
    return "High Risk"


def _risk_color(level: str) -> str:
    return {"Healthy": "green", "Moderate Risk": "yellow", "High Risk": "red"}.get(level, "green")


def _is_valid(x: Any) -> bool:
    try:
        val = float(x)
        return not math.isnan(val)
    except Exception:
        return False


def fuse_risk_from_inputs(
    *,
    ndvi_stats: Optional[Dict[str, Any]] = None,
    sensor_stats: Optional[Dict[str, Any]] = None,
    soil_data: Optional[Dict[str, Any]] = None,
    weather_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Soil-First Fusion Model:
      - Agro Soil Moisture (Primary) → 50%
      - Satellite NDVI (Secondary)  → 25%
      - Weather/Sensor Humidity     → 25%
    """
    ndvi_stats = ndvi_stats or {}
    sensor_stats = sensor_stats or {}
    soil_data = soil_data or {}
    weather_stats = weather_stats or {}

    # 1. Soil factor (Primary - 50%)
    # Logic: Prefer live AgroMonitoring soil_moisture, fallback to CSV sensor mean.
    soil_m = float(soil_data.get("soil_moisture", float("nan")))
    if not _is_valid(soil_m):
        soil_m = float(sensor_stats.get("soil_moisture_mean", float("nan")))

    # 2. NDVI factor (25%)
    ndvi_m = float(ndvi_stats.get("mean", 0.35))

    # 3. Environmental factor (Humidity/Temp - 25%)
    hum_m = float(weather_stats.get("humidity_mean", 60.0))
    temp_m = float(weather_stats.get("temperature_mean", 25.0))
    
    if _is_valid(sensor_stats.get("humidity_mean")):
        hum_m = (hum_m + float(sensor_stats["humidity_mean"])) / 2
    if _is_valid(sensor_stats.get("temperature_mean")):
        temp_m = (temp_m + float(sensor_stats["temperature_mean"])) / 2

    # Calculate Risks (0 to 1, where 1 is dangerous stress)
    soil_risk = 0.0
    if _is_valid(soil_m):
        if soil_m < 0.30:
            soil_risk = max(0.0, min(1.0, (0.30 - soil_m) / 0.15))
        else:
            soil_risk = max(0.0, min(1.0, (soil_m - 0.30) / 0.20))
    
    ndvi_risk = max(0.0, min(1.0, (0.60 - ndvi_m) / 0.60))
    hum_risk  = max(0.0, min(1.0, (hum_m - 40.0) / 50.0))

    # Master Weighted Score
    score = (0.50 * soil_risk) + (0.25 * ndvi_risk) + (0.25 * hum_risk)
    level = _risk_level(score)

    alerts: List[Dict[str, str]] = []
    if _is_valid(soil_m):
        if soil_m < 0.15:
            alerts.append({"level": "red", "message": f"CRITICAL: Soil moisture {soil_m:.2f} m³/m³ (Drought Stress)."})
        elif soil_m > 0.45:
            alerts.append({"level": "yellow", "message": f"WARNING: Soil moisture {soil_m:.2f} (Waterlogging/Fungal risk)."})
        else:
            alerts.append({"level": "green", "message": "Optimal soil moisture levels detected."})

    if ndvi_m < 0.28:
        alerts.append({"level": "yellow", "message": f"NDVI Health Scan: Sparse vegetation detected ({ndvi_m:.2f})."})

    if hum_m > 75:
        alerts.append({"level": "red", "message": f"Humidity Alert: Conditions ({hum_m:.1f}%) favor fungal leaf rot."})

    return {
        "risk": {
            "score": round(float(score), 4),
            "level": level,
            "color": _risk_color(level),
        },
        "alerts": alerts,
        "report_summary": f"Soil-First Fusion analysis: {level} (score {score:.0%}). Priority driver: Soil Moisture ({soil_m if _is_valid(soil_m) else 'N/A'}).",
        "drivers": {
            "soil_moisture": soil_m if _is_valid(soil_m) else None,
            "ndvi_mean": ndvi_m,
            "humidity_mean": hum_m,
            "temperature_mean": temp_m
        },
        "weather_stats": {
            "humidity_mean": hum_m,
            "temperature_mean": temp_m,
            "humidity_last": float(weather_stats.get("humidity_last", hum_m))
        }
    }


def fuse_risk(*, field_result: Dict[str, Any], sensor_result: Dict[str, Any]) -> Dict[str, Any]:
    """Unified entry point for API fusion."""
    res = fuse_risk_from_inputs(
        ndvi_stats=field_result.get("ndvi_stats"),
        soil_data=field_result.get("soil_data"),
        weather_stats=field_result.get("weather_stats"),
        sensor_stats=sensor_result.get("sensor_stats")
    )
    # Carry over the forecast if it exists so the graph doesn't break
    if "forecast" in field_result:
        res["forecast"] = field_result["forecast"]
    return res
