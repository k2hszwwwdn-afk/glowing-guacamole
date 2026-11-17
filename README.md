# EarthWatch

EarthWatch is a live earthquake dashboard and KDE Plasma companion widget for
Bazzite and other Linux desktops. A dark, high-detail world map plots live
epicenters; select an event from the map or list for a five-stat detail popup
and an optional nearby archive photo.

## Features

- USGS feeds for the past hour, day, week, M4.5+ events, and significant events.
- Automatic feed checks every **30 seconds** in both the dashboard and widget.
- Natural Earth 1:10m land geometry, magnitude-colored epicenters, and map zoom
  levels of 1×, 1.5×, 2×, and 3×. Select an earthquake before zooming to focus
  the map on it.
- Event count, strongest magnitude, average depth, and tsunami-flag count.
- A magnitude filter and a recent-event list.
- Select an event to see magnitude, depth, significance, felt reports, tsunami
  status, and its UTC origin time.
- An optional geotagged Wikimedia Commons image search within 10 km of the
  event. Images display their title, contributor, and license; they are
  archival and may not show current conditions.
- English, Simplified Chinese, Spanish, and Arabic interface options. The
  Plasma widget has a separate language setting.
- A custom launcher icon showing a fractured globe, installed in the Education
  application category.

USGS feed generation and network caching determine how quickly a new
earthquake appears. EarthWatch is **not** an earthquake early-warning service.
Event place names come directly from USGS and may remain in English.

## Run from the repository

Python 3.10+ and PySide6 are required.

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

## Install on Bazzite / KDE Plasma

```bash
./install.sh
```

The user-level installer sets up the local Python environment, the desktop
launcher and icon, and the Plasma applet. Launch **EarthWatch** from the
**Education** section of the application menu. Add the companion widget with
**Edit Mode → Add Widgets → EarthWatch**.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Data sources and attribution

- Earthquake data: [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/).
- Coastlines: [Natural Earth 1:10m land data](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/), public domain. The bundled copy is from the
  [Natural Earth Vector GeoJSON repository](https://github.com/nvkelso/natural-earth-vector).
- Optional area images: [Wikimedia Commons](https://commons.wikimedia.org/);
  image attribution and license are shown in the event details.
