from __future__ import annotations

import csv
import io
from typing import Any, Dict, List


def _to_float(x: str) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def analyze_sensor_csv(csv_stream) -> Dict[str, Any]:
    """
    Parse sensor CSV and compute simple stats.

    Expected columns (header):
      - soil_moisture
      - temperature
      - humidity

    Returns series arrays for Chart.js and stats for fusion.
    """
    raw = csv_stream.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(raw))
    required = {"soil_moisture", "temperature", "humidity"}
    header = set(reader.fieldnames or [])
    missing = sorted(required - header)
    if missing:
        raise ValueError(f"Missing required CSV columns: {missing}")

    t_idx: List[int] = []
    soil: List[float] = []
    temp: List[float] = []
    hum: List[float] = []

    for i, row in enumerate(reader):
        t_idx.append(i)
        soil.append(_to_float(row.get("soil_moisture", "")))
        temp.append(_to_float(row.get("temperature", "")))
        hum.append(_to_float(row.get("humidity", "")))

    def _mean(xs: List[float]) -> float:
        xs2 = [x for x in xs if x == x]  # NaN check
        return float(sum(xs2) / max(1, len(xs2)))

    soil_mean = _mean(soil)
    temp_mean = _mean(temp)
    hum_mean = _mean(hum)
    hum_last = hum[-1] if hum else float("nan")

    return {
        "series": {
            "t": t_idx,
            "soil_moisture": soil,
            "temperature": temp,
            "humidity": hum,
        },
        "sensor_stats": {
            "soil_moisture_mean": soil_mean,
            "temperature_mean": temp_mean,
            "humidity_mean": hum_mean,
            "humidity_last": float(hum_last),
        },
    }

