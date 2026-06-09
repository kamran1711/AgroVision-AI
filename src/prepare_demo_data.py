from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (
    DATA_DIR,
    SYNTHETIC_RANDOM_SEED,
    SYNTHETIC_TIME_STEPS,
    SYNTHETIC_ZONES_COLS,
    SYNTHETIC_ZONES_ROWS,
)
from src.synthetic_data import generate_synthetic_dataset


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output-csv", type=str, default=str(Path(DATA_DIR) / "synthetic_dataset.csv"))
    p.add_argument("--zone-rows", type=int, default=SYNTHETIC_ZONES_ROWS)
    p.add_argument("--zone-cols", type=int, default=SYNTHETIC_ZONES_COLS)
    p.add_argument("--time-steps", type=int, default=SYNTHETIC_TIME_STEPS)
    p.add_argument("--seed", type=int, default=SYNTHETIC_RANDOM_SEED)
    args = p.parse_args()

    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = generate_synthetic_dataset(
        zone_rows=args.zone_rows,
        zone_cols=args.zone_cols,
        time_steps=args.time_steps,
        random_seed=args.seed,
    )

    fieldnames = [
        "zone_id",
        "zone_row",
        "zone_col",
        "t",
        "ndvi",
        "soil_moisture",
        "air_temperature",
        "humidity",
        "leaf_wetness",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print("Saved synthetic dataset to:", out_path)


if __name__ == "__main__":
    main()

