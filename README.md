# Shaker Breaker

Shaker Breaker 1.0 is a live earthquake dashboard and KDE Plasma companion
widget for Bazzite and other Linux desktops. A dark, high-detail world map plots live
epicenters; select an event from the map or list for a five-stat detail popup
and an optional daytime satellite view from NASA.

## Features

- USGS feeds for the past hour, day, week, M4.5+ events, and significant events.
- Automatic feed checks every **30 seconds** in both the dashboard and widget.
- Natural Earth 1:10m land geometry with a Natural Earth projection, magnitude-
  colored epicenters, click-and-drag panning, and pointer-centered scroll zoom
  from 1× up to 32×.
- Magnitude 5.0+ epicenters pulse; USGS tsunami-flagged epicenters are white.
- Event count, strongest magnitude, average depth, and tsunami-flag count.
- A magnitude filter and a recent-event list.
- Select an event to see magnitude, depth, significance, felt reports, tsunami
  status, and its UTC origin time.
- Optional daylight MODIS Terra true-color satellite imagery from NASA GIBS,
  using the event date or the nearest available earlier daily observation.
- English, Simplified Chinese, Spanish, and Arabic interface options with the
  same left-to-right layout in every language.
- Event details clarify that the USGS tsunami flag is not an active local
  warning, with a link to NOAA's official tsunami warnings.
- A Buy Me a Coffee button in the dashboard opens the project's support page.
- English, Simplified Chinese, Spanish, and Arabic interface options. The
  Plasma widget has a separate language setting.
- A custom fractured-globe icon for the launcher and app window, installed in
  the Education application category.

USGS feed generation and network caching determine how quickly a new
earthquake appears. Shaker Breaker is **not** an earthquake early-warning service.
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
launcher and icon, and the Plasma applet. Launch **Shaker Breaker** from the
**Education** section of the application menu. Add the companion widget with
**Edit Mode → Add Widgets → Shaker Breaker**.
The expanded widget keeps its rounded card without the Plasma square backdrop.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Data sources and attribution

- Earthquake data: [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/).
- Coastlines: [Natural Earth 1:10m land data](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/), public domain. The bundled copy is from the
  [Natural Earth Vector GeoJSON repository](https://github.com/nvkelso/natural-earth-vector).
- Optional daytime imagery: [NASA Global Imagery Browse Services](https://nasa-gibs.github.io/gibs-api-docs/);
  satellite layer and observation date are shown in the event details.
- Tsunami warning status: [NOAA Tsunami Warning Centers](https://www.tsunami.gov/).
