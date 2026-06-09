## PlantSense AI - Precision Agriculture Monitoring System

Full-stack prototype (Flask backend + modern responsive dashboard UI).

### Features in this demo
1. Image upload -> NDVI-like heatmap (simulated) + Healthy/Diseased classification (dummy CNN prototype).
2. Sensor CSV upload -> Chart.js trends + sensor stats.
3. LSTM-like stress forecast (dummy forecast).
4. Data fusion rules -> Risk score/level + color-coded alerts + report summary.

### Run locally
1. Install dependencies:
```bash
python3 -m pip install -r requirements.txt
```

2. Start the full-stack app:
```bash
python3 -m backend.app
```

3. Open the dashboard:
`http://127.0.0.1:5000/`

### Notes for production upgrades
- The current image + forecast logic is dependency-light so the prototype runs reliably.
- Replace the dummy logic with real CNN/LSTM when you have OpenCV/NumPy/TensorFlow working in your environment.

