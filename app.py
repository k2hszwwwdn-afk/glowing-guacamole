"""Shaker Breaker: a live USGS earthquake dashboard for KDE and Linux desktops."""

from __future__ import annotations

import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PySide6.QtCore import QPointF, QSize, QSettings, QThread, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QImage,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from earthquake_data import FEEDS, FeedError, FeedSnapshot, Earthquake, fetch_feed, filter_events
from map_data import LandPolygon, load_land_polygons
from translations import LANGUAGE_NAMES, translate


REFRESH_INTERVAL_MS = 30_000
ACCENT = "#59e1d0"
MUTED = "#8195a5"
MIN_ZOOM = 1.0
MAX_ZOOM = 32.0


def natural_earth_projection(longitude: float, latitude: float) -> tuple[float, float]:
    """Project WGS84 longitude/latitude into the Natural Earth world-map projection."""
    lam = math.radians(longitude)
    phi = math.radians(max(-90.0, min(90.0, latitude)))
    phi2 = phi * phi
    phi4 = phi2 * phi2
    x = lam * (
        0.8707
        + phi2
        * (
            -0.131979
            + phi2 * (-0.013791 + phi4 * phi2 * (0.003971 - 0.001529 * phi2))
        )
    )
    y = phi * (
        1.007226
        + phi2 * (0.015085 + phi4 * (-0.044475 + 0.028874 * phi2 - 0.005916 * phi4))
    )
    return x, y


NATURAL_EARTH_MAX_X = math.pi * 0.8707
NATURAL_EARTH_MAX_Y = natural_earth_projection(0.0, 90.0)[1]


class FeedWorker(QThread):
    received = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            self.received.emit(fetch_feed(self.url))
        except FeedError as error:
            self.failed.emit(str(error))


class StatCard(QFrame):
    def __init__(self, label: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(98)
        self.accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 12)
        layout.setSpacing(3)

        self.label = QLabel(label)
        self.label.setObjectName("statLabel")
        self.value = QLabel("—")
        self.value.setObjectName("statValue")
        self.note = QLabel("")
        self.note.setObjectName("statNote")
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.note)

    def set_value(self, value: str, note: str) -> None:
        self.value.setText(value)
        self.note.setText(note)
        self.value.setStyleSheet(f"color: {self.accent};")

    def set_label(self, label: str) -> None:
        self.label.setText(label)


