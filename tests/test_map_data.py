import unittest

from map_data import LAND_DATA, load_land_polygons


class LandMapTests(unittest.TestCase):
    def test_bundled_high_resolution_map_contains_global_coastlines(self):
        polygons = load_land_polygons()

        self.assertTrue(LAND_DATA.is_file())
        self.assertGreater(len(polygons), 6_000)
        coordinates = [
            point
            for polygon in polygons
            for ring in polygon[:1]
            for point in ring
        ]
        longitudes = [longitude for longitude, _latitude in coordinates]
        latitudes = [latitude for _longitude, latitude in coordinates]
        self.assertLessEqual(min(longitudes), -179)
        self.assertGreaterEqual(max(longitudes), 179)
        self.assertLessEqual(min(latitudes), -80)
        self.assertGreaterEqual(max(latitudes), 80)


if __name__ == "__main__":
    unittest.main()
