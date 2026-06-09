from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DATA_DIR
from src.risk_scoring import RiskScoringConfig, predict_latest_risks


def _read_zones_from_csv(input_csv: Path) -> dict:
    zones = {}
    with input_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zone_id = int(row["zone_id"])
            zones.setdefault(
                zone_id,
                {
                    "zone_row": int(row["zone_row"]),
                    "zone_col": int(row["zone_col"]),
                    # series elements: (t, ndvi, soil_moisture, air_temperature, humidity, leaf_wetness)
                    "series": [],
                },
            )["series"].append(
                (
                    int(float(row["t"])),
                    float(row["ndvi"]),
                    float(row["soil_moisture"]),
                    float(row["air_temperature"]),
                    float(row["humidity"]),
                    float(row["leaf_wetness"]),
                )
            )
    return zones


def predict_latest_from_csv(
    *,
    input_csv: Path,
    lookback_steps: int,
) -> list[dict]:
    zones = _read_zones_from_csv(input_csv)
    cfg = RiskScoringConfig(lookback_steps=lookback_steps)
    return predict_latest_risks(zones=zones, cfg=cfg)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=str, required=False, default=str(Path(DATA_DIR) / "synthetic_dataset.csv"))
    p.add_argument("--output-csv", type=str, default=str(Path(DATA_DIR) / "risk_predictions_latest.csv"))
    p.add_argument("--lookback-steps", type=int, default=12)
    args = p.parse_args()

    input_csv = Path(args.input_csv)
    if not input_csv.exists():
        raise SystemExit(f"Input CSV not found: {input_csv}")

    latest = predict_latest_from_csv(input_csv=input_csv, lookback_steps=args.lookback_steps)
    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "zone_id",
        "t",
        "zone_row",
        "zone_col",
        "risk_probability",
        "ndvi_last",
        "ndvi_change_lb",
        "moist_mean_lb",
        "wet_mean_lb",
        "rh_mean_lb",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(latest)
    print("Saved predictions to:", out_path)


if __name__ == "__main__":
    main()

