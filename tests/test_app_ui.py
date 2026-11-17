import os
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QImage,
    QMouseEvent,
    QPainter,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication

from app import (
    MAX_ZOOM,
    EarthquakeMap,
    EventDetailsDialog,
    MainWindow,
    PhotoWorker,
    natural_earth_projection,
)
from earthquake_data import Earthquake
from translations import translate


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

    def test_main_window_uses_the_existing_application_icon(self):
        with patch.object(QTimer, "singleShot"):
            window = MainWindow()
        try:
            self.assertFalse(window.windowIcon().isNull())
            self.assertFalse(window.windowIcon().pixmap(64, 64).isNull())
            self.assertFalse(QApplication.instance().windowIcon().isNull())
        finally:
            window.close()

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

    def test_map_zoom_is_anchored_to_pointer_and_has_a_high_limit(self):
        earthquake_map = EarthquakeMap()
        earthquake_map.resize(800, 500)
        map_rect = earthquake_map._map_rect()
        event = self.sample_event()
        anchor = earthquake_map._project(event.longitude, event.latitude, map_rect)

        earthquake_map._zoom_at(anchor, 8.0)
        zoomed_anchor = earthquake_map._project(event.longitude, event.latitude, map_rect)
        self.assertAlmostEqual(zoomed_anchor.x(), anchor.x(), places=5)
        self.assertAlmostEqual(zoomed_anchor.y(), anchor.y(), places=5)

        earthquake_map._zoom_at(anchor, MAX_ZOOM * 10)
        self.assertEqual(earthquake_map.zoom_factor, MAX_ZOOM)

    def test_natural_earth_projection_keeps_world_edges_symmetric(self):
        left = natural_earth_projection(-180.0, 0.0)
        right = natural_earth_projection(180.0, 0.0)
        north = natural_earth_projection(45.0, 60.0)
        south = natural_earth_projection(45.0, -60.0)

        self.assertAlmostEqual(left[0], -right[0])
        self.assertEqual(left[1], 0.0)
        self.assertAlmostEqual(north[0], south[0])
        self.assertAlmostEqual(north[1], -south[1])

    def test_mouse_wheel_zoom_uses_pointer_location(self):
        earthquake_map = EarthquakeMap()
        earthquake_map.resize(800, 500)
        map_rect = earthquake_map._map_rect()
        position = QPointF(
            map_rect.center().x() + map_rect.width() * 0.08,
            map_rect.center().y() - map_rect.height() * 0.06,
        )
        old_scale = earthquake_map._scale(map_rect)
        anchor = (
            earthquake_map.pan_x + (position.x() - map_rect.center().x()) / old_scale,
            earthquake_map.pan_y - (position.y() - map_rect.center().y()) / old_scale,
        )
        wheel = QWheelEvent(
            position,
            position,
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        earthquake_map.wheelEvent(wheel)
        new_scale = earthquake_map._scale(map_rect)
        zoomed_anchor = (
            earthquake_map.pan_x + (position.x() - map_rect.center().x()) / new_scale,
            earthquake_map.pan_y - (position.y() - map_rect.center().y()) / new_scale,
        )
        self.assertAlmostEqual(earthquake_map.zoom_factor, 1.2)
        self.assertAlmostEqual(zoomed_anchor[0], anchor[0], places=5)
        self.assertAlmostEqual(zoomed_anchor[1], anchor[1], places=5)

    def test_map_drag_pans_and_tsunami_markers_are_white_and_animated(self):
        earthquake_map = EarthquakeMap()
        earthquake_map.resize(800, 500)
        earthquake_map._zoom_at(earthquake_map._map_rect().center(), 4.0)
        start = earthquake_map._map_rect().center()
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            start,
            start,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move_to = QPointF(start) + QPointF(24, 16)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            move_to,
            move_to,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            move_to,
            move_to,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        earthquake_map.mousePressEvent(press)
        earthquake_map.mouseMoveEvent(move)
        earthquake_map.mouseReleaseEvent(release)
        self.assertNotEqual((earthquake_map.pan_x, earthquake_map.pan_y), (0.0, 0.0))

        tsunami_event = replace(self.sample_event(), magnitude=5.0, tsunami=True)
        earthquake_map.set_events([tsunami_event])
        self.assertTrue(earthquake_map._pulse_timer.isActive())
        image = QImage(earthquake_map.size(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        earthquake_map.render(painter, QPoint())
        painter.end()
        point = earthquake_map._project(
            tsunami_event.longitude,
            tsunami_event.latitude,
        ).toPoint()
        self.assertEqual(image.pixelColor(point), QColor("#ffffff"))

    def test_language_switching_keeps_the_layout_left_to_right(self):
        settings = QSettings("Glowing Guacamole", "EarthWatch")
        previous_language = settings.value("language")
        with patch.object(QTimer, "singleShot"):
            window = MainWindow()
        try:
            for language in ("en", "zh", "es", "ar"):
                window.language_picker.setCurrentIndex(
                    window.language_picker.findData(language)
                )
                self.assertEqual(
                    window.layoutDirection(),
                    Qt.LayoutDirection.LeftToRight,
                )
                self.assertEqual(window.brand_title.text(), "Shaker Breaker")
        finally:
            if previous_language is None:
                settings.remove("language")
            else:
                settings.setValue("language", previous_language)
            window.close()

    def test_satellite_image_uses_nasa_daylight_layer_and_event_date(self):
        event = self.sample_event()
        day = datetime(2025, 1, 2, tzinfo=timezone.utc)
        request = urlsplit(PhotoWorker.snapshot_url(event, day))
        query = parse_qs(request.query)

        self.assertEqual(request.scheme, "https")
        self.assertEqual(request.netloc, "gibs.earthdata.nasa.gov")
        self.assertEqual(query["LAYERS"], ["MODIS_Terra_CorrectedReflectance_TrueColor"])
        self.assertEqual(query["TIME"], ["2025-01-02"])
        self.assertEqual(query["CRS"], ["EPSG:4326"])

    def test_coffee_button_opens_the_requested_support_page(self):
        with patch.object(QTimer, "singleShot"):
            window = MainWindow()
        try:
            with patch.object(
                QDesktopServices,
                "openUrl",
                return_value=True,
            ) as open_url:
                window.coffee_button.click()
            open_url.assert_called_once()
            self.assertEqual(
                open_url.call_args.args[0].toString(),
                "https://buymeacoffee.com/neomatrix847",
            )
        finally:
            window.close()

    def test_brand_and_tsunami_copy_are_translated_for_every_language(self):
        for language in ("en", "zh", "es", "ar"):
            with self.subTest(language=language):
                self.assertEqual(translate(language, "app_title"), "Shaker Breaker")
                self.assertTrue(translate(language, "tsunami_flag_detail"))
                self.assertTrue(translate(language, "official_tsunami_link"))


if __name__ == "__main__":
    unittest.main()