class PhotoWorker(QThread):
    photo_found = Signal(bytes, str, str, str, str)
    unavailable = Signal(str)

    def __init__(self, event: Earthquake, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.earthquake = event

    @staticmethod
    def snapshot_url(event: Earthquake, day: datetime) -> str:
        latitude = max(-89.5, min(89.5, event.latitude))
        longitude = max(-180.0, min(180.0, event.longitude))
        half_latitude = 1.0
        half_longitude = min(
            4.0,
            max(1.0, half_latitude / max(math.cos(math.radians(latitude)), 0.25)),
        )
        min_latitude = max(-90.0, latitude - half_latitude)
        max_latitude = min(90.0, latitude + half_latitude)
        min_longitude = longitude - half_longitude
        max_longitude = longitude + half_longitude
        if min_longitude < -180.0:
            max_longitude += -180.0 - min_longitude
            min_longitude = -180.0
        if max_longitude > 180.0:
            min_longitude -= max_longitude - 180.0
            max_longitude = 180.0
        query = urlencode(
            {
                "SERVICE": "WMS",
                "REQUEST": "GetMap",
                "VERSION": "1.3.0",
                "LAYERS": "MODIS_Terra_CorrectedReflectance_TrueColor",
                "STYLES": "",
                "CRS": "EPSG:4326",
                "BBOX": (
                    f"{min_latitude:.5f},{min_longitude:.5f},"
                    f"{max_latitude:.5f},{max_longitude:.5f}"
                ),
                "WIDTH": "512",
                "HEIGHT": "512",
                "FORMAT": "image/jpeg",
                "TIME": day.strftime("%Y-%m-%d"),
            }
        )
        return f"https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?{query}"

    @staticmethod
    def _request(url: str, max_bytes: int) -> tuple[bytes, str, str]:
        request = Request(
            url,
            headers={"User-Agent": "ShakerBreaker/1.0 (desktop earthquake monitor)"},
        )
        with urlopen(request, timeout=12) as response:
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
            data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("The archive image is too large.")
        return data, final_url, content_type

    def run(self) -> None:
        had_response = False
        event_day = self.earthquake.occurred_at.astimezone(timezone.utc).date()
        for days_back in range(3):
            day = datetime.combine(
                event_day - timedelta(days=days_back),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            try:
                image, image_url, content_type = self._request(
                    self.snapshot_url(self.earthquake, day), 4_000_000
                )
            except (OSError, TimeoutError, ValueError, TypeError):
                continue
            if (
                not image_url.startswith("https://gibs.earthdata.nasa.gov/")
                or content_type != "image/jpeg"
            ):
                continue
            had_response = True
            satellite_image = QImage()
            if len(image) < 3_000 or not satellite_image.loadFromData(image):
                continue
            self.photo_found.emit(
                image,
                f"MODIS Terra True Color · {day.date().isoformat()}",
                "NASA GIBS / MODIS Terra",
                "NASA Earthdata",
                "https://worldview.earthdata.nasa.gov/",
            )
            return
        self.unavailable.emit("not_found" if had_response else "failed")


class EventDetailsDialog(QDialog):
    def __init__(
        self,
        event: Earthquake,
        language: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.language = language
        self.source_url = ""
        self.setWindowTitle(translate(language, "event_details"))
        self.setMinimumWidth(660)
        self.setStyleSheet(
            "QDialog { background:#0a1118; color:#e5eef3; }"
            "QLabel { background:transparent; color:#e5eef3; }"
            "QFrame#metric { background:#111c26; border:1px solid #1c303b; border-radius:10px; }"
            "QPushButton { background:#14232e; border:1px solid #263d49; border-radius:8px; padding:9px 13px; }"
            "QPushButton#primary { background:#59e1d0; color:#081412; border:0; font-weight:700; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel(event.place)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:20px; font-weight:700;")
        occurred = QLabel(
            translate(
                language,
                "time_utc",
                time=event.occurred_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        occurred.setStyleSheet("color:#8ba0ad; font-size:11px;")
        layout.addWidget(title)
        layout.addWidget(occurred)

        metrics = QGridLayout()
        metrics.setSpacing(8)
        magnitude = (
            translate(language, "magnitude_label", magnitude=event.magnitude)
            if event.magnitude is not None
            else "—"
        )
        values = (
            ("magnitude", magnitude, "#ff9a57"),
            ("depth", f"{event.depth_km:.1f} km", "#a9b5ff"),
            ("significance", f"{event.significance:,}", "#59e1d0"),
            (
                "felt_reports",
                str(event.felt_reports) if event.felt_reports else translate(language, "no_reports"),
                "#ffd166",
            ),
            ("tsunami", translate(language, "yes" if event.tsunami else "no"), "#ff667a"),
        )
        for index, (key, value, color) in enumerate(values):
            tile = QFrame()
            tile.setObjectName("metric")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(12, 9, 12, 10)
            tile_layout.setSpacing(3)
            label = QLabel(translate(language, key))
            label.setStyleSheet("color:#8195a5; font-size:9px; font-weight:700;")
            stat_value = QLabel(value)
            stat_value.setStyleSheet(f"color:{color}; font-size:18px; font-weight:700;")
            tile_layout.addWidget(label)
            tile_layout.addWidget(stat_value)
            metrics.addWidget(tile, index // 3, index % 3)
        layout.addLayout(metrics)

        tsunami_detail = QLabel(
            translate(
                language,
                "tsunami_flag_detail" if event.tsunami else "tsunami_clear_detail",
            )
        )
        tsunami_detail.setWordWrap(True)
        tsunami_detail.setStyleSheet(
            "background:#111c26; border:1px solid #263d49; border-radius:8px;"
            "color:#dce8ed; padding:10px 12px;"
        )
        layout.addWidget(tsunami_detail)
        tsunami_link = QLabel(
            f'<a href="https://www.tsunami.gov/" style="color:#59e1d0;">'
            f'{translate(language, "official_tsunami_link")}</a>'
        )
        tsunami_link.setOpenExternalLinks(True)
        layout.addWidget(tsunami_link)

        photo_heading = QLabel(translate(language, "satellite_view"))
        photo_heading.setStyleSheet("color:#9cb0bc; font-size:10px; font-weight:700; letter-spacing:1px;")
        layout.addWidget(photo_heading)
        self.photo_label = QLabel(translate(language, "photo_loading"))
        self.photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_label.setWordWrap(True)
        self.photo_label.setFixedSize(610, 245)
        self.photo_label.setStyleSheet(
            "background:#101d26; border:1px solid #1c303b; border-radius:10px; color:#8195a5; padding:10px;"
        )
        layout.addWidget(self.photo_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.attribution = QLabel("")
        self.attribution.setWordWrap(True)
        self.attribution.setStyleSheet("color:#8195a5; font-size:9px;")
        layout.addWidget(self.attribution)
        disclaimer = QLabel(translate(language, "photo_disclaimer"))
        disclaimer.setStyleSheet("color:#617885; font-size:9px;")
        layout.addWidget(disclaimer)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_button = QPushButton(translate(language, "close"))
        close_button.clicked.connect(self.accept)
        open_button = QPushButton(translate(language, "open_usgs"))
        open_button.setObjectName("primary")
        open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(event.url)))
        actions.addWidget(close_button)
        actions.addWidget(open_button)
        layout.addLayout(actions)

    def show_photo(
        self,
        data: bytes,
        title: str,
        artist: str,
        license_name: str,
        source_url: str,
    ) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.show_photo_unavailable("failed")
            return
        self.photo_label.setPixmap(
            pixmap.scaled(
                self.photo_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.source_url = source_url
        self.attribution.setText(
            translate(
                self.language,
                "photo_attribution",
                title=title,
                artist=artist,
                license=license_name,
            )
        )
        self.attribution.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.attribution.setOpenExternalLinks(True)
        self.attribution.setToolTip(source_url)
        self.attribution.mousePressEvent = lambda _event: QDesktopServices.openUrl(QUrl(source_url))

    def show_photo_unavailable(self, reason: str) -> None:
        key = "photo_unavailable" if reason == "not_found" else "photo_failed"
        self.photo_label.setText(translate(self.language, key))


class EarthquakeMap(QWidget):
    eventSelected = Signal(object)
    zoomChanged = Signal(float)

    def __init__(self, language: str = "en") -> None:
        super().__init__()
        self.events: list[Earthquake] = []
        self.land_polygons: tuple[LandPolygon, ...] = ()
        self.language = language
        self._zoom_factor = MIN_ZOOM
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.selected_id = ""
        self._land_cache_paths: tuple[QPainterPath, ...] | None = None
        self._base_map_cache: QPixmap | None = None
        self._base_map_cache_key: tuple | None = None
        self._press_position: QPointF | None = None
        self._last_mouse_position: QPointF | None = None
        self._dragging = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self.update)
        self.setMinimumHeight(290)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    def set_language(self, language: str) -> None:
        self.language = language
        self._base_map_cache_key = None
        self.update()

    def set_land_polygons(self, polygons: tuple[LandPolygon, ...]) -> None:
        self.land_polygons = polygons
        self._land_cache_paths = None
        self._base_map_cache_key = None
        self.update()

    def set_events(self, events: list[Earthquake]) -> None:
        self.events = events
        if self.selected_id and not any(event.event_id == self.selected_id for event in events):
            self.selected_id = ""
        if any(event.magnitude is not None and event.magnitude >= 5.0 for event in events):
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
        self.update()

    def select_event(self, event: Earthquake) -> None:
        self.selected_id = event.event_id
        if self.zoom_factor > MIN_ZOOM:
            self.pan_x, self.pan_y = natural_earth_projection(
                event.longitude,
                event.latitude,
            )
            self._constrain_pan()
            self._base_map_cache_key = None
        self.update()

    def zoom_in(self) -> None:
        self._zoom_at(self._map_rect().center(), min(MAX_ZOOM, self.zoom_factor * 1.2))

    def zoom_out(self) -> None:
        self._zoom_at(self._map_rect().center(), max(MIN_ZOOM, self.zoom_factor / 1.2))

    def reset_zoom(self) -> None:
        self._zoom_factor = MIN_ZOOM
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._base_map_cache_key = None
        self.zoomChanged.emit(self._zoom_factor)
        self.update()

    def _map_rect(self):
        return self.rect().adjusted(1, 1, -1, -1).adjusted(20, 27, -20, -30)

    @staticmethod
    def _base_scale(rect) -> float:
        return min(
            rect.width() / (2 * NATURAL_EARTH_MAX_X),
            rect.height() / (2 * NATURAL_EARTH_MAX_Y),
        )

    def _scale(self, rect) -> float:
        return self._base_scale(rect) * self.zoom_factor

    def _constrain_pan(self, rect=None) -> None:
        rect = rect or self._map_rect()
        scale = self._scale(rect)
        half_width = rect.width() / (2 * scale)
        half_height = rect.height() / (2 * scale)
        self.pan_x = (
            0.0
            if half_width >= NATURAL_EARTH_MAX_X
            else max(
                -NATURAL_EARTH_MAX_X + half_width,
                min(NATURAL_EARTH_MAX_X - half_width, self.pan_x),
            )
        )
        self.pan_y = (
            0.0
            if half_height >= NATURAL_EARTH_MAX_Y
            else max(
                -NATURAL_EARTH_MAX_Y + half_height,
                min(NATURAL_EARTH_MAX_Y - half_height, self.pan_y),
            )
        )

    def _zoom_at(self, position: QPointF, zoom: float) -> None:
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if math.isclose(zoom, self.zoom_factor, rel_tol=1e-6):
            return
        rect = self._map_rect()
        old_scale = self._scale(rect)
        anchor_x = self.pan_x + (position.x() - rect.center().x()) / old_scale
        anchor_y = self.pan_y - (position.y() - rect.center().y()) / old_scale
        self._zoom_factor = zoom
        new_scale = self._scale(rect)
        self.pan_x = anchor_x - (position.x() - rect.center().x()) / new_scale
        self.pan_y = anchor_y + (position.y() - rect.center().y()) / new_scale
        self._constrain_pan(rect)
        self._base_map_cache_key = None
        self.zoomChanged.emit(self.zoom_factor)
        self.update()

    def _project(self, longitude: float, latitude: float, rect=None) -> QPointF:
        rect = rect or self._map_rect()
        x, y = natural_earth_projection(longitude, latitude)
        scale = self._scale(rect)
        x = rect.center().x() + (x - self.pan_x) * scale
        y = rect.center().y() - (y - self.pan_y) * scale
        return QPointF(x, y)

    def _land_paths(self) -> tuple[QPainterPath, ...]:
        if self._land_cache_paths is not None:
            return self._land_cache_paths
        paths = []
        for polygon in self.land_polygons:
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            for ring in polygon:
                if len(ring) < 4:
                    continue
                first = natural_earth_projection(ring[0][0], ring[0][1])
                path.moveTo(QPointF(*first))
                for longitude, latitude in ring[1:]:
                    path.lineTo(*natural_earth_projection(longitude, latitude))
                path.closeSubpath()
            paths.append(path)
        self._land_cache_paths = tuple(paths)
        return self._land_cache_paths

    def _base_cache_key(self) -> tuple:
        return (
            self.size(),
            self.devicePixelRatioF(),
            round(self.zoom_factor, 6),
            round(self.pan_x, 8),
            round(self.pan_y, 8),
            self.language,
        )

    def _render_base_map(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        size = QSize(round(self.width() * dpr), round(self.height() * dpr))
        pixmap = QPixmap(size)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(1, 1, -1, -1)
        panel = QPainterPath()
        panel.addRoundedRect(bounds, 14, 14)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#101f2a"))
        gradient.setColorAt(1, QColor("#0b151e"))
        painter.fillPath(panel, gradient)

        map_rect = self._map_rect()
        painter.save()
        painter.setClipPath(panel)
        painter.setClipRect(map_rect, Qt.ClipOperation.IntersectClip)
        scale = self._scale(map_rect)
        transform = QTransform(
            scale,
            0,
            0,
            -scale,
            map_rect.center().x() - self.pan_x * scale,
            map_rect.center().y() + self.pan_y * scale,
        )
        painter.setWorldTransform(transform)
        painter.setPen(QPen(QColor(102, 176, 184, 36), 0, Qt.PenStyle.DashLine))
        for latitude in (-75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75):
            start = natural_earth_projection(-180, latitude)
            end = natural_earth_projection(180, latitude)
            painter.drawLine(QPointF(*start), QPointF(*end))
        for longitude in range(-150, 180, 30):
            path = QPainterPath()
            for index, latitude in enumerate(range(-85, 86, 2)):
                point = natural_earth_projection(longitude, latitude)
                if index == 0:
                    path.moveTo(QPointF(*point))
                else:
                    path.lineTo(QPointF(*point))
            painter.drawPath(path)

        painter.setPen(QPen(QColor("#365b64"), 0))
        painter.setBrush(QColor(38, 77, 84, 190))
        for path in self._land_paths():
            painter.drawPath(path)
        painter.restore()

        painter.setPen(QPen(QColor("#78a1ac"), 1))
        painter.drawText(
            bounds.adjusted(15, 10, -15, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            translate(self.language, "epicenter_field"),
        )
        painter.setPen(QColor("#597987"))
        painter.drawText(
            bounds.adjusted(0, 10, -15, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            translate(self.language, "global_live"),
        )
        painter.end()
        return pixmap

    @staticmethod
    def event_color(magnitude: float | None) -> QColor:
        if magnitude is None:
            return QColor("#59e1d0")
        if magnitude >= 6:
            return QColor("#ff667a")
        if magnitude >= 4:
            return QColor("#ff9a57")
        if magnitude >= 2.5:
            return QColor("#ffd166")
        return QColor("#59e1d0")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cache_key = self._base_cache_key()
        if self._base_map_cache is None or self._base_map_cache_key != cache_key:
            self._base_map_cache = self._render_base_map()
            self._base_map_cache_key = cache_key
        painter.drawPixmap(0, 0, self._base_map_cache)

        bounds = self.rect().adjusted(1, 1, -1, -1)
        panel = QPainterPath()
        panel.addRoundedRect(bounds, 14, 14)
        map_rect = self._map_rect()
        painter.setClipPath(panel)
        painter.setClipRect(map_rect, Qt.ClipOperation.IntersectClip)
        pulse = (math.sin(time.monotonic() * math.tau / 1.6) + 1) / 2
        for index, quake in enumerate(self.events[:1500]):
            point = self._project(quake.longitude, quake.latitude, map_rect)
            if not map_rect.adjusted(-20, -20, 20, 20).contains(point.toPoint()):
                continue
            magnitude = quake.magnitude or 0
            radius = min(3.0 + magnitude * 1.15, 12.0)
            is_pulsing = quake.magnitude is not None and quake.magnitude >= 5.0
            pulse_scale = 1.0 + pulse * 0.35 if is_pulsing else 1.0
            color = QColor("#ffffff") if quake.tsunami else self.event_color(quake.magnitude)
            is_selected = quake.event_id == self.selected_id
            glow_radius = radius * (2.7 + pulse * 1.2 if is_pulsing else 2.7)
            glow = QRadialGradient(point, glow_radius)
            halo = QColor(color)
            halo.setAlpha(
                min(235, (120 if is_selected else 75) + int(pulse * 90))
                if is_pulsing
                else (110 if is_selected else 70)
            )
            glow.setColorAt(0, halo)
            glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(point, glow_radius, glow_radius)
            if quake.tsunami:
                painter.setPen(QPen(QColor("#0a1118"), 1.0))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            core_radius = radius * pulse_scale + (1.5 if is_selected else 0)
            painter.drawEllipse(point, core_radius, core_radius)
            if magnitude >= 5 and index < 10:
                painter.setPen(QColor("#f4fafb"))
                painter.drawText(
                    point + QPointF(core_radius + 4, -core_radius - 2),
                    f"M{magnitude:.1f}",
                )
        painter.end()

    def _nearest_event(self, position: QPointF) -> Earthquake | None:
        map_rect = self._map_rect()
        nearest: Earthquake | None = None
        nearest_distance = 18.0
        for quake in self.events:
            point = self._project(quake.longitude, quake.latitude, map_rect)
            distance = math.hypot(point.x() - position.x(), point.y() - position.y())
            if distance < nearest_distance:
                nearest = quake
                nearest_distance = distance
        return nearest

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._map_rect().contains(
            event.position().toPoint()
        ):
            self._press_position = event.position()
            self._last_mouse_position = event.position()
            self._dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._press_position is not None
            and self._last_mouse_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            position = event.position()
            if not self._dragging and math.hypot(
                position.x() - self._press_position.x(),
                position.y() - self._press_position.y(),
            ) >= 4:
                self._dragging = True
            if self._dragging:
                delta = position - self._last_mouse_position
                scale = self._scale(self._map_rect())
                self.pan_x -= delta.x() / scale
                self.pan_y += delta.y() / scale
                self._constrain_pan()
                self._base_map_cache_key = None
                self.update()
            self._last_mouse_position = position
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_position is not None:
            position = event.position()
            dragged = self._dragging
            self._press_position = None
            self._last_mouse_position = None
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if not dragged:
                nearest = self._nearest_event(position)
                if nearest is not None:
                    self.select_event(nearest)
                    self.eventSelected.emit(nearest)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        zoom = max(
            MIN_ZOOM,
            min(MAX_ZOOM, self.zoom_factor * 1.2 ** (delta / 120)),
        )
        self._zoom_at(event.position(), zoom)
        event.accept()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        app_icon = QIcon(str(Path(__file__).resolve().parent / "icons" / "earthwatch.svg"))
        self.setWindowIcon(app_icon)
        QApplication.instance().setWindowIcon(app_icon)
        self.settings = QSettings("Glowing Guacamole", "EarthWatch")
        saved_language = str(self.settings.value("language", "en"))
        self.language = saved_language if saved_language in LANGUAGE_NAMES else "en"
        QApplication.instance().setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.resize(1240, 830)
        self.setMinimumSize(980, 680)
        self.snapshot: FeedSnapshot | None = None
        self.worker: FeedWorker | None = None
        self.photo_workers: list[PhotoWorker] = []
        self.refresh_pending = False
        self._close_when_idle = False
        self.last_received = 0.0
        self.last_error = ""
        self.land_polygons = load_land_polygons()
        self._build_ui()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

        self.age_timer = QTimer(self)
        self.age_timer.setInterval(1000)
        self.age_timer.timeout.connect(self._update_status)
        self.age_timer.start()
        QTimer.singleShot(120, self.refresh)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget { color: #e5eef3; font-family: "Noto Sans"; }
            QWidget#centralWidget { background: #0a1118; }
            QLabel { background: transparent; }
            QFrame#statCard, QFrame#feedCard { background: #111c26; border: 1px solid #1c303b; border-radius: 12px; }
            QLabel#statLabel { color: #8096a5; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QLabel#statValue { color: #59e1d0; font-size: 26px; font-weight: 700; }
            QLabel#statNote { color: #8ba0ad; font-size: 11px; }
            QLabel#sectionTitle { color: #dce8ed; font-size: 14px; font-weight: 700; }
            QLabel#eyebrow { color: #59e1d0; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
            QComboBox, QPushButton { background: #14232e; border: 1px solid #263d49; border-radius: 8px; padding: 7px 10px; min-height: 22px; }
            QComboBox { padding-right: 30px; }
            QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 26px; border: 0; border-left: 1px solid #263d49; border-top-right-radius: 7px; border-bottom-right-radius: 7px; background: #14232e; }
            QComboBox QAbstractItemView { background: #14232e; color: #e5eef3; border: 1px solid #263d49; selection-background-color: #17313a; selection-color: #e5eef3; outline: 0; }
            QComboBox:hover, QPushButton:hover { border-color: #59e1d0; }
            QComboBox::drop-down:hover { background: #1b303a; }
            QPushButton#refreshButton { color: #081412; background: #59e1d0; border: 0; font-weight: 700; }
            QPushButton#refreshButton:hover { background: #82f2df; }
            QPushButton#coffeeButton { color: #1b1700; background: #ffdd00; border: 1px solid #e6c700; border-radius: 8px; padding: 5px 10px; min-height: 24px; font-size: 10px; font-weight: 800; }
            QPushButton#coffeeButton:hover { background: #ffe84d; border-color: #ffdd00; }
            QPushButton#coffeeButton:pressed { background: #edcf00; }
            QListWidget { background: transparent; border: 0; outline: 0; }
            QListWidget::item { border-bottom: 1px solid #20313a; padding: 7px 3px; }
            QListWidget::item:selected { background: #17313a; border-radius: 7px; }
            QScrollBar:vertical { width: 7px; background: transparent; }
            QScrollBar::handle:vertical { background: #355361; border-radius: 3px; min-height: 24px; }
            """
        )
        central = QWidget()
        central.setObjectName("centralWidget")
        main = QVBoxLayout(central)
        main.setContentsMargins(28, 22, 28, 20)
        main.setSpacing(15)

        header = QHBoxLayout()
        brand = QHBoxLayout()
        brand.setSpacing(12)
        mark = QLabel("⌁")
        mark.setFixedSize(44, 44)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(
            "background:#123039; border:1px solid #28616a; border-radius:13px;"
            "color:#59e1d0; font-size:31px; font-weight:700;"
        )
        brand_text = QVBoxLayout()
        self.brand_title = QLabel("Shaker Breaker")
        self.brand_title.setStyleSheet("font-size:21px; font-weight:800; letter-spacing:2px;")
        self.brand_subtitle = QLabel()
        self.brand_subtitle.setStyleSheet(f"color:{MUTED}; font-size:11px;")
        brand_text.addWidget(self.brand_title)
        brand_text.addWidget(self.brand_subtitle)
        brand.addWidget(mark)
        brand.addLayout(brand_text)
        header.addLayout(brand)
        header.addStretch(1)

        self.language_label = QLabel()
        self.language_picker = QComboBox()
        for language_code, language_name in LANGUAGE_NAMES.items():
            self.language_picker.addItem(language_name, language_code)
        self.language_picker.setCurrentIndex(
            max(0, self.language_picker.findData(self.language))
        )
        self.language_picker.currentIndexChanged.connect(self._language_changed)

        self.feed_picker = QComboBox()
        for url in FEEDS.values():
            self.feed_picker.addItem("", url)
        self.feed_picker.setCurrentIndex(1)
        self.feed_picker.currentIndexChanged.connect(self._feed_changed)
        self.magnitude_picker = QComboBox()
        self.magnitude_options = (
            ("filter_all", 0.0),
            ("filter_m1", 1.0),
            ("filter_m25", 2.5),
            ("filter_m4", 4.0),
            ("filter_m5", 5.0),
        )
        for _key, magnitude in self.magnitude_options:
            self.magnitude_picker.addItem("", magnitude)
        self.magnitude_picker.currentIndexChanged.connect(self._render_snapshot)
        header.addWidget(self.language_label)
        header.addWidget(self.language_picker)
        header.addWidget(self.feed_picker)
        header.addWidget(self.magnitude_picker)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        main.addLayout(header)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color:#718995; font-size:10px; font-weight:700; letter-spacing:1px;")
        main.addWidget(self.status_label)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.event_stat = StatCard("", ACCENT)
        self.strongest_stat = StatCard("", "#ff9a57")
        self.depth_stat = StatCard("", "#a9b5ff")
        self.tsunami_stat = StatCard("", "#ff667a")
        for card in (self.event_stat, self.strongest_stat, self.depth_stat, self.tsunami_stat):
            stats.addWidget(card, 1)
        main.addLayout(stats)

        content = QHBoxLayout()
        content.setSpacing(14)
        left = QVBoxLayout()
        map_heading = QHBoxLayout()
        self.map_heading_label = self._section_label("")
        map_heading.addWidget(self.map_heading_label)
        map_heading.addStretch(1)
        self.map_count = QLabel("")
        self.map_count.setStyleSheet("color:#8195a5; font-size:11px;")
        map_heading.addWidget(self.map_count)
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setToolTip("Zoom out")
        self.zoom_out_button.setFixedWidth(34)
        self.zoom_level_label = QLabel("1×")
        self.zoom_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_level_label.setFixedWidth(36)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setToolTip("Zoom in")
        self.zoom_in_button.setFixedWidth(34)
        self.zoom_reset_button = QPushButton("1:1")
        self.zoom_reset_button.setToolTip("Reset map zoom")
        map_heading.addWidget(self.zoom_out_button)
        map_heading.addWidget(self.zoom_level_label)
        map_heading.addWidget(self.zoom_in_button)
        map_heading.addWidget(self.zoom_reset_button)
        left.addLayout(map_heading)
        self.map = EarthquakeMap(self.language)
        self.map.set_land_polygons(self.land_polygons)
        self.map.eventSelected.connect(self._show_event_dialog)
        self.map.zoomChanged.connect(self._zoom_changed)
        self.zoom_in_button.clicked.connect(self.map.zoom_in)
        self.zoom_out_button.clicked.connect(self.map.zoom_out)
        self.zoom_reset_button.clicked.connect(self.map.reset_zoom)
        left.addWidget(self.map, 1)

        legend = QHBoxLayout()
        self.legend_heading = QLabel()
        legend.addWidget(self.legend_heading)
        legend.addStretch(1)
        self.legend_labels: list[QLabel] = []
        self.legend_colors = (
            "#59e1d0",
            "#ffd166",
            "#ff9a57",
            "#ff667a",
            "#ff9a57",
            "#ffffff",
        )
        self.legend_captions = (
            "<2.5",
            "2.5+",
            "4.0+",
            "6.0+",
            "pulse_legend",
            "tsunami_legend",
        )
        for color, caption in zip(
            self.legend_colors,
            self.legend_captions,
        ):
            text = self.tr(caption) if caption in ("pulse_legend", "tsunami_legend") else caption
            key = QLabel(f"●  {text}")
            key.setStyleSheet(f"color:{color}; font-size:10px;")
            self.legend_labels.append(key)
            legend.addWidget(key)
        left.addLayout(legend)

        right = QFrame()
        right.setObjectName("feedCard")
        right.setMinimumWidth(310)
        right.setMaximumWidth(375)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 15, 14, 12)
        right_layout.setSpacing(8)
        feed_head = QHBoxLayout()
        self.latest_heading = self._section_label("")
        feed_head.addWidget(self.latest_heading)
        feed_head.addStretch(1)
        self.event_count_label = QLabel("—")
        self.event_count_label.setStyleSheet("color:#59e1d0; font-size:11px; font-weight:700;")
        feed_head.addWidget(self.event_count_label)
        right_layout.addLayout(feed_head)
        self.event_explainer = QLabel()
        self.event_explainer.setStyleSheet("color:#8195a5; font-size:10px;")
        right_layout.addWidget(self.event_explainer)
        self.event_list = QListWidget()
        self.event_list.itemClicked.connect(self._open_selected_event)
        right_layout.addWidget(self.event_list, 1)
        content.addLayout(left, 1)
        content.addWidget(right)
        main.addLayout(content, 1)

        footer = QHBoxLayout()
        self.footer_source = QLabel()
        self.footer_source.setStyleSheet("color:#617885; font-size:9px; font-weight:700; letter-spacing:1px;")
        self.footer_source.setCursor(Qt.CursorShape.PointingHandCursor)
        self.footer_source.mousePressEvent = lambda _event: QDesktopServices.openUrl(
            QUrl("https://earthquake.usgs.gov/earthquakes/feed/")
        )
        self.footer_warning = QLabel()
        self.footer_warning.setStyleSheet("color:#617885; font-size:9px; font-weight:700; letter-spacing:1px;")
        self.coffee_button = QPushButton()
        self.coffee_button.setObjectName("coffeeButton")
        self.coffee_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.coffee_button.clicked.connect(self._open_coffee_link)
        footer.addWidget(self.footer_source)
        footer.addStretch(1)
        footer.addWidget(self.footer_warning)
        footer.addWidget(self.coffee_button)
        main.addLayout(footer)
        self.setCentralWidget(central)
        self._retranslate()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def tr(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)

    def _language_changed(self, index: int) -> None:
        language = self.language_picker.itemData(index)
        if not isinstance(language, str) or language not in LANGUAGE_NAMES:
            return
        self.language = language
        self.settings.setValue("language", language)
        self.map.set_language(language)
        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(self.tr("app_title"))
        self.brand_title.setText(self.tr("app_title"))
        self.brand_subtitle.setText(self.tr("tagline"))
        self.language_label.setText(self.tr("language"))
        for index, key in enumerate(
            ("feed_hour", "feed_day", "feed_week", "feed_m45", "feed_significant")
        ):
            self.feed_picker.setItemText(index, self.tr(key))
        for index, (key, _threshold) in enumerate(self.magnitude_options):
            self.magnitude_picker.setItemText(index, self.tr(key))
        self.refresh_button.setText(self.tr("refresh"))
        self.event_stat.set_label(self.tr("events_stat"))
        self.strongest_stat.set_label(self.tr("strongest_stat"))
        self.depth_stat.set_label(self.tr("depth_stat"))
        self.tsunami_stat.set_label(self.tr("tsunami_stat"))
        if self.snapshot is None:
            for card in (
                self.event_stat,
                self.strongest_stat,
                self.depth_stat,
                self.tsunami_stat,
            ):
                card.note.setText(self.tr("waiting_feed"))
        self.map_heading_label.setText(self.tr("global_activity"))
        self.legend_heading.setText(self.tr("magnitude_key"))
        for label, color, caption in zip(
            self.legend_labels,
            self.legend_colors,
            self.legend_captions,
        ):
            text = self.tr(caption) if caption in ("pulse_legend", "tsunami_legend") else caption
            label.setText(f"●  {text}")
            label.setStyleSheet(f"color:{color}; font-size:10px;")
        self.latest_heading.setText(self.tr("latest_events"))
        self.event_explainer.setText(self.tr("select_event"))
        self.footer_source.setText(self.tr("source"))
        self.footer_warning.setText(self.tr("not_warning"))
        self.coffee_button.setText(f"☕  {self.tr('buy_me_coffee')}")
        self.coffee_button.setToolTip(self.tr("buy_me_coffee"))
        self.zoom_in_button.setToolTip(self.tr("zoom_in"))
        self.zoom_out_button.setToolTip(self.tr("zoom_out"))
        self.zoom_reset_button.setToolTip(self.tr("zoom_reset"))
        self.map.setToolTip(self.tr("map_controls"))
        if self.snapshot is None:
            self.status_label.setText(self.tr("connecting"))
        elif self.last_error:
            self.status_label.setText(self.tr("feed_unavailable"))
        else:
            self._update_status()
        if self.snapshot is not None:
            self._render_snapshot()

    def _open_coffee_link(self) -> None:
        QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/neomatrix847"))

    def _zoom_changed(self, zoom: float) -> None:
        self.zoom_level_label.setText(f"{zoom:g}×")

    def _feed_changed(self, _index: int) -> None:
        self.refresh()

    def refresh(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.refresh_pending = True
            return
        url = self.feed_picker.currentData()
        self.status_label.setText(self.tr("requesting"))
        self.status_label.setStyleSheet("color:#ffd166; font-size:10px; font-weight:700; letter-spacing:1px;")
        self.refresh_button.setEnabled(False)
        self.worker = FeedWorker(url)
        self.worker.received.connect(self._feed_received)
        self.worker.failed.connect(self._feed_failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _feed_received(self, snapshot: FeedSnapshot) -> None:
        self.snapshot = snapshot
        self.last_received = time.monotonic()
        self.last_error = ""
        self._render_snapshot()
        self._update_status()

    def _feed_failed(self, message: str) -> None:
        self.last_error = message
        self.status_label.setText(self.tr("feed_unavailable"))
        self.status_label.setStyleSheet("color:#ff9a57; font-size:10px; font-weight:700; letter-spacing:1px;")
        self.map_count.setToolTip(message)

    def _worker_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self._close_if_idle()
        if self.refresh_pending:
            self.refresh_pending = False
            QTimer.singleShot(0, self.refresh)

    def _photo_worker_finished(self) -> None:
        worker = self.sender()
        if worker in self.photo_workers:
            self.photo_workers.remove(worker)
            worker.deleteLater()
        self._close_if_idle()

    def _workers_running(self) -> bool:
        feed_running = self.worker is not None and self.worker.isRunning()
        return feed_running or any(worker.isRunning() for worker in self.photo_workers)

    def _close_if_idle(self) -> None:
        if self._close_when_idle and not self._workers_running():
            self._close_when_idle = False
            self.close()

    def closeEvent(self, event) -> None:
        if self._workers_running():
            self._close_when_idle = True
            self.status_label.setText(self.tr("waiting_close"))
            event.ignore()
            return
        super().closeEvent(event)

    def _visible_events(self) -> list[Earthquake]:
        if self.snapshot is None:
            return []
        return filter_events(
            self.snapshot.events,
            float(self.magnitude_picker.currentData()),
        )

    def _render_snapshot(self, _index: int = -1) -> None:
        if self.snapshot is None:
            return
        events = self._visible_events()
        self.map.set_events(events)
        self.event_count_label.setText(self.tr("events_count", count=len(events)))
        self.map_count.setText(self.tr("plotted", count=len(events)))

        self.event_stat.set_value(f"{len(events):,}", self.tr("events_note"))
        strongest = max(
            (event for event in events if event.magnitude is not None),
            key=lambda event: event.magnitude or -math.inf,
            default=None,
        )
        self.strongest_stat.set_value(
            self.tr("magnitude_label", magnitude=strongest.magnitude)
            if strongest and strongest.magnitude is not None
            else "—",
            strongest.place if strongest else self.tr("no_events_band"),
        )
        if events:
            average_depth = sum(event.depth_km for event in events) / len(events)
            self.depth_stat.set_value(
                f"{average_depth:.1f} km",
                self.tr("depth_note"),
            )
        else:
            self.depth_stat.set_value("—", self.tr("no_events"))
        tsunami_count = sum(event.tsunami for event in events)
        self.tsunami_stat.set_value(str(tsunami_count), self.tr("tsunami_note"))
        self._populate_events(events[:45])

    def _populate_events(self, events: list[Earthquake]) -> None:
        self.event_list.clear()
        for event in events:
            magnitude = event.magnitude
            mag_label = (
                self.tr("magnitude_label", magnitude=magnitude)
                if magnitude is not None
                else "M —"
            )
            color = EarthquakeMap.event_color(magnitude).name()
            local_time = event.occurred_at.astimezone().strftime("%H:%M:%S")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, event.event_id)
            self.event_list.addItem(item)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 3, 5, 3)
            row_layout.setSpacing(9)
            magnitude_label = QLabel(mag_label)
            magnitude_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            magnitude_label.setFixedWidth(55)
            magnitude_label.setStyleSheet(
                f"background:{color}22; border:1px solid {color}66; border-radius:6px;"
                f"color:{color}; font-size:11px; font-weight:800; padding:5px 2px;"
            )
            text = QVBoxLayout()
            text.setSpacing(2)
            place = QLabel(event.place)
            place.setStyleSheet("font-size:11px; font-weight:600;")
            place.setWordWrap(True)
            details = QLabel()
            details.setText(
                self.tr(
                    "local_time",
                    time=local_time,
                    depth=event.depth_km,
                )
            )
            details.setStyleSheet("color:#8195a5; font-size:9px;")
            text.addWidget(place)
            text.addWidget(details)
            row_layout.addWidget(magnitude_label)
            row_layout.addLayout(text, 1)
            self.event_list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())

    def _open_selected_event(self, item: QListWidgetItem) -> None:
        event_id = item.data(Qt.ItemDataRole.UserRole)
        event = next(
            (
                event
                for event in self.snapshot.events
                if event.event_id == event_id
            ),
            None,
        ) if self.snapshot is not None else None
        if event is not None:
            self.map.select_event(event)
            self._show_event_dialog(event)

    def _show_event_dialog(self, event: Earthquake) -> None:
        dialog = EventDetailsDialog(event, self.language, self)
        worker = PhotoWorker(event, self)
        self.photo_workers.append(worker)
        worker.photo_found.connect(dialog.show_photo)
        worker.unavailable.connect(dialog.show_photo_unavailable)
        worker.finished.connect(self._photo_worker_finished)
        worker.start()
        dialog.exec()
        dialog.deleteLater()

    def _update_status(self) -> None:
        if self.last_error:
            return
        if self.snapshot is None:
            return
        age_seconds = max(0, int(time.monotonic() - self.last_received))
        generated = self.snapshot.generated_at
        generated_text = (
            generated.astimezone().strftime("%H:%M:%S %Z")
            if generated is not None
            else self.tr("feed_generated")
        )
        self.status_label.setText(
            self.tr("live_status", generated=generated_text, age=age_seconds)
        )
        self.status_label.setStyleSheet(
            "color:#59e1d0; font-size:10px; font-weight:700; letter-spacing:1px;"
        )


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Shaker Breaker")
    application.setApplicationVersion("1.0")
    application.setOrganizationName("Glowing Guacamole")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
