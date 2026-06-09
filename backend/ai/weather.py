from __future__ import annotations

import hashlib
import json
import math
import os
import random
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _risk_level(score: float) -> str:
    if score < 0.33:
        return "Healthy"
    if score < 0.66:
        return "Moderate Risk"
    return "High Risk"


def _risk_color(level: str) -> str:
    if level == "Healthy":
        return "green"
    if level == "Moderate Risk":
        return "yellow"
    return "red"


def _risk_from_humidity_temp(*, humidity_mean: float, temperature_mean: float) -> Tuple[float, str, str]:
    # Map humidity in [45..90] to [0..1]
    humidity_factor = _clamp((humidity_mean - 45.0) / 45.0, 0.0, 1.0)
    # Map temperature in [20..35] to [0..1]
    temperature_factor = _clamp((temperature_mean - 20.0) / 20.0, 0.0, 1.0)

    score = 0.65 * humidity_factor + 0.35 * temperature_factor
    level = _risk_level(score)
    color = _risk_color(level)
    return float(score), level, color


def _dummy_weather_series(lat: float, lon: float, horizon: int) -> Dict[str, Any]:
    seed_material = f"{lat:.6f},{lon:.6f}"
    seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)

    base_h = rng.uniform(45.0, 90.0)
    base_t = rng.uniform(15.0, 35.0)

    # deterministic "drift" so the forecast looks like a trajectory
    hum_trend = rng.uniform(-0.9, 0.9)
    temp_trend = rng.uniform(-0.35, 0.35)

    future_h: List[float] = []
    future_t: List[float] = []
    for i in range(horizon):
        hum = base_h + hum_trend * i + rng.uniform(-3.0, 3.0)
        temp = base_t + temp_trend * i + rng.uniform(-1.2, 1.2)
        future_h.append(_clamp(hum, 0.0, 100.0))
        future_t.append(_clamp(temp, -10.0, 60.0))

    humidity_mean = float(sum(future_h) / max(1, len(future_h)))
    temperature_mean = float(sum(future_t) / max(1, len(future_t)))
    humidity_last = float(future_h[-1]) if future_h else float("nan")
    return {
        "future_humidity": future_h,
        "future_temperature": future_t,
        "humidity_mean": humidity_mean,
        "temperature_mean": temperature_mean,
        "humidity_last": humidity_last,
    }


def _fetch_openweather_forecast(*, lat: float, lon: float) -> Dict[str, Any]:
    api_key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENWEATHER_API_KEY not set.")

    # OpenWeather "5 day / 3 hour forecast"
    url = (
        "https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "PlantSenseAI/1.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read()

    return json.loads(raw.decode("utf-8", errors="replace"))


def _extract_forecast_points(openweather_payload: Dict[str, Any], horizon: int) -> Dict[str, Any]:
    items = openweather_payload.get("list") or []
    if not items:
        raise RuntimeError("OpenWeather response missing `list`.")

    future_h: List[float] = []
    future_t: List[float] = []
    for it in items[:horizon]:
        main = it.get("main") or {}
        if "humidity" in main and "temp" in main:
            future_h.append(float(main["humidity"]))
            future_t.append(float(main["temp"]))

    if not future_h:
        raise RuntimeError("No humidity/temp points extracted from OpenWeather payload.")

    humidity_mean = float(sum(future_h) / max(1, len(future_h)))
    temperature_mean = float(sum(future_t) / max(1, len(future_t)))
    humidity_last = float(future_h[-1])

    return {
        "future_humidity": [_clamp(x, 0.0, 100.0) for x in future_h],
        "future_temperature": [_clamp(x, -50.0, 70.0) for x in future_t],
        "humidity_mean": humidity_mean,
        "temperature_mean": temperature_mean,
        "humidity_last": humidity_last,
    }


def analyze_weather_area(*, lat: float, lon: float, horizon: int = 12) -> Dict[str, Any]:
    """
    Weather-driven risk + alerts.

    If `OPENWEATHER_API_KEY` is not set (or API call fails), we produce deterministic
    dummy series based on the selected coordinates so the prototype still works.
    """
    horizon = int(horizon)
    if horizon <= 0:
        horizon = 1

    try:
        payload = _fetch_openweather_forecast(lat=lat, lon=lon)
        series = _extract_forecast_points(payload, horizon=horizon)
    except Exception:
        series = _dummy_weather_series(lat=lat, lon=lon, horizon=horizon)

    humidity_mean = float(series["humidity_mean"])
    temperature_mean = float(series["temperature_mean"])
    humidity_last = float(series["humidity_last"])

    score, level, color = _risk_from_humidity_temp(
        humidity_mean=humidity_mean, temperature_mean=temperature_mean
    )

    # Alerts driven by heuristics, mapped to UI badge colors.
    alerts: List[Dict[str, str]] = []
    if humidity_mean >= 75.0:
        alerts.append({"level": "red", "message": "High humidity: conditions favor fungal disease spread."})
    elif humidity_mean >= 65.0:
        alerts.append({"level": "yellow", "message": "Elevated humidity: increase scouting for early symptoms."})
    else:
        alerts.append({"level": "green", "message": "Humidity appears within safer ranges for plant health."})

    if temperature_mean >= 32.0:
        alerts.append({"level": _risk_color(level), "message": "Hotter conditions increase crop stress risk; ensure adequate irrigation."})

    if humidity_last >= 85.0:
        alerts.append({"level": "red" if level != "Healthy" else "yellow", "message": "Forecast ends with very humid conditions; plan preventive actions."})

    drivers: List[str] = [
        f"Humidity mean is {humidity_mean:.1f}% over the next window.",
        f"Temperature mean is {temperature_mean:.1f}°C over the next window."
    ]
    if humidity_mean >= 65.0:
        drivers.append("High humidity is the primary risk driver.");
    if temperature_mean >= 32.0:
        drivers.append("High temperature adds stress on top of humidity.");

    report_summary = f"Weather risk: {level}. Humidity mean {humidity_mean:.1f}%, temperature mean {temperature_mean:.1f}°C."

    # Build a stress risk curve (0..1) from future humidity + temperature.
    future_h = series["future_humidity"]
    future_t = series["future_temperature"]
    stress: List[float] = []
    for i in range(len(future_h)):
        h = float(future_h[i])
        t = float(future_t[i]) if i < len(future_t) else float("nan")
        humidity_term = _clamp((h - 40.0) / 45.0, 0.0, 1.0)
        temp_term = 0.5 * _clamp((t - 20.0) / 20.0, 0.0, 1.0) if t == t else 0.0
        stress.append(float(_clamp(0.75 * humidity_term + 0.25 * temp_term, 0.0, 1.0)))

    return {
        "risk": {"score": score, "level": level, "color": color},
        "alerts": alerts,
        "report_summary": report_summary,
        "weather_stats": {
            "humidity_mean": humidity_mean,
            "temperature_mean": temperature_mean,
            "humidity_last": humidity_last,
        },
        "weather_drivers": drivers,
        "forecast": {
            "future_humidity": future_h,
            "future_temperature": future_t,
            "stress_risk_future": stress,
        },
    }

