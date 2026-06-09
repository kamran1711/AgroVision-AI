from __future__ import annotations

import argparse
from pathlib import Path

from config import MODELS_DIR

def main() -> None:
    # Keep this file so the project structure still makes sense,
    # but the easy MVP is rule-based to avoid heavy native dependencies.
    p = argparse.ArgumentParser()
    p.add_argument("--output-model", type=str, default=str(Path(MODELS_DIR) / "risk_model.joblib"))
    args = p.parse_args()

    print(
        "ML training is not included in this easy MVP.\n"
        "Use `src/predict_risk.py` for rule-based risk scoring, which runs without NumPy/Pandas."
    )


if __name__ == "__main__":
    main()

