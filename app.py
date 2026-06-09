from __future__ import annotations

import csv
from pathlib import Path

import streamlit as st

from config import DATA_DIR, SYNTHETIC_ZONES_COLS, SYNTHETIC_ZONES_ROWS
from src.predict_risk import predict_latest_from_csv
from src.synthetic_data import generate_synthetic_dataset


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / DATA_DIR / "synthetic_dataset.csv"


def _ensure_dirs() -> None:
    (ROOT / DATA_DIR).mkdir(parents=True, exist_ok=True)


def _risk_to_color_style(risk: float) -> str:
    # risk in [0, 1], 0=green, 1=red
    risk = max(0.0, min(1.0, float(risk)))
    hue = int(120.0 * (1.0 - risk))  # 120 green -> 0 red
    return f"background-color: hsl({hue}, 80%, 45%); color: white;"


def _render_zone_heatmap(latest: list[dict]) -> None:
    # latest must contain zone_row/zone_col and risk_probability for each zone.
    grid = [[None for _ in range(SYNTHETIC_ZONES_COLS)] for _ in range(SYNTHETIC_ZONES_ROWS)]
    for row in latest:
        grid[int(row["zone_row"])][int(row["zone_col"])] = float(row["risk_probability"])

    html = [
        '<div style="overflow-x:auto;">',
        '<table style="border-collapse: collapse; margin-top: 8px;">',
    ]
    for r in range(SYNTHETIC_ZONES_ROWS):
        html.append("<tr>")
        for c in range(SYNTHETIC_ZONES_COLS):
            v = grid[r][c]
            if v is None:
                cell = '<td style="border:1px solid #444; width:44px; height:30px; text-align:center; font-size:11px;">--</td>'
            else:
                pct = int(round(v * 100))
                style = _risk_to_color_style(v)
                cell = (
                    '<td style="border:1px solid #444; width:44px; height:30px; text-align:center; '
                    f"font-size:11px; {style}"
                    f'">{pct}%</td>'
                )
            html.append(cell)
        html.append("</tr>")
    html.append("</table></div>")

    st.markdown("\n".join(html), unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="Plant Disease Risk (MVP)", layout="wide")
    st.title("Plant Disease & Stress Risk (Easy MVP)")
    st.caption("This demo uses synthetic time-series data + sensor context, then scores risk per zone. It avoids heavy numeric dependencies so it runs easily here.")

    _ensure_dirs()


    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Step 1: Data")
        if st.button("1) Generate demo data", use_container_width=True):
            rows = generate_synthetic_dataset(
                zone_rows=SYNTHETIC_ZONES_ROWS,
                zone_cols=SYNTHETIC_ZONES_COLS,
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
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            with DATA_PATH.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            st.success(f"Saved: {DATA_PATH}")

        st.divider()
        st.subheader("Step 2: Predict latest risk")

        lookback_steps = st.slider("Lookback steps", 6, 24, 12, 1)
        risk_threshold = st.slider("Highlight risk above", 0.0, 1.0, 0.65, 0.01)

        if st.button("2) Predict latest risk", use_container_width=True):
            if not DATA_PATH.exists():
                st.error("Missing demo data. Click 'Generate demo data' first.")
                st.stop()

            latest = predict_latest_from_csv(input_csv=DATA_PATH, lookback_steps=lookback_steps)

            # Filter and sort for quick inspection.
            high = [r for r in latest if r["risk_probability"] >= risk_threshold]
            high.sort(key=lambda r: r["risk_probability"], reverse=True)

            st.write(f"High-risk zones (>= {risk_threshold:.2f}): {len(high)}")
            st.write("Top 10:")
            st.write(high[:10])

            st.session_state["latest_risk"] = latest

    with col2:
        latest = st.session_state.get("latest_risk")
        if latest:
            st.subheader("Risk zones map (latest)")
            _render_zone_heatmap(latest)
        else:
            st.info("Generate data + predict to see the heatmap.")


if __name__ == "__main__":
    main()

