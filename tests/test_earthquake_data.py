import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from earthquake_data import FEEDS, FeedError, fetch_feed, filter_events, parse_geojson


def feature(event_id, magnitude, timestamp, coordinates, **properties):
    return {
        "type": "Feature",
        "id": event_id,
        "properties": {
            "mag": magnitude,
            "place": f"{event_id} test location",
            "time": timestamp,
            "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
            **properties,
        },
        "geometry": {"type": "Point", "coordinates": coordinates},
    }


class ParseGeoJsonTests(unittest.TestCase):
    def test_normalizes_and_sorts_valid_events(self):
        payload = {
            "type": "FeatureCollection",
            "metadata": {"title": "Past day", "generated": 1_700_000_100_000},
            "features": [
                feature("older", 2.3, 1_700_000_000_000, [-123.1, 45.2, 8.5]),
                feature(
                    "newer",
                    4.7,
                    1_700_000_050_000,
                    [142.3, 38.1, 32],
                    sig=420,
                    felt=12,
                    tsunami=1,
                ),
            ],
        }

        snapshot = parse_geojson(json.dumps(payload))

        self.assertEqual(snapshot.title, "Past day")
        self.assertEqual(snapshot.events[0].event_id, "newer")
        self.assertEqual(snapshot.events[0].occurred_at, datetime.fromtimestamp(
            1_700_000_050, tz=timezone.utc
        ))
        self.assertTrue(snapshot.events[0].tsunami)
        self.assertEqual(snapshot.events[0].felt_reports, 12)
        self.assertEqual(snapshot.events[1].longitude, -123.1)

    def test_skips_malformed_or_out_of_range_events(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                feature("good", 2.0, 1_700_000_000_000, [1, 2, 3]),
                feature("bad-lat", 2.0, 1_700_000_000_000, [1, 100, 3]),
                feature("bad-time", 2.0, 9_999_999_999_999_999, [1, 2, 3]),
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point"}},
            ],
        }

        snapshot = parse_geojson(json.dumps(payload))

        self.assertEqual([event.event_id for event in snapshot.events], ["good"])

    def test_rejects_unexpected_feed_document(self):
        with self.assertRaisesRegex(FeedError, "unexpected feed format"):
            parse_geojson('{"type":"Feature"}')

    def test_filters_unknown_and_below_threshold_magnitudes(self):
        snapshot = parse_geojson(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        feature("m1", 1.0, 1_700_000_000_000, [0, 0, 1]),
                        feature("m4", 4.0, 1_700_000_001_000, [0, 0, 1]),
                        feature("unknown", None, 1_700_000_002_000, [0, 0, 1]),
                    ],
                }
            )
        )

        self.assertEqual(
            [event.event_id for event in filter_events(snapshot.events, 2.5)],
            ["m4"],
        )


class FeedClientTests(unittest.TestCase):
    def test_feed_catalog_uses_only_usgs_summary_urls(self):
        self.assertEqual(len(FEEDS), 5)
        self.assertTrue(
            all(url.startswith("https://earthquake.usgs.gov/") for url in FEEDS.values())
        )

    def test_rejects_non_usgs_feed_before_network_access(self):
        with patch("earthquake_data.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(FeedError, "Only official USGS"):
                fetch_feed("https://example.com/all_day.geojson")

        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
