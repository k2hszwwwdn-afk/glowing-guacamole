"""Loader for the bundled Natural Earth 1:10m land polygons."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path


LAND_DATA = Path(__file__).resolve().parent / "data" / "ne_10m_land.geojson"
LandRing = tuple[tuple[float, float], ...]
LandPolygon = tuple[LandRing, ...]


@lru_cache(maxsize=1)
def load_land_polygons(path: str | Path = LAND_DATA) -> tuple[LandPolygon, ...]:
    """Load exterior and interior rings from Natural Earth GeoJSON."""
    data_path = Path(path)
    try:
        document = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load Natural Earth map data from {data_path}: {error}") from error

    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ValueError("Natural Earth map data is not a GeoJSON FeatureCollection.")

    polygons: list[LandPolygon] = []
    for feature in document.get("features", []):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            continue
        if geometry_type == "Polygon":
            source_polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            source_polygons = coordinates
        else:
            continue

        for source_polygon in source_polygons:
            if not isinstance(source_polygon, list):
                continue
            rings: list[LandRing] = []
            for source_ring in source_polygon:
                if not isinstance(source_ring, list) or len(source_ring) < 4:
                    continue
                ring: list[tuple[float, float]] = []
                for point in source_ring:
                    if not isinstance(point, list) or len(point) < 2:
                        continue
                    longitude, latitude = point[0], point[1]
                    if (
                        isinstance(longitude, bool)
                        or isinstance(latitude, bool)
                        or not isinstance(longitude, (int, float))
                        or not isinstance(latitude, (int, float))
                        or not math.isfinite(longitude)
                        or not math.isfinite(latitude)
                        or not -180 <= longitude <= 180
                        or not -90 <= latitude <= 90
                    ):
                        continue
                    ring.append((float(longitude), float(latitude)))
                if len(ring) >= 4:
                    rings.append(tuple(ring))
            if rings:
                polygons.append(tuple(rings))

    if not polygons:
        raise ValueError("Natural Earth map data contains no usable land polygons.")
    return tuple(polygons)
