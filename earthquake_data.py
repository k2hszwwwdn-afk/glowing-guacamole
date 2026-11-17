"""USGS earthquake summary feed client and validated data models."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


FEED_BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"
FEEDS = {
    "Past hour": f"{FEED_BASE_URL}/all_hour.geojson",
    "Past day": f"{FEED_BASE_URL}/all_day.geojson",
    "Past week": f"{FEED_BASE_URL}/all_week.geojson",
    "M4.5+ · past day": f"{FEED_BASE_URL}/4.5_day.geojson",
    "Significant · past month": f"{FEED_BASE_URL}/significant_month.geojson",
}
REQUEST_TIMEOUT_SECONDS = 15


class FeedError(RuntimeError):
    """Raised when the USGS feed cannot be fetched or validated."""


@dataclass(frozen=True)
class Earthquake:
    event_id: str
    magnitude: float | None
    place: str
    occurred_at: datetime
    longitude: float
    latitude: float
    depth_km: float
    significance: int
    felt_reports: int
    tsunami: bool
    url: str


@dataclass(frozen=True)
class FeedSnapshot:
    title: str
    generated_at: datetime | None
    events: tuple[Earthquake, ...]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def parse_geojson(payload: bytes | str) -> FeedSnapshot:
    """Validate a USGS GeoJSON summary and normalize valid earthquake records."""
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeedError("USGS returned invalid JSON.") from error

    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise FeedError("USGS returned an unexpected feed format.")
    features = document.get("features")
    if not isinstance(features, list):
        raise FeedError("USGS feed is missing its event list.")

    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    generated_ms = _number(metadata.get("generated"))
    try:
        generated_at = (
            datetime.fromtimestamp(generated_ms / 1000, tz=timezone.utc)
            if generated_ms is not None
            else None
        )
    except (OverflowError, OSError, ValueError):
        generated_at = None
    events: list[Earthquake] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue
        coordinates = geometry.get("coordinates")
        if (
            geometry.get("type") != "Point"
            or not isinstance(coordinates, list)
            or len(coordinates) < 3
        ):
            continue

        longitude, latitude, depth = (_number(value) for value in coordinates[:3])
        timestamp = _number(properties.get("time"))
        if (
            longitude is None
            or latitude is None
            or depth is None
            or timestamp is None
            or not -180 <= longitude <= 180
            or not -90 <= latitude <= 90
        ):
            continue

        magnitude = _number(properties.get("mag"))
        significance = _number(properties.get("sig"))
        felt_reports = _number(properties.get("felt"))
        url = properties.get("url")
        place = properties.get("place")
        event_id = feature.get("id")
        if not isinstance(url, str) or not url.startswith(
            "https://earthquake.usgs.gov/"
        ):
            continue
        if not isinstance(place, str) or not isinstance(event_id, str):
            continue

        try:
            occurred_at = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        events.append(
            Earthquake(
                event_id=event_id,
                magnitude=magnitude,
                place=place,
                occurred_at=occurred_at,
                longitude=longitude,
                latitude=latitude,
                depth_km=depth,
                significance=int(significance or 0),
                felt_reports=int(felt_reports or 0),
                tsunami=properties.get("tsunami") == 1,
                url=url,
            )
        )

    events.sort(key=lambda event: event.occurred_at, reverse=True)
    title = metadata.get("title")
    return FeedSnapshot(
        title=title if isinstance(title, str) else "USGS Earthquakes",
        generated_at=generated_at,
        events=tuple(events),
    )


def fetch_feed(url: str) -> FeedSnapshot:
    """Fetch one public USGS summary feed over HTTPS."""
    if url not in FEEDS.values():
        raise FeedError("Only official USGS earthquake summary feeds are supported.")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/geo+json, application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "EarthWatch/1.0 (desktop earthquake monitor)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return parse_geojson(response.read())
    except urllib.error.HTTPError as error:
        raise FeedError(f"USGS request failed with HTTP {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise FeedError(f"Could not reach the USGS earthquake feed: {error}") from error


def filter_events(
    events: tuple[Earthquake, ...] | list[Earthquake],
    minimum_magnitude: float = 0,
) -> list[Earthquake]:
    """Keep events with a known magnitude at or above the selected threshold."""
    return [
        event
        for event in events
        if event.magnitude is not None and event.magnitude >= minimum_magnitude
    ]
