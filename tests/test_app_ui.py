import os
import sys
import unittest
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app import EarthquakeMap, EventDetailsDialog
from earthquake_data import Earthquake


class AppUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(sys.argv)

    @staticmethod
    def sample_event():
        return Earthquake(
            "test-event",
            4.3,
            "Test location",
            datetime.now(timezone.utc),
            0.0,
            0.0,
            8.2,
            220,
            4,
            False,
            "https://earthquake.usgs.gov/earthquakes/eventpage/test-event",
        )

    def test_event_dialog_does_not_shadow_qobject_event_handler(self):
        dialog = EventDetailsDialog(self.sample_event(), "en")
        self.assertTrue(callable(dialog.event))
        self.assertEqual(dialog.windowTitle(), "Earthquake details")
        dialog.close()

    def test_map_paints_markers_with_fractional_projection_coordinates(self):
        earthquake_map = EarthquakeMap()
        earthquake_map.resize(600, 400)
        earthquake_map.set_events([self.sample_event()])
        image = QImage(earthquake_map.size(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        earthquake_map.render(painter, QPoint())
        painter.end()

        map_rect = earthquake_map.rect().adjusted(1, 1, -1, -1).adjusted(20, 27, -20, -30)
        point = earthquake_map._project(0.0, 0.0, map_rect).toPoint()
        self.assertEqual(image.pixelColor(point), QColor("#ff9a57"))


if __name__ == "__main__":
    unittest.main()
