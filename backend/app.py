from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
import os

# Load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass  # dotenv not installed — use system env vars or export manually

from flask import Flask, jsonify, request, send_from_directory
try:
    # Prefer using Flask-Cors if available in the environment (better for deployed CORS handling)
    from flask_cors import CORS
except Exception:
    CORS = None

from backend.ai.agromonitoring import analyze_field as analyze_field_agro
from backend.ai.fusion import fuse_risk
from backend.ai.image_processing import analyze_crop_image
from backend.ai.prediction import predict_stress_trend
from backend.ai.sensors import analyze_sensor_csv
from backend.ai.weather import analyze_weather_area


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

    # Enable CORS for API endpoints. If Flask-Cors is installed, use it; otherwise keep the manual header fallback.
    if CORS:
        CORS(app, resources={r"/api/*": {"origins": "*"}})
    else:
        @app.after_request
        def allow_cors(response: Any) -> Any:
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response

    @app.get("/")
    def index() -> Any:
        return send_from_directory(app.static_folder, "index.html")

    @app.post("/api/analyze-image")
    def api_analyze_image() -> Any:
        if "image" not in request.files:
            return jsonify({"error": "Missing form field: image"}), 400

        file = request.files["image"]
        if not file.filename:
            return jsonify({"error": "Empty image filename"}), 400

        result = analyze_crop_image(file.stream)
        return jsonify(result)

    @app.post("/api/analyze-sensors")
    def api_analyze_sensors() -> Any:
        # Accept a CSV upload. Expected columns:
        #   soil_moisture, temperature, humidity
        if "csv" not in request.files:
            return jsonify({"error": "Missing form field: csv"}), 400

        file = request.files["csv"]
        if not file.filename:
            return jsonify({"error": "Empty csv filename"}), 400

        analysis = analyze_sensor_csv(file.stream)
        return jsonify(analysis)


    @app.post("/api/weather-risk")
    def api_weather_risk() -> Any:
        payload = request.get_json(force=True) or {}
        lat = payload.get("lat")
        lon = payload.get("lon")
        horizon = int(payload.get("horizon", 12))

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except Exception:
            return jsonify({"error": "Payload must include numeric `lat` and `lon`."}), 400

        result = analyze_weather_area(lat=lat_f, lon=lon_f, horizon=horizon)
        return jsonify(result)

    @app.post("/api/analyze-field")
    def api_analyze_field() -> Any:
        """
        Primary analysis endpoint using AgroMonitoring API.
        """
        payload = request.get_json(force=True) or {}
        lat = payload.get("lat")
        lon = payload.get("lon")
        horizon = int(payload.get("horizon", 12))
        polygon_coords = payload.get("polygon_coords")

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except Exception:
            return jsonify({"error": "Payload must include numeric `lat` and `lon`."}), 400

        agro_key = os.environ.get("AGROMONITORING_API_KEY", "").strip()

        if agro_key:
            try:
                result = analyze_field_agro(
                    lat=lat_f,
                    lon=lon_f,
                    polygon_coords=polygon_coords if isinstance(polygon_coords, list) else None,
                    horizon=horizon,
                )
                return jsonify(result)
            except Exception as exc:
                fallback_result = analyze_weather_area(lat=lat_f, lon=lon_f, horizon=horizon)
                fallback_result["source"] = "weather_fallback"
                fallback_result["agro_error"] = str(exc)
                return jsonify(fallback_result)
        else:
            result = analyze_weather_area(lat=lat_f, lon=lon_f, horizon=horizon)
            result["source"] = "weather_only"
            result["ndvi_stats"] = {}
            result["soil_data"] = {}
            return jsonify(result)

    @app.get("/api/sample-sensors")
    def api_sample_sensors() -> Any:
        """Returns the content of data/sample_sensors.csv for demo purposes."""
        sample_path = ROOT / "data" / "sample_sensors.csv"
        if not sample_path.exists():
            return jsonify({"error": "Sample file not found"}), 404
        
        with open(sample_path, "r") as f:
            analysis = analyze_sensor_csv(f)
        return jsonify(analysis)

    @app.post("/api/fuse")
    def api_fuse() -> Any:
        """
        Fused analysis: Satellite (agro) + Weather + Ground Sensors (CSV).
        Requires 'field_analysis' and 'sensor_analysis' in payload.
        """
        payload = request.get_json(force=True) or {}
        field_res = payload.get("field_analysis", {})
        sensor_res = payload.get("sensor_analysis", {})

        if not field_res:
            return jsonify({"error": "No field analysis found to fuse. Run 'Check Area Risk' first."}), 400

        result = fuse_risk(field_result=field_res, sensor_result=sensor_res)
        return jsonify(result)

    @app.post("/api/predict-stress")
    def api_predict_stress() -> Any:
        """
        24-hour predictive trend based on current field health and weather forecast.
        """
        payload = request.get_json(force=True) or {}
        field_res = payload.get("field_analysis", {})
        horizon = int(payload.get("horizon", 24))

        if not field_res:
             return jsonify({"error": "No field analysis found for prediction."}), 400

        forecast_data = field_res.get("weather_stats", {}) # Current agro-weather
        # In multi-source mode, we use the forecast list from AgroMonitoring
        weather_forecast = {
            "future_humidity": field_res.get("forecast", {}).get("future_humidity", []),
            "future_temperature": field_res.get("forecast", {}).get("future_temperature", []),
        }
        
        soil_current = field_res.get("soil_data", {}).get("soil_moisture", 0.30)
        
        result = predict_stress_trend(
            weather_forecast=weather_forecast,
            soil_current=soil_current,
            horizon=horizon
        )
        return jsonify(result)

    return app


app = create_app()


host = os.environ.get("HOST", "0.0.0.0")
port = int(os.environ.get("PORT", 10000))

app.run(
    host=host,
    port=port,
    debug=False,
    use_reloader=False
)