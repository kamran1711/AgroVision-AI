from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


AGRO_BASE = "http://api.agromonitoring.com/agro/1.0"


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

def _api_key() -> str:
    key = os.environ.get("AGROMONITORING_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AGROMONITORING_API_KEY not set in environment.")
    return key


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _request(method: str, endpoint: str, body: Optional[Dict] = None, params: Optional[Dict] = None) -> Any:
    """Authenticated HTTP request to AgroMonitoring API."""
    key = _api_key()
    all_params: Dict[str, Any] = {"appid": key}
    if params:
        all_params.update(params)

    # Add metric units for weather endpoints
    if "weather" in endpoint:
        all_params.setdefault("units", "metric")

    query = urllib.parse.urlencode(all_params)
    url = f"{AGRO_BASE}/{endpoint}?{query}"

    data = json.dumps(body).encode("utf-8") if body else None
    headers: Dict[str, str] = {"User-Agent": "PlantSenseAI/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# ──────────────────────────────────────────────
# Polygon management
# ──────────────────────────────────────────────

def create_polygon(*, name: str, coordinates: List[List[float]]) -> str:
    """
    Create a field polygon in AgroMonitoring.

    coordinates: list of [lon, lat] pairs (GeoJSON order).
    The ring is automatically closed if not already.
    Returns the polygon ID string.
    """
    ring = list(coordinates)
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]

    payload = {
        "name": name,
        "geo_json": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring],
            },
        },
    }
    result = _request("POST", "polygons", body=payload)
    return str(result["id"])


# ──────────────────────────────────────────────
# NDVI (satellite vegetation index)
# ──────────────────────────────────────────────

def get_ndvi_stats(polygon_id: str) -> Dict[str, Any]:
    """
    Fetch the most-recent NDVI statistics for a polygon.

    Returns dict with keys: mean, min, max, std, valid_pixels_percent.
    Returns empty dict if no imagery is available yet (new polygons take time).
    """
    try:
        history = _request("GET", "ndvi/history", params={"polyid": polygon_id})
        if not history:
            return {}

        latest = max(history, key=lambda x: x.get("dt", 0))
        dc = latest.get("dc") or {}
        if not dc:
            return {}

        return {
            "mean": round(float(dc.get("mean", 0.0)), 4),
            "min": round(float(dc.get("p25", dc.get("min", 0.0))), 4),
            "max": round(float(dc.get("p75", dc.get("max", 0.0))), 4),
            "std": round(float(dc.get("std", 0.0)), 4),
            "valid_pixels_percent": round(float(dc.get("valid_pixels_percent", 0.0)), 1),
            "timestamp": int(latest.get("dt", 0)),
            "source": "satellite",
        }
    except Exception:
        return {}


# ──────────────────────────────────────────────
# Soil data
# ──────────────────────────────────────────────

