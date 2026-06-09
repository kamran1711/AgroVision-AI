
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Load .env
env_path = Path(".env")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val

AGRO_BASE = "http://api.agromonitoring.com/agro/1.0"
API_KEY = os.environ.get("AGROMONITORING_API_KEY")

def test_create_polygon():
    url = f"{AGRO_BASE}/polygons?appid={API_KEY}"
    payload = {
        "name": f"test_poly_{int(time.time())}",
        "geo_json": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-122.4194, 37.7749],
                    [-122.4094, 37.7749],
                    [-122.4094, 37.7849],
                    [-122.4194, 37.7849],
                    [-122.4194, 37.7749]
                ]]
            }
        }
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status: {resp.status}")
            print(f"Response: {resp.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}")
        print(f"Headers: {e.headers}")
        print(f"Body: {e.read().decode()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if not API_KEY:
        print("No API KEY found in .env")
    else:
        test_create_polygon()
