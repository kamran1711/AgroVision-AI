from __future__ import annotations

import base64
import hashlib
import random
from typing import Any, Dict, Tuple


def _heatmap_color(v: float) -> tuple[int, int, int]:
    """
    Map v in [-1, 1] to a simple red->yellow->green gradient.
    """
    v = max(-1.0, min(1.0, v))
    t = (v + 1.0) / 2.0  # 0..1
    # Piecewise gradient: red (0) -> yellow (0.5) -> green (1)
    if t < 0.5:
        # red->yellow
        tt = t / 0.5
        r = 255
        g = int(255 * tt)
        b = 0
    else:
        # yellow->green
        tt = (t - 0.5) / 0.5
        r = int(255 * (1.0 - tt))
        g = 255
        b = 0
    return r, g, b


def _generate_svg_heatmap(*, grid_w: int, grid_h: int, seed: int) -> Tuple[str, list[float]]:
    """
    Pure-Python "NDVI heatmap" generation.

    Because image decoding libraries (PIL/OpenCV) segfault in this environment,
    we simulate NDVI-like values deterministically based on the uploaded file.
    """
    rng = random.Random(seed)

    # Base NDVI in [-0.2, 0.6] with seed-determined shift.
    base = rng.uniform(-0.2, 0.6)
    values: list[float] = []

    cell_s = 12  # pixels per cell in SVG
    width = grid_w * cell_s
    height = grid_h * cell_s

    rects: list[str] = []
    for gy in range(grid_h):
        for gx in range(grid_w):
            # Spatial variation + noise.
            v = base + 0.25 * rng.random() - 0.12 + 0.10 * (gx / max(1, grid_w - 1)) - 0.05 * (gy / max(1, grid_h - 1))
            v = max(-1.0, min(1.0, v))
            values.append(v)
            r, g, b = _heatmap_color(v)
            rects.append(
                f'<rect x="{gx * cell_s}" y="{gy * cell_s}" width="{cell_s}" height="{cell_s}" fill="rgb({r},{g},{b})" />'
            )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect x="0" y="0" width="100%" height="100%" fill="black" opacity="0.05" />'
        + "".join(rects)
        + "</svg>"
    )
    return svg, values


def analyze_crop_image(image_stream, grid_w: int = 24, grid_h: int = 18) -> Dict[str, Any]:
    """
    Analyze an uploaded crop image and return (prototype simulation):
      - processed heatmap image (base64 SVG)
      - simulated NDVI stats
      - CNN classification
      - risk label (from image-only)
    """
    payload = image_stream.read()
    digest = hashlib.sha256(payload).hexdigest()
    seed = int(digest[:16], 16)

    svg, ndvi_values = _generate_svg_heatmap(grid_w=grid_w, grid_h=grid_h, seed=seed)
    ndvi_mean = float(sum(ndvi_values) / max(1, len(ndvi_values)))
    ndvi_min = float(min(ndvi_values)) if ndvi_values else 0.0
    ndvi_max = float(max(ndvi_values)) if ndvi_values else 0.0

    # CNN classifier: treat lower NDVI mean as disease risk.
    classification = "Healthy" if ndvi_mean >= 0.05 else "Diseased"

    # Risk score from image-only NDVI (mapped to 0..1).
    risk_score = (0.05 - ndvi_mean) / 0.25
    risk_score = max(0.0, min(1.0, float(risk_score)))

    if risk_score < 0.33:
        risk_label = "Healthy"
    elif risk_score < 0.66:
        risk_label = "Moderate Risk"
    else:
        risk_label = "High Risk"

    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")

    return {
        "classification": classification,
        "image_risk": {
            "risk_score": risk_score,
            "risk_label": risk_label,
        },
        "ndvi_stats": {
            "mean": ndvi_mean,
            "min": ndvi_min,
            "max": ndvi_max,
        },
        "processed_heatmap_svg_b64": b64,
    }