def get_soil_data(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetch current soil moisture and temperature.

    AgroMonitoring returns:
      t0    — surface soil temperature (Kelvin)
      t10   — soil temperature at 10 cm depth (Kelvin)
      moisture — volumetric soil moisture (m³/m³)
    """
    try:
        data = _request("GET", "soil", params={"lat": lat, "lon": lon})
        t0_k = float(data.get("t0", 273.15))
        t10_k = float(data.get("t10", 273.15))
        moisture = float(data.get("moisture", float("nan")))

        return {
            "soil_moisture": round(moisture, 3),           # 0..1 (m³/m³)
            "soil_temp_surface_c": round(t0_k - 273.15, 1),
            "soil_temp_10cm_c": round(t10_k - 273.15, 1),
            "timestamp": int(data.get("dt", 0)),
            "source": "agromonitoring",
        }
    except Exception:
        return {}


# ──────────────────────────────────────────────
# Weather forecast
# ──────────────────────────────────────────────

def get_weather_forecast(lat: float, lon: float, horizon: int = 12) -> Dict[str, Any]:
    """
    Fetch weather forecast from AgroMonitoring.
    Note: The API returns a top-level list of forecast objects.
    """
    try:
        data = _request("GET", "weather/forecast", params={"lat": lat, "lon": lon})
        # The API returns a direct list or a dict with a 'list' key.
        items = data if isinstance(data, list) else data.get("list", [])
        if not items:
            raise RuntimeError("Empty forecast data.")

        future_h: List[float] = []
        future_t: List[float] = []

        for it in items[:horizon]:
            main = it.get("main") or {}
            if "humidity" in main and "temp" in main:
                hum = float(main["humidity"])
                temp = float(main["temp"])

                # Safety: If temp > 100, it's likely Kelvin (needs conversion to Celsius)
                if temp > 100:
                    temp -= 273.15

                future_h.append(_clamp(hum, 0.0, 100.0))
                future_t.append(round(temp, 1))

        if not future_h:
            raise RuntimeError("No usable forecast coordinates found.")

        return {
            "future_humidity": future_h,
            "future_temperature": future_t,
            "humidity_mean": round(sum(future_h) / len(future_h), 1),
            "temperature_mean": round(sum(future_t) / len(future_t), 1),
            "humidity_last": round(future_h[-1], 1),
            "source": "agromonitoring",
        }
    except Exception as exc:
        # Fallback to previous weather logic if anything fails
        return {}


# ──────────────────────────────────────────────
# Risk computation
# ──────────────────────────────────────────────

def _risk_level(score: float) -> str:
    if score < 0.33:
        return "Healthy"
    if score < 0.66:
        return "Moderate Risk"
    return "High Risk"


def _risk_color(level: str) -> str:
    return {"Healthy": "green", "Moderate Risk": "yellow", "High Risk": "red"}.get(level, "green")


def compute_agro_risk(
    *,
    ndvi_stats: Dict[str, Any],
    soil_data: Dict[str, Any],
    weather: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute disease/stress risk from AgroMonitoring data.

    Weights:
      NDVI (lower = more stress)  → 0.40
      Soil moisture (high = risk) → 0.25
      Humidity (high = risk)      → 0.25
      Temperature (high = risk)   → 0.10
    """
    alerts: List[Dict[str, str]] = []
    drivers: List[str] = []
    has_ndvi = bool(ndvi_stats)
    has_soil = bool(soil_data)
    has_weather = bool(weather)

    # ── NDVI factor ──────────────────────────────────────────────────────────
    ndvi_mean = float(ndvi_stats.get("mean", 0.35)) if has_ndvi else 0.35
    # Low NDVI → high score. Healthy crops ~0.6, stressed ~0.2, bare soil ~0.0
    ndvi_factor = _clamp((0.55 - ndvi_mean) / 0.55, 0.0, 1.0)

    if has_ndvi:
        if ndvi_mean < 0.20:
            alerts.append({"level": "red", "message": f"🛰️ Critically low NDVI ({ndvi_mean:.2f}): severe vegetation stress detected."})
        elif ndvi_mean < 0.35:
            alerts.append({"level": "yellow", "message": f"🛰️ Low NDVI ({ndvi_mean:.2f}): crop health declining — scout for disease or pest damage."})
        else:
            alerts.append({"level": "green", "message": f"🛰️ NDVI {ndvi_mean:.2f}: vegetation health appears adequate."})
        drivers.append(f"Satellite NDVI mean is {ndvi_mean:.3f} (range 0=bare soil → 1=dense vegetation).")

    # ── Soil moisture factor ─────────────────────────────────────────────────
    soil_moisture = float(soil_data.get("soil_moisture", float("nan"))) if has_soil else float("nan")
    soil_factor = 0.0
    if soil_moisture == soil_moisture:  # not NaN
        # Very high moisture (>0.45) → waterlogging/fungal risk; very low (<0.15) → drought stress
        soil_factor = _clamp((soil_moisture - 0.20) / 0.35, 0.0, 1.0)
        if soil_moisture > 0.45:
            alerts.append({"level": "yellow", "message": f"🌱 High soil moisture ({soil_moisture:.2f} m³/m³): waterlogging risk, favours fungal disease."})
            drivers.append(f"Soil moisture is elevated at {soil_moisture:.2f} m³/m³.")
        elif soil_moisture < 0.15:
            alerts.append({"level": "yellow", "message": f"🌱 Low soil moisture ({soil_moisture:.2f} m³/m³): drought stress may suppress plant immunity."})
            drivers.append(f"Soil moisture is low at {soil_moisture:.2f} m³/m³.")
        else:
            drivers.append(f"Soil moisture is {soil_moisture:.2f} m³/m³ (within normal range).")

    # ── Weather factors ──────────────────────────────────────────────────────
    humidity_mean = float(weather.get("humidity_mean", 60.0)) if has_weather else 60.0
    temperature_mean = float(weather.get("temperature_mean", 25.0)) if has_weather else 25.0
    humidity_last = float(weather.get("humidity_last", humidity_mean)) if has_weather else humidity_mean

    humidity_factor = _clamp((humidity_mean - 45.0) / 45.0, 0.0, 1.0)
    temp_factor = _clamp((temperature_mean - 20.0) / 20.0, 0.0, 1.0)

    if has_weather:
        if humidity_mean >= 75.0:
            alerts.append({"level": "red", "message": f"🌧️ High forecast humidity ({humidity_mean:.0f}%): conditions strongly favour fungal spread."})
        elif humidity_mean >= 60.0:
            alerts.append({"level": "yellow", "message": f"🌧️ Elevated humidity ({humidity_mean:.0f}%): increase scouting frequency."})
        else:
            alerts.append({"level": "green", "message": f"🌧️ Humidity ({humidity_mean:.0f}%) within safer ranges."})
        if temperature_mean >= 30.0:
            alerts.append({"level": "yellow", "message": f"🌡️ High temperature ({temperature_mean:.1f}°C): heat stress increases crop vulnerability."})
        drivers.append(f"Forecast humidity mean: {humidity_mean:.0f}%, temperature mean: {temperature_mean:.1f}°C.")

    if humidity_last >= 85.0:
        alerts.append({"level": "red", "message": "🌧️ Forecast ends with very high humidity — plan preventive fungicide application."})

    # ── Composite risk score ─────────────────────────────────────────────────
    w_ndvi = 0.40
    w_soil = 0.25
    w_hum = 0.25
    w_temp = 0.10

    # Adjust weights when data is missing
    if not has_ndvi:
        w_ndvi = 0.0
        w_hum += 0.20
        w_soil += 0.15
        w_temp += 0.05
    if not has_soil or soil_moisture != soil_moisture:
        w_soil = 0.0
        w_hum += 0.15
        w_ndvi += 0.10

    total_w = w_ndvi + w_soil + w_hum + w_temp
    if total_w == 0:
        score = 0.5
    else:
        score = (w_ndvi * ndvi_factor + w_soil * soil_factor + w_hum * humidity_factor + w_temp * temp_factor) / total_w

    score = _clamp(score, 0.0, 1.0)
    level = _risk_level(score)

    # ── Report summary ───────────────────────────────────────────────────────
    parts = [f"AgroMonitoring risk: {level} (score {score:.0%})."]
    if has_ndvi:
        parts.append(f"NDVI: {ndvi_mean:.3f}.")
    if has_soil and soil_moisture == soil_moisture:
        parts.append(f"Soil moisture: {soil_moisture:.2f} m³/m³.")
    if has_weather:
        parts.append(f"Humidity: {humidity_mean:.0f}%. Temp: {temperature_mean:.1f}°C.")
    report_summary = " ".join(parts)

    # ── Stress risk curve (for forecast chart) ────────────────────────────────
    future_h = weather.get("future_humidity", []) if has_weather else []
    future_t = weather.get("future_temperature", []) if has_weather else []
    stress_curve: List[float] = []
    for i in range(len(future_h)):
        h = float(future_h[i])
        t = float(future_t[i]) if i < len(future_t) else temperature_mean
        h_term = _clamp((h - 40.0) / 45.0, 0.0, 1.0)
        t_term = _clamp((t - 20.0) / 20.0, 0.0, 1.0)
        # Blend weather with NDVI factor if available
        base = 0.70 * h_term + 0.30 * t_term
        if has_ndvi:
            base = 0.55 * h_term + 0.20 * t_term + 0.25 * ndvi_factor
        stress_curve.append(round(_clamp(base, 0.0, 1.0), 3))

    return {
        "risk": {"score": round(score, 4), "level": level, "color": _risk_color(level)},
        "alerts": alerts,
        "report_summary": report_summary,
        "weather_stats": {
            "humidity_mean": humidity_mean,
            "temperature_mean": temperature_mean,
            "humidity_last": humidity_last,
        },
        "weather_drivers": drivers,
        "forecast": {
            "future_humidity": weather.get("future_humidity", []),
            "future_temperature": weather.get("future_temperature", []),
            "stress_risk_future": stress_curve,
        },
    }


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────

def get_latest_imagery(polygon_id: str) -> Optional[str]:
    """Search for the latest satellite imagery for the polygon and return the NDVI image URL."""
    now = int(time.time())
    start = now - (30 * 24 * 3600)  # Last 30 days

    params = {
        "polyid": polygon_id,
        "start": start,
        "end": now,
    }
    try:
        results = _request("GET", "image/search", params=params)
        if not results or not isinstance(results, list):
            return None

        # Sort by d (date) descending to get latest
        results.sort(key=lambda x: x.get("dt", 0), reverse=True)
        latest = results[0]

        # Extract NDVI URL from the 'image' dict
        image_urls = latest.get("image", {})
        return image_urls.get("ndvi")
    except Exception:
        return None


def analyze_field(
    *,
    lat: float,
    lon: float,
    polygon_coords: Optional[List[List[float]]] = None,
    horizon: int = 12,
) -> Dict[str, Any]:
    """
    Full AgroMonitoring field analysis.

    polygon_coords: list of [lon, lat] pairs (GeoJSON order).
                    If provided, creates a polygon and retrieves satellite NDVI.
                    If None, only weather + soil are used.

    Returns a response dict compatible with the frontend rendering functions,
    plus extra keys: ndvi_stats, soil_data, polygon_id, source.
    """
    ndvi_stats: Dict[str, Any] = {}
    soil_data: Dict[str, Any] = {}
    weather: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    # ── 1. Create polygon ─────────────────────────────────────────────────────
    polygon_id = None
    ndvi_stats = {}
    imagery_url = None

    if polygon_coords:
        try:
            # 1. Register/Get Polygon
            polygon_id = create_polygon(
                name=f"plantsense_{int(time.time())}", coordinates=polygon_coords
            )
            # 2. Get numerical stats
            ndvi_stats = get_ndvi_stats(polygon_id)
            # 3. Get visual imagery URL
            imagery_url = get_latest_imagery(polygon_id)
        except Exception as exc:
            errors["polygon"] = str(exc)

    # ── 2. Soil data (lat/lon, no polygon needed) ─────────────────────────────
    try:
        soil_data = get_soil_data(lat=lat, lon=lon)
    except Exception as exc:
        errors["soil"] = str(exc)

    # ── 3. Weather forecast ───────────────────────────────────────────────────
    try:
        weather = get_weather_forecast(lat=lat, lon=lon, horizon=horizon)
    except Exception as exc:
        errors["weather"] = str(exc)

    # ── 4. Risk computation ───────────────────────────────────────────────────
    risk_result = compute_agro_risk(
        ndvi_stats=ndvi_stats,
        soil_data=soil_data,
        weather=weather,
    )

    return {
        **risk_result,
        "ndvi_stats": ndvi_stats,
        "soil_data": soil_data,
        "polygon_id": polygon_id,
        "source": "agromonitoring",
        "errors": errors,
        "imagery_url": imagery_url,
    }
